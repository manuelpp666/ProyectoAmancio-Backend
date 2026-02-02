from pydantic import BaseModel
from typing import Optional
from decimal import Decimal
from datetime import datetime

# --- Exoneracion ---
class ExoneracionBase(BaseModel):
    motivo: str
    concepto_exonerado: str
    porcentaje_descuento: Decimal = Decimal(100.0)
    activo: bool = True

class ExoneracionCreate(ExoneracionBase):
    id_matricula: int

class ExoneracionResponse(ExoneracionBase):
    id_exoneracion: int
    fecha_aprobacion: datetime
    class Config: from_attributes = True

# --- Matricula ---
class MatriculaBase(BaseModel):
    id_anio_escolar: str
    id_alumno: int
    id_seccion: int
    tipo_matricula: str = 'REGULAR'

class MatriculaCreate(MatriculaBase):
    pass

class MatriculaResponse(MatriculaBase):
    id_matricula: int
    fecha_matricula: datetime
    estado: str
    class Config: from_attributes = True