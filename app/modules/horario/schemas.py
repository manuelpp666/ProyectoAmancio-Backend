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
    id_hora: int
    dia_semana: Literal["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

class HorarioResponse(BaseModel):
    id_horario: int
    id_hora: int
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
    horas_semanales: int = Field(default=0, ge=0, le=100)
    
    model_config = ConfigDict(from_attributes=True)