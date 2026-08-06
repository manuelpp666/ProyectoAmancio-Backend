"""
Catálogo de permisos del panel de administración (lado servidor).

Es el espejo de ProyectoAmancio/src/config/permisos.ts: la misma estructura de
apartado → pestaña → subpestaña. Si se añade una pestaña en el panel hay que
añadirla en los dos sitios.

Aquí se usa para dos cosas:
  * darle todos los permisos a un administrador nuevo (por defecto entra con
    acceso completo y el director le va cerrando lo que no le toque);
  * completar los permisos guardados de antes con las pestañas nuevas.
"""

# Cada entrada es una clave; si tiene hijos, es un diccionario anidado.
CATALOGO = {
    "panel_control": True,
    "gestion_estudiantes": {
        "estudiantes": True,
        "postulantes": True,
        "renovaciones": True,
        "verano": True,
    },
    "gestion_personal": {
        "admin": True,
        "docente": True,
        "auxiliar": True,
        "psicologo": True,
    },
    "tramites_finanzas": {
        "config": True,
        "solicitudes": True,
        "tipos_pagos": True,
        "recaudacion": True,
    },
    "academico": {
        "estructura": True,
        "horarios": True,
        "docentes": True,
        "estudiantes": True,
        "cursos": True,
    },
    "contenido_web": {
        "info_general": {
            "inicio": True,
            "login": True,
            "nosotros": True,
            "docentes": True,
            "calendario": True,
            "noticias": True,
            "admision": True,
            "footer": True,
        },
        "noticias": True,
        "calendario": True,
    },
    "chatbot": True,
    "mensajeria": True,
    "seguridad": True,
}


def _copiar(plantilla, valor: bool):
    """Reproduce la forma del catálogo con todas sus hojas en `valor`."""
    if isinstance(plantilla, dict):
        return {k: _copiar(v, valor) for k, v in plantilla.items()}
    return valor


def permisos_completos() -> dict:
    """Todo activado: lo que recibe un administrador recién creado."""
    return _copiar(CATALOGO, True)


def normalizar(permisos, plantilla=None) -> dict:
    """
    Completa unos permisos guardados con el catálogo actual.

    Lo ya decidido se respeta; lo que nunca se configuró se da por activado,
    para que una pestaña nueva no deje fuera a quien tenía permisos de antes.
    Una rama guardada como booleano se propaga a todos sus hijos.
    """
    plantilla = CATALOGO if plantilla is None else plantilla
    guardado = permisos if isinstance(permisos, dict) else {}
    todo = guardado.get("all") is True

    salida = {}
    for clave, sub in plantilla.items():
        valor = True if todo else guardado.get(clave)

        if not isinstance(sub, dict):
            salida[clave] = True if valor is None else bool(valor)
            continue

        if valor is None or valor is True:
            salida[clave] = _copiar(sub, True)
        elif valor is False:
            salida[clave] = _copiar(sub, False)
        else:
            salida[clave] = normalizar(valor, sub)
    return salida
