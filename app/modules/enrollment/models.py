from sqlalchemy import Column, Integer, String, DECIMAL, ForeignKey, DateTime, Boolean, CHAR
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base

class Matricula(Base):
    __tablename__ = "matricula"

    id_matricula = Column(Integer, primary_key=True, index=True)
    id_anio_escolar = Column(String(6), ForeignKey("anio_escolar.id_anio_escolar"))
    id_alumno = Column(Integer, ForeignKey("alumno.id_alumno"))
    id_seccion = Column(Integer, ForeignKey("seccion.id_seccion"), nullable=True)
    id_grado = Column(Integer, ForeignKey("grado.id_grado"))
    
    fecha_matricula = Column(DateTime, default=func.now())
    estado = Column(String(20), default="MATRICULADO")
    tipo_matricula = Column(String(20), default="REGULAR")
    # NORMAL / CONDICIONADA / REPITE — resultado de la evaluación de fin de año
    condicion = Column(String(20), nullable=True, default="NORMAL")

    # --- RELACIONES ---
    alumno = relationship("app.modules.users.alumno.models.Alumno")
    anio_escolar = relationship("app.modules.academic.models.AnioEscolar")
    grado = relationship("app.modules.academic.models.Grado")
    seccion = relationship("app.modules.academic.models.Seccion")

    # --- AQUÍ ESTABA EL ERROR ---
    # Faltaba definir esta propiedad para que 'Exoneracion' pudiera encontrarla
    exoneraciones = relationship("Exoneracion", back_populates="matricula")

class SolicitudMatricula(Base):
    __tablename__ = "solicitud_matricula"

    id_solicitud_matricula = Column(Integer, primary_key=True, index=True)
    id_alumno = Column(Integer, ForeignKey("alumno.id_alumno"), nullable=False)
    id_anio_escolar_origen = Column(String(6), nullable=True)
    anio_destino = Column(String(6), nullable=False)
    grado_destino = Column(String(50), nullable=True)
    comentario = Column(String, nullable=True)
    estado = Column(String(20), default="PENDIENTE")  # PENDIENTE / APROBADA / RECHAZADA
    respuesta_admin = Column(String, nullable=True)
    fecha_solicitud = Column(DateTime, default=func.now())

    alumno = relationship("app.modules.users.alumno.models.Alumno")


class Exoneracion(Base):
    __tablename__ = "exoneracion"
    id_exoneracion = Column(Integer, primary_key=True)
    id_matricula = Column(Integer, ForeignKey("matricula.id_matricula"))
    motivo = Column(String(100), nullable=False)
    concepto_exonerado = Column(String(50), nullable=False)
    porcentaje_descuento = Column(DECIMAL(5, 2), default=100.00)
    fecha_aprobacion = Column(DateTime, server_default=func.now())
    activo = Column(Boolean, default=True)

    matricula = relationship("Matricula", back_populates="exoneraciones")