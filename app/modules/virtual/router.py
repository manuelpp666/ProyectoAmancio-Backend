from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.database import get_db
from . import models, schemas

router = APIRouter(prefix="/virtual", tags=["Aula Virtual"])

@router.post("/tareas/")
def crear_tarea(tarea: schemas.TareaCreate, db: Session = Depends(get_db)):
    nuevo = models.Tarea(**tarea.dict())
    db.add(nuevo)
    db.commit()
    return nuevo

@router.post("/chat/mensaje/")
def enviar_mensaje(mensaje: schemas.MensajeCreate, db: Session = Depends(get_db)):
    nuevo = models.Mensaje(**mensaje.dict())
    db.add(nuevo)
    db.commit()
    # Aquí deberías actualizar también 'ultimo_mensaje' en la tabla Conversacion
    return nuevo