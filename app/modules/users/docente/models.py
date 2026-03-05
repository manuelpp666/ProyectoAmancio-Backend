from sqlalchemy import Column, Integer, String, Text, ForeignKey, DECIMAL # <-- Asegúrate de importar DECIMAL
from sqlalchemy.orm import relationship
from app.db.database import Base

class Docente(Base):
    __tablename__ = "docente"

    id_docente = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuario.id_usuario"), unique=True)
    dni = Column(String(8), unique=True, index=True, nullable=False)
    nombres = Column(String(250), nullable=False)
    apellidos = Column(String(250), nullable=False)
    especialidad = Column(String(100))
    descripcion = Column(Text)
    telefono = Column(String(9))
    email = Column(String(100))
    url_perfil = Column(String(255))
    
    sueldo = Column(DECIMAL(10, 2), default=0.00) # <--- NUEVA COLUMNA AGREGADA

    usuario = relationship("Usuario")