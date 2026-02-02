from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class NoticiaCreate(BaseModel):
    titulo: str
    contenido: str
    id_autor: int
    categoria: Optional[str] = None
    imagen_portada_url: Optional[str] = None

class NoticiaResponse(NoticiaCreate):
    id_noticia: int
    fecha_publicacion: datetime
    activo: bool
    class Config: from_attributes = True

class EventoCreate(BaseModel):
    titulo: str
    fecha_inicio: datetime
    tipo_evento: Optional[str] = None
    color: Optional[str] = None
    descripcion: Optional[str] = None

class EventoResponse(EventoCreate):
    id_evento: int
    activo: bool
    class Config: from_attributes = True