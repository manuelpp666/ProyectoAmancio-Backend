from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from datetime import date
from app.core.util.utils import DniStr # Importante

class UsuarioEnAlumno(BaseModel):
    activo: bool
    username: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class AlumnoBase(BaseModel):
    nombres: str = Field(..., max_length=250)
    apellidos: str = Field(..., max_length=250)
    fecha_nacimiento: Optional[date] = None
    genero: Optional[str] = Field(None, max_length=1)
    direccion: Optional[str] = Field(None, max_length=300)
    enfermedad: Optional[str] = Field(None, max_length=150)
    talla_polo: Optional[str] = Field(None, max_length=5)
    colegio_procedencia: Optional[str] = Field(None, max_length=100)
    id_grado_ingreso: Optional[int] = None
    relacion_fraternal: bool = False
    estado_ingreso: str = 'POSTULANTE'

class AlumnoCreate(AlumnoBase):
    dni: DniStr  # Validación automática aquí
    id_usuario: Optional[int] = None

class AlumnoResponse(AlumnoBase):
    id_alumno: int
    id_usuario: Optional[int] = None
    dni: str # En la respuesta se entrega como string normal
    usuario: Optional[UsuarioEnAlumno] = None 
    motivo_rechazo: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)