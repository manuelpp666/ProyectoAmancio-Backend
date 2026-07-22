from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import Optional
from app.core.util.utils import DniStr, TelefonoStr

class FamiliarBase(BaseModel):
    nombres: str = Field(..., max_length=250)
    apellidos: str = Field(..., max_length=250)
    email: Optional[EmailStr] = None
    direccion: Optional[str] = Field(None, max_length=300)
    tipo_parentesco: Optional[str] = Field(None, max_length=50)

class FamiliarCreate(FamiliarBase):
    dni: DniStr
    telefono: TelefonoStr

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