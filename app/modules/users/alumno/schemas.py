from pydantic import BaseModel
from typing import Optional
from datetime import date

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
    id_usuario: Optional[int] = None # Se puede crear sin usuario al inicio (postulante)

class AlumnoResponse(AlumnoBase):
    id_alumno: int
    id_usuario: Optional[int] = None
    
    class Config:
        from_attributes = True