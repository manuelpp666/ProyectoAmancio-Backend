from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session
from app.db.database import get_db
from . import models, schemas
from app.core.util.jwt import create_access_token
from app.core.util.password import get_password_hash
from app.core.util.password import verify_password
from app.modules.personal.models import Administrador

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])

@router.post("/", response_model=schemas.UsuarioResponse)
def crear_usuario(usuario: schemas.UsuarioCreate, db: Session = Depends(get_db)):
    db_user = models.Usuario(
        username=usuario.username,
        password_hash=get_password_hash(usuario.password), # Hashear password
        rol=usuario.rol,
        activo=usuario.activo
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@router.post("/login", response_model=schemas.LoginResponse)
def login(credentials: schemas.UsuarioLogin, response: Response, db: Session = Depends(get_db)):
    # 1. Buscar al usuario por nombre de usuario
    user = db.query(models.Usuario).filter(models.Usuario.username == credentials.username).first()
    
    # 2. Validar existencia
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Credenciales inválidas"
        )

    # 3. Validar contraseña usando tu función de bcrypt
    if not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Credenciales inválidas"
        )
    
    # 4. Validar si el usuario está activo
    if not user.activo:
        raise HTTPException(status_code=403, detail="Cuenta desactivada")
    
    # --- NUEVA LÓGICA PARA PERMISOS ---
    permisos_data = None
    if user.rol == "ADMIN":
        # Buscamos el registro en la tabla de administradores vinculado a este usuario
        admin_profile = db.query(Administrador).filter(Administrador.id_usuario == user.id_usuario).first()
        if admin_profile:
            permisos_data = admin_profile.permisos
    # ----------------------------------

    access_token = create_access_token(
        data={
            "sub": user.username, 
            "id": user.id_usuario, 
            "rol": user.rol
        }
    )

    # CONFIGURAR LA COOKIE HTTPONLY
    response.set_cookie(
        key="authToken",
        value=access_token,
        httponly=True,   # <--- Lo más importante: JS no podrá leerla
        secure=False,    # Ponlo en True cuando uses HTTPS (Producción)
        samesite="lax",
        max_age=604800,  # 7 días en segundos
        path="/",
    )
    # 6. Retornar los datos que el frontend necesita para el UseContext(aqui se usara JWT)
    return {
        "id_usuario": user.id_usuario,
        "username": user.username,
        "rol": user.rol,
        "access_token": access_token,
        "token_type": "bearer",
        "status": "success",
        "permisos": permisos_data
    }