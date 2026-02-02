from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.database import get_db
from . import models, schemas

router = APIRouter(prefix="/academic", tags=["Académico"])

@router.post("/anios/", response_model=schemas.AnioEscolarResponse)
def crear_anio(anio: schemas.AnioEscolarCreate, db: Session = Depends(get_db)):
    nuevo = models.AnioEscolar(**anio.dict())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

@router.get("/secciones/", response_model=list[schemas.SeccionResponse])
def listar_secciones(db: Session = Depends(get_db)):
    return db.query(models.Seccion).all()