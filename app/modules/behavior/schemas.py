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

class ReporteUpdate(BaseModel):
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


class NotaConductaUpdate(BaseModel):
    id_matricula: int
    bimestre: int = Field(ge=1, le=4)
    nota: float = Field(ge=0, le=20)
    forzar: bool = False


class NotaConductaItem(BaseModel):
    id_matricula: int
    id_alumno: int
    dni: str
    alumno: str
    nivel: str
    grado: str
    id_grado: int
    seccion: str
    id_seccion: int
    total_reportes: int
    puntos_descontados: int
    nota_calculada: int
    nota_manual: Optional[float] = None
    nota_final: float
    origen: str
    es_modificado: bool
    cuadra_con_calculo: bool


class RespuestaListaConducta(BaseModel):
    anio: str
    bimestre: int
    total: int
    pagina: int
    por_pagina: int
    alumnos: list[NotaConductaItem]