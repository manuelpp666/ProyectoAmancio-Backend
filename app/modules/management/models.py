from sqlalchemy import Column, Integer, String, DECIMAL, ForeignKey, Date, DateTime, CHAR
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
    id_nota = Column(Integer, primary_key=True)
    id_matricula = Column(Integer, ForeignKey("matricula.id_matricula"))
    id_curso = Column(Integer, ForeignKey("curso.id_curso"))
    bimestre = Column(Integer, nullable=False)
    tipo_nota = Column(String(20), default='PROMEDIO')
    valor = Column(DECIMAL(4, 2), nullable=False)
    fecha_registro = Column(DateTime, server_default=func.now())

class ResumenNota(Base):
    __tablename__ = "resumen_nota"
    id_resumen_notas = Column(Integer, primary_key=True)
    id_matricula = Column(Integer, ForeignKey("matricula.id_matricula"))
    id_curso = Column(Integer, ForeignKey("curso.id_curso"))
    nota_bimestre1 = Column(DECIMAL(5, 2))
    nota_bimestre2 = Column(DECIMAL(5, 2))
    nota_bimestre3 = Column(DECIMAL(5, 2))
    nota_bimestre4 = Column(DECIMAL(5, 2))
    promedio_final = Column(DECIMAL(5, 2))
    estado_curso = Column(String(20), default='EN CURSO')