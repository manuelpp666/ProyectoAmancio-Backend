from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.database import get_db
from . import models, schemas

router = APIRouter(prefix="/conducta", tags=["Conducta y Psicología"])

@router.post("/reportes/")
def crear_reporte(reporte: schemas.ReporteCreate, db: Session = Depends(get_db)):
    nuevo = models.ReporteConducta(**reporte.dict())
    db.add(nuevo)
    db.commit()
    return nuevo