from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime

from .constants import PUNTAJE_MAXIMO

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

class ReporteEliminar(BaseModel):
    """Motivo por el que se borra un reporte de conducta.

    Es obligatorio: borrar un reporte le devuelve puntos de conducta al alumno,
    así que tiene que quedar dicho por qué. El mínimo de 10 caracteres es el
    mismo que ya se exige al describir el suceso, para que no valga un "ya".
    """
    motivo: str = Field(min_length=10, max_length=300)

    @field_validator("motivo")
    @classmethod
    def limpiar_motivo(cls, v: str) -> str:
        v = (v or "").strip()
        if len(v) < 10:
            raise ValueError("Explique el motivo con al menos 10 caracteres.")
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

# ---------------------------------------------------------------------------
# Catálogo de faltas (lo edita el administrador)
# ---------------------------------------------------------------------------
#
# Dos niveles, como el Reglamento Interno: el TIPO de falta agrupa
# ("Respeto", "Honradez") y dentro van las faltas concretas con los puntos que
# descuentan. Lo que aquí se guarde es lo que verá el auxiliar al reportar y lo
# que restará de los 20 puntos de conducta del bimestre.


def _limpiar(v: str) -> str:
    v = (v or "").strip()
    if not v:
        raise ValueError("No puede quedar vacío.")
    return v


class TipoFaltaGuardar(BaseModel):
    # 60 es lo que admite la columna. Se corta aquí para que el aviso lo dé la
    # API con un mensaje entendible y no la base con un error de truncado.
    nombre: str = Field(min_length=3, max_length=60)

    @field_validator("nombre")
    @classmethod
    def limpiar_nombre(cls, v: str) -> str:
        return _limpiar(v)


class FaltaGuardar(BaseModel):
    id_tipo_falta: int = Field(gt=0)
    nombre: str = Field(min_length=3, max_length=120)
    # El tope es el propio puntaje de conducta: una falta no puede descontar
    # más de los 20 puntos con los que el alumno empieza el bimestre.
    puntos: int = Field(ge=0, le=PUNTAJE_MAXIMO)
    medida: Optional[str] = Field(None, max_length=60)
    cambio_ie: bool = False
    descripcion: Optional[str] = Field(None, max_length=2000)

    @field_validator("nombre")
    @classmethod
    def limpiar_nombre(cls, v: str) -> str:
        return _limpiar(v)

    @field_validator("medida", "descripcion")
    @classmethod
    def vaciar_si_blanco(cls, v: Optional[str]) -> Optional[str]:
        # Un campo opcional que llega con espacios se guarda como NULL y no
        # como " ": si no, la pantalla enseña una medida que no dice nada.
        v = (v or "").strip()
        return v or None
