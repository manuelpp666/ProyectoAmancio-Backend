# -*- coding: utf-8 -*-
"""
El 20 de los cursos que salen en la libreta pero no se dictan.

La lista vive en `curso_nota_automatica` (curso + grado + valor) y la cargó el
script 17. Ese script puso el 20 en los bimestres que ya tenían notas el día
que se ejecutó (el I y el II) y dejaba los siguientes "al backend", pero el
backend nunca lo hacía: en el III bimestre los docentes cerraban sus cursos y
estos se quedaban vacíos. Esto es lo que faltaba.

CUÁNDO SE PONE EL 20
    Un bimestre está "en marcha" en una sección cuando esa sección ya tiene
    alguna nota real en él (de un curso que NO está en la lista). Solo ahí se
    pone el 20. Así no se inventan bimestres: si se rellenara por calendario,
    el IV aparecería en Notas Finales y en la libreta lleno de veintes antes de
    que nadie haya puesto una nota de verdad.

    Se llama al cerrar un docente su bimestre (la nota real acaba de nacer) y
    al arrancar el backend, que repasa el año entero por si algo se quedó atrás.

QUÉ NO TOCA
    * Ninguna nota que ya exista: el 20 solo entra donde no hay nada.
    * A los exonerados de ese curso: en la libreta llevan EXO, no una nota.
    * A los retirados: no se les cierra ningún bimestre, tampoco este.
    * Los años de verano: la lista es del año regular, y en verano los grados
      se repiten con otros cursos.

Es idempotente: ejecutarlo dos veces no duplica nada.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

# Una sola sentencia, la misma lógica que el script 17 (pasos 5 a 7) pero
# sección por sección. INSERT IGNORE además del NOT EXISTS: si dos procesos
# rellenan a la vez, el segundo choca con la clave única y se salta la fila en
# vez de fallar.
_RELLENAR = """
INSERT IGNORE INTO nota (id_matricula, id_curso, bimestre, tipo_nota, valor)
SELECT m.id_matricula, cna.id_curso, b.bimestre, 'PROMEDIO', cna.valor
  FROM curso_nota_automatica cna
  JOIN seccion s   ON s.id_grado = cna.id_grado
                  AND s.id_anio_escolar = :anio
  JOIN matricula m ON m.id_seccion = s.id_seccion
                  AND m.id_anio_escolar = :anio
  JOIN alumno a    ON a.id_alumno = m.id_alumno
  JOIN (
        -- Secciones y bimestres que ya tienen alguna nota real.
        SELECT DISTINCT m2.id_seccion, n2.bimestre
          FROM nota n2
          JOIN matricula m2 ON m2.id_matricula = n2.id_matricula
          JOIN seccion s2   ON s2.id_seccion = m2.id_seccion
         WHERE m2.id_anio_escolar = :anio
           AND NOT EXISTS (SELECT 1 FROM curso_nota_automatica c2
                            WHERE c2.id_curso = n2.id_curso
                              AND c2.id_grado = s2.id_grado)
       ) b ON b.id_seccion = s.id_seccion
 WHERE COALESCE(a.estado_ingreso, '') <> 'RETIRADO'
   {filtros}
   AND NOT EXISTS (SELECT 1 FROM nota x
                    WHERE x.id_matricula = m.id_matricula
                      AND x.id_curso     = cna.id_curso
                      AND x.bimestre     = b.bimestre)
   AND NOT EXISTS (SELECT 1 FROM exoneracion_curso e
                    WHERE e.id_matricula = m.id_matricula
                      AND e.id_curso     = cna.id_curso)
"""


def _es_regular(db: Session, anio: str) -> bool:
    tipo = db.execute(text("SELECT tipo FROM anio_escolar WHERE id_anio_escolar = :a"),
                      {"a": anio}).scalar()
    return (tipo or "REGULAR").upper() != "VERANO"


def rellenar(db: Session, anio: str, id_seccion: Optional[int] = None,
             bimestre: Optional[int] = None) -> int:
    """Pone el 20 que falte. Devuelve cuántas notas creó.

    Sin `id_seccion` ni `bimestre` repasa el año entero. No hace commit: lo
    deja al llamador. Si las tablas no existen (una base donde no se ejecutó
    el script 17 o el 18) devuelve 0 en vez de fallar: es un añadido y no
    puede tumbar lo que lo llama.
    """
    if not anio or not _es_regular(db, str(anio)):
        return 0

    filtros, params = [], {"anio": str(anio)}
    if id_seccion is not None:
        filtros.append("AND s.id_seccion = :seccion")
        params["seccion"] = int(id_seccion)
    if bimestre is not None:
        filtros.append("AND b.bimestre = :bimestre")
        params["bimestre"] = int(bimestre)

    sentencia = text(_RELLENAR.format(filtros="\n   ".join(filtros)))
    try:
        return db.execute(sentencia, params).rowcount or 0
    except (ProgrammingError, OperationalError) as e:
        print(f"[NOTAS AUTOMÁTICAS] No se pudo rellenar (¿falta la tabla?): {e}")
        return 0


def rellenar_anios_activos(db: Session) -> int:
    """El repaso del arranque: todos los años regulares activos."""
    anios = [r[0] for r in db.execute(text(
        "SELECT id_anio_escolar FROM anio_escolar WHERE activo = 1"))]
    total = 0
    for anio in anios:
        total += rellenar(db, anio)
    return total
