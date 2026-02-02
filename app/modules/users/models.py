from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.database import Base
import enum

class RolEnum(str, enum.Enum):
    ADMIN = "ADMIN"
    DOCENTE = "DOCENTE"
    ALUMNO = "ALUMNO"
    FAMILIAR = "FAMILIAR"

class Usuario(Base):
    __tablename__ = "usuario"
    id_usuario = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    rol = Column(Enum(RolEnum), nullable=False)
    activo = Column(Boolean, default=True)
    fecha_creacion = Column(DateTime, server_default=func.now())

    alumno = relationship("app.modules.users.alumno.models.Alumno", back_populates="usuario", uselist=False)
    docente = relationship("app.modules.users.docente.models.Docente", back_populates="usuario", uselist=False)
    familiar = relationship("app.modules.users.familiar.models.Familiar", back_populates="usuario", uselist=False)