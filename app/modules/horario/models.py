from sqlalchemy import (
    Column, Integer, String, ForeignKey, Enum, Time, CHAR, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.db.database import Base
from datetime import time
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


# ---------------------------------------------------------------------------
# CONFIGURACIÓN DE LA REJILLA DE HORARIOS
#
# Antes, la duración del bloque (50 min) y los recesos (10:50 y 17:30) estaban
# escritos a mano en el frontend, en dos sitios distintos: el constructor del
# panel y la tabla que ven docentes y alumnos. Cambiarlos obligaba a tocar
# código, y era fácil que los dos se desincronizaran.
#
# Ahora la rejilla se calcula en el backend a partir de estas dos tablas, así
# que el panel, el horario del docente, el del alumno y el PDF siempre pintan
# exactamente los mismos bloques.
# ---------------------------------------------------------------------------

# Ámbitos válidos. Primaria y secundaria existen en las dos modalidades;
# la Pre Academia solo tiene sentido en verano.
AMBITOS_REGULAR = ("PRIMARIA", "SECUNDARIA")
AMBITOS_VERANO = ("PRIMARIA", "SECUNDARIA", "PRE_ACADEMIA")
MODALIDADES = ("REGULAR", "VERANO")


class ConfiguracionHorario(Base):
    """Cómo se construye la rejilla de un ámbito (nivel) en una modalidad."""
    __tablename__ = "configuracion_horario"

    id_configuracion = Column(Integer, primary_key=True)
    # PRIMARIA / SECUNDARIA / PRE_ACADEMIA
    ambito = Column(String(20), nullable=False)
    # REGULAR / VERANO
    modalidad = Column(String(20), nullable=False, default="REGULAR")

    # Minutos que dura cada bloque de clase
    duracion_bloque = Column(Integer, nullable=False, default=45)
    # Principio y fin de la jornada
    hora_inicio = Column(Time, nullable=False, default=time(7, 30))
    hora_fin = Column(Time, nullable=False, default=time(13, 30))

    __table_args__ = (
        UniqueConstraint("ambito", "modalidad", name="uq_config_ambito_modalidad"),
    )

    recesos = relationship(
        "RecesoHorario",
        back_populates="configuracion",
        cascade="all, delete-orphan",
        order_by="RecesoHorario.hora_inicio",
    )


class RecesoHorario(Base):
    """Un descanso dentro de la jornada: dónde empieza y cuánto dura.

    Se guardan como filas independientes para que se puedan añadir, mover o
    quitar tantos como haga falta, sin tocar código.
    """
    __tablename__ = "receso_horario"

    id_receso = Column(Integer, primary_key=True)
    id_configuracion = Column(
        Integer,
        ForeignKey("configuracion_horario.id_configuracion", ondelete="CASCADE"),
        nullable=False,
    )
    nombre = Column(String(40), nullable=False, default="Recreo")
    hora_inicio = Column(Time, nullable=False)
    duracion = Column(Integer, nullable=False)  # minutos

    configuracion = relationship("ConfiguracionHorario", back_populates="recesos")
