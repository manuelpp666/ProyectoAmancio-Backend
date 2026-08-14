# -*- coding: utf-8 -*-
"""
Datos para el PDF de la libreta de notas de UN alumno, por bimestre.

Alimenta el botón "Descargar libreta" de la pestaña "Notas Finales" del
panel. Es solo de lectura, igual que `router_notas.py` (léelo si algo aquí no
queda claro: comparte estilo, autorización y varias de sus consultas).

Por qué vive en su propio archivo y no dentro de `router_notas.py` ni de
`academic/router.py`: es una pantalla nueva, acotada a un alumno concreto, y
así el diff de esta tarea no se mezcla con el de esos archivos que ya están
en producción.

Dos cosas que este endpoint da por hechas porque las está construyendo OTRA
tarea en paralelo, y que aquí se tratan con cuidado para no reventar si
todavía no existen:

  * `Area.orden_primaria` / `Area.orden_secundaria`: el orden oficial de las
    áreas en la libreta. Si la columna no está en el modelo, o está pero la
    tabla real todavía no la tiene, se cae al orden alfabético.
  * `app.modules.behavior.models.NotaConducta`: la nota de conducta por
    bimestre. Si el modelo no existe todavía, la conducta sale `null` y no
    se rompe nada.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.core.util.security import get_current_user
from app.modules.academic.models import Area, Curso, Grado, Nivel, PlanEstudio, Seccion
from app.modules.enrollment.models import Matricula
from app.modules.management.models import ExoneracionCurso, Nota
from app.modules.users.alumno.models import Alumno

# La conducta la modela otra tarea en paralelo. Se importa de forma
# defensiva: si el módulo aún no la declara, este endpoint sigue
# funcionando y simplemente no manda la conducta (null en vez de reventar).
try:
    from app.modules.behavior.models import NotaConducta  # type: ignore
except ImportError:  # pragma: no cover - depende de la otra tarea
    NotaConducta = None  # type: ignore

router = APIRouter(prefix="/academic", tags=["Académico"])

ROLES_PERMITIDOS = ("ADMIN", "DOCENTE", "AUXILIAR")

BIMESTRES = (1, 2, 3, 4)


def _autorizar(usuario: dict) -> None:
    if (usuario or {}).get("rol") not in ROLES_PERMITIDOS:
        raise HTTPException(403, "No tienes permiso para consultar la libreta")


def _redondear_entero(valor: float) -> int:
    """Redondeo al entero más cercano, medio punto hacia arriba.

    `round()` de Python usa redondeo bancario (12.5 -> 12), y la libreta del
    colegio redondea siempre hacia arriba en el medio punto (12.5 -> 13). Por
    eso no se usa `round()` directo aquí.
    """
    return int(Decimal(str(valor)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _redondear_2(valor: float) -> float:
    return float(Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _orden_areas(db: Session, ids_area: set, primaria: bool) -> dict:
    """Orden oficial de las áreas en la libreta, con caída elegante.

    Devuelve {id_area: (orden, nombre)}. Si `orden_primaria` /
    `orden_secundaria` no existen todavía (ni en el modelo, ni en la tabla
    real), se cae al orden alfabético por nombre.
    """
    if not ids_area:
        return {}

    nombre_columna = "orden_primaria" if primaria else "orden_secundaria"
    columna = getattr(Area, nombre_columna, None)
    if columna is not None:
        try:
            filas = (
                db.query(Area.id_area, Area.nombre, columna.label("orden"))
                .filter(Area.id_area.in_(ids_area))
                .all()
            )
            # Si la columna existe pero está vacía para todas, tampoco sirve
            # de nada usarla: se cae al alfabético igual.
            if any(f.orden is not None for f in filas):
                return {
                    f.id_area: (f.orden if f.orden is not None else 9999, f.nombre)
                    for f in filas
                }
        except Exception:
            # La tabla real no tiene la columna todavía aunque el modelo sí
            # la declare: se descarta la consulta rota y se sigue con la
            # sesión limpia.
            db.rollback()

    filas = db.query(Area.id_area, Area.nombre).filter(Area.id_area.in_(ids_area)).all()
    return {f.id_area: (0, f.nombre) for f in filas}


@router.get("/libreta/{id_matricula}")
def libreta(
    id_matricula: int,
    bimestre: Optional[int] = Query(None, ge=1, le=4, description="Bimestre destacado en el pie del PDF"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Todo lo que necesita el PDF de la libreta de un alumno.

    La tabla siempre trae los cuatro bimestres (1..4), tenga o no notas
    cargadas todavía: así el PDF puede dibujar las cuatro columnas de la
    libreta oficial aunque el año esté a la mitad. El parámetro `bimestre`
    solo decide cuál es el bimestre "destacado" en el pie (puntaje
    acumulado, ponderado y conducta que se leen de un vistazo); si no se
    manda, se usa el bimestre más avanzado que ya tenga alguna nota.
    """
    _autorizar(current_user)

    fila = (
        db.query(Matricula, Alumno, Seccion, Grado, Nivel)
        .join(Alumno, Alumno.id_alumno == Matricula.id_alumno)
        .outerjoin(Seccion, Seccion.id_seccion == Matricula.id_seccion)
        .outerjoin(Grado, Grado.id_grado == Matricula.id_grado)
        .outerjoin(Nivel, Nivel.id_nivel == Grado.id_nivel)
        .filter(Matricula.id_matricula == id_matricula)
        .first()
    )
    if not fila:
        raise HTTPException(404, "No existe esa matrícula")
    matricula, alumno, seccion, grado, nivel = fila

    es_primaria = "PRIM" in (nivel.nombre or "").upper() if nivel else True

    # --- cursos del plan de estudios del grado (columnas fijas de la libreta) ---
    cursos_plan = []
    if grado:
        cursos_plan = (
            db.query(Curso.id_curso, Curso.nombre, Curso.id_area)
            .join(PlanEstudio, PlanEstudio.id_curso == Curso.id_curso)
            .filter(PlanEstudio.id_grado == grado.id_grado)
            .all()
        )

    # --- cursos con nota que no estén en el plan (dato suelto, por si acaso) ---
    # No debería pasar en un colegio con el plan bien cargado, pero si pasa,
    # mejor mostrar la nota igual que perderla silenciosamente.
    ids_plan = {c.id_curso for c in cursos_plan}
    q_extra = (
        db.query(Curso.id_curso, Curso.nombre, Curso.id_area)
        .join(Nota, Nota.id_curso == Curso.id_curso)
        .filter(Nota.id_matricula == id_matricula)
    )
    if ids_plan:
        q_extra = q_extra.filter(~Curso.id_curso.in_(ids_plan))
    cursos_extra = q_extra.distinct().all()

    cursos_todos = list(cursos_plan) + list(cursos_extra)
    if not cursos_todos:
        # Alumno sin plan de estudios y sin ninguna nota cargada: la libreta
        # sale igual, solo que vacía. No es un 404, la matrícula existe.
        return {
            "alumno": _alumno_info(matricula, alumno, nivel, grado, seccion),
            "bimestre_cabecera": bimestre,
            "areas": [],
            "resumen": {
                "por_bimestre": {str(b): {"puntaje_acumulado": None, "num_areas": 0, "ponderado": None} for b in BIMESTRES},
                "conducta_por_bimestre": {str(b): None for b in BIMESTRES},
                "ponderado_final_anual": None,
            },
        }

    # --- notas del alumno, todas (los cuatro bimestres) ---
    notas_por_curso: dict = {}
    for n in (
        db.query(Nota.id_curso, Nota.bimestre, Nota.valor)
        .filter(Nota.id_matricula == id_matricula)
        .all()
    ):
        notas_por_curso.setdefault(n.id_curso, {})[n.bimestre] = float(n.valor)

    # --- cursos de los que está exonerado (vale para el año completo) ---
    exonerados = {
        e.id_curso
        for e in db.query(ExoneracionCurso.id_curso)
        .filter(ExoneracionCurso.id_matricula == id_matricula)
        .all()
    }

    # --- orden oficial de las áreas ---
    ids_area = {c.id_area for c in cursos_todos if c.id_area}
    orden_areas = _orden_areas(db, ids_area, es_primaria)

    # --- agrupar cursos por área ---
    bloques: dict = {}
    for c in cursos_todos:
        area_id = c.id_area
        info = bloques.setdefault(area_id, {"cursos": []})
        orden, nombre_area = orden_areas.get(area_id, (9999, None))
        info["orden"] = orden
        info["nombre"] = nombre_area or "SIN ÁREA"

        notas_curso = notas_por_curso.get(c.id_curso, {})
        info["cursos"].append(
            {
                "id_curso": c.id_curso,
                "nombre": c.nombre,
                "exonerado": c.id_curso in exonerados,
                "notas": {str(b): notas_curso.get(b) for b in BIMESTRES},
            }
        )

    # --- promedio de área por bimestre y anual (reglas 1 y 4 del PDF) ---
    for info in bloques.values():
        promedio_bim = {}
        for b in BIMESTRES:
            valores = [
                c["notas"][str(b)] for c in info["cursos"] if c["notas"][str(b)] is not None
            ]
            # Un curso sin nota (incluido el exonerado) no suma ni divide.
            promedio_bim[str(b)] = _redondear_entero(sum(valores) / len(valores)) if valores else None
        info["promedio_por_bimestre"] = promedio_bim

        existentes = [v for v in promedio_bim.values() if v is not None]
        info["promedio_anual"] = _redondear_entero(sum(existentes) / len(existentes)) if existentes else None
        # Área sin ninguna nota en todo el año: exonerada por completo (EXO).
        info["exonerada"] = info["promedio_anual"] is None

    # --- puntaje acumulado y ponderado, por bimestre (reglas 2, 3 y 5) ---
    resumen_bim = {}
    for b in BIMESTRES:
        promedios_area = [
            info["promedio_por_bimestre"][str(b)]
            for info in bloques.values()
            if info["promedio_por_bimestre"][str(b)] is not None
        ]
        if promedios_area:
            puntaje = sum(promedios_area)
            ponderado = _redondear_2(puntaje / len(promedios_area))
        else:
            puntaje = None
            ponderado = None
        resumen_bim[str(b)] = {
            "puntaje_acumulado": puntaje,
            "num_areas": len(promedios_area),
            "ponderado": ponderado,
        }

    ponderados_existentes = [v["ponderado"] for v in resumen_bim.values() if v["ponderado"] is not None]
    ponderado_final_anual = (
        _redondear_2(sum(ponderados_existentes) / len(ponderados_existentes))
        if ponderados_existentes
        else None
    )

    # --- conducta por bimestre, tolerando que el modelo aún no exista ---
    conducta_bim = {str(b): None for b in BIMESTRES}
    if NotaConducta is not None:
        try:
            for nc in (
                db.query(NotaConducta.bimestre, NotaConducta.valor)
                .filter(NotaConducta.id_matricula == id_matricula)
                .all()
            ):
                conducta_bim[str(nc.bimestre)] = nc.valor
        except Exception:
            # La tabla todavía no existe en la base real, aunque el modelo
            # ya esté declarado: se descarta y sigue sin conducta.
            db.rollback()

    # --- bimestre que se destaca en el pie del PDF ---
    bimestre_cabecera = bimestre
    if bimestre_cabecera is None:
        con_datos = [b for b in BIMESTRES if resumen_bim[str(b)]["puntaje_acumulado"] is not None]
        bimestre_cabecera = max(con_datos) if con_datos else None

    # --- áreas en el orden de la libreta, con sus cursos alfabéticos ---
    areas_out = []
    for area_id, info in sorted(bloques.items(), key=lambda kv: (kv[1]["orden"], kv[1]["nombre"])):
        areas_out.append(
            {
                "id_area": area_id,
                "nombre": info["nombre"],
                "cursos": sorted(info["cursos"], key=lambda c: c["nombre"]),
                "promedio_por_bimestre": info["promedio_por_bimestre"],
                "promedio_anual": info["promedio_anual"],
                "exonerada": info["exonerada"],
            }
        )

    return {
        "alumno": _alumno_info(matricula, alumno, nivel, grado, seccion),
        "bimestre_cabecera": bimestre_cabecera,
        "areas": areas_out,
        "resumen": {
            "por_bimestre": resumen_bim,
            "conducta_por_bimestre": conducta_bim,
            "ponderado_final_anual": ponderado_final_anual,
        },
    }


def _alumno_info(matricula, alumno, nivel, grado, seccion) -> dict:
    return {
        "id_matricula": matricula.id_matricula,
        "dni": alumno.dni,
        "nombres": alumno.nombres,
        "apellidos": alumno.apellidos,
        "nivel": nivel.nombre if nivel else None,
        "grado": grado.nombre if grado else None,
        "seccion": seccion.nombre if seccion else None,
        "anio_escolar": matricula.id_anio_escolar,
    }
