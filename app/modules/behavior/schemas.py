from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ReporteCreate(BaseModel):
    id_alumno: int
    id_docente: int
    id_nivel_conducta: int
    descripcion_suceso: str

class CitaCreate(BaseModel):
    id_alumno: int
    id_familiar: int
    motivo: str
    fecha_cita: datetime