from pydantic import BaseModel
from typing import Optional, List
from datetime import date

# --- Año Escolar ---
class AnioEscolarCreate(BaseModel):
    id_anio_escolar: str
    fecha_inicio: date
    fecha_fin: date
    activo: bool

class AnioEscolarResponse(AnioEscolarCreate):
    class Config: from_attributes = True

# --- Seccion ---
class SeccionBase(BaseModel):
    nombre: str
    aula: str
    vacantes: int
    id_grado: int

class SeccionCreate(SeccionBase): pass

class SeccionResponse(SeccionBase):
    id_seccion: int
    class Config: from_attributes = True