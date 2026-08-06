"""
Estados por los que pasa un alumno (`alumno.estado_ingreso`).

Existe este archivo porque el estado se venía escribiendo a mano en cada sitio,
con dos problemas que se colaron sin que nadie los viera:

  * Las consultas comparaban en minúscula ("postulante") contra datos guardados
    en mayúscula. Funcionaba solo porque MySQL, con la intercalación actual, no
    distingue mayúsculas; en PostgreSQL o con otra intercalación, la pestaña de
    Solicitudes de Admisión se habría quedado vacía sin dar ningún error.
  * La carga inicial escribió "ACEPTADO", un valor que no usaba ninguna otra
    parte del sistema, así que los alumnos no encajaban en ninguna condición.

Regla: todo lo que se guarde pasa por `normalizar()`, y las comparaciones usan
estas constantes. Nunca literales sueltos.
"""

POSTULANTE = "POSTULANTE"   # Envió su solicitud y espera respuesta
ADMITIDO = "ADMITIDO"       # Aceptado, aún sin matrícula
ESTUDIANTE = "ESTUDIANTE"   # Matriculado y cursando
RETIRADO = "RETIRADO"       # Dejó el colegio
RECHAZADO = "RECHAZADO"     # Solicitud denegada

ESTADOS = (POSTULANTE, ADMITIDO, ESTUDIANTE, RETIRADO, RECHAZADO)

# Alumnos que ya forman parte del colegio
ACTIVOS = (ADMITIDO, ESTUDIANTE)

# Nombres antiguos que pudieran quedar en la base, y su equivalente actual.
# "ACEPTADO" lo introdujo la carga inicial de 2026 y no significaba nada para
# el resto del sistema; equivale a un alumno ya matriculado.
EQUIVALENCIAS = {
    "ACEPTADO": ESTUDIANTE,
    "ACTIVO": ESTUDIANTE,
    "ALUMNO": ESTUDIANTE,
}


def normalizar(valor):
    """
    Devuelve el estado canónico, o None si no se reconoce.

    Acepta cualquier combinación de mayúsculas y espacios, para que un valor
    escrito a mano desde phpMyAdmin no rompa nada.
    """
    if not valor:
        return None
    limpio = str(valor).strip().upper()
    limpio = EQUIVALENCIAS.get(limpio, limpio)
    return limpio if limpio in ESTADOS else None
