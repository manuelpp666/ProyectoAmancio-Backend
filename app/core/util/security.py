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