"""
Tipos reutilizables para validar datos de personas (DNI, teléfono, correo).

Sobre los campos opcionales: un <input> que el usuario deja en blanco no viaja
como null, viaja como cadena vacía. Si "" se valida como si fuera un valor real,
el formulario entero se rechaza con un 422 por un dato que precisamente se
decidió no llenar. Eso hacía imposible, por ejemplo, editar a un administrador
sin correo: el formulario devolvía "" y la API respondía
"value is not a valid email address".

Por eso los tipos *Opcional convierten "" (o solo espacios) en None ANTES de
validar. Los tipos obligatorios se mantienen estrictos: ahí una cadena vacía sí
es un error.
"""
from typing import Annotated, Optional

from pydantic import AfterValidator, BeforeValidator, EmailStr


def vacio_a_nulo(v):
    """Un campo opcional en blanco significa 'sin dato', no 'dato inválido'."""
    if isinstance(v, str) and not v.strip():
        return None
    return v


# Estas funciones son "reutilizables"
def validar_dni_format(v):
    # None solo llega desde los tipos opcionales; ahí ausencia es válida.
    if v is None:
        return v
    if not v.isdigit() or len(v) != 8:
        raise ValueError('El DNI debe tener exactamente 8 dígitos numéricos')
    return v

def validar_telefono_format(v):
    if v is None:
        return v
    if not v.isdigit() or len(v) != 9:
        raise ValueError('El teléfono debe tener exactamente 9 dígitos numéricos')
    return v


# Creamos "Tipos" reutilizables
DniStr = Annotated[str, AfterValidator(validar_dni_format)]
TelefonoStr = Annotated[str, AfterValidator(validar_telefono_format)]

# Versiones opcionales: el formulario puede mandarlos vacíos y se guardan como
# NULL. Usar estas en vez de Optional[DniStr] / Optional[TelefonoStr] /
# Optional[EmailStr], que rechazan la cadena vacía.
DniOpcional = Annotated[
    Optional[str], BeforeValidator(vacio_a_nulo), AfterValidator(validar_dni_format)
]
TelefonoOpcional = Annotated[
    Optional[str], BeforeValidator(vacio_a_nulo), AfterValidator(validar_telefono_format)
]
EmailOpcional = Annotated[Optional[EmailStr], BeforeValidator(vacio_a_nulo)]
