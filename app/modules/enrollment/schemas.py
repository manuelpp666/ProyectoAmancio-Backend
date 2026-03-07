from pydantic import BaseModel, ConfigDict
from typing import Optional, Literal
from decimal import Decimal
from datetime import datetime
from pydantic import Field, field_validator

# Importamos el esquema de alumno para anidarlo
from app.modules.users.alumno.schemas import AlumnoResponse
from app.modules.academic.schemas import GradoResponse, SeccionResponse

# --- Exoneracion ---
class ExoneracionBase(BaseModel):
    motivo: str = Field(..., min_length=5, max_length=255)
    concepto_exonerado: str = Field(..., min_length=3, max_length=100)
    porcentaje_descuento: Decimal = Field(
        default=Decimal("100.0"), 
        ge=Decimal("0.0"), 
        le=Decimal("100.0"),
        decimal_places=2
    )
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
    tipo_matricula: Literal["REGULAR", "BECADO"] = "REGULAR"

class MatriculaCreate(MatriculaBase):
    pass

class MatriculaResponse(MatriculaBase):
    id_matricula: int
    fecha_matricula: datetime
    estado: Literal["MATRICULADO", "RETIRADO"] = "MATRICULADO"
    
    # --- IMPORTANTE: Estos campos anidados son los que faltaban ---
    alumno: Optional[AlumnoResponse] = None
    grado: Optional[GradoResponse] = None
    seccion: Optional[SeccionResponse] = None
    # --------------------------------------------------------------

    model_config = ConfigDict(from_attributes=True)