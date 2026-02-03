from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import date

# Esquema auxiliar para la relación (opcional, igual que en Docente)
class UsuarioEnAlumno(BaseModel):
    activo: bool
    # Puedes agregar username u otros campos aquí
    model_config = ConfigDict(from_attributes=True)

class AlumnoBase(BaseModel):
    dni: str
    nombres: str
    apellidos: str
    fecha_nacimiento: Optional[date] = None
    genero: Optional[str] = None
    direccion: Optional[str] = None
    enfermedad: Optional[str] = None
    talla_polo: Optional[str] = None
    colegio_procedencia: Optional[str] = None
    relacion_fraternal: bool = False
    estado_ingreso: str = 'POSTULANTE'

class AlumnoCreate(AlumnoBase):
    id_usuario: Optional[int] = None

class AlumnoResponse(AlumnoBase):
    id_alumno: int
    id_usuario: Optional[int] = None
    
    # IMPORTANTE: Agregar la relación si quieres ver datos del usuario
    usuario: Optional[UsuarioEnAlumno] = None 

    # Usar model_config para Pydantic V2
    model_config = ConfigDict(from_attributes=True)