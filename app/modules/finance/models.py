from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, DateTime, Date, Text, Boolean, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base
import enum

# Opcional: Definir estados como Enums para evitar errores de escritura
class EstadoPago(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    PAGADO = "PAGADO"
    VENCIDO = "VENCIDO"
    ANULADO = "ANULADO"

class TipoTramite(Base):
    __tablename__ = "tipo_tramite"

    id_tipo_tramite = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    costo = Column(Numeric(10, 2), default=0.00)
    requisitos = Column(Text, nullable=True)
    activo = Column(Boolean, default=True)
    alcance = Column(String(20), default="TODOS") # E.g., 'PRIMARIA', 'SECUNDARIA'
    grados_permitidos = Column(String(255), nullable=True)

    # Relación: Un tipo de trámite puede estar en muchas solicitudes
    solicitudes = relationship("SolicitudTramite", back_populates="tipo")

class SolicitudTramite(Base):
    __tablename__ = "solicitud_tramite"

    id_solicitud_tramite = Column(Integer, primary_key=True, index=True)
    id_alumno = Column(Integer, ForeignKey("alumno.id_alumno"))
    id_tipo_tramite = Column(Integer, ForeignKey("tipo_tramite.id_tipo_tramite"))
    fecha_solicitud = Column(DateTime, server_default=func.now())
    estado = Column(String(20), default="PENDIENTE_PAGO")
    archivo_adjunto = Column(String(255), nullable=True)
    comentario_usuario = Column(Text, nullable=True)
    respuesta_administrativa = Column(Text, nullable=True)

    # Relaciones
    alumno = relationship("Alumno") # Asumiendo que existe el modelo Alumno
    tipo = relationship("TipoTramite", back_populates="solicitudes")
    pago = relationship("Pago", back_populates="solicitud", uselist=False)

class Pago(Base):
    __tablename__ = "pago"

    id_pago = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuario.id_usuario"), nullable=True)
    id_alumno = Column(Integer, ForeignKey("alumno.id_alumno"), nullable=False)
    id_matricula = Column(Integer, ForeignKey("matricula.id_matricula"), nullable=True)
    id_solicitud_tramite = Column(Integer, ForeignKey("solicitud_tramite.id_solicitud_tramite"), nullable=True)
    
    concepto = Column(String(150), nullable=False) # E.g., 'Pensión Marzo', 'Certificado'
    monto = Column(Numeric(10, 2), nullable=False)
    mora = Column(Numeric(10, 2), default=0.00)
    monto_total = Column(Numeric(10, 2), nullable=False)
    
    # Campos específicos para la integración BCP
    codigo_operacion_bcp = Column(String(50), nullable=True)
    estado = Column(String(20), default="PENDIENTE")
    fecha_vencimiento = Column(Date, nullable=True)
    fecha_pago = Column(DateTime, nullable=True)
    json_respuesta_banco = Column(Text, nullable=True) # Para guardar el log del Webhook

    # Relaciones para facilitar consultas
    alumno = relationship("Alumno")
    solicitud = relationship("SolicitudTramite", back_populates="pago")
    matricula = relationship("Matricula")