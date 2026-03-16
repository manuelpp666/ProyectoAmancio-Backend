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