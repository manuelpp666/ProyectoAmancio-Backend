from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.sql import func
from app.db.database import Base

class Noticia(Base):
    __tablename__ = "noticia"
    id_noticia = Column(Integer, primary_key=True, index=True)
    titulo = Column(String(200), nullable=False)
    contenido = Column(Text, nullable=False)
    fecha_publicacion = Column(DateTime, server_default=func.now())
    imagen_portada_url = Column(String(255))
    categoria = Column(String(50))
    activo = Column(Boolean, default=True)
    id_autor = Column(Integer, ForeignKey("usuario.id_usuario"))

class Evento(Base):
    __tablename__ = "evento"
    id_evento = Column(Integer, primary_key=True, index=True)
    titulo = Column(String(150), nullable=False)
    descripcion = Column(Text)
    fecha_inicio = Column(DateTime, nullable=False)
    fecha_fin = Column(DateTime)
    tipo_evento = Column(String(50))
    color = Column(String(20))
    activo = Column(Boolean, default=True)