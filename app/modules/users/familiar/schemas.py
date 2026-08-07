from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from app.core.util.utils import DniStr, TelefonoStr, EmailOpcional

class FamiliarBase(BaseModel):
    nombres: str = Field(..., max_length=250)
    apellidos: str = Field(..., max_length=250)
    # El formulario manda "" cuando el apoderado no da correo.
    email: EmailOpcional = None
    direccion: Optional[str] = Field(None, max_length=300)

class FamiliarCreate(FamiliarBase):
    dni: DniStr
    telefono: TelefonoStr
    # El parentesco es un dato de entrada que se guarda en relacion_familiar,
    # no en la tabla familiar (ver models.Familiar).
    tipo_parentesco: Optional[str] = Field(None, max_length=50)

class FamiliarAlumnoCreate(FamiliarCreate):
    """Familiar vinculado a un alumno: el parentesco es obligatorio."""
    tipo_parentesco: str = Field(..., min_length=2, max_length=50)

class FamiliarUpdate(FamiliarBase):
    """Edición de los datos de un familiar ya vinculado a un alumno."""
    dni: DniStr
    telefono: TelefonoStr
    tipo_parentesco: str = Field(..., min_length=2, max_length=50)

class FamiliarResponse(FamiliarBase):
    id_familiar: int
    dni: str
    telefono: str
    model_config = ConfigDict(from_attributes=True)