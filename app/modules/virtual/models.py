from sqlalchemy import Column, Integer, String, DECIMAL, ForeignKey, DateTime, Text, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base

class Tarea(Base):
    __tablename__ = "tarea"
    id_tarea = Column(Integer, primary_key=True)
    id_carga_academica = Column(Integer, ForeignKey("carga_academica.id_carga_academica"))
    titulo = Column(String(150), nullable=False)
    descripcion = Column(Text)
    fecha_publicacion = Column(DateTime, server_default=func.now())
    fecha_entrega = Column(DateTime, nullable=False)
    estado = Column(String(20), default='ACTIVO')

class EntregaTarea(Base):
    __tablename__ = "entrega_tarea"
    id_entrega = Column(Integer, primary_key=True)
    id_tarea = Column(Integer, ForeignKey("tarea.id_tarea"))
    id_alumno = Column(Integer, ForeignKey("alumno.id_alumno"))
    archivo_url = Column(String(255))
    comentario_alumno = Column(Text)
    fecha_envio = Column(DateTime, server_default=func.now())
    calificacion = Column(DECIMAL(4, 2))
    retroalimentacion_docente = Column(Text)

class Conversacion(Base):
    __tablename__ = "conversacion"
    id_conversacion = Column(Integer, primary_key=True)
    usuario1_id = Column(Integer, ForeignKey("usuario.id_usuario"))
    usuario2_id = Column(Integer, ForeignKey("usuario.id_usuario"))
    ultimo_mensaje = Column(Text)
    fecha_actualizacion = Column(DateTime, server_default=func.now())

class Mensaje(Base):
    __tablename__ = "mensaje"
    id_mensaje = Column(Integer, primary_key=True)
    id_conversacion = Column(Integer, ForeignKey("conversacion.id_conversacion"))
    remitente_id = Column(Integer, ForeignKey("usuario.id_usuario"))
    contenido = Column(Text, nullable=False)
    leido = Column(Boolean, default=False)
    fecha_envio = Column(DateTime, server_default=func.now())