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
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.core.util.security import get_current_user
from app.modules.academic.models import AnioEscolar, Area, Curso, Grado, Nivel, Seccion
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

    # --- columnas: los cursos con nota en TODO el conjunto filtrado ---
    # Se calcula aparte de la página para que la tabla no cambie de columnas al
    # avanzar. Es una consulta ligera: agrupa por curso, no por alumno.
    ids_filtrados = base.order_by(None).with_entities(Matricula.id_matricula).subquery()
    q_cursos = (db.query(Curso.id_curso, Curso.nombre, Area.nombre.label("area"))
                .join(Nota, Nota.id_curso == Curso.id_curso)
                .outerjoin(Area, Area.id_area == Curso.id_area)
                .filter(Nota.id_matricula.in_(db.query(ids_filtrados.c.id_matricula))))
    if bimestre:
        q_cursos = q_cursos.filter(Nota.bimestre == bimestre)
    cursos = (q_cursos.group_by(Curso.id_curso, Curso.nombre, Area.nombre)
              .order_by(Area.nombre.asc(), Curso.nombre.asc()).all())
    columnas = [{"id_curso": c.id_curso, "curso": c.nombre, "area": c.area} for c in cursos]

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
            # El promedio se saca únicamente sobre los cursos CON nota, igual
            # que en la libreta del colegio: un curso exonerado no divide.
            "promedio": round(sum(valores) / len(valores), 2) if valores else None,
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
