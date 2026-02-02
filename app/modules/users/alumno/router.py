from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.db.database import get_db
from . import models, schemas # Asegúrate de importar los modelos correctos

router = APIRouter(prefix="/alumnos", tags=["Alumnos"])

@router.post("/", response_model=schemas.AlumnoResponse)
def crear_alumno(alumno: schemas.AlumnoCreate, db: Session = Depends(get_db)):
    db_alumno = models.Alumno(**alumno.dict())
    db.add(db_alumno)
    db.commit()
    db.refresh(db_alumno)
    return db_alumno

@router.get("/", response_model=List[schemas.AlumnoResponse])
def listar_alumnos(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(models.Alumno).offset(skip).limit(limit).all()

@router.get("/{id}", response_model=schemas.AlumnoResponse)
def obtener_alumno(id: int, db: Session = Depends(get_db)):
    alumno = db.query(models.Alumno).filter(models.Alumno.id_alumno == id).first()
    if not alumno:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")
    return alumno

# Implementar PUT y DELETE de forma similarv