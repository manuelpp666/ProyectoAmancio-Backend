# -*- coding: utf-8 -*-
"""
Lo que acepta cada paso de la recuperación.

Las reglas viven aquí y no solo en la pantalla: los endpoints son públicos y
cualquiera puede llamarlos sin pasar por el navegador.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator, model_validator

from app.modules.seguridad.schemas import limpiar_dni

ROLES = ("ADMIN", "DOCENTE", "ALUMNO", "AUXILIAR", "PSICOLOGO")

PASSWORD_MIN = 8
# bcrypt solo mira los primeros 72 bytes, y la versión instalada rechaza los
# que pasan de ahí. Se cuenta en bytes porque una tilde ocupa dos.
PASSWORD_MAX_BYTES = 72

_CODIGO = re.compile(r"^\d{6}$")


def _rol(v: str) -> str:
    rol = (v or "").strip().upper()
    if rol not in ROLES:
        raise ValueError("Elige una de las cuentas de la lista.")
    return rol


class ConsultaDni(BaseModel):
    dni: str

    @field_validator("dni")
    @classmethod
    def validar_dni(cls, v: str) -> str:
        return limpiar_dni(v)


class CuentaElegida(ConsultaDni):
    rol: str

    @field_validator("rol")
    @classmethod
    def validar_rol(cls, v: str) -> str:
        return _rol(v)


class VerificarCodigo(CuentaElegida):
    codigo: str

    @field_validator("codigo")
    @classmethod
    def validar_codigo(cls, v: str) -> str:
        limpio = re.sub(r"\s+", "", v or "")
        if not _CODIGO.match(limpio):
            raise ValueError("El código son 6 cifras.")
        return limpio


class CambiarPassword(CuentaElegida):
    token: str = Field(..., min_length=20, max_length=200)
    nueva: str
    confirmacion: str

    @field_validator("nueva")
    @classmethod
    def validar_nueva(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Escribe tu nueva contraseña.")
        if v != v.strip():
            raise ValueError("La contraseña no puede empezar ni terminar con espacios.")
        if len(v) < PASSWORD_MIN:
            raise ValueError(f"La contraseña debe tener al menos {PASSWORD_MIN} caracteres.")
        if len(v.encode("utf-8")) > PASSWORD_MAX_BYTES:
            raise ValueError("La contraseña es demasiado larga (máximo 72 caracteres).")
        return v

    @model_validator(mode="after")
    def coinciden(self):
        if self.nueva != self.confirmacion:
            raise ValueError("Las contraseñas no coinciden.")
        if self.nueva == self.dni:
            raise ValueError("La nueva contraseña no puede ser tu DNI. Elige una distinta.")
        return self
