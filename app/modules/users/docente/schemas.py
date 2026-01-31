from pydantic import BaseModel, EmailStr, Field, ConfigDict
from app.core.util.utils import DniStr, TelefonoStr


class DocenteBase(BaseModel):
    nombres: str = Field(..., max_length=250)
    apellidos: str = Field(..., max_length=250)
    especialidad: str | None = Field(default=None, max_length=100)
    email: EmailStr
    id_usuario: int | None = None

class DocenteCreate(DocenteBase):
    # Ya no necesitas las líneas de validator(...)
    # Al usar DniStr, la validación ocurre automáticamente
    dni: DniStr
    telefono: TelefonoStr

class DocenteResponse(DocenteBase):
    id_docente: int
    dni: str
    telefono: str

    # Pydantic V2 usa model_config en lugar de class Config
    model_config = ConfigDict(from_attributes=True)
