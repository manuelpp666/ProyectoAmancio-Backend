from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.db.database import Base

class Familiar(Base):
    __tablename__ = "familiar"
    id_familiar = Column(Integer, primary_key=True, index=True)
    # Eliminado el id_usuario
    dni = Column(String(8), unique=True)
    nombres = Column(String(250))
    apellidos = Column(String(250))
    telefono = Column(String(9))
    email = Column(String(150))
    direccion = Column(String(300))
    tipo_parentesco = Column(String(50))
     
    alumnos_rel = relationship("RelacionFamiliar", back_populates="familiar")