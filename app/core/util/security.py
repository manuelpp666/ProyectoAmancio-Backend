# app/core/security.py
from fastapi import Request, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()
# ¡IMPORTANTE! Mueve esto a tus variables de entorno (.env) después
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="usuarios/login")

def get_current_user(request: Request):
    # 1. Intentar sacar el token del Header (como antes)
    authorization: str = request.headers.get("Authorization")
    token = None

    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
    else:
        # 2. Si no está en el Header, buscarlo en la COOKIE
        token = request.cookies.get("authToken")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No se encontró el token de autenticación",
        )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Token inválido")
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Token expirado o corrupto")


def require_roles(*roles_permitidos: str):
    """
    Dependencia reutilizable de autorización por rol.

    Uso:
        @router.get("/algo")
        def endpoint(current_user: dict = Depends(require_roles("ADMIN"))):
            ...

    Devuelve el payload del usuario si su rol está permitido; de lo contrario
    lanza 403. Reemplaza el patrón repetido `if current_user.get("rol") != ...`.
    """
    def checker(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user.get("rol") not in roles_permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para realizar esta acción",
            )
        return current_user
    return checker


def require_service_key(env_var_name: str, header_name: str = "X-Service-Key"):
    """
    Dependencia de autenticación máquina-a-máquina (webhooks bancarios, cron jobs).

    Compara el header indicado contra el valor de una variable de entorno.
    Si la variable no está configurada, el endpoint queda bloqueado por defecto
    (fail-closed) para evitar dejarlo abierto por olvido.
    """
    def checker(request: Request):
        secret_esperado = os.getenv(env_var_name)
        secret_recibido = request.headers.get(header_name)
        if not secret_esperado or secret_recibido != secret_esperado:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credencial de servicio inválida",
            )
        return True
    return checker


def ensure_owner_or_roles(current_user: dict, id_usuario: int, *roles_privilegiados: str):
    """
    Verifica que el usuario de la sesión sea el dueño del recurso (su propio
    id_usuario) o tenga uno de los roles privilegiados (p. ej. ADMIN).

    Corrige el patrón erróneo `rol != "X" and id != id_usuario`, que dejaba
    pasar a cualquier usuario del rol "X" hacia recursos de OTRO usuario.
    """
    es_dueno = current_user.get("id") == id_usuario
    es_privilegiado = current_user.get("rol") in roles_privilegiados
    if not (es_dueno or es_privilegiado):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No puedes acceder a información de otro usuario",
        )
    return current_user