from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.db.database import Base

class Familiar(Base):
    __tablename__ = "familiar"
    id_familiar = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuario.id_usuario"), unique=True)
    dni = Column(String(8), unique=True)
    nombres = Column(String(250))
    apellidos = Column(String(250))
    telefono = Column(String(9))
    email = Column(String(150))
    direccion = Column(String(300))
    tipo_parentesco = Column(String(50))

    usuario = relationship("Usuario")