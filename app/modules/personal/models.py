from sqlalchemy import Column, Integer, String, DECIMAL, ForeignKey
from sqlalchemy.orm import relationship
from app.db.database import Base

class Administrador(Base):
    __tablename__ = "administrador"
    id_admin = Column(Integer, primary_key=True)
    id_usuario = Column(Integer, ForeignKey("usuario.id_usuario"), unique=True)
    dni = Column(String(8), unique=True, nullable=False)
    nombres = Column(String(250), nullable=False)
    apellidos = Column(String(250), nullable=False)
    telefono = Column(String(9))
    email = Column(String(100))
    sueldo = Column(DECIMAL(10, 2), default=0.00)
    usuario = relationship("Usuario")

class Auxiliar(Base):
    __tablename__ = "auxiliar"
    id_auxiliar = Column(Integer, primary_key=True)
    id_usuario = Column(Integer, ForeignKey("usuario.id_usuario"), unique=True)
    dni = Column(String(8), unique=True, nullable=False)
    nombres = Column(String(250), nullable=False)
    apellidos = Column(String(250), nullable=False)
    telefono = Column(String(9))
    email = Column(String(100))
    sueldo = Column(DECIMAL(10, 2), default=0.00)
    usuario = relationship("Usuario")