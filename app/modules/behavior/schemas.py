from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime

class ReporteCreate(BaseModel):
    id_alumno: int
    id_nivel_conducta: int
    descripcion_suceso: str = Field(min_length=10, max_length=1000)

    @field_validator("descripcion_suceso")
    @classmethod
    def limpiar_descripcion(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 10:
            raise ValueError("La descripción debe tener al menos 10 caracteres.")
        return v

class CitaCreate(BaseModel):
    id_alumno: int
    id_familiar: Optional[int] = None
    motivo: str
    fecha_cita: datetime


class CitaResultado(BaseModel):
    """Lo que el psicólogo escribe al cerrar una cita ya atendida.

    Va en el cuerpo de la petición y no en la URL: es un texto largo, y como
    query param se rompería con los saltos de línea y los acentos.
    """
    resultado: str = Field(min_length=10, max_length=1000)