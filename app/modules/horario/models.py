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

class HoraLectiva(Base):
    __tablename__ = "hora_lectiva"
    id_hora = Column(Integer, primary_key=True)
    hora_inicio = Column(Time, nullable=False)
    hora_fin = Column(Time, nullable=False)
    tipo = Column(String(20), default="clase") # clase, receso

class HorarioEscolar(Base):
    __tablename__ = "horario_escolar"
    id_horario = Column(Integer, primary_key=True)
    # En lugar de curso y docente por separado, usamos la carga académica
    id_carga_academica = Column(Integer, ForeignKey("carga_academica.id_carga_academica"))
    id_hora = Column(Integer, ForeignKey("hora_lectiva.id_hora"))
    dia_semana = Column(Enum(DiaSemana), nullable=False) 

    # RELACIÓN CLAVE: Esto arregla el error del JOIN y permite h.carga.curso.nombre
    carga = relationship("CargaAcademica", backref="horarios_asignados")
    bloque_hora = relationship("HoraLectiva")