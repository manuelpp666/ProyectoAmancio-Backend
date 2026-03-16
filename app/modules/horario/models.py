from sqlalchemy import Column, Integer, String, ForeignKey, Enum, Time, CHAR
from sqlalchemy.orm import relationship
from app.db.database import Base
import enum

class DiaSemana(enum.Enum):
    Lunes = "Lunes"
    Martes = "Martes"
    Miércoles = "Miércoles"
    Jueves = "Jueves"
    Viernes = "Viernes"
    Sábado = "Sábado"

# Conservamos la tabla para que no de error si otros módulos la llaman, pero ya no la usa HorarioEscolar
class HoraLectiva(Base):
    __tablename__ = "hora_lectiva"
    id_hora = Column(Integer, primary_key=True)
    hora_inicio = Column(Time, nullable=False)
    hora_fin = Column(Time, nullable=False)
    tipo = Column(String(20), default="clase")

class HorarioEscolar(Base):
    __tablename__ = "horario_escolar"
    id_horario = Column(Integer, primary_key=True)
    id_carga_academica = Column(Integer, ForeignKey("carga_academica.id_carga_academica"))
    dia_semana = Column(Enum(DiaSemana), nullable=False) 
    
    # --- AHORA USA HORAS REALES EN VEZ DE ID ---
    hora_inicio = Column(Time, nullable=False)
    hora_fin = Column(Time, nullable=False)

    carga = relationship("CargaAcademica", backref="horarios_asignados")