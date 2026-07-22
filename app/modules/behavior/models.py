from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text, Boolean
from sqlalchemy.sql import func
from app.db.database import Base
from sqlalchemy.orm import relationship

class TipoFalta(Base):
    __tablename__ = "tipo_falta"
    id_tipo_falta = Column(Integer, primary_key=True)
    nombre = Column(String(60), nullable=False, unique=True)

class NivelConducta(Base):
    __tablename__ = "nivel_conducta"
    id_nivel_conducta = Column(Integer, primary_key=True)
    nombre = Column(String(120), nullable=False)
    id_tipo_falta = Column(Integer, ForeignKey("tipo_falta.id_tipo_falta"), nullable=False)
    puntos = Column(Integer, nullable=False)
    medida = Column(String(60))  # sanción del reglamento (p. ej. "Acto reflexivo por 3 días")
    cambio_ie = Column(Boolean, nullable=False, default=False)  # la falta amerita cambio de I.E.
    descripcion = Column(Text)
    tipo = relationship("TipoFalta")

class ReporteConducta(Base):
    __tablename__ = "reporte_conducta"
    id_reporte = Column(Integer, primary_key=True)
    id_alumno = Column(Integer, ForeignKey("alumno.id_alumno"))
    id_docente = Column(Integer, ForeignKey("docente.id_docente"))
    id_nivel_conducta = Column(Integer, ForeignKey("nivel_conducta.id_nivel_conducta"))
    fecha_reporte = Column(DateTime, server_default=func.now())
    descripcion_suceso = Column(Text, nullable=False)
    estado = Column(String(20), default='REGISTRADO')
    nivel = relationship("NivelConducta")
    alumno = relationship("Alumno")

class CitaPsicologia(Base):
    __tablename__ = "cita_psicologia"
    id_cita = Column(Integer, primary_key=True)
    id_alumno = Column(Integer, ForeignKey("alumno.id_alumno"))
    id_familiar = Column(Integer, ForeignKey("familiar.id_familiar"))
    motivo = Column(String(200), nullable=False)
    fecha_cita = Column(DateTime, nullable=False)
    estado = Column(String(20), default='PROGRAMADA')
    resultado_reunion = Column(Text)