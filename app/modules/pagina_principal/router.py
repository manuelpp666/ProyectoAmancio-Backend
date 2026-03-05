from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.db.database import get_db
from . import models, schemas
from sqlalchemy import or_
from datetime import datetime,date
from sqlalchemy import extract,desc,asc

router = APIRouter(prefix="/configuracion", tags=["Configuracion de Pagina"])

# Obtener todos los elementos de una sección (ej: /configuracion/home)
@router.get("/{seccion}", response_model=List[schemas.ConfigRead])
def get_config_by_section(seccion: str, db: Session = Depends(get_db)):
    config = db.query(models.PaginaConfiguracion).filter(models.PaginaConfiguracion.seccion == seccion).all()
    if not config:
        raise HTTPException(status_code=404, detail="Sección no encontrada")
    return config

# Actualizar un valor específico por su clave (ej: /configuracion/hero_titulo)
@router.put("/{clave}", response_model=schemas.ConfigRead)
def update_or_create_config(
    clave: str, 
    config_update: schemas.ConfigUpdate, 
    seccion: str, # Pasamos la sección como query param
    db: Session = Depends(get_db)
):
    item = db.query(models.PaginaConfiguracion).filter(
        models.PaginaConfiguracion.clave == clave
    ).first()
    
    if item:
        item.valor = config_update.valor
    else:
        item = models.PaginaConfiguracion(
            clave=clave,
            valor=config_update.valor,
            seccion=seccion,
            tipo="text"
        )
        db.add(item)
    
    db.commit()
    db.refresh(item)
    return item

# Endpoint especial para traer TODA la configuración y armar el objeto global
@router.get("/", response_model=List[schemas.ConfigRead])
def get_all_configs(db: Session = Depends(get_db)):
    return db.query(models.PaginaConfiguracion).all()