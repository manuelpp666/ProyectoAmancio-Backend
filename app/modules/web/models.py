import json

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.types import TypeDecorator
from app.db.database import Base


class ListaDeTexto(TypeDecorator):
    """Una lista de cadenas guardada como JSON en una columna de texto.

    Se usa para las imágenes de una noticia: lo único que importa de ellas es
    el orden, así que no compensa una tabla aparte.
    El orden de la lista ES el orden en que se muestran.

    Si el texto guardado no es una lista JSON válida se devuelve None en vez
    de reventar: una noticia con el campo a medias tiene que seguir abriéndose.
    """
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return json.dumps([str(v) for v in value], ensure_ascii=False)

    def process_result_value(self, value, dialect):
        if not value:
            return None
        try:
            datos = json.loads(value)
        except (TypeError, ValueError):
            return None
        return [str(v) for v in datos] if isinstance(datos, list) else None


class Noticia(Base):
    __tablename__ = "noticia"
    id_noticia = Column(Integer, primary_key=True, index=True)
    titulo = Column(String(200), nullable=False)
    contenido = Column(Text, nullable=False)
    fecha_publicacion = Column(DateTime, server_default=func.now())
    # La primera de `imagenes`. Se mantiene porque es lo que sale en las
    # tarjetas del listado y en el inicio, y porque las noticias de antes de
    # las galerías solo tienen esto.
    imagen_portada_url = Column(String(255))
    # Las imágenes en el orden en que se subieron, sin tope de cantidad (el
    # que hay lo pone el tamaño del TEXT y lo comprueba el esquema). NULL en
    # las noticias antiguas: ahí manda `imagen_portada_url` y se muestra esa
    # sola.
    imagenes = Column(ListaDeTexto, nullable=True)
    categoria = Column(String(50))
    activo = Column(Boolean, default=True)
    id_autor = Column(Integer, ForeignKey("usuario.id_usuario"))

class Evento(Base):
    __tablename__ = "evento"
    id_evento = Column(Integer, primary_key=True, index=True)
    id_anio_escolar = Column(String(6), ForeignKey("anio_escolar.id_anio_escolar"), nullable=True)
    titulo = Column(String(150), nullable=False)
    descripcion = Column(Text)
    fecha_inicio = Column(DateTime, nullable=False)
    fecha_fin = Column(DateTime)
    tipo_evento = Column(String(50))
    color = Column(String(20))
    activo = Column(Boolean, default=True)