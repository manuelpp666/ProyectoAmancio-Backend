from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.db.database import get_db
from . import models, schemas

router = APIRouter(prefix="/web", tags=["Web Institucional"])

@router.post("/noticias/", response_model=schemas.NoticiaResponse)
def crear_noticia(noticia: schemas.NoticiaCreate, db: Session = Depends(get_db)):
    try:
        # model_dump() es la forma estándar en Pydantic v2
        nueva = models.Noticia(**noticia.model_dump())
        db.add(nueva)
        db.commit()
        db.refresh(nueva)
        return nueva
    except Exception as e:
        db.rollback() # Revierte los cambios si hubo error
        raise HTTPException(
            status_code=500, 
            detail=f"Error interno al crear la noticia: {str(e)}"
        )

@router.get("/noticias/", response_model=List[schemas.NoticiaResponse])
def listar_noticias(db: Session = Depends(get_db)):
    return db.query(models.Noticia).filter(models.Noticia.activo == True).all()

@router.get("/noticias/{noticia_id}", response_model=schemas.NoticiaResponse)
def obtener_noticia(noticia_id: int, db: Session = Depends(get_db)):
    noticia = db.query(models.Noticia).filter(models.Noticia.id_noticia == noticia_id).first()
    if not noticia:
        raise HTTPException(status_code=404, detail="Noticia no encontrada")
    return noticia

@router.delete("/noticias/{noticia_id}")
def eliminar_noticia(noticia_id: int, db: Session = Depends(get_db)):
    noticia = db.query(models.Noticia).filter(models.Noticia.id_noticia == noticia_id).first()
    if not noticia:
        raise HTTPException(status_code=404, detail="Noticia no encontrada")
    
    # En lugar de borrar físicamente, cambiamos el estado
    noticia.activo = not noticia.activo
    db.commit()
    return {"message": "Noticia actualizada correctamente"}

@router.put("/noticias/{noticia_id}", response_model=schemas.NoticiaResponse)
def actualizar_noticia(noticia_id: int, noticia_update: schemas.NoticiaCreate, db: Session = Depends(get_db)):
    db_noticia = db.query(models.Noticia).filter(models.Noticia.id_noticia == noticia_id).first()
    if not db_noticia:
        raise HTTPException(status_code=404, detail="Noticia no encontrada")
    
    for key, value in noticia_update.dict().items():
        setattr(db_noticia, key, value)
    
    db.commit()
    db.refresh(db_noticia)
    return db_noticia

@router.post("/eventos/", response_model=schemas.EventoResponse)
def crear_evento(evento: schemas.EventoCreate, db: Session = Depends(get_db)):
    nueva = models.Evento(**evento.dict())
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva

@router.get("/eventos/", response_model=List[schemas.EventoResponse])
def listar_eventos(db: Session = Depends(get_db)):
    return db.query(models.Evento).filter(models.Evento.activo == True).all()