from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from . import models, schemas
from app.core.util.password import get_password_hash

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