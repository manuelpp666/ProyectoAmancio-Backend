from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.database import get_db
from . import models, schemas
from app.core.util.password import get_password_hash
from app.core.util.password import verify_password

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
def login(credentials: schemas.UsuarioLogin, db: Session = Depends(get_db)):
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

    # 5. Retornar los datos que el frontend necesita para el UseContext(aqui se usara JWT)
    return {
        "id_usuario": user.id_usuario,
        "username": user.username,
        "rol": user.rol,
        "status": "success"
    }