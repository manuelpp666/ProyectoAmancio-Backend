from pydantic import BaseModel,Field, ConfigDict, model_validator
from datetime import datetime
from typing import List, Optional, Literal

MAXIMO_IMAGENES = 4

class NoticiaCreate(BaseModel):
    titulo: str = Field(..., min_length=5, max_length=150)
    contenido: str = Field(..., min_length=10)
    id_autor: int = Field(..., gt=0)
    categoria: Optional[str] = None
    imagen_portada_url: Optional[str] = None
    # Galería de la noticia, en el orden en que se subieron las fotos. La
    # primera es además la portada. Las noticias de vídeo no la usan: ahí
    # `imagen_portada_url` guarda la URL de YouTube.
    imagenes: Optional[List[str]] = None

    @model_validator(mode='after')
    def normalizar_imagenes(self) -> 'NoticiaCreate':
        """Limpia la galería y la deja coherente con la portada.

        Quita huecos y repetidas —subir dos veces la misma foto no debe
        pintarla dos veces—, corta en 4 y se asegura de que la portada sea la
        primera, que es lo que ve quien entra desde el listado.
        """
        if self.imagenes is not None:
            limpias: List[str] = []
            for url in self.imagenes:
                url = (url or "").strip()
                if url and url not in limpias:
                    limpias.append(url)
            self.imagenes = limpias[:MAXIMO_IMAGENES] or None
        if self.imagenes:
            self.imagen_portada_url = self.imagenes[0]
        return self

class NoticiaResponse(NoticiaCreate):
    id_noticia: int
    fecha_publicacion: datetime
    activo: bool
    model_config = ConfigDict(from_attributes=True)

class EventoCreate(BaseModel):
    titulo: str = Field(..., min_length=3, max_length=100)
    fecha_inicio: datetime
    id_anio_escolar: Optional[str] = None
    fecha_fin: Optional[datetime] = None
    tipo_evento: Optional[str] = None
    color: Optional[str] = Field(default="#3182ce", pattern=r"^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$")
    descripcion: Optional[str] = Field(None, max_length=500)
    @model_validator(mode='after')
    def validar_rango_fechas(self) -> 'EventoCreate':
        if self.fecha_fin and self.fecha_fin < self.fecha_inicio:
            raise ValueError("La fecha de fin no puede ser anterior al inicio del evento")
        return self

class EventoResponse(EventoCreate):
    id_evento: int
    activo: bool
    model_config = ConfigDict(from_attributes=True)