from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()
# ¡IMPORTANTE! Mueve esto a tus variables de entorno (.env) después
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
# Fallback a 60 min si la variable no está configurada (evita crash al arrancar)
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES") or 60)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # Añadimos la fecha de expiración al payload
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt