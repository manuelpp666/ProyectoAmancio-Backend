from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional
from datetime import date
from app.core.util.utils import DniStr # Importante

class UsuarioEnAlumno(BaseModel):
    activo: bool
    username: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

# 1. BASE: Tolerante para leer datos de la Base de Datos sin explotar
class AlumnoBase(BaseModel):
    nombres: str
    apellidos: str
    fecha_nacimiento: Optional[date] = None
    genero: Optional[str] = None
    direccion: Optional[str] = None
    enfermedad: Optional[str] = None
    talla_polo: Optional[str] = None
    colegio_procedencia: Optional[str] = None
    id_grado_ingreso: Optional[int] = None
    relacion_fraternal: Optional[bool] = False
    estado_ingreso: Optional[str] = 'POSTULANTE'

# 2. CREATE: Estricto SOLO cuando se registra un alumno nuevo desde la web
class AlumnoCreate(AlumnoBase):
    dni: DniStr  # Validación automática aquí
    id_usuario: Optional[int] = None

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

class GradoEnAlumno(BaseModel):
    id_grado: int
    nombre: str
    model_config = ConfigDict(from_attributes=True)

# 3. RESPONSE: Lo que se envía al Frontend
class AlumnoResponse(AlumnoBase):
    id_alumno: int
    id_usuario: Optional[int] = None
    dni: str 
    usuario: Optional[UsuarioEnAlumno] = None 
    motivo_rechazo: Optional[str] = None
    grado_ingreso: Optional[GradoEnAlumno] = None
    model_config = ConfigDict(from_attributes=True)