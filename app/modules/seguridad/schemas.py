# -*- coding: utf-8 -*-
"""
Lo que se acepta en una solicitud de acceso.

Las comprobaciones están aquí y no solo en la pantalla a propósito: el
formulario es público —tiene que serlo, lo usa quien no puede entrar— y
cualquiera puede llamar al endpoint sin pasar por el navegador.

Cada regla responde a una forma concreta de que la solicitud llegue inservible.
Una solicitud con el DNI mal escrito o con un "no puedo entrar" por toda
explicación obliga al administrador a perseguir a la persona para poder
ayudarla, que es justo lo que este formulario venía a evitar.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

# Un DNI peruano son ocho cifras.
DNI_LARGO = 8
# Un móvil peruano son nueve cifras y empieza por 9. Los fijos de Lima son
# siete y empiezan por otra cosa; se aceptan también porque un apoderado mayor
# puede no tener móvil, y dejarle fuera por eso sería absurdo.
TELEFONO_MIN, TELEFONO_MAX = 7, 9

DESCRIPCION_MIN = 20
DESCRIPCION_MAX = 1000

# Solo dígitos, para poder quitar espacios, guiones y el prefijo del país.
_NO_DIGITOS = re.compile(r"\D+")


def _solo_digitos(texto: str) -> str:
    return _NO_DIGITOS.sub("", texto or "")


class SolicitudAccesoCreate(BaseModel):
    dni: str = Field(..., description="Los 8 dígitos del DNI")
    telefono: str = Field(..., description="Teléfono de contacto")
    descripcion: str = Field(..., description="Qué le pasa al intentar entrar")

    @field_validator("dni")
    @classmethod
    def validar_dni(cls, v: str) -> str:
        limpio = _solo_digitos(v)
        if not limpio:
            raise ValueError("Escribe tu DNI.")
        if len(limpio) != DNI_LARGO:
            # Se dice cuántas cifras puso: casi siempre es una de más o una de
            # menos, y así lo ve sin tener que contarlas.
            raise ValueError(
                f"El DNI tiene {DNI_LARGO} cifras y escribiste {len(limpio)}.")
        if limpio == limpio[0] * DNI_LARGO:
            raise ValueError("Ese DNI no es válido: son ocho cifras iguales.")
        if limpio == "12345678":
            raise ValueError("Escribe tu DNI real, no un ejemplo.")
        return limpio

    @field_validator("telefono")
    @classmethod
    def validar_telefono(cls, v: str) -> str:
        limpio = _solo_digitos(v)
        # El prefijo del país sobra: el colegio llama desde Perú.
        if len(limpio) > TELEFONO_MAX and limpio.startswith("51"):
            limpio = limpio[2:]
        if not limpio:
            raise ValueError("Escribe un teléfono donde podamos llamarte.")
        if not (TELEFONO_MIN <= len(limpio) <= TELEFONO_MAX):
            raise ValueError(
                f"El teléfono tiene {len(limpio)} cifras: debe tener entre "
                f"{TELEFONO_MIN} y {TELEFONO_MAX}.")
        if len(limpio) == TELEFONO_MAX and not limpio.startswith("9"):
            raise ValueError("Un celular de nueve cifras empieza por 9.")
        if limpio == limpio[0] * len(limpio):
            raise ValueError("Ese teléfono no es válido: son todas cifras iguales.")
        return limpio

    @field_validator("descripcion")
    @classmethod
    def validar_descripcion(cls, v: str) -> str:
        limpio = " ".join((v or "").split())
        if len(limpio) < DESCRIPCION_MIN:
            raise ValueError(
                f"Cuenta un poco más: hacen falta al menos {DESCRIPCION_MIN} "
                f"caracteres para saber qué te pasa.")
        if len(limpio) > DESCRIPCION_MAX:
            raise ValueError(
                f"La descripción es demasiado larga (máximo "
                f"{DESCRIPCION_MAX} caracteres).")
        # "aaaaaaaaaaaaaaaaaaaaaa" pasa el mínimo y no dice nada. Con tres
        # palabras distintas ya hay algo que leer.
        if len(set(limpio.lower().split())) < 3:
            raise ValueError(
                "Explica el problema con tus palabras: por ejemplo, qué "
                "mensaje te sale al intentar entrar.")
        return limpio


class SolicitudAccesoAtender(BaseModel):
    """Lo que el administrador cambia cuando ya la ha resuelto."""
    estado: str = Field(..., pattern="^(PENDIENTE|ATENDIDA|DESCARTADA)$")
    nota: str | None = Field(None, max_length=300)
