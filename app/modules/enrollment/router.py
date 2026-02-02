from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.database import get_db
from . import models, schemas

router = APIRouter(prefix="/matriculas", tags=["Matrícula"])

@router.post("/", response_model=schemas.MatriculaResponse)
def crear_matricula(matricula: schemas.MatriculaCreate, db: Session = Depends(get_db)):
    nueva = models.Matricula(**matricula.dict())
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva

@router.post("/exoneracion/", response_model=schemas.ExoneracionResponse)
def crear_exoneracion(exoneracion: schemas.ExoneracionCreate, db: Session = Depends(get_db)):
    nueva = models.Exoneracion(**exoneracion.dict())
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva