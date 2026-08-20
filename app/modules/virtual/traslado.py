# -*- coding: utf-8 -*-
"""
Traslado de las notas del aula virtual cuando un alumno cambia de sección.

POR QUÉ HACE FALTA ESTE ARCHIVO
El expediente académico del alumno no necesita traslado ninguno: las notas
oficiales (`nota`), el resumen, la conducta y la asistencia cuelgan de su
MATRÍCULA, y la matrícula es la misma antes y después del cambio. Cambiar de
sección solo reescribe `matricula.id_seccion`, así que la libreta y la sábana
oficial siguen al alumno solas.

El aula virtual es el único sitio donde no. Ahí las notas cuelgan de TAREAS, y
cada tarea pertenece a una carga académica, es decir, a UNA sección concreta.
Las tareas de 1ero Amarillo y las de 1ero Azul son objetos distintos aunque se
llamen igual. Al mover al alumno, sus calificaciones se quedaban apuntando a
las tareas de la sección vieja: el docente nuevo lo veía aparecer con promedio
0,0 y el alumno perdía de vista lo que ya había hecho.

CÓMO SE EMPAREJAN LAS TAREAS
Se busca en la sección destino una tarea equivalente: mismo curso, mismo
bimestre, mismo tipo de evaluación y mismo título. Es un emparejamiento
deliberadamente estricto. Si el docente de la otra sección puso tareas
distintas no hay equivalencia posible, y entonces NO se inventa nada: la
calificación se queda donde está y se informa de cuántas quedaron sin mover.
Copiar la nota de "Práctica de fracciones" sobre "Control de sumas" sería
fabricar un dato académico.

QUÉ NO HACE
  * No pisa una calificación que el alumno ya tuviera en la tarea destino.
  * No duplica: la entrega se reapunta, no se copia. El alumno ya no sale en la
    sección vieja, así que dejarla allí solo la escondería.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.modules.management.models import CargaAcademica

from .models import Tarea, EntregaTarea


def _clave(tarea: Tarea, id_curso: int) -> tuple:
    """Lo que tiene que coincidir para considerar dos tareas la misma."""
    return (
        id_curso,
        tarea.bimestre,
        (tarea.tipo_evaluacion or "").strip().upper(),
        (tarea.titulo or "").strip().lower(),
    )


def trasladar_entregas(db: Session, *, id_alumno: int, id_seccion_origen: int,
                       id_seccion_destino: int, id_anio_escolar: str) -> dict:
    """Reapunta las calificaciones del alumno a las tareas de su nueva sección.

    Devuelve un resumen: cuántas se movieron, cuántas no encontraron
    equivalente y cuántas se dejaron porque ya había nota en el destino.
    No hace commit: lo hace quien llama, dentro de su misma transacción.
    """
    vacio = {"trasladadas": 0, "sin_equivalente": 0, "ya_tenia_nota": 0}
    if not id_seccion_origen or id_seccion_origen == id_seccion_destino:
        return vacio

    # Curso de cada carga, en las dos secciones.
    def cargas_de(id_seccion):
        filas = (db.query(CargaAcademica.id_carga_academica, CargaAcademica.id_curso)
                 .filter(CargaAcademica.id_seccion == id_seccion,
                         CargaAcademica.id_anio_escolar == id_anio_escolar).all())
        return {c: cur for c, cur in filas}

    cargas_origen = cargas_de(id_seccion_origen)
    cargas_destino = cargas_de(id_seccion_destino)
    if not cargas_origen or not cargas_destino:
        return vacio

    # Índice de las tareas del destino por su "clave" de equivalencia.
    destino_por_clave: dict = {}
    for t in (db.query(Tarea)
              .filter(Tarea.id_carga_academica.in_(list(cargas_destino.keys()))).all()):
        destino_por_clave.setdefault(_clave(t, cargas_destino[t.id_carga_academica]), t)

    # Entregas del alumno en las tareas de la sección que deja.
    entregas = (db.query(EntregaTarea, Tarea)
                .join(Tarea, Tarea.id_tarea == EntregaTarea.id_tarea)
                .filter(EntregaTarea.id_alumno == id_alumno,
                        Tarea.id_carga_academica.in_(list(cargas_origen.keys())))
                .all())

    resumen = dict(vacio)
    for entrega, tarea in entregas:
        equivalente = destino_por_clave.get(_clave(tarea, cargas_origen[tarea.id_carga_academica]))
        if not equivalente:
            resumen["sin_equivalente"] += 1
            continue

        # ¿Ya tenía algo en la tarea destino? Entonces no se toca.
        ya = (db.query(EntregaTarea)
              .filter(EntregaTarea.id_tarea == equivalente.id_tarea,
                      EntregaTarea.id_alumno == id_alumno).first())
        if ya:
            resumen["ya_tenia_nota"] += 1
            continue

        entrega.id_tarea = equivalente.id_tarea
        resumen["trasladadas"] += 1

    return resumen
