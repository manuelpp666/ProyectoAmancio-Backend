from sqlalchemy import Column, Integer, String, Enum, Boolean, DateTime
from sqlalchemy.sql import func
from app.db.database import Base

class Usuario(Base):
    __tablename__ = "usuario"
    id_usuario = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    rol = Column(Enum('ADMIN', 'DOCENTE', 'ALUMNO', 'FAMILIAR'), nullable=False)
    activo = Column(Boolean, default=1)
    fecha_creacion = Column(DateTime, server_default=func.now())