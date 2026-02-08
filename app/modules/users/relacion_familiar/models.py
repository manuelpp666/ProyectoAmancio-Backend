from sqlalchemy import Column, Integer, String, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.db.database import Base

class RelacionFamiliar(Base):
    __tablename__ = "relacion_familiar"
    id_relacion_familiar = Column(Integer, primary_key=True, index=True)
    id_alumno = Column(Integer, ForeignKey("alumno.id_alumno"))
    id_familiar = Column(Integer, ForeignKey("familiar.id_familiar"))
    tipo_parentesco = Column(String(50))

    # Relaciones para acceder fácilmente a los objetos
    alumno = relationship("Alumno", back_populates="familiares_rel")
    familiar = relationship("Familiar", back_populates="alumnos_rel")