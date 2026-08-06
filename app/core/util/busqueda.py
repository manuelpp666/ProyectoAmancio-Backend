"""
Búsqueda por texto sobre varias columnas a la vez.

Todos los buscadores de la aplicación funcionan igual: se escriben una o varias
palabras y cada una debe aparecer en algún dato de la fila, sin importar el
orden ni en qué columna esté. Así, escribir el nombre tal como se ve en la
tabla ("CASTRO CASTILLO, CARLOS") encuentra al alumno aunque los apellidos y
los nombres se guarden en columnas distintas.

Comparar columna por columna no sirve para eso: `apellidos LIKE '%castro
carlos%'` no encuentra nada, porque ese texto no está entero en ninguna
columna. Por eso se concatenan primero y se busca sobre el resultado.
"""
from sqlalchemy import func


def _escapar(palabra: str) -> str:
    """Neutraliza los comodines de LIKE: sin esto, escribir "%" lo listaría todo."""
    return palabra.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def palabras(termino: str) -> list:
    """Parte el término en palabras. Las comas se tratan como separador para que
    copiar y pegar "Apellidos, Nombres" desde la tabla siga funcionando."""
    return (termino or "").replace(",", " ").split()


def texto_de(*columnas):
    """Une las columnas en un solo texto separado por espacios.

    concat_ws ignora los NULL, así que una fila sin alumno (los outerjoin de
    caja) no desaparece del listado ni rompe la comparación.
    """
    return func.concat_ws(" ", *columnas)


def filtrar(query, termino: str, *columnas):
    """Añade al query una condición LIKE por cada palabra del término.

    La colación de la base (utf8mb4_unicode_ci) ignora mayúsculas y tildes, así
    que "maria" también encuentra a MARÍA.
    """
    completo = texto_de(*columnas)
    for palabra in palabras(termino):
        query = query.filter(completo.like(f"%{_escapar(palabra)}%"))
    return query
