from pydantic import BaseModel
from typing import Optional
from decimal import Decimal
from datetime import datetime

# Importamos el esquema de alumno para anidarlo
from app.modules.users.alumno.schemas import AlumnoResponse
from app.modules.academic.schemas import GradoResponse, SeccionResponse

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

class MatriculaBase(BaseModel):
    id_anio_escolar: str
    id_alumno: int
    id_grado: int
    id_seccion: Optional[int] = None
    tipo_matricula: str = "REGULAR"

class MatriculaCreate(MatriculaBase):
    pass

class MatriculaResponse(MatriculaBase):
    id_matricula: int
    fecha_matricula: datetime
    estado: str
    
    # --- IMPORTANTE: Estos campos anidados son los que faltaban ---
    alumno: Optional[AlumnoResponse] = None
    grado: Optional[GradoResponse] = None
    seccion: Optional[SeccionResponse] = None
    # --------------------------------------------------------------

    class Config:
        from_attributes = True