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

El bimestre es ACUMULATIVO: pedir el III trae los bimestres I, II y III, y
todos los promedios se calculan solo sobre esos tres. Es lo que hace la
libreta en papel, que en cada entrega reimprime los bimestres anteriores. Sin
esto, la libreta del I bimestre saldría con columnas de bimestres que el
alumno todavía no ha cursado y el promedio de área mezclaría notas que en esa
fecha aún no existían.

`Area.orden_primaria` / `Area.orden_secundaria` es el orden oficial de las
áreas en la libreta; lo crea el script 19. Si esas columnas no estuvieran (una
base a la que todavía no se le pasó el script), se cae al orden alfabético en
vez de reventar.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.core.util.security import get_current_user
from app.modules.academic.models import (AnioEscolar, Area, Curso, Grado, Nivel,
                                         PlanEstudio, Seccion)
from app.modules.enrollment.models import Matricula
from app.modules.management.models import ExoneracionCurso, Nota
from app.modules.behavior import bimestres as bimestres_util
from app.modules.behavior.constants import calcular_puntaje
from app.modules.behavior.models import (NivelConducta, NotaConducta,
                                         ReporteConducta)
from app.modules.users.alumno.models import Alumno

router = APIRouter(prefix="/academic", tags=["Académico"])

ROLES_PERMITIDOS = ("ADMIN", "DOCENTE", "AUXILIAR")

BIMESTRES = (1, 2, 3, 4)

# Tope de libretas por descarga. Cada una es una página A4 que se dibuja en el
# navegador, así que no puede ser ilimitado. 700 deja sitio para el colegio
# entero (577 matriculados en 2026) y sigue frenando una petición absurda.
# Lo normal es filtrar por sección: son 30 y salen en un momento.
MAXIMO_LIBRETAS = 700


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


def _exoneraciones_matricula(db: Session, id_matricula: int) -> set:
    """Cursos de los que un alumno está exonerado. Ver `_exoneraciones_varias`."""
    try:
        return {e.id_curso for e in db.query(ExoneracionCurso.id_curso)
                .filter(ExoneracionCurso.id_matricula == id_matricula).all()}
    except (ProgrammingError, OperationalError):
        db.rollback()
        return set()


def _exoneraciones_varias(db: Session, ids_matricula) -> dict:
    """id_matricula -> {id_curso, ...}, para muchos alumnos a la vez.

    `exoneracion_curso` es una tabla del script 18: en una base a la que
    todavía no se le pasó, o que viene de un respaldo anterior a ese script,
    no existe. Sin nadie exonerado la libreta solo pierde el EXO y muestra la
    nota o el guion normal, así que se prefiere eso a tumbar la descarga.
    """
    try:
        exo: dict = {}
        for e in (db.query(ExoneracionCurso.id_matricula, ExoneracionCurso.id_curso)
                  .filter(ExoneracionCurso.id_matricula.in_(ids_matricula)).all()):
            exo.setdefault(e.id_matricula, set()).add(e.id_curso)
        return exo
    except (ProgrammingError, OperationalError):
        db.rollback()
        return {}


def _conducta_resuelta(db: Session, ae, ids_matricula, visibles: tuple) -> dict:
    """id_matricula -> {bimestre: nota de conducta}, con el mismo criterio que
    la pantalla de notas finales.

    La nota de conducta se resuelve en dos pasos, igual que en
    `router_notas.py` (busca "Resolución de nota de conducta"):

      1. La guardada en `nota_conducta`, si el auxiliar la puso a mano o vino
         en la migración.
      2. Si no hay ninguna, se DEDUCE: el alumno arranca el bimestre con 20 y
         cada reporte le descuenta los puntos de su falta.

    Antes la libreta solo hacía el paso 1 y dejaba la casilla en blanco. Como
    las notas del II bimestre nunca se cargaron —553 alumnos tienen la del I y
    22 la del II—, la pantalla enseñaba un 20 deducido y la libreta salía
    vacía para el mismo alumno. Son la misma nota y tienen que decir lo mismo.

    Los tramos de fechas se piden con el mismo `rango()` que usa la pantalla,
    de forma que las dos sumen exactamente los mismos reportes.
    """
    guardadas: dict = {}
    try:
        for nc in (db.query(NotaConducta.id_matricula, NotaConducta.bimestre,
                            NotaConducta.valor)
                   .filter(NotaConducta.id_matricula.in_(ids_matricula),
                           NotaConducta.bimestre.in_(visibles)).all()):
            guardadas.setdefault(nc.id_matricula, {})[nc.bimestre] = float(nc.valor)
    except (ProgrammingError, OperationalError):
        db.rollback()
        guardadas = {}

    # Sin año escolar no se sabe dónde empieza y acaba cada bimestre, así que
    # no hay forma de saber qué reportes contar: se devuelve lo guardado.
    if ae is None:
        return guardadas

    # En verano no hay nota de conducta: son siete semanas sin bimestres. La
    # pantalla la deja en None y aquí se hace lo mismo.
    tipo = (ae.tipo or "REGULAR").strip().upper()
    if tipo == "VERANO":
        return guardadas

    try:
        alumno_de = {m.id_matricula: m.id_alumno for m in
                     db.query(Matricula.id_matricula, Matricula.id_alumno)
                     .filter(Matricula.id_matricula.in_(ids_matricula)).all()}
        ids_alumno = {v for v in alumno_de.values() if v}
        hoy = date.today()

        for numero in visibles:
            tramo = bimestres_util.rango(
                db, ae.id_anio_escolar, numero,
                getattr(ae, "fecha_inicio", None), getattr(ae, "fecha_fin", None), tipo)
            if not tramo:
                continue
            desde, hasta = tramo

            # Un bimestre que todavía no ha empezado no se deduce: saldría un
            # 20 impreso en la libreta de un tramo que nadie ha cursado. Pasa
            # al pedir el año completo antes de que acabe. La pantalla no cae
            # en esto porque solo enseña una columna, la del bimestre en curso.
            if desde > hoy:
                continue

            puntos: dict = {}
            if ids_alumno:
                for r in (db.query(ReporteConducta.id_alumno,
                                   func.coalesce(func.sum(NivelConducta.puntos), 0))
                          .join(NivelConducta,
                                NivelConducta.id_nivel_conducta == ReporteConducta.id_nivel_conducta)
                          .filter(ReporteConducta.id_alumno.in_(ids_alumno),
                                  func.date(ReporteConducta.fecha_reporte) >= desde,
                                  func.date(ReporteConducta.fecha_reporte) <= hasta)
                          .group_by(ReporteConducta.id_alumno).all()):
                    puntos[r[0]] = int(r[1] or 0)

            for id_matricula in ids_matricula:
                fila = guardadas.setdefault(id_matricula, {})
                if numero in fila:
                    continue        # manda siempre la nota guardada
                fila[numero] = float(calcular_puntaje(puntos.get(alumno_de.get(id_matricula), 0)))
    except (ProgrammingError, OperationalError):
        # Una base sin las tablas de conducta se queda con lo que hubiera
        # guardado; la libreta pierde la nota deducida, no la descarga entera.
        db.rollback()

    return guardadas


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


def _armar_libreta(*, alumno_info: dict, cursos, notas_por_curso: dict,
                   exonerados: set, conducta: dict, visibles: tuple,
                   bimestre: Optional[int], orden_areas: dict) -> dict:
    """Monta la libreta de UN alumno a partir de datos ya cargados.

    Aquí no se consulta la base: todo llega resuelto. Es lo que permite que el
    endpoint de una libreta y el de un grupo entero den exactamente el mismo
    resultado —el colegio los compara— sin que el segundo haga una consulta por
    alumno.

    `cursos` es una lista de filas con id_curso, nombre e id_area.
    `orden_areas` es {id_area: (orden, nombre)}.
    """
    if not cursos:
        # Alumno sin plan de estudios y sin ninguna nota: la libreta sale
        # vacía, no es un error.
        return {
            "alumno": alumno_info,
            "bimestre_cabecera": bimestre,
            "bimestres_visibles": list(visibles),
            "areas": [],
            "resumen": {
                "por_bimestre": {str(b): {"puntaje_acumulado": None, "num_areas": 0,
                                          "ponderado": None} for b in visibles},
                "conducta_por_bimestre": {str(b): None for b in visibles},
                "ponderado_final_anual": None,
            },
        }

    # --- agrupar cursos por área ---
    bloques: dict = {}
    for c in cursos:
        info = bloques.setdefault(c.id_area, {"cursos": []})
        orden, nombre_area = orden_areas.get(c.id_area, (9999, None))
        info["orden"] = orden
        info["nombre"] = nombre_area or "SIN ÁREA"

        # Un curso exonerado se muestra SIN notas, aunque las tenga guardadas.
        #
        # La exoneración se puede poner a mitad de año, cuando el docente ya
        # calificó. Sus notas no se borran —siguen en `nota`, intactas— pero
        # mientras la exoneración esté puesta no se enseñan ni entran en
        # ningún promedio: el curso sale EXO, que es lo que significa estar
        # exonerado. Si se retira la exoneración, reaparecen tal cual estaban.
        esta_exonerado = c.id_curso in exonerados
        notas_curso = {} if esta_exonerado else notas_por_curso.get(c.id_curso, {})
        info["cursos"].append({
            "id_curso": c.id_curso,
            "nombre": c.nombre,
            "exonerado": esta_exonerado,
            "notas": {str(b): notas_curso.get(b) for b in visibles},
        })

    # --- promedio de área por bimestre y anual (reglas 1 y 4 del PDF) ---
    for info in bloques.values():
        promedio_bim = {}
        for b in visibles:
            valores = [c["notas"][str(b)] for c in info["cursos"]
                       if c["notas"][str(b)] is not None]
            # Un curso sin nota (incluido el exonerado) no suma ni divide.
            promedio_bim[str(b)] = (_redondear_entero(sum(valores) / len(valores))
                                    if valores else None)
        info["promedio_por_bimestre"] = promedio_bim

        existentes = [v for v in promedio_bim.values() if v is not None]
        info["promedio_anual"] = (_redondear_entero(sum(existentes) / len(existentes))
                                  if existentes else None)
        # Área sin ninguna nota en todo el año: exonerada por completo (EXO).
        info["exonerada"] = info["promedio_anual"] is None

    # --- puntaje acumulado y ponderado, por bimestre (reglas 2, 3 y 5) ---
    resumen_bim = {}
    for b in visibles:
        promedios_area = [info["promedio_por_bimestre"][str(b)]
                          for info in bloques.values()
                          if info["promedio_por_bimestre"][str(b)] is not None]
        if promedios_area:
            puntaje = sum(promedios_area)
            ponderado = _redondear_2(puntaje / len(promedios_area))
        else:
            puntaje = None
            ponderado = None
        resumen_bim[str(b)] = {"puntaje_acumulado": puntaje,
                               "num_areas": len(promedios_area),
                               "ponderado": ponderado}

    ponderados = [v["ponderado"] for v in resumen_bim.values() if v["ponderado"] is not None]
    ponderado_final_anual = (_redondear_2(sum(ponderados) / len(ponderados))
                             if ponderados else None)

    # --- bimestre que se destaca en el pie del PDF ---
    bimestre_cabecera = bimestre
    if bimestre_cabecera is None:
        con_datos = [b for b in visibles
                     if resumen_bim[str(b)]["puntaje_acumulado"] is not None]
        bimestre_cabecera = max(con_datos) if con_datos else None

    areas_out = [{
        "id_area": area_id,
        "nombre": info["nombre"],
        "cursos": sorted(info["cursos"], key=lambda c: c["nombre"]),
        "promedio_por_bimestre": info["promedio_por_bimestre"],
        "promedio_anual": info["promedio_anual"],
        "exonerada": info["exonerada"],
    } for area_id, info in sorted(bloques.items(),
                                  key=lambda kv: (kv[1]["orden"], kv[1]["nombre"]))]

    return {
        "alumno": alumno_info,
        "bimestre_cabecera": bimestre_cabecera,
        "bimestres_visibles": list(visibles),
        "areas": areas_out,
        "resumen": {
            "por_bimestre": resumen_bim,
            "conducta_por_bimestre": {str(b): conducta.get(b) for b in visibles},
            "ponderado_final_anual": ponderado_final_anual,
        },
    }


@router.get("/libreta/{id_matricula}")
def libreta(
    id_matricula: int,
    bimestre: Optional[int] = Query(None, ge=1, le=4, description="Último bimestre a incluir; es acumulativo"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Todo lo que necesita el PDF de la libreta de un alumno.

    `bimestre` es el ÚLTIMO que entra, no el único: pedir el III devuelve I,
    II y III, y los promedios de área, el puntaje acumulado y el ponderado se
    calculan solo sobre esos. Sin `bimestre` se devuelve el año completo.

    `bimestres_visibles` dice qué columnas debe dibujar el PDF, para que no
    tenga que deducirlo mirando qué notas vienen en null.
    """
    _autorizar(current_user)

    # Bimestres que entran en esta libreta. Todo lo que sigue —notas, promedios
    # de área, puntaje, ponderado y conducta— se calcula solo sobre estos.
    visibles = tuple(b for b in BIMESTRES if bimestre is None or b <= bimestre)

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
        .filter(Nota.id_matricula == id_matricula, Nota.bimestre.in_(visibles))
    )
    if ids_plan:
        q_extra = q_extra.filter(~Curso.id_curso.in_(ids_plan))
    cursos_extra = q_extra.distinct().all()

    cursos_todos = list(cursos_plan) + list(cursos_extra)

    # --- notas del alumno, solo de los bimestres que entran en esta libreta ---
    notas_por_curso: dict = {}
    for n in (
        db.query(Nota.id_curso, Nota.bimestre, Nota.valor)
        .filter(Nota.id_matricula == id_matricula, Nota.bimestre.in_(visibles))
        .all()
    ):
        notas_por_curso.setdefault(n.id_curso, {})[n.bimestre] = float(n.valor)

    # --- cursos de los que está exonerado (vale para el año completo) ---
    exonerados = _exoneraciones_matricula(db, id_matricula)

    # --- orden oficial de las áreas ---
    ids_area = {c.id_area for c in cursos_todos if c.id_area}
    orden_areas = _orden_areas(db, ids_area, es_primaria)

    # --- conducta, solo de los bimestres que entran ---
    # La guardada si la hay y, si no, la deducida de los reportes: es la misma
    # regla que aplica la tabla de notas finales. Ver `_conducta_resuelta`.
    ae_alumno = (db.query(AnioEscolar)
                 .filter(AnioEscolar.id_anio_escolar == matricula.id_anio_escolar)
                 .first())
    conducta = _conducta_resuelta(db, ae_alumno, [id_matricula], visibles)         .get(id_matricula, {})

    return _armar_libreta(
        alumno_info=_alumno_info(matricula, alumno, nivel, grado, seccion),
        cursos=cursos_todos,
        notas_por_curso=notas_por_curso,
        exonerados=exonerados,
        conducta=conducta,
        visibles=visibles,
        bimestre=bimestre,
        orden_areas=orden_areas,
    )


@router.get("/libretas")
def libretas_en_bloque(
    anio: Optional[str] = Query(None, description="Año escolar; por defecto el activo"),
    bimestre: Optional[int] = Query(None, ge=1, le=4),
    nivel: Optional[str] = Query(None),
    id_grado: Optional[int] = Query(None),
    id_seccion: Optional[int] = Query(None),
    dni: Optional[str] = Query(None),
    limite: int = Query(MAXIMO_LIBRETAS, ge=1, le=MAXIMO_LIBRETAS),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Las libretas de TODOS los alumnos que cumplan los filtros, de una vez.

    Los filtros son los mismos que los de la tabla de notas finales, y se
    resuelven con la misma consulta (`router_notas._base`), para que lo que se
    descargue sea exactamente la selección que se está viendo en pantalla.

    Todo se carga en bloque: seis consultas para el grupo entero, no seis por
    alumno. Con una sección de 30 son 6 consultas en vez de 180.

    Devuelve también `descripcion`, el texto de los filtros usados, para que el
    PDF se pueda nombrar y encabezar sin que el navegador tenga que recomponerlo.
    """
    _autorizar(current_user)

    # Import perezoso: `_base` vive en el router de notas y es la MISMA consulta
    # que pinta la tabla. Duplicarla aquí sería garantizar que algún día dejen
    # de coincidir.
    from app.modules.academic.router_notas import _base

    # --- año escolar ---
    if anio:
        ae = db.query(AnioEscolar).filter(AnioEscolar.id_anio_escolar == anio).first()
        if not ae:
            raise HTTPException(404, f"No existe el año escolar {anio}")
    else:
        ae = (db.query(AnioEscolar).filter(AnioEscolar.activo.is_(True))
              .order_by(AnioEscolar.id_anio_escolar.desc()).first())
        if not ae:
            raise HTTPException(404, "No hay ningún año escolar activo")
    anio = ae.id_anio_escolar
    if (ae.tipo or "REGULAR").strip().upper() == "VERANO":
        bimestre = None                 # en verano el bimestre no significa nada

    visibles = tuple(b for b in BIMESTRES if bimestre is None or b <= bimestre)

    base = _base(db, anio, nivel, id_grado, id_seccion, dni)
    total = base.order_by(None).count()
    if total == 0:
        raise HTTPException(404, "Ningún estudiante coincide con esos filtros")
    if total > limite:
        raise HTTPException(
            400, f"Son {total} libretas y el máximo por descarga es {limite}. "
                 f"Filtra por grado o por sección y descárgalas por partes.")

    filas = (base
             .with_entities(Matricula.id_matricula, Matricula.id_anio_escolar,
                            Alumno.dni, Alumno.apellidos, Alumno.nombres,
                            Nivel.nombre.label("nivel"),
                            Grado.id_grado.label("id_grado"),
                            Grado.nombre.label("grado"),
                            Grado.orden.label("orden_grado"),
                            Seccion.nombre.label("seccion"))
             .order_by(Nivel.nombre.asc(), Grado.orden.asc(), Seccion.nombre.asc(),
                       Alumno.apellidos.asc(), Alumno.nombres.asc())
             .all())

    ids = [f.id_matricula for f in filas]
    ids_grado = {f.id_grado for f in filas if f.id_grado}

    # --- 1. plan de estudios de todos los grados implicados ---
    plan_por_grado: dict = {}
    if ids_grado:
        for fila in (db.query(PlanEstudio.id_grado, Curso.id_curso, Curso.nombre,
                              Curso.id_area)
                     .join(Curso, Curso.id_curso == PlanEstudio.id_curso)
                     .filter(PlanEstudio.id_grado.in_(ids_grado)).distinct().all()):
            plan_por_grado.setdefault(fila.id_grado, []).append(fila)

    # --- 2. notas de todos, en una consulta ---
    notas_por_matricula: dict = {}
    cursos_con_nota: dict = {}
    for n in (db.query(Nota.id_matricula, Nota.id_curso, Nota.bimestre, Nota.valor)
              .filter(Nota.id_matricula.in_(ids), Nota.bimestre.in_(visibles)).all()):
        notas_por_matricula.setdefault(n.id_matricula, {}) \
                           .setdefault(n.id_curso, {})[n.bimestre] = float(n.valor)
        cursos_con_nota.setdefault(n.id_matricula, set()).add(n.id_curso)

    # --- 3. datos de todos los cursos con nota ---
    # Se cargan TODOS, no solo los que faltan en algún plan: un curso puede
    # estar en el plan de un grado y no en el de otro (Tutoría está en el de
    # primaria pero no en el de 1º de secundaria, y allí va con 20 automático).
    # Filtrar aquí contra la unión de los planes le quitaría ese curso a los
    # alumnos del grado que no lo tiene, que son justo los que lo necesitan.
    # Quién se lleva cada uno se decide más abajo, contra el plan de SU grado.
    ids_sueltos = {c for cs in cursos_con_nota.values() for c in cs}
    info_curso: dict = {}
    if ids_sueltos:
        info_curso = {c.id_curso: c for c in
                      db.query(Curso.id_curso, Curso.nombre, Curso.id_area)
                      .filter(Curso.id_curso.in_(ids_sueltos)).all()}

    # --- 4. exoneraciones ---
    exo_por_matricula = _exoneraciones_varias(db, ids)

    # --- 5. conducta ---
    # Guardada o deducida de los reportes, igual que en la tabla de notas
    # finales y que en la libreta de uno solo. Ver `_conducta_resuelta`.
    conducta_por_matricula = _conducta_resuelta(db, ae, ids, visibles)

    # --- 6. orden de las áreas, en los dos niveles ---
    # Se resuelve una vez para todas: el orden depende del nivel del alumno, y
    # en una descarga de "todos" conviven primaria y secundaria.
    ids_area = {c.id_area for cursos in plan_por_grado.values() for c in cursos if c.id_area}
    ids_area |= {c.id_area for c in info_curso.values() if c.id_area}
    orden_primaria = _orden_areas(db, ids_area, True)
    orden_secundaria = _orden_areas(db, ids_area, False)

    salida = []
    for f in filas:
        cursos = list(plan_por_grado.get(f.id_grado, []))
        ids_plan = {c.id_curso for c in cursos}
        for id_curso in sorted(cursos_con_nota.get(f.id_matricula, set()) - ids_plan):
            extra = info_curso.get(id_curso)
            if extra is not None:
                cursos.append(extra)

        es_primaria = "PRIM" in (f.nivel or "").upper()
        salida.append(_armar_libreta(
            alumno_info={
                "id_matricula": f.id_matricula,
                "dni": f.dni,
                "nombres": f.nombres,
                "apellidos": f.apellidos,
                "nivel": f.nivel,
                "grado": f.grado,
                "seccion": f.seccion,
                "anio_escolar": f.id_anio_escolar,
            },
            cursos=cursos,
            notas_por_curso=notas_por_matricula.get(f.id_matricula, {}),
            exonerados=exo_por_matricula.get(f.id_matricula, set()),
            conducta=conducta_por_matricula.get(f.id_matricula, {}),
            visibles=visibles,
            bimestre=bimestre,
            orden_areas=orden_primaria if es_primaria else orden_secundaria,
        ))

    return {
        "anio": anio,
        "bimestre": bimestre,
        "bimestres_visibles": list(visibles),
        "descripcion": _descripcion_filtros(filas, anio, bimestre, dni),
        "total": total,
        "libretas": salida,
    }


def _descripcion_filtros(filas, anio: str, bimestre: Optional[int],
                         dni: Optional[str]) -> str:
    """Cómo se llama la selección que se está descargando.

    Se describe por lo que REALMENTE salió, no por lo que se pidió: si el
    filtro era "todos" pero solo hay una sección con alumnos, el archivo lo
    dice. Así el nombre del PDF no miente sobre su contenido.
    """
    partes = [anio]
    niveles = {f.nivel for f in filas if f.nivel}
    grados = {f.grado for f in filas if f.grado}
    secciones = {f.seccion for f in filas if f.seccion}

    partes.append(next(iter(niveles)) if len(niveles) == 1 else "Todos los niveles")
    if len(grados) == 1:
        partes.append(next(iter(grados)))
    if len(secciones) == 1:
        partes.append(f"Sección {next(iter(secciones))}")
    elif len(grados) == 1:
        partes.append(f"{len(secciones)} secciones")
    partes.append(f"{bimestre}º bimestre" if bimestre else "Año completo")
    if dni:
        partes.append(f"DNI {dni.strip()}")
    return " · ".join(p for p in partes if p)


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
