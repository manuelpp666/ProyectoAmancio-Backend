from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.db.database import get_db
from . import models, schemas
from sqlalchemy import or_
from datetime import datetime,date
from app.core.util.security import get_current_user
from sqlalchemy import extract,desc,asc
from app.modules.academic import models as academic_models

router = APIRouter(prefix="/web", tags=["Web Institucional"])

@router.get("/anio-activo")
def obtener_anio_activo_publico(db: Session = Depends(get_db)):
    """
    Endpoint público: devuelve el tipo (REGULAR/VERANO) del año escolar
    vigente según la fecha actual. Usado en el inicio de la web.
    """
    hoy = date.today()
    anio = db.query(academic_models.AnioEscolar).filter(
        academic_models.AnioEscolar.fecha_inicio <= hoy,
        academic_models.AnioEscolar.fecha_fin >= hoy
    ).first()
    return {"tipo": anio.tipo if anio else "REGULAR", "activo": anio is not None}


@router.get("/estado-admision")
def estado_admision_publico(db: Session = Depends(get_db)):
    """
    Endpoint público para el botón de Admisión del inicio:
    - abierto=True  -> hay inscripciones vigentes hoy (devuelve tipo y fin).
    - abierto=False + proxima_inscripcion -> hay inscripciones futuras (devuelve fecha y tipo).
    - abierto=False sin proxima_inscripcion -> no mostrar nada.
    """
    hoy = date.today()

    # 1. Todos los años con inscripciones vigentes hoy.
    #    Pueden ser DOS a la vez (el año regular y el de verano se solapan),
    #    así que se devuelven todos y la web muestra un botón por cada uno.
    abiertos = db.query(academic_models.AnioEscolar).filter(
        academic_models.AnioEscolar.inicio_inscripcion != None,
        academic_models.AnioEscolar.fin_inscripcion != None,
        academic_models.AnioEscolar.inicio_inscripcion <= hoy,
        academic_models.AnioEscolar.fin_inscripcion >= hoy
    ).order_by(academic_models.AnioEscolar.inicio_inscripcion.asc()).all()

    if abiertos:
        inscripciones = [
            {
                "id_anio_escolar": a.id_anio_escolar,
                "tipo": a.tipo,
                "fin_inscripcion": a.fin_inscripcion,
            }
            for a in abiertos
        ]
        primero = abiertos[0]
        return {
            "abierto": True,
            # Campos sueltos del primero: los mantiene el código que ya existía
            "tipo": primero.tipo,
            "fin_inscripcion": primero.fin_inscripcion,
            # Lista completa: lo que usa el inicio para pintar uno o dos botones
            "inscripciones": inscripciones,
        }

    # 2. Si no, ¿hay inscripciones futuras? -> la más próxima
    proxima = db.query(academic_models.AnioEscolar).filter(
        academic_models.AnioEscolar.inicio_inscripcion != None,
        academic_models.AnioEscolar.inicio_inscripcion > hoy
    ).order_by(academic_models.AnioEscolar.inicio_inscripcion.asc()).first()

    if proxima:
        return {
            "abierto": False,
            "tipo": proxima.tipo,
            "proxima_inscripcion": proxima.inicio_inscripcion,
        }

    # 3. Nada que mostrar
    return {"abierto": False}

@router.post("/noticias/", response_model=schemas.NoticiaResponse)
def crear_noticia(noticia: schemas.NoticiaCreate, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información")
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
    # Público: la web principal necesita leer el detalle de la noticia sin sesión
    noticia = db.query(models.Noticia).filter(models.Noticia.id_noticia == noticia_id).first()
    if not noticia:
        raise HTTPException(status_code=404, detail="Noticia no encontrada")
    return noticia

@router.delete("/noticias/{noticia_id}")
def eliminar_noticia(noticia_id: int, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información")
    

    noticia = db.query(models.Noticia).filter(models.Noticia.id_noticia == noticia_id).first()
    if not noticia:
        raise HTTPException(status_code=404, detail="Noticia no encontrada")
    
    # En lugar de borrar físicamente, cambiamos el estado
    noticia.activo = not noticia.activo
    db.commit()
    return {"message": "Noticia actualizada correctamente"}

@router.put("/noticias/{noticia_id}", response_model=schemas.NoticiaResponse)
def actualizar_noticia(noticia_id: int, noticia_update: schemas.NoticiaCreate, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información")

    db_noticia = db.query(models.Noticia).filter(models.Noticia.id_noticia == noticia_id).first()
    if not db_noticia:
        raise HTTPException(status_code=404, detail="Noticia no encontrada")
    
    for key, value in noticia_update.model_dump().items():
        setattr(db_noticia, key, value)
    
    db.commit()
    db.refresh(db_noticia)
    return db_noticia

@router.post("/eventos/", response_model=schemas.EventoResponse)
def crear_evento(evento: schemas.EventoCreate, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información")
    nueva = models.Evento(**evento.model_dump())
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
def actualizar_evento(evento_id: int, evento_update: schemas.EventoCreate, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información")
    db_evento = db.query(models.Evento).filter(models.Evento.id_evento == evento_id).first()
    if not db_evento:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    
    for key, value in evento_update.model_dump().items():
        setattr(db_evento, key, value)
    
    db.commit()
    db.refresh(db_evento)
    return db_evento

@router.delete("/eventos/{evento_id}")
def eliminar_evento(evento_id: int, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información")


    db_evento = db.query(models.Evento).filter(models.Evento.id_evento == evento_id).first()
    if not db_evento:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    
    # "Soft delete" lógico (igual que hiciste con noticias)
    db_evento.activo = False
    db.commit()
    return {"message": "Evento desactivado correctamente"}


@router.get("/eventos/resumen")
def obtener_resumen_eventos(db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    hoy = datetime.now()
    
    # 1. Evento más cercano que YA PASÓ (el último realizado)
    evento_pasado = db.query(models.Evento).filter(
        models.Evento.activo == True,
        models.Evento.fecha_inicio < hoy
    ).order_by(desc(models.Evento.fecha_inicio)).first()
    
    # 2. Próximos eventos (los más cercanos al futuro, ordenados)
    proximos_eventos = db.query(models.Evento).filter(
        models.Evento.activo == True,
        models.Evento.fecha_inicio >= hoy
    ).order_by(asc(models.Evento.fecha_inicio)).limit(5).all()

    proximo_evento = proximos_eventos[0] if proximos_eventos else None

    # Calcular días faltantes para el próximo
    dias_faltantes = None
    if proximo_evento:
        delta = proximo_evento.fecha_inicio - hoy
        dias_faltantes = delta.days if delta.days >= 0 else 0

    return {
        "evento_pasado": evento_pasado,
        "proximo_evento": proximo_evento,
        "proximos_eventos": proximos_eventos,
        "dias_faltantes_proximo": dias_faltantes
    }


@router.get("/eventos/por-anio/{anio_id}", response_model=List[schemas.EventoResponse])
def listar_eventos_por_anio_academico(anio_id: str, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    """
    Lista eventos filtrados por el ID del año académico (ej: '2024-R').
    """
    return db.query(models.Evento)\
             .filter(models.Evento.id_anio_escolar == anio_id, models.Evento.activo == True)\
             .order_by(models.Evento.fecha_inicio.asc())\
             .all()