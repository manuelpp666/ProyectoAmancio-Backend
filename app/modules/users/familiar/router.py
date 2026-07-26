from fastapi import APIRouter, Depends,HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from . import models, schemas
from app.core.util.security import get_current_user

router = APIRouter(prefix="/familiares", tags=["Familiares"])

@router.post("/", response_model=schemas.FamiliarResponse)
def crear_familiar(familiar: schemas.FamiliarCreate, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user) ):

    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No tienes permisos para registrar familiares")

    existente = db.query(models.Familiar).filter(models.Familiar.dni == familiar.dni).first()
    if existente:
        raise HTTPException(status_code=400, detail="Ya existe un familiar registrado con ese DNI.")

    datos = familiar.model_dump()
    datos.pop("tipo_parentesco", None)  # el parentesco vive en relacion_familiar
    nuevo = models.Familiar(**datos)
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

@router.get("/")
def listar_familiares(db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user) ):
    
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes ver modificar esta información")

    return db.query(models.Familiar).all()