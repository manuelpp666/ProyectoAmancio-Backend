from sqlalchemy import Column, Integer, String, DECIMAL, ForeignKey, Date, DateTime, CHAR, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.database import Base

class CargaAcademica(Base):
    __tablename__ = "carga_academica"
    id_carga_academica = Column(Integer, primary_key=True)
    id_anio_escolar = Column(CHAR(6), ForeignKey("anio_escolar.id_anio_escolar"))
    id_seccion = Column(Integer, ForeignKey("seccion.id_seccion"))
    id_curso = Column(Integer, ForeignKey("curso.id_curso"))
    id_docente = Column(Integer, ForeignKey("docente.id_docente"))

    curso = relationship("Curso") 
    docente = relationship("Docente")
    seccion = relationship("Seccion")
    anio_escolar = relationship("AnioEscolar")

class Asistencia(Base):
    __tablename__ = "asistencia"
    id_asistencia = Column(Integer, primary_key=True)
    id_matricula = Column(Integer, ForeignKey("matricula.id_matricula"))
    fecha = Column(Date, nullable=False)
    estado = Column(String(1), nullable=False) # P, T, F, J
    observacion = Column(String(150))

class Nota(Base):
    __tablename__ = "nota"
    # Un alumno solo puede tener una nota de cada tipo por curso y bimestre.
    # Al cerrar el bimestre la aplicación busca la fila y la actualiza, así que
    # esto no le estorba: protege de cargas masivas repetidas, que es como se
    # duplicaron las notas de 2026 al ejecutar dos veces el mismo script.
    __table_args__ = (
        UniqueConstraint("id_matricula", "id_curso", "bimestre", "tipo_nota",
                         name="uq_nota_alumno_curso_bim"),
    )
    id_nota = Column(Integer, primary_key=True)
    id_matricula = Column(Integer, ForeignKey("matricula.id_matricula"))
    id_curso = Column(Integer, ForeignKey("curso.id_curso"))
    bimestre = Column(Integer, nullable=False)
    tipo_nota = Column(String(20), default='PROMEDIO')
    valor = Column(DECIMAL(4, 2), nullable=False)
    fecha_registro = Column(DateTime, server_default=func.now())

class ResumenNota(Base):
    __tablename__ = "resumen_nota"
    # Una sola boleta por alumno y curso: los cuatro bimestres van en columnas
    # de esta misma fila, no en filas distintas.
    __table_args__ = (
        UniqueConstraint("id_matricula", "id_curso", name="uq_resumen_alumno_curso"),
    )
    id_resumen_notas = Column(Integer, primary_key=True)
    id_matricula = Column(Integer, ForeignKey("matricula.id_matricula"))
    id_curso = Column(Integer, ForeignKey("curso.id_curso"))
    nota_bimestre1 = Column(DECIMAL(5, 2))
    nota_bimestre2 = Column(DECIMAL(5, 2))
    nota_bimestre3 = Column(DECIMAL(5, 2))
    nota_bimestre4 = Column(DECIMAL(5, 2))
    promedio_final = Column(DECIMAL(5, 2))
    estado_curso = Column(String(20), default='EN CURSO')

# --- NUEVO: MODELO DE TUTORÍA ---
class TutorSeccion(Base):
    __tablename__ = "tutor_seccion"
    id_tutor_seccion = Column(Integer, primary_key=True)
    id_anio_escolar = Column(CHAR(6), ForeignKey("anio_escolar.id_anio_escolar"))
    id_seccion = Column(Integer, ForeignKey("seccion.id_seccion"))
    id_docente = Column(Integer, ForeignKey("docente.id_docente"))

    docente = relationship("Docente")
    seccion = relationship("Seccion")
    anio_escolar = relationship("AnioEscolar")