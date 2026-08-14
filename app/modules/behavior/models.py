from sqlalchemy import (Column, Integer, String, ForeignKey, DateTime, Text, Boolean,
                        DECIMAL, UniqueConstraint)
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

class NotaConducta(Base):
    """La nota de conducta de un alumno en un bimestre, sobre 20.

    Existe porque hay dos formas de llegar a ese número y no se pueden mezclar:

      MIGRADO   la puso el colegio en el sistema antiguo. No hay reportes
                detrás, así que calcularla daría 20 para todos y no cuadraría
                con la libreta que las familias ya tienen impresa.
      CALCULADO la deduce el sistema restando a 20 los puntos de cada reporte
                del bimestre.

    Cuando hay fila migrada, manda ella. No va en la tabla `nota` a propósito:
    en la libreta la conducta ocupa su propia fila y no entra ni en el puntaje
    acumulado ni en el promedio de áreas.
    """
    __tablename__ = "nota_conducta"
    __table_args__ = (
        UniqueConstraint("id_matricula", "bimestre", name="uq_conducta_matricula_bim"),
    )
    id_nota_conducta = Column(Integer, primary_key=True)
    id_matricula = Column(Integer, ForeignKey("matricula.id_matricula"), nullable=False)
    bimestre = Column(Integer, nullable=False)
    valor = Column(DECIMAL(4, 2), nullable=False)
    origen = Column(String(20), nullable=False, default="MIGRADO")
    fecha_registro = Column(DateTime, server_default=func.now())
