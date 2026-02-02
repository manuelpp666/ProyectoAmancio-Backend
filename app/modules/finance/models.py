from sqlalchemy import Column, Integer, String, DECIMAL, ForeignKey, Date, DateTime, Text, Boolean
from sqlalchemy.sql import func
from app.db.database import Base

class TipoTramite(Base):
    __tablename__ = "tipo_tramite"
    id_tipo_tramite = Column(Integer, primary_key=True)
    nombre = Column(String(100), nullable=False)
    costo = Column(DECIMAL(10, 2), default=0.00)
    requisitos = Column(Text)
    activo = Column(Boolean, default=True)

class SolicitudTramite(Base):
    __tablename__ = "solicitud_tramite"
    id_solicitud_tramite = Column(Integer, primary_key=True)
    id_alumno = Column(Integer, ForeignKey("alumno.id_alumno"))
    id_tipo_tramite = Column(Integer, ForeignKey("tipo_tramite.id_tipo_tramite"))
    fecha_solicitud = Column(DateTime, server_default=func.now())
    estado = Column(String(20), default='PENDIENTE_PAGO')
    archivo_adjunto = Column(String(255))
    comentario_usuario = Column(Text)
    respuesta_administrativa = Column(Text)

class Pago(Base):
    __tablename__ = "pago"
    id_pago = Column(Integer, primary_key=True)
    id_usuario = Column(Integer, ForeignKey("usuario.id_usuario"))
    id_alumno = Column(Integer, ForeignKey("alumno.id_alumno"), nullable=False)
    id_matricula = Column(Integer, ForeignKey("matricula.id_matricula"))
    id_solicitud_tramite = Column(Integer, ForeignKey("solicitud_tramite.id_solicitud_tramite"))
    concepto = Column(String(150), nullable=False)
    monto = Column(DECIMAL(10, 2), nullable=False)
    mora = Column(DECIMAL(10, 2), default=0.00)
    monto_total = Column(DECIMAL(10, 2), nullable=False)
    codigo_operacion_bcp = Column(String(50))
    estado = Column(String(20), default='PENDIENTE')
    fecha_vencimiento = Column(Date)
    fecha_pago = Column(DateTime)
    json_respuesta_banco = Column(Text)