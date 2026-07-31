from sqlalchemy import Column, Integer, String, DECIMAL, ForeignKey, DateTime, Boolean
from sqlalchemy.sql import func
from app.db.database import Base


class CursoDesaprobado(Base):
    """Un curso desaprobado por un alumno en un año escolar.
    Es la unidad de verdad para la acumulación (secundaria) y la nivelación."""
    __tablename__ = "curso_desaprobado"

    id = Column(Integer, primary_key=True, index=True)
    id_alumno = Column(Integer, ForeignKey("alumno.id_alumno"), nullable=False)
    id_curso = Column(Integer, ForeignKey("curso.id_curso"), nullable=False)
    id_anio_escolar = Column(String(6), ForeignKey("anio_escolar.id_anio_escolar"))
    nivel = Column(String(20))  # PRIMARIA / SECUNDARIA
    promedio = Column(DECIMAL(5, 2), nullable=True)
    recuperado = Column(Boolean, default=False)
    id_anio_recuperado = Column(String(6), nullable=True)
    fecha = Column(DateTime, server_default=func.now())


class EvaluacionFinal(Base):
    """Resultado de la evaluación de fin de año por alumno."""
    __tablename__ = "evaluacion_final"

    id = Column(Integer, primary_key=True, index=True)
    id_alumno = Column(Integer, ForeignKey("alumno.id_alumno"), nullable=False)
    id_anio_escolar = Column(String(6), ForeignKey("anio_escolar.id_anio_escolar"))
    id_matricula = Column(Integer, ForeignKey("matricula.id_matricula"), nullable=True)
    nivel = Column(String(20))
    id_grado = Column(Integer, ForeignKey("grado.id_grado"), nullable=True)
    total_desaprobados = Column(Integer, default=0)
    acumulado_desaprobados = Column(Integer, default=0)
    # PROMOVIDO / REQUIERE_NIVELACION / REPITE
    resultado = Column(String(20), default="PROMOVIDO")
    correo_enviado = Column(Boolean, default=False)
    fecha = Column(DateTime, server_default=func.now())


class SolicitudVerano(Base):
    """Inscripción a un año académico de verano (externos e internos)."""
    __tablename__ = "solicitud_verano"

    id = Column(Integer, primary_key=True, index=True)
    id_alumno = Column(Integer, ForeignKey("alumno.id_alumno"), nullable=False)
    id_anio_escolar = Column(String(6), ForeignKey("anio_escolar.id_anio_escolar"))
    id_grado = Column(Integer, ForeignKey("grado.id_grado"), nullable=True)
    origen = Column(String(20))       # EXTERNO / INTERNO / NIVELACION
    modalidad = Column(String(20))    # CURSOS / TALLER / CURSOS_Y_TALLER / NIVELACION
    estado = Column(String(20), default="PENDIENTE_PAGO")  # PENDIENTE_PAGO / PAGADO / ADMITIDO / RECHAZADA
    id_pago = Column(Integer, ForeignKey("pago.id_pago"), nullable=True)
    id_matricula = Column(Integer, ForeignKey("matricula.id_matricula"), nullable=True)
    fecha = Column(DateTime, server_default=func.now())


class SolicitudVeranoCurso(Base):
    """Cursos / talleres elegidos en una inscripción de verano."""
    __tablename__ = "solicitud_verano_curso"

    id = Column(Integer, primary_key=True, index=True)
    id_solicitud_verano = Column(Integer, ForeignKey("solicitud_verano.id"), nullable=False)
    id_curso = Column(Integer, ForeignKey("curso.id_curso"), nullable=False)
    es_taller = Column(Boolean, default=False)
