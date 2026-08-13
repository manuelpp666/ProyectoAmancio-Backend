from pydantic import BaseModel, ConfigDict,Field, model_validator, field_validator
from datetime import time
from typing import Optional, List, Literal

# --- Hora Lectiva (Los bloques de tiempo) ---
class HoraLectivaBase(BaseModel):
    hora_inicio: time
    hora_fin: time
    tipo: Literal["clase", "receso"] = "clase"
    @model_validator(mode='after')
    def validar_orden_tiempo(self) -> 'HoraLectivaBase':
        if self.hora_fin <= self.hora_inicio:
            raise ValueError("La hora de fin debe ser posterior a la hora de inicio")
        return self

class HoraLectivaResponse(HoraLectivaBase):
    id_hora: int
    model_config = ConfigDict(from_attributes=True)

# --- Horario Escolar (Asignación) ---
class HorarioCreate(BaseModel):
    id_carga_academica: int
    # ELIMINADO id_hora y reemplazado por horas dinámicas
    dia_semana: Literal["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    hora_inicio: str 
    hora_fin: str

class HorarioResponse(BaseModel):
    id_horario: int
    # ELIMINADO id_hora y reemplazado por horas dinámicas
    hora_inicio: str
    hora_fin: str
    dia_semana: str
    id_carga_academica: int
    
    # Estos campos son útiles para que el frontend pinte los cuadros azules/rojos
    curso_nombre: Optional[str] = None
    docente_nombre: Optional[str] = None
    seccion_nombre: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

# --- Schema para el Sidebar de Materias ---
class MateriaDisponibleResponse(BaseModel):
    id_carga_academica: int
    curso_nombre: str = Field(..., min_length=2, max_length=100)
    docente_nombre: str = Field(..., min_length=2, max_length=250)

    # CAMBIAMOS horas_semanales por minutos_semanales Y AÑADIMOS minutos_asignados respetando tus validaciones
    minutos_semanales: int = Field(default=0, ge=0)
    minutos_asignados: int = Field(default=0, ge=0)

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# CONFIGURACIÓN DE LA REJILLA
# ---------------------------------------------------------------------------
Ambito = Literal["PRIMARIA", "SECUNDARIA", "PRE_ACADEMIA"]
Modalidad = Literal["REGULAR", "VERANO"]


class RecesoBase(BaseModel):
    nombre: str = Field(default="Recreo", min_length=1, max_length=40)
    hora_inicio: str = Field(..., pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    duracion: int = Field(..., ge=5, le=180, description="Minutos que dura el receso")


class RecesoResponse(RecesoBase):
    id_receso: int
    model_config = ConfigDict(from_attributes=True)


class ConfiguracionUpdate(BaseModel):
    """Solo la jornada y la duración del bloque; los recesos van aparte."""
    duracion_bloque: int = Field(..., ge=10, le=240)
    hora_inicio: str = Field(..., pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    hora_fin: str = Field(..., pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    # Si el cambio deja clases en horas que dejan de existir, el servidor
    # responde 409 en vez de guardar. El panel pregunta y reenvía esto en true.
    confirmar: bool = False

    @model_validator(mode="after")
    def validar_jornada(self) -> "ConfiguracionUpdate":
        if self.hora_fin <= self.hora_inicio:
            raise ValueError("La jornada debe terminar después de empezar")
        inicio_min = int(self.hora_inicio[:2]) * 60 + int(self.hora_inicio[3:])
        fin_min = int(self.hora_fin[:2]) * 60 + int(self.hora_fin[3:])
        if fin_min - inicio_min < self.duracion_bloque:
            raise ValueError(
                "La jornada es más corta que un bloque: no cabría ninguna clase"
            )
        return self


class BloqueResponse(BaseModel):
    """Una fila de la rejilla, ya calculada."""
    hora_inicio: str
    hora_fin: str
    tipo: Literal["clase", "receso"]
    duracion: int
    nombre: Optional[str] = None  # solo para los recesos


class ConfiguracionResponse(BaseModel):
    id_configuracion: int
    ambito: Ambito
    modalidad: Modalidad
    duracion_bloque: int
    hora_inicio: str
    hora_fin: str
    recesos: List[RecesoResponse] = []
    # La rejilla resultante, para previsualizarla sin recalcular en el cliente
    bloques: List[BloqueResponse] = []

    model_config = ConfigDict(from_attributes=True)