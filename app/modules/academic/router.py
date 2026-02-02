from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.database import get_db
from . import models, schemas # Crea los schemas correspondientes

router = APIRouter(prefix="/academic", tags=["Académico"])

@router.post("/secciones/", response_model=schemas.SeccionResponse)
def crear_seccion(seccion: schemas.SeccionCreate, db: Session = Depends(get_db)):
    nuevo = models.Seccion(**seccion.dict())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

# Puedes agregar endpoints para Grados, Cursos, etc. aquí mismo o separar en sub-routers