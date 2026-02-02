from sqlalchemy import Column, Integer, String, DECIMAL, ForeignKey, DateTime, Boolean, CHAR
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base

class Matricula(Base):
    __tablename__ = "matricula"
    id_matricula = Column(Integer, primary_key=True)
    id_anio_escolar = Column(CHAR(6), ForeignKey("anio_escolar.id_anio_escolar"))
    id_alumno = Column(Integer, ForeignKey("alumno.id_alumno"))
    id_seccion = Column(Integer, ForeignKey("seccion.id_seccion"))
    fecha_matricula = Column(DateTime, server_default=func.now())
    estado = Column(String(20), default='MATRICULADO')
    tipo_matricula = Column(String(20), default='REGULAR')

    # Relaciones (Asegúrate de que los modelos referenciados existan)
    # alumno = relationship("Alumno") 
    # seccion = relationship("Seccion")
    exoneraciones = relationship("Exoneracion", back_populates="matricula")

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