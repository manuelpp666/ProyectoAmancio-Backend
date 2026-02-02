from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from app.db.database import get_db
from . import models, schemas

router = APIRouter(prefix="/gestion", tags=["Gestión Académica"])

# --- Carga Académica ---
@router.post("/carga/", response_model=schemas.CargaResponse)
def asignar_carga(carga: schemas.CargaCreate, db: Session = Depends(get_db)):
    nueva = models.CargaAcademica(**carga.dict())
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva

@router.get("/carga/", response_model=List[schemas.CargaResponse])
def listar_cargas(db: Session = Depends(get_db)):
    return db.query(models.CargaAcademica).all()

# --- Notas ---
@router.post("/notas/", response_model=schemas.NotaResponse)
def registrar_nota(nota: schemas.NotaCreate, db: Session = Depends(get_db)):
    nueva = models.Nota(**nota.dict())
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva

# --- Asistencia ---
@router.post("/asistencia/", response_model=schemas.AsistenciaResponse)
def registrar_asistencia(asistencia: schemas.AsistenciaCreate, db: Session = Depends(get_db)):
    nueva = models.Asistencia(**asistencia.dict())
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva