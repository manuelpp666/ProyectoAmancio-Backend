import json

from pydantic import BaseModel,Field, ConfigDict, model_validator
from datetime import datetime
from typing import List, Optional, Literal

# Una noticia puede llevar todas las fotos que haga falta. El único límite
# real es la columna donde se guarda la lista: es un TEXT de MySQL, 65 535
# bytes, y ahí caben del orden de 600 URLs de Cloudinary.
#
# Se comprueba a propósito, aunque no se vaya a alcanzar nunca: MySQL no
# avisa al pasarse, RECORTA. Y una lista JSON cortada por la mitad ya no se
# puede leer, así que la noticia se quedaría sin NINGUNA foto en vez de sin
# la última. Mejor un error claro antes de guardar.
LIMITE_BYTES_GALERIA = 65_000

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
        pintarla dos veces— y se asegura de que la portada sea la primera,
        que es lo que ve quien entra desde el listado. No hay tope de fotos;
        lo único que se vigila es que la lista quepa en su columna.
        """
        if self.imagenes is not None:
            limpias: List[str] = []
            for url in self.imagenes:
                url = (url or "").strip()
                if url and url not in limpias:
                    limpias.append(url)
            medida = len(json.dumps(limpias, ensure_ascii=False).encode("utf-8"))
            if medida > LIMITE_BYTES_GALERIA:
                raise ValueError(
                    f"La galería tiene {len(limpias)} imágenes y no cabe en la "
                    f"noticia. Quita algunas y vuelve a guardar.")
            self.imagenes = limpias or None
        if self.imagenes:
            self.imagen_portada_url = self.imagenes[0]
        return self

class NoticiaResponse(NoticiaCreate):
    id_noticia: int
    fecha_publicacion: datetime
    activo: bool
    model_config = ConfigDict(from_attributes=True)

# Color predeterminado de cada tipo de evento. Tiene que decir lo mismo que
# ProyectoAmancio/src/components/utils/eventos.ts: el panel manda el color ya
# resuelto, y esto es la red por si el evento se crea desde otro sitio.
COLOR_POR_TIPO_EVENTO = {
    "inicio de clases": "#0E7490",
    "ceremonia": "#093E7A",
    "festividades": "#701C32",
    "feriado": "#D97706",
    "actividad": "#059669",
    "actividad escolar": "#2563EB",
    "vacaciones": "#DB2777",
}
COLOR_EVENTO_POR_DEFECTO = "#093E7A"


class EventoCreate(BaseModel):
    titulo: str = Field(..., min_length=3, max_length=100)
    fecha_inicio: datetime
    id_anio_escolar: Optional[str] = None
    fecha_fin: Optional[datetime] = None
    tipo_evento: Optional[str] = None
    # Si no viene, se rellena con el color del tipo (ver asignar_color_por_tipo).
    color: Optional[str] = Field(default=None, pattern=r"^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$")
    descripcion: Optional[str] = Field(None, max_length=500)

    @model_validator(mode='after')
    def validar_rango_fechas(self) -> 'EventoCreate':
        if self.fecha_fin and self.fecha_fin < self.fecha_inicio:
            raise ValueError("La fecha de fin no puede ser anterior al inicio del evento")
        return self

    @model_validator(mode='after')
    def asignar_color_por_tipo(self) -> 'EventoCreate':
        # Un evento sin color pintaba de gris en el calendario y no salía en la
        # leyenda. Se le da el de su tipo, y si el tipo no está en la lista, el
        # azul de la marca.
        if not (self.color or "").strip():
            tipo = (self.tipo_evento or "").strip().lower()
            self.color = COLOR_POR_TIPO_EVENTO.get(tipo, COLOR_EVENTO_POR_DEFECTO)
        return self

class EventoResponse(EventoCreate):
    id_evento: int
    activo: bool
    model_config = ConfigDict(from_attributes=True)