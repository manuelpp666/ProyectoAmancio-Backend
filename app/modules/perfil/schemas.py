from pydantic import BaseModel, EmailStr, Field
from typing import Optional

class ChangePasswordSchema(BaseModel):
    username: str
    current_password: str
    new_password: str = Field(..., min_length=8)


class RegistrarCorreoSchema(BaseModel):
    # EmailStr rechaza direcciones mal escritas antes de guardarlas: un correo
    # con una errata deja al apoderado sin recibir los avisos y nadie se entera.
    email: EmailStr


class EstadoPrimerIngresoResponse(BaseModel):
    debe_cambiar_password: bool
    debe_registrar_correo: bool
    # Para el alumno el correo es el del apoderado, y el texto de la pantalla
    # cambia en consecuencia.
    es_alumno: bool
    email_actual: Optional[str] = None

class ActualizarPerfilAdminSchema(BaseModel):
    telefono: Optional[str] = None
    email: Optional[str] = None
    url_perfil: Optional[str] = None

# --- Perfil del Alumno ---
class ActualizarDireccionSchema(BaseModel):
    direccion: str = Field(..., min_length=3, max_length=300)

class ActualizarMedicosSchema(BaseModel):
    # Permitimos vaciarlo (None / cadena vacía) o registrar la condición
    enfermedad: Optional[str] = Field(None, max_length=150)

class FamiliarCreateSchema(BaseModel):
    nombres: str = Field(..., min_length=2, max_length=250)
    apellidos: str = Field(..., min_length=2, max_length=250)
    dni: str = Field(..., min_length=8, max_length=8)
    telefono: Optional[str] = Field(None, max_length=9)
    email: Optional[str] = Field(None, max_length=150)
    direccion: Optional[str] = Field(None, max_length=300)
    tipo_parentesco: str = Field(..., min_length=2, max_length=50)