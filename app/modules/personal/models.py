from sqlalchemy import Column, Integer, String, DECIMAL, ForeignKey, JSON
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
    url_perfil = Column(String(255), nullable=True)
    sueldo = Column(DECIMAL(10, 2), default=0.00)
    permisos = Column(JSON, nullable=True)
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

class Psicologo(Base):
    __tablename__ = "psicologo"
    id_psicologo = Column(Integer, primary_key=True)
    id_usuario = Column(Integer, ForeignKey("usuario.id_usuario"), unique=True)
    dni = Column(String(8), unique=True, nullable=False)
    nombres = Column(String(250), nullable=False)
    apellidos = Column(String(250), nullable=False)
    telefono = Column(String(9))
    email = Column(String(100))
    sueldo = Column(DECIMAL(10, 2), default=0.00)
    usuario = relationship("Usuario")