# -*- coding: utf-8 -*-
"""
A qué bimestre pertenece una fecha.

Hace falta porque la nota de conducta se reinicia cada bimestre: para saber
cuánto le queda a un alumno hay que sumar solo los reportes de ESE tramo del
año, y un reporte solo trae su fecha.

Las fechas viven en la tabla `bimestre` (una fila por año escolar y número),
que se crea con el script 18. Si esa tabla está vacía —por ejemplo en una base
recién montada— se reparte el año escolar en cuatro tramos iguales, que es
mejor que quedarse sin poder calcular nada.
"""

from __future__ import annotations

import datetime as dt
from typing import List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

# Cuántos bimestres tiene un año escolar regular.
TOTAL_BIMESTRES = 4


def _del_calendario(db: Session, anio: str) -> List[Tuple[int, dt.date, dt.date]]:
    """Lee la tabla `bimestre`. Devuelve [] si no existe o está vacía."""
    try:
        filas = db.execute(
            text("SELECT numero, fecha_inicio, fecha_fin FROM bimestre "
                 "WHERE id_anio_escolar = :anio ORDER BY numero"),
            {"anio": anio},
        ).fetchall()
    except Exception:
        # La tabla puede no existir todavía si no se ejecutó el script 18. No
        # es motivo para tumbar la petición: se cae al reparto automático.
        db.rollback()
        return []
    return [(f[0], f[1], f[2]) for f in filas]


def _repartido(inicio: dt.date, fin: dt.date) -> List[Tuple[int, dt.date, dt.date]]:
    """El año escolar en cuatro tramos iguales. Solo como último recurso."""
    dias = (fin - inicio).days
    if dias <= 0:
        return [(1, inicio, fin)]
    tramos = []
    for n in range(1, TOTAL_BIMESTRES + 1):
        desde = inicio + dt.timedelta(days=dias * (n - 1) // TOTAL_BIMESTRES)
        hasta = inicio + dt.timedelta(days=dias * n // TOTAL_BIMESTRES)
        tramos.append((n, desde, hasta))
    return tramos


def calendario(db: Session, anio: str,
               inicio: Optional[dt.date] = None,
               fin: Optional[dt.date] = None) -> List[Tuple[int, dt.date, dt.date]]:
    """Los tramos del año, de la tabla si los hay y repartidos si no."""
    tramos = _del_calendario(db, anio)
    if tramos:
        return tramos
    if inicio and fin:
        return _repartido(inicio, fin)
    return []


def bimestre_de(fecha: dt.date,
                tramos: List[Tuple[int, dt.date, dt.date]]) -> Optional[int]:
    """En qué bimestre cae una fecha.

    Los tramos vienen ordenados y pegados unos a otros, así que se compara con
    el inicio del siguiente en vez de con el fin del propio: si el colegio deja
    un hueco entre bimestres (vacaciones), un reporte de esos días cuenta en el
    bimestre que acaba de terminar en lugar de perderse.
    """
    if not tramos or fecha is None:
        return None
    if isinstance(fecha, dt.datetime):
        fecha = fecha.date()
    if fecha < tramos[0][1]:
        return None                      # antes de que empiece el año escolar
    for indice, (numero, desde, _hasta) in enumerate(tramos):
        siguiente = tramos[indice + 1][1] if indice + 1 < len(tramos) else None
        if fecha >= desde and (siguiente is None or fecha < siguiente):
            return numero
    return tramos[-1][0]


def bimestre_actual(db: Session, anio: str,
                    inicio: Optional[dt.date] = None,
                    fin: Optional[dt.date] = None,
                    hoy: Optional[dt.date] = None) -> Optional[int]:
    """El bimestre en curso. None si la fecha queda fuera del año escolar."""
    tramos = calendario(db, anio, inicio, fin)
    return bimestre_de(hoy or dt.date.today(), tramos)


def rango(db: Session, anio: str, numero: int,
          inicio: Optional[dt.date] = None,
          fin: Optional[dt.date] = None) -> Optional[Tuple[dt.date, dt.date]]:
    """Las fechas de un bimestre concreto, para filtrar consultas."""
    for n, desde, hasta in calendario(db, anio, inicio, fin):
        if n == numero:
            return (desde, hasta)
    return None
