# -*- coding: utf-8 -*-
"""
Consulta de notas finales por curso y bimestre.

Alimenta la pestaña "Notas Finales" de Gestión de Estudiantes. Es solo de
lectura: no escribe nada, así que no puede afectar a las notas ni a nada más.

Por qué vive en su propio archivo y no dentro de `academic/router.py`: ese
router ya está en producción y es grande. Añadir aquí deja el cambio acotado y
hace evidente qué es nuevo.

La consulta puede tocar muchas filas (313 alumnos x 20 cursos por bimestre son
más de 6000 notas), así que:

  * Se pagina por ALUMNO, no por nota: cada página trae pocos alumnos con
    todas sus notas, que es como se lee la tabla.
  * Las columnas se calculan sobre el total filtrado, no sobre la página, para
    que no cambien al pasar de página.
  * Son dos consultas por petición, no una por alumno.

Dos cosas se hacen EXACTAMENTE igual que en `router_libreta.py`, y tienen que
seguir haciéndose igual, porque lo que se ve aquí y lo que sale impreso en el
PDF son el mismo dato y el colegio los compara:

  * Las columnas son los cursos del PLAN DE ESTUDIOS de los grados filtrados,
    no solo los que ya tienen nota. Un curso sin cargar tiene que verse como
    una casilla pendiente; si se omite la columna, nadie se entera de que
    falta.
  * El promedio es el PONDERADO DE ÁREAS, no la media de las notas sueltas.
    Son números distintos: en 5to de secundaria, con 19 cursos repartidos en
    11 áreas, la media plana da 14.63 y el ponderado de la libreta 16.45. Se
    promedia dentro de cada área, se redondea a entero, y recién esos enteros
    se promedian entre sí.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.core.util.security import get_current_user
from app.modules.academic.models import (AnioEscolar, Area, Curso, Grado, Nivel,
                                         PlanEstudio, Seccion)
from app.modules.enrollment.models import Matricula
from app.modules.management.models import ExoneracionCurso, Nota
from app.modules.users.alumno.models import Alumno

router = APIRouter(prefix="/academic", tags=["Académico"])

# Tope duro de alumnos por página. Sin él, un `por_pagina=100000` traería la
# tabla entera y tumbaría la respuesta.
MAXIMO_POR_PAGINA = 100

ROLES_PERMITIDOS = ("ADMIN", "DOCENTE", "AUXILIAR")


def _autorizar(usuario: dict) -> None:
    if (usuario or {}).get("rol") not in ROLES_PERMITIDOS:
        raise HTTPException(403, "No tienes permiso para consultar las notas")


def _entero(valor: float) -> int:
    """Redondeo al entero más cercano con el medio punto hacia arriba.

    `round()` de Python redondea 12.5 a 12 (redondeo bancario) y la libreta
    del colegio lo sube a 13. Misma función que en `router_libreta.py`: si una
    de las dos cambia, la tabla y el PDF dejan de coincidir.
    """
    return int(Decimal(str(valor)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _dos_decimales(valor: float) -> float:
    return float(Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _clave_curso(nombre: str) -> str:
    """Orden de los cursos dentro de un área, el mismo que imprime la libreta.

    Es la ordenación por punto de código, sin normalizar acentos: por eso
    ÁLGEBRA va detrás de RAZONAMIENTO MATEMÁTICO y no delante de ARITMÉTICA.
    Se ve raro escrito, pero es exactamente el orden del papel, y es también
    el que usa `router_libreta.py` al ordenar los cursos de cada bloque. Se
    ordena por el nombre tal cual está en la base, sin tocarlo, para que las
    dos pantallas den el mismo resultado carácter a carácter.
    """
    return nombre or ""


def _base(db: Session, anio: str, nivel, id_grado, id_seccion, dni):
    """Matrículas que cumplen los filtros. Es la misma para contar y para listar."""
    q = (db.query(Matricula.id_matricula, Alumno.dni, Alumno.apellidos, Alumno.nombres,
                  Nivel.nombre.label("nivel"), Grado.nombre.label("grado"),
                  Grado.orden.label("orden_grado"), Seccion.nombre.label("seccion"))
         .join(Alumno, Alumno.id_alumno == Matricula.id_alumno)
         .join(Seccion, Seccion.id_seccion == Matricula.id_seccion)
         .join(Grado, Grado.id_grado == Seccion.id_grado)
         .join(Nivel, Nivel.id_nivel == Grado.id_nivel)
         .filter(Matricula.id_anio_escolar == anio))
    if nivel:
        q = q.filter(Nivel.nombre == nivel)
    if id_grado:
        q = q.filter(Grado.id_grado == id_grado)
    if id_seccion:
        q = q.filter(Seccion.id_seccion == id_seccion)
    if dni:
        # Se busca por coincidencia parcial para que sirva escribiendo solo el
        # principio del documento, que es como se usa en las otras pantallas.
        q = q.filter(Alumno.dni.like(f"%{dni.strip()}%"))
    return q


@router.get("/notas-finales")
def notas_finales(
    anio: Optional[str] = Query(None, description="Año escolar; por defecto el activo"),
    bimestre: Optional[int] = Query(None, ge=1, le=4),
    nivel: Optional[str] = Query(None),
    id_grado: Optional[int] = Query(None),
    id_seccion: Optional[int] = Query(None),
    dni: Optional[str] = Query(None),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(25, ge=1, le=MAXIMO_POR_PAGINA),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Notas finales de cada curso, por alumno.

    En verano no hay bimestres: el año escolar de tipo VERANO guarda una sola
    nota por curso, así que el filtro de bimestre se ignora y se devuelve esa.
    """
    _autorizar(current_user)

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
    es_verano = (ae.tipo or "REGULAR").strip().upper() == "VERANO"
    if es_verano:
        bimestre = None          # en verano el bimestre no significa nada

    base = _base(db, anio, nivel, id_grado, id_seccion, dni)

    # --- cuántos alumnos hay en total con esos filtros ---
    total = base.order_by(None).count()

    # --- columnas: el plan de estudios de los grados filtrados ---
    # Se calcula aparte de la página para que la tabla no cambie de columnas al
    # avanzar. Son los cursos que el alumno DEBERÍA tener, no los que ya tienen
    # nota: si solo se listaran los segundos, un curso que nadie cargó
    # desaparecería de la tabla y no habría forma de notar que falta.
    ids_filtrados = base.order_by(None).with_entities(Matricula.id_matricula).subquery()
    ids_grado = [g for (g,) in base.order_by(None)
                 .with_entities(Grado.id_grado).distinct().all()]

    cursos_plan = []
    if ids_grado:
        cursos_plan = (db.query(Curso.id_curso, Curso.nombre, Curso.id_area)
                       .join(PlanEstudio, PlanEstudio.id_curso == Curso.id_curso)
                       .filter(PlanEstudio.id_grado.in_(ids_grado)).distinct().all())

    # Cursos con nota que NO están en el plan. Pasa de verdad: los que van con
    # 20 automático (Arte y Pintura, Tutoría, Cívica...) tienen nota pero
    # deliberadamente no se metieron en `plan_estudio`, para no tocar horarios
    # ni asignación de docentes. Sin esta segunda consulta no saldrían.
    q_extra = (db.query(Curso.id_curso, Curso.nombre, Curso.id_area)
               .join(Nota, Nota.id_curso == Curso.id_curso)
               .filter(Nota.id_matricula.in_(db.query(ids_filtrados.c.id_matricula))))
    if bimestre:
        q_extra = q_extra.filter(Nota.bimestre == bimestre)
    ids_plan = {c.id_curso for c in cursos_plan}
    if ids_plan:
        q_extra = q_extra.filter(~Curso.id_curso.in_(ids_plan))
    cursos_todos = list(cursos_plan) + list(q_extra.distinct().all())

    # --- orden de la libreta: primero por área, luego por curso ---
    # El orden de las áreas NO es el mismo en los dos niveles (Inglés va
    # tercero en primaria y último en secundaria), así que se elige según lo
    # que se esté mirando. Si el filtro mezcla niveles se usa el de
    # secundaria, que es el que tiene más áreas, y primaria queda de reserva.
    niveles_vistos = {n for (n,) in base.order_by(None)
                      .with_entities(Nivel.nombre).distinct().all()}
    solo_primaria = bool(niveles_vistos) and all(
        "PRIM" in (n or "").upper() for n in niveles_vistos)

    areas_info = {a.id_area: a for a in db.query(Area).all()}

    def _orden_area(id_area):
        a = areas_info.get(id_area)
        if a is None:
            return (9999, "")            # curso sin área: al final
        orden = getattr(a, "orden_primaria" if solo_primaria else "orden_secundaria", None)
        if orden is None:
            # El área no existe en ese nivel (o falta el script 19): se usa el
            # orden del otro nivel antes que mandarla al final sin más.
            orden = getattr(a, "orden_secundaria" if solo_primaria else "orden_primaria", None)
        return (orden if orden is not None else 9999, a.nombre or "")

    cursos_todos.sort(key=lambda c: (_orden_area(c.id_area), _clave_curso(c.nombre)))
    columnas = [{"id_curso": c.id_curso, "curso": c.nombre,
                 "id_area": c.id_area,
                 "area": (areas_info[c.id_area].nombre
                          if c.id_area in areas_info else None)}
                for c in cursos_todos]

    # id_curso -> id_area, para agrupar las notas de cada alumno por área.
    area_de_curso = {c.id_curso: c.id_area for c in cursos_todos}

    # --- la página de alumnos ---
    filas = (base.order_by(Nivel.nombre.asc(), Grado.orden.asc(), Seccion.nombre.asc(),
                           Alumno.apellidos.asc(), Alumno.nombres.asc())
             .offset((pagina - 1) * por_pagina).limit(por_pagina).all())
    if not filas:
        return {"anio": anio, "es_verano": es_verano, "bimestre": bimestre,
                "columnas": columnas, "alumnos": [], "total": total,
                "pagina": pagina, "por_pagina": por_pagina}

    # --- las notas de esos alumnos, en UNA consulta ---
    ids = [f.id_matricula for f in filas]
    q_notas = (db.query(Nota.id_matricula, Nota.id_curso, Nota.bimestre, Nota.valor)
               .filter(Nota.id_matricula.in_(ids)))
    if bimestre:
        q_notas = q_notas.filter(Nota.bimestre == bimestre)
    por_alumno: dict = {}
    for n in q_notas.all():
        # Si no se filtró por bimestre y hay varias, se queda la del bimestre
        # más alto: es la más reciente y es lo que se espera ver.
        actual = por_alumno.setdefault(n.id_matricula, {})
        previo = actual.get(n.id_curso)
        if previo is None or n.bimestre >= previo[1]:
            actual[n.id_curso] = (float(n.valor), n.bimestre)

    # --- quién está exonerado de qué, en la misma página ---
    # Una casilla vacía puede ser un exonerado o una nota que nadie cargó, y
    # en la libreta no se escriben igual: el exonerado sale EXO y el otro sale
    # pendiente. Esta consulta es la que permite distinguirlos.
    exonerados: dict = {}
    for e in (db.query(ExoneracionCurso.id_matricula, ExoneracionCurso.id_curso)
              .filter(ExoneracionCurso.id_matricula.in_(ids)).all()):
        exonerados.setdefault(e.id_matricula, set()).add(e.id_curso)

    alumnos = []
    for f in filas:
        notas = por_alumno.get(f.id_matricula, {})
        valores = [v for v, _ in notas.values()]
        exo = exonerados.get(f.id_matricula, set())

        # --- ponderado de áreas, exactamente como la libreta ---
        # Se agrupa por área, se promedia dentro de cada una y se redondea a
        # entero; el ponderado es la media de esos enteros. Un área sin
        # ninguna nota (toda exonerada, o sin cargar) ni suma ni divide.
        por_area: dict = {}
        for id_curso, (valor, _) in notas.items():
            por_area.setdefault(area_de_curso.get(id_curso), []).append(valor)
        promedios_area = [_entero(sum(v) / len(v)) for v in por_area.values() if v]

        alumnos.append({
            "id_matricula": f.id_matricula,
            "dni": f.dni,
            "alumno": f"{f.apellidos or ''}, {f.nombres or ''}".strip(", "),
            "nivel": f.nivel,
            "grado": f.grado,
            "seccion": f.seccion,
            # Solo los cursos con nota. Los que falten se pintan vacíos.
            "notas": {str(c): v for c, (v, _) in notas.items()},
            # Los cursos de los que está exonerado, para pintar EXO en vez de
            # dejar la casilla en blanco.
            "exonerados": [str(c) for c in sorted(exo)],
            "cursos_con_nota": len(valores),
            # Suma de los promedios de área: es el "PUNTAJE ACUMULADO" que sale
            # impreso en el pie de la libreta.
            "puntaje_acumulado": sum(promedios_area) if promedios_area else None,
            "num_areas": len(promedios_area),
            "promedio": (_dos_decimales(sum(promedios_area) / len(promedios_area))
                         if promedios_area else None),
        })

    return {"anio": anio, "es_verano": es_verano, "bimestre": bimestre,
            "columnas": columnas, "alumnos": alumnos, "total": total,
            "pagina": pagina, "por_pagina": por_pagina}


@router.get("/notas-finales/filtros")
def filtros_disponibles(
    anio: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Lo que se puede elegir en los desplegables, para no inventar opciones."""
    _autorizar(current_user)

    anios = [{"id": a.id_anio_escolar, "tipo": a.tipo, "activo": bool(a.activo)}
             for a in db.query(AnioEscolar)
             .order_by(AnioEscolar.id_anio_escolar.desc()).all()]
    if not anio:
        activo = next((a for a in anios if a["activo"]), None)
        anio = activo["id"] if activo else (anios[0]["id"] if anios else None)

    secciones = []
    if anio:
        secciones = [{"id_seccion": s.id_seccion, "seccion": s.nombre,
                      "id_grado": g.id_grado, "grado": g.nombre,
                      "orden": g.orden, "nivel": n.nombre}
                     for s, g, n in db.query(Seccion, Grado, Nivel)
                     .join(Grado, Grado.id_grado == Seccion.id_grado)
                     .join(Nivel, Nivel.id_nivel == Grado.id_nivel)
                     .filter(Seccion.id_anio_escolar == anio)
                     .order_by(Nivel.nombre, Grado.orden, Seccion.nombre).all()]

    bimestres = []
    if anio:
        bimestres = [b for (b,) in db.query(Nota.bimestre)
                     .join(Matricula, Matricula.id_matricula == Nota.id_matricula)
                     .filter(Matricula.id_anio_escolar == anio)
                     .group_by(Nota.bimestre).order_by(Nota.bimestre).all()]

    return {"anios": anios, "anio": anio, "secciones": secciones,
            "bimestres": bimestres}
