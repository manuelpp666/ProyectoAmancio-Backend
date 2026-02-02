from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class TareaCreate(BaseModel):
    id_carga_academica: int
    titulo: str
    descripcion: Optional[str]
    fecha_entrega: datetime

class EntregaCreate(BaseModel):
    id_tarea: int
    id_alumno: int
    archivo_url: Optional[str]
    comentario_alumno: Optional[str]

class MensajeCreate(BaseModel):
    id_conversacion: int
    remitente_id: int
    contenido: str