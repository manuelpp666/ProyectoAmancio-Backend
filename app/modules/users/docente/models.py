from sqlalchemy import Column, Integer, String
from app.db.database import Base


class Docente(Base):
    __tablename__ = "docente"

    id_docente = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, nullable=True)
    dni = Column(String(8), nullable=False, unique=True)
    nombres = Column(String(250), nullable=False)
    apellidos = Column(String(250), nullable=False)
    especialidad = Column(String(100), nullable=True)
    telefono = Column(String(9))
    email = Column(String(100))