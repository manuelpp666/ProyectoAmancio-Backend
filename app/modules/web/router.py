from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from app.db.database import get_db
from . import models, schemas

router = APIRouter(prefix="/web", tags=["Web Institucional"])

@router.post("/noticias/", response_model=schemas.NoticiaResponse)
def crear_noticia(noticia: schemas.NoticiaCreate, db: Session = Depends(get_db)):
    nueva = models.Noticia(**noticia.dict())
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva

@router.get("/noticias/", response_model=List[schemas.NoticiaResponse])
def listar_noticias(db: Session = Depends(get_db)):
    return db.query(models.Noticia).filter(models.Noticia.activo == True).all()

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