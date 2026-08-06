from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session
from app.db.database import get_db
from . import models, schemas
from app.core.util.jwt import create_access_token
from app.core.util.password import get_password_hash
from app.core.util.password import verify_password
from app.core.util.security import require_roles
from app.modules.personal.models import Administrador
from app.modules.pagina_principal.models import PaginaConfiguracion
from app.core.util.correo_usuario import tiene_correo
from app.core.util.permisos import normalizar as normalizar_permisos

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])

# Claves de pagina_configuracion que encienden o apagan lo que se exige en el
# primer ingreso. Ambas se administran desde el panel de control > Seguridad.
CLAVE_FORZAR_CAMBIO = "forzar_cambio_password_inicial"
CLAVE_EXIGIR_CORREO = "exigir_correo_primer_ingreso"


def _interruptor(db: Session, clave: str) -> bool:
    """Lee un interruptor global. Si no está configurado, se asume activado."""
    fila = db.query(PaginaConfiguracion).filter(
        PaginaConfiguracion.clave == clave
    ).first()
    if not fila:
        return True
    return str(fila.valor).strip().lower() in ("1", "true", "si", "sí", "on")


def _exigir_cambio_password(db: Session) -> bool:
    return _interruptor(db, CLAVE_FORZAR_CAMBIO)


def _exigir_correo(db: Session) -> bool:
    return _interruptor(db, CLAVE_EXIGIR_CORREO)

@router.post("/", response_model=schemas.UsuarioResponse)
def crear_usuario(
    usuario: schemas.UsuarioCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles("ADMIN")),
):
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
            # Se completan con el catálogo actual: un administrador con permisos
            # guardados antes de añadir una pestaña no se queda sin ella.
            permisos_data = normalizar_permisos(admin_profile.permisos)
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
        path="/",
    )
    # ¿Hay que obligarlo a cambiar la contraseña? Solo si el colegio tiene la
    # exigencia activada Y este usuario todavía usa la clave inicial.
    debe_cambiar = bool(user.debe_cambiar_password) and _exigir_cambio_password(db)

    # ¿Y a registrar un correo? Solo si la exigencia está activada y la cuenta
    # todavía no tiene ninguno. Al alumno se le pide el de su apoderado.
    debe_registrar_correo = _exigir_correo(db) and not tiene_correo(db, user)

    # 6. Retornar los datos que el frontend necesita para el UseContext(aqui se usara JWT)
    return {
        "id_usuario": user.id_usuario,
        "username": user.username,
        "rol": user.rol,
        "access_token": access_token,
        "token_type": "bearer",
        "status": "success",
        "permisos": permisos_data,
        "debe_cambiar_password": debe_cambiar,
        "debe_registrar_correo": debe_registrar_correo,
    }

@router.post("/logout")
def logout(response: Response):
    # Forzamos la expiración absoluta de la cookie
    response.set_cookie(
        key="authToken",
        value="",
        httponly=True,
        samesite="lax",
        secure=False, # True en producción con HTTPS
        path="/",
        expires=0,    # Expira ya
        max_age=0     # Expira ya
    )
    return {"status": "success", "message": "Sesión cerrada correctamente"}