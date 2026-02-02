from sqlalchemy import Column, Integer, String, Boolean, Date, ForeignKey, CHAR
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

class Grado(Base):
    __tablename__ = "grado"
    id_grado = Column(Integer, primary_key=True)
    id_nivel = Column(Integer, ForeignKey("nivel.id_nivel"))
    nombre = Column(String(20))
    orden = Column(Integer)
    
    secciones = relationship("Seccion", back_populates="grado")

class Seccion(Base):
    __tablename__ = "seccion"
    id_seccion = Column(Integer, primary_key=True)
    id_grado = Column(Integer, ForeignKey("grado.id_grado"))
    nombre = Column(String(5))
    aula = Column(String(20))
    vacantes = Column(Integer)

    grado = relationship("Grado", back_populates="secciones")

class Area(Base):
    __tablename__ = "area"
    id_area = Column(Integer, primary_key=True)
    nombre = Column(String(100))

class Curso(Base):
    __tablename__ = "curso"
    id_curso = Column(Integer, primary_key=True)
    id_area = Column(Integer, ForeignKey("area.id_area"))
    nombre = Column(String(100))
