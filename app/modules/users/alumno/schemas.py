from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, Literal
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
    genero: Optional[Literal["M", "F", "X"]] = None
    direccion: Optional[str] = Field(None, max_length=300)
    enfermedad: Optional[str] = Field(None, max_length=150)
    talla_polo: Optional[str] = Field(None, max_length=5)
    colegio_procedencia: Optional[str] = Field(None, max_length=100)
    id_grado_ingreso: Optional[int] = None
    relacion_fraternal: bool = False
    estado_ingreso: str = 'POSTULANTE'
    @field_validator('fecha_nacimiento')
    @classmethod
    def validar_edad(cls, v):
        if v:
            hoy = date.today()
            edad = hoy.year - v.year - ((hoy.month, hoy.day) < (v.month, v.day))
            if edad < 3: # Edad mínima para inicial
                raise ValueError("El alumno debe tener al menos 3 años.")
            if edad > 20: # Límite razonable para educación escolar
                raise ValueError("La edad del alumno excede el límite escolar permitido.")
        return v

class AlumnoCreate(AlumnoBase):
    dni: DniStr  # Validación automática aquí
    id_usuario: Optional[int] = None

class GradoEnAlumno(BaseModel):
    id_grado: int
    nombre: str
    # Si quieres incluir el nivel (Primaria/Secundaria)
    # nivel: Optional[dict] = None 
    model_config = ConfigDict(from_attributes=True)

class AlumnoResponse(AlumnoBase):
    id_alumno: int
    id_usuario: Optional[int] = None
    dni: str # En la respuesta se entrega como string normal
    usuario: Optional[UsuarioEnAlumno] = None 
    motivo_rechazo: Optional[str] = Field(None, max_length=200)
    grado_ingreso: Optional[GradoEnAlumno] = None
    model_config = ConfigDict(from_attributes=True)