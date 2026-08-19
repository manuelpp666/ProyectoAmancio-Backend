# -*- coding: utf-8 -*-
"""
Exoneración de un alumno en un curso.

Antes, que un alumno estuviera exonerado se deducía de que no tuviera nota.
Eso se confunde con un olvido de carga, y una vez impresa la libreta ya no hay
forma de saber cuál de las dos cosas era. Aquí el docente lo deja dicho:
queda su nombre y la fecha, y la libreta puede escribir EXO con seguridad.

Un exonerado no suma ni divide en el promedio. Es lo que hace el colegio y lo
que confirman las libretas del sistema antiguo: en una de ellas nueve áreas
suman 134 y el ponderado es 134/9 = 14.89, no 134/10.

Quién puede tocar esto:
  * el DOCENTE de esa carga académica, y solo de la suya
  * el ADMIN, para corregir sin depender del docente
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.core.util.security import get_current_user
from app.modules.enrollment.models import Matricula
from app.modules.management.models import CargaAcademica, ExoneracionCurso
from app.modules.users.alumno.models import Alumno
from app.modules.users.docente.models import Docente

router = APIRouter(prefix="/academic", tags=["Académico"])


class ExoneracionEntrada(BaseModel):
    id_matricula: int
    id_curso: int
    motivo: Optional[str] = Field(None, max_length=150)


def _docente_de(db: Session, usuario: dict) -> Optional[Docente]:
    return (db.query(Docente)
            .filter(Docente.id_usuario == (usuario or {}).get("id")).first())


def _carga_o_404(db: Session, id_carga: int) -> CargaAcademica:
    carga = (db.query(CargaAcademica)
             .filter(CargaAcademica.id_carga_academica == id_carga).first())
    if not carga:
        raise HTTPException(404, "Carga académica no encontrada")
    return carga


def _autorizar_carga(db: Session, usuario: dict, carga: CargaAcademica) -> Optional[int]:
    """Devuelve el id_docente que firma el cambio. Lanza 403 si no puede."""
    rol = (usuario or {}).get("rol")
    if rol == "ADMIN":
        return None
    if rol != "DOCENTE":
        raise HTTPException(403, "No tienes permiso para modificar exoneraciones")
    docente = _docente_de(db, usuario)
    if not docente or docente.id_docente != carga.id_docente:
        raise HTTPException(403, "Ese curso no es tuyo")
    return docente.id_docente


def _carga_del_curso(db: Session, id_matricula: int, id_curso: int) -> CargaAcademica:
    """La carga académica que corresponde al alumno y curso indicados.

    Sirve para comprobar permisos cuando la petición no trae el id de la carga:
    el alumno pertenece a una sección, y esa sección tiene un docente asignado
    para ese curso.
    """
    matricula = (db.query(Matricula)
                 .filter(Matricula.id_matricula == id_matricula).first())
    if not matricula:
        raise HTTPException(404, "La matrícula no existe")
    carga = (db.query(CargaAcademica)
             .filter(CargaAcademica.id_seccion == matricula.id_seccion,
                     CargaAcademica.id_curso == id_curso,
                     CargaAcademica.id_anio_escolar == matricula.id_anio_escolar)
             .first())
    if not carga:
        raise HTTPException(404, "Ese curso no se dicta en la sección del alumno")
    return carga


@router.get("/exoneraciones/carga/{id_carga}")
def listar_por_carga(id_carga: int, db: Session = Depends(get_db),
                     current_user: dict = Depends(get_current_user)):
    """Qué alumnos de esta carga están exonerados. Alimenta la sábana de notas."""
    if (current_user or {}).get("rol") not in ("ADMIN", "DOCENTE", "AUXILIAR"):
        raise HTTPException(403, "No tienes permiso para consultar exoneraciones")
    carga = _carga_o_404(db, id_carga)

    filas = (db.query(ExoneracionCurso, Matricula, Alumno)
             .join(Matricula, Matricula.id_matricula == ExoneracionCurso.id_matricula)
             .join(Alumno, Alumno.id_alumno == Matricula.id_alumno)
             .filter(ExoneracionCurso.id_curso == carga.id_curso,
                     Matricula.id_seccion == carga.id_seccion,
                     Matricula.id_anio_escolar == carga.id_anio_escolar,
                     Alumno.estado_ingreso != "RETIRADO")
             .all())

    return {
        "id_carga_academica": id_carga,
        "id_curso": carga.id_curso,
        "exonerados": [
            {"id_matricula": e.id_matricula, "id_alumno": m.id_alumno,
             "alumno": f"{a.apellidos}, {a.nombres}", "motivo": e.motivo,
             "fecha": e.fecha_registro.strftime("%d/%m/%Y") if e.fecha_registro else None}
            for e, m, a in filas
        ],
    }


def _matricula_en_carga(db: Session, carga: CargaAcademica, id_alumno: int) -> Matricula:
    """La matrícula del alumno dentro de esa carga.

    La sábana del docente trabaja con id_alumno, no con id_matricula. En vez de
    cambiar ese endpoint —que ya está en producción— se resuelve aquí.
    """
    matricula = (db.query(Matricula)
                 .filter(Matricula.id_alumno == id_alumno,
                         Matricula.id_seccion == carga.id_seccion,
                         Matricula.id_anio_escolar == carga.id_anio_escolar)
                 .first())
    if not matricula:
        raise HTTPException(404, "El alumno no está matriculado en esa sección")
    return matricula


@router.post("/exoneraciones/carga/{id_carga}/alumno/{id_alumno}")
def marcar_en_carga(id_carga: int, id_alumno: int,
                    motivo: Optional[str] = None,
                    db: Session = Depends(get_db),
                    current_user: dict = Depends(get_current_user)):
    """Exonera desde la sábana de notas, que trabaja con id_alumno."""
    carga = _carga_o_404(db, id_carga)
    _autorizar_carga(db, current_user, carga)
    matricula = _matricula_en_carga(db, carga, id_alumno)
    return marcar(ExoneracionEntrada(id_matricula=matricula.id_matricula,
                                     id_curso=carga.id_curso, motivo=motivo),
                  db=db, current_user=current_user)


@router.delete("/exoneraciones/carga/{id_carga}/alumno/{id_alumno}")
def quitar_en_carga(id_carga: int, id_alumno: int, db: Session = Depends(get_db),
                    current_user: dict = Depends(get_current_user)):
    """Quita la exoneración desde la sábana de notas."""
    carga = _carga_o_404(db, id_carga)
    _autorizar_carga(db, current_user, carga)
    matricula = _matricula_en_carga(db, carga, id_alumno)
    return quitar(matricula.id_matricula, carga.id_curso,
                  db=db, current_user=current_user)


@router.post("/exoneraciones")
def marcar(entrada: ExoneracionEntrada, db: Session = Depends(get_db),
           current_user: dict = Depends(get_current_user)):
    """Marca a un alumno como exonerado de un curso."""
    carga = _carga_del_curso(db, entrada.id_matricula, entrada.id_curso)
    id_docente = _autorizar_carga(db, current_user, carga)

    ya = (db.query(ExoneracionCurso)
          .filter(ExoneracionCurso.id_matricula == entrada.id_matricula,
                  ExoneracionCurso.id_curso == entrada.id_curso).first())
    if ya:
        return {"mensaje": "El alumno ya estaba exonerado de este curso",
                "id_exoneracion_curso": ya.id_exoneracion_curso}

    # Se puede exonerar aunque ya tenga notas, y las notas NO se borran.
    #
    # Antes esto devolvía un 409 pidiendo borrarlas primero. Era una mala
    # solución: obligaba a destruir el trabajo del docente para marcar una
    # exoneración que a menudo llega a mitad de año (un traslado, un
    # certificado médico, una convalidación), y si luego se retiraba la
    # exoneración las notas ya no estaban en ninguna parte.
    #
    # Ahora la exoneración solo TAPA las notas: mientras esté puesta, el curso
    # sale como EXO y no cuenta para ningún promedio, pero las filas siguen en
    # `nota`. Al quitarla, el alumno recupera exactamente lo que tenía.
    # Ver `router_libreta._armar_libreta` y `router_notas.sabana_general`.

    fila = ExoneracionCurso(id_matricula=entrada.id_matricula,
                            id_curso=entrada.id_curso,
                            motivo=(entrada.motivo or "").strip() or None,
                            id_docente=id_docente)
    db.add(fila)
    try:
        db.commit()
    except IntegrityError:
        # Dos pestañas abiertas marcando a la vez: la clave única corta la
        # segunda y no es un error que deba ver el usuario.
        db.rollback()
        return {"mensaje": "El alumno ya estaba exonerado de este curso"}
    db.refresh(fila)
    return {"mensaje": "Alumno exonerado del curso",
            "id_exoneracion_curso": fila.id_exoneracion_curso}


@router.delete("/exoneraciones/{id_matricula}/{id_curso}")
def quitar(id_matricula: int, id_curso: int, db: Session = Depends(get_db),
           current_user: dict = Depends(get_current_user)):
    """Deja de considerar exonerado al alumno."""
    carga = _carga_del_curso(db, id_matricula, id_curso)
    _autorizar_carga(db, current_user, carga)

    fila = (db.query(ExoneracionCurso)
            .filter(ExoneracionCurso.id_matricula == id_matricula,
                    ExoneracionCurso.id_curso == id_curso).first())
    if not fila:
        raise HTTPException(404, "Ese alumno no figura como exonerado")
    db.delete(fila)
    db.commit()
    return {"mensaje": "Exoneración retirada"}
