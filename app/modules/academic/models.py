from sqlalchemy import Column, Integer, String, Boolean, Date, ForeignKey, CHAR, Text
from sqlalchemy.orm import relationship
from app.db.database import Base

class AnioEscolar(Base):
    __tablename__ = "anio_escolar"
    id_anio_escolar = Column(CHAR(6), primary_key=True)
    fecha_inicio = Column(Date)
    fecha_fin = Column(Date)
    activo = Column(Boolean, default=False)

class Nivel(Base):
    __tablename__ = "nivel"
    id_nivel = Column(Integer, primary_key=True)
    nombre = Column(String(20))
    
    # Relación: Un nivel tiene muchos grados
    grados = relationship("Grado", back_populates="nivel")

class Grado(Base):
    __tablename__ = "grado"
    id_grado = Column(Integer, primary_key=True)
    id_nivel = Column(Integer, ForeignKey("nivel.id_nivel"))
    nombre = Column(String(20))
    orden = Column(Integer)
    
    nivel = relationship("Nivel", back_populates="grados")
    secciones = relationship("Seccion", back_populates="grado")
    planes_estudio = relationship("PlanEstudio", back_populates="grado")

class Seccion(Base):
    __tablename__ = "seccion"
    id_seccion = Column(Integer, primary_key=True)
    id_grado = Column(Integer, ForeignKey("grado.id_grado"))
    nombre = Column(String(5))
    aula = Column(String(20))
    vacantes = Column(Integer)

    grado = relationship("Grado", back_populates="secciones")

class PlanEstudio(Base):
    __tablename__ = "plan_estudio"
    id_plan_estudio = Column(Integer, primary_key=True)
    id_curso = Column(Integer, ForeignKey("curso.id_curso"))
    id_grado = Column(Integer, ForeignKey("grado.id_grado"))

    # Relaciones
    curso = relationship("Curso", back_populates="planes_estudio")
    grado = relationship("Grado", back_populates="planes_estudio")


class Area(Base):
    __tablename__ = "area"
    id_area = Column(Integer, primary_key=True)
    nombre = Column(String(100))
    
    # Relación: Un área tiene muchos cursos
    cursos = relationship("Curso", back_populates="area")

class Curso(Base):
    __tablename__ = "curso"
    id_curso = Column(Integer, primary_key=True)
    id_area = Column(Integer, ForeignKey("area.id_area"))
    nombre = Column(String(100))

    area = relationship("Area", back_populates="cursos")
    planes_estudio = relationship("PlanEstudio", back_populates="curso")