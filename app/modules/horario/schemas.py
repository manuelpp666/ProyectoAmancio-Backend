from pydantic import BaseModel, ConfigDict
from datetime import time
from typing import Optional, List

# --- Hora Lectiva (Los bloques de tiempo) ---
class HoraLectivaBase(BaseModel):
    hora_inicio: time
    hora_fin: time
    tipo: str

class HoraLectivaResponse(HoraLectivaBase):
    id_hora: int
    model_config = ConfigDict(from_attributes=True)

# --- Horario Escolar (Asignación) ---
class HorarioCreate(BaseModel):
    id_carga_academica: int
    id_hora: int
    dia_semana: str

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
    curso_nombre: str
    docente_nombre: str
    horas_semanales: int = 0
    
    model_config = ConfigDict(from_attributes=True)