# -*- coding: utf-8 -*-
"""
Reacomoda las notas de conducta de un año cuando cambian las fechas de sus
bimestres.

Un reporte no guarda su bimestre: solo trae su fecha, y en qué bimestre cae se
decide cada vez con la tabla `bimestre` (ver `bimestres.py`). Por eso, al
corregir las fechas, el reporte ya cuenta solo en el bimestre que le toca.

Lo que se quedaba atrás es `nota_conducta`. Cada vez que se registra, edita o
elimina un reporte se guarda ahí la nota CALCULADA del bimestre de ese día, y
todas las pantallas (y la libreta) dan por buena la fila guardada antes que el
cálculo. Con las fechas mal puestas, un reporte del IV bimestre dejaba su
descuento guardado en el III: al corregirlas, el III seguía con el descuento
y el IV lo volvía a restar.

Aquí se rehacen esas filas con las fechas nuevas. Solo las de origen
CALCULADO: las MIGRADO (vienen del sistema antiguo, sin reportes detrás) y las
MANUAL (las puso a mano el auxiliar, el tutor o el administrador) son
decisiones de una persona y no se tocan.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.modules.academic.models import AnioEscolar
from app.modules.enrollment.models import Matricula
from . import models
from . import bimestres as bimestres_util
from .constants import calcular_puntaje

ORIGEN_CALCULADO = "CALCULADO"


def reacomodar_notas_conducta(db: Session, anio_id: str) -> dict:
    """Rehace las notas CALCULADO de conducta del año con las fechas actuales.

    Para cada alumno matriculado y cada bimestre:
      * con reportes en ese tramo -> nota calculada (se crea o se corrige);
      * sin reportes -> se borra la fila calculada que hubiera: las pantallas
        y la libreta vuelven a deducir el 20 por su cuenta, igual que con
        cualquier alumno sin reportes.

    Suma los reportes con el mismo criterio que las pantallas (fecha dentro
    del tramo, ambos extremos incluidos), para que lo guardado y lo que se
    deduce digan lo mismo. No hace commit: eso lo decide quien llama.
    """
    resumen = {"creadas": 0, "corregidas": 0, "eliminadas": 0, "respetadas": 0}

    ae = db.query(AnioEscolar).filter(AnioEscolar.id_anio_escolar == anio_id).first()
    if not ae:
        return resumen
    tramos = bimestres_util.calendario(
        db, anio_id, getattr(ae, "fecha_inicio", None), getattr(ae, "fecha_fin", None),
        tipo=((ae.tipo or "REGULAR").strip().upper()),
    )
    if not tramos:
        return resumen

    alumno_de = {m.id_matricula: m.id_alumno for m in
                 db.query(Matricula.id_matricula, Matricula.id_alumno)
                 .filter(Matricula.id_anio_escolar == anio_id).all()}
    if not alumno_de:
        return resumen

    # Puntos y número de reportes por alumno y bimestre. Un alumno puede tener
    # más de un reporte el mismo día, así que no se agrupa por fecha.
    desde_anio = min(desde for _n, desde, _h in tramos)
    hasta_anio = max(hasta for _n, _d, hasta in tramos)
    reportes = (
        db.query(models.ReporteConducta.id_alumno,
                 func.date(models.ReporteConducta.fecha_reporte),
                 models.NivelConducta.puntos)
        .join(models.NivelConducta)
        .filter(models.ReporteConducta.id_alumno.in_(set(alumno_de.values())),
                func.date(models.ReporteConducta.fecha_reporte) >= desde_anio,
                func.date(models.ReporteConducta.fecha_reporte) <= hasta_anio)
        .all()
    )
    por_alumno: dict = {}   # (id_alumno, bimestre) -> puntos descontados
    for id_alumno, fecha, puntos in reportes:
        if fecha is None:
            continue
        for numero, desde, hasta in tramos:
            if desde <= fecha <= hasta:
                clave = (id_alumno, numero)
                por_alumno[clave] = por_alumno.get(clave, 0) + int(puntos or 0)

    guardadas = {
        (n.id_matricula, n.bimestre): n for n in
        db.query(models.NotaConducta)
        .filter(models.NotaConducta.id_matricula.in_(list(alumno_de))).all()
    }

    # Lo que debería haber guardado como CALCULADO con las fechas actuales.
    esperadas = {}
    for id_matricula, id_alumno in alumno_de.items():
        for numero, _d, _h in tramos:
            if (id_alumno, numero) in por_alumno:
                esperadas[(id_matricula, numero)] = calcular_puntaje(por_alumno[(id_alumno, numero)])

    ahora = datetime.now()
    for clave, nota in esperadas.items():
        fila = guardadas.get(clave)
        if fila is None:
            db.add(models.NotaConducta(id_matricula=clave[0], bimestre=clave[1],
                                       valor=nota, origen=ORIGEN_CALCULADO))
            resumen["creadas"] += 1
        elif (fila.origen or "") != ORIGEN_CALCULADO:
            resumen["respetadas"] += 1
        elif float(fila.valor) != float(nota):
            fila.valor = nota
            fila.fecha_registro = ahora
            resumen["corregidas"] += 1

    for clave, fila in guardadas.items():
        if (fila.origen or "") == ORIGEN_CALCULADO and clave not in esperadas:
            db.delete(fila)
            resumen["eliminadas"] += 1

    db.flush()
    return resumen
