from sqlalchemy import Column, Integer, String, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.db.database import Base


class Docente(Base):
    __tablename__ = "docente"

    id_docente = Column(Integer, primary_key=True, index=True)
    # Llave foránea que conecta con la tabla usuario
    id_usuario = Column(Integer, ForeignKey("usuario.id_usuario"), nullable=False, unique=True)
    
    dni = Column(String(8), nullable=False, unique=True)
    nombres = Column(String(250), nullable=False)
    apellidos = Column(String(250), nullable=False)
    especialidad = Column(String(100), nullable=True)
    descripcion = Column(Text, nullable=True) 
    url_perfil = Column(String(255), nullable=True)
    telefono = Column(String(9))
    email = Column(String(100))

    #Relación para acceder a los datos de usuario desde el docente
    # docente.usuario.username
    usuario = relationship("Usuario")