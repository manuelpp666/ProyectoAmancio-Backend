from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.db.database import get_db
from . import models, schemas
from sqlalchemy import or_
from datetime import datetime
from sqlalchemy import extract

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
def listar_noticias(search: str = None, db: Session = Depends(get_db)):
    """
    Lista noticias activas con filtro opcional por título o contenido.
    """
    query = db.query(models.Noticia).filter(models.Noticia.activo == True)

    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            or_(
                models.Noticia.titulo.ilike(search_filter),
                models.Noticia.contenido.ilike(search_filter)
            )
        )
    
    return query.all()

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

# 1. Listar eventos del año actual (filtrado y ordenado)
@router.get("/eventos/actual", response_model=List[schemas.EventoResponse])
def listar_eventos_anio_actual(db: Session = Depends(get_db)):
    anio_actual = datetime.now().year
    return db.query(models.Evento)\
             .filter(models.Evento.activo == True, extract('year', models.Evento.fecha_inicio) == anio_actual)\
             .order_by(models.Evento.fecha_inicio.asc())\
             .all()

# 2. Listar TODOS los eventos (ordenados)
@router.get("/eventos/todos", response_model=List[schemas.EventoResponse])
def listar_todos_eventos(db: Session = Depends(get_db)):
    return db.query(models.Evento)\
             .filter(models.Evento.activo == True)\
             .order_by(models.Evento.fecha_inicio.asc())\
             .all()


@router.put("/eventos/{evento_id}", response_model=schemas.EventoResponse)
def actualizar_evento(evento_id: int, evento_update: schemas.EventoCreate, db: Session = Depends(get_db)):
    db_evento = db.query(models.Evento).filter(models.Evento.id_evento == evento_id).first()
    if not db_evento:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    
    for key, value in evento_update.model_dump().items():
        setattr(db_evento, key, value)
    
    db.commit()
    db.refresh(db_evento)
    return db_evento

@router.delete("/eventos/{evento_id}")
def eliminar_evento(evento_id: int, db: Session = Depends(get_db)):
    db_evento = db.query(models.Evento).filter(models.Evento.id_evento == evento_id).first()
    if not db_evento:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    
    # "Soft delete" lógico (igual que hiciste con noticias)
    db_evento.activo = False
    db.commit()
    return {"message": "Evento desactivado correctamente"}