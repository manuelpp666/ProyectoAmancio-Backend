from sqlalchemy import Column, Integer, String, Boolean, Date, ForeignKey, CHAR
from sqlalchemy.orm import relationship
from app.db.database import Base

class AnioEscolar(Base):
    __tablename__ = "anio_escolar"
    id_anio_escolar = Column(CHAR(6), primary_key=True)
    fecha_inicio = Column(Date, nullable=False)
    fecha_fin = Column(Date)
    activo = Column(Boolean, default=False)

class Grado(Base):
    __tablename__ = "grado"
    id_grado = Column(Integer, primary_key=True, index=True)
    id_nivel = Column(Integer, ForeignKey("nivel.id_nivel"))
    nombre = Column(String(20), nullable=False)
    orden = Column(Integer, nullable=False)
    
    nivel = relationship("Nivel") # Necesitas definir modelo Nivel
    secciones = relationship("Seccion", back_populates="grado")

class Seccion(Base):
    __tablename__ = "seccion"
    id_seccion = Column(Integer, primary_key=True, index=True)
    id_grado = Column(Integer, ForeignKey("grado.id_grado"))
    nombre = Column(String(5), nullable=False)
    aula = Column(String(20))
    vacantes = Column(Integer, default=30)

    grado = relationship("Grado", back_populates="secciones")

# Define Nivel, Area, Curso de manera similar...