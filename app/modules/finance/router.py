from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.database import get_db
from . import models, schemas

router = APIRouter(prefix="/finance", tags=["Finanzas"])

@router.post("/pagos/", response_model=schemas.PagoResponse)
def crear_pago(obj: schemas.PagoCreate, db: Session = Depends(get_db)):
    nuevo = models.Pago(**obj.dict())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

@router.post("/tramites/", response_model=schemas.TramiteResponse)
def solicitar_tramite(obj: schemas.TramiteCreate, db: Session = Depends(get_db)):
    nuevo = models.SolicitudTramite(**obj.dict())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo