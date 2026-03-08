from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.database import get_db
from . import models, schemas
from app.core.util.security import get_current_user

router = APIRouter(prefix="/familiares", tags=["Familiares"])

@router.post("/", response_model=schemas.FamiliarResponse)
def crear_familiar(familiar: schemas.FamiliarCreate, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user) ):
    nuevo = models.Familiar(**familiar.model_dump())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

@router.get("/")
def listar_familiares(db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user) ):
    return db.query(models.Familiar).all()