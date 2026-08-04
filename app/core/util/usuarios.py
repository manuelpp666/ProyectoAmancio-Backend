"""
Nomenclatura de nombres de usuario.

El sistema guarda un único rol por usuario (usuario.rol es un ENUM simple),
pero en el colegio hay personas que cumplen dos funciones: docentes que además
son auxiliares, o el director que también dicta un curso. Con el DNI como
username esa persona solo podía existir una vez.

La solución es prefijar el username con el rol, de modo que la misma persona
puede tener una cuenta por cada función sin chocar con la restricción UNIQUE:

    DOC-16793446   ->  Tomás Serquén como docente
    ADM-16793446   ->  Tomás Serquén como director

Cada cuenta entra a su propio panel. El DNI sigue siendo el mismo en la ficha
de cada rol, así que la persona se sigue identificando por DNI en los listados.
"""

PREFIJO_POR_ROL = {
    "ADMIN": "ADM",
    "DOCENTE": "DOC",
    "ALUMNO": "ALU",
    "AUXILIAR": "AUX",
    "PSICOLOGO": "PSI",
}

SEPARADOR = "-"


def generar_username(dni: str, rol: str) -> str:
    """Devuelve el username normalizado para un DNI y un rol. Ej: 'DOC-74634911'."""
    dni_limpio = (dni or "").strip()
    prefijo = PREFIJO_POR_ROL.get((rol or "").strip().upper())
    if not prefijo:
        raise ValueError(f"Rol desconocido para generar el username: {rol!r}")
    return f"{prefijo}{SEPARADOR}{dni_limpio}"


def extraer_dni(username: str) -> str:
    """DNI contenido en un username con prefijo. Tolera usernames antiguos sin él."""
    if not username:
        return ""
    if SEPARADOR in username:
        prefijo, _, resto = username.partition(SEPARADOR)
        if prefijo.upper() in PREFIJO_POR_ROL.values():
            return resto
    return username


def extraer_rol(username: str) -> str | None:
    """Rol deducido del prefijo del username, o None si no lo lleva."""
    if not username or SEPARADOR not in username:
        return None
    prefijo = username.partition(SEPARADOR)[0].upper()
    for rol, p in PREFIJO_POR_ROL.items():
        if p == prefijo:
            return rol
    return None
