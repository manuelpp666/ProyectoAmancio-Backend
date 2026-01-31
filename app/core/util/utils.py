from pydantic import field_validator
from typing import Annotated
from pydantic import AfterValidator

# Estas funciones son "reutilizables"
def validar_dni_format(v):
    if not v.isdigit() or len(v) != 8:
        raise ValueError('El DNI debe tener exactamente 8 dígitos numéricos')
    return v

def validar_telefono_format(v):
    if not v.isdigit() or len(v) != 9:
        raise ValueError('El teléfono debe tener exactamente 9 dígitos numéricos')
    return v


# Creamos "Tipos" reutilizables
DniStr = Annotated[str, AfterValidator(validar_dni_format)]
TelefonoStr = Annotated[str, AfterValidator(validar_telefono_format)]