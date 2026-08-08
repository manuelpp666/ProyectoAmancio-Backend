"""
DATOS DE PRUEBA — Química de 5to "A" (carga académica 269, año 2026).

Crea tareas y entregas ficticias para el docente Abraham Yamunaque Huamán, de
modo que se pueda probar el flujo completo de calificación: poner notas,
corregirlas y cerrar el bimestre.

Se cubren los tres estados posibles de un alumno en una actividad:

  * CALIFICADA        entrega con nota puesta
  * ENTREGADA         el alumno subió su archivo pero aún no tiene nota
                      (es lo que alimenta el contador «Pendientes de Calificar»)
  * SIN ENTREGA       no hay registro; al cerrar el bimestre cuenta como cero

Los pesos suman exactamente 100 %, así que el botón «Cerrar Bimestre» estará
habilitado y se podrá probar también ese paso.

ESTO NO ES DATO REAL. Para borrarlo todo:

    python scripts/datos_prueba_quimica_5toA.py --borrar

Uso:
    python scripts/datos_prueba_quimica_5toA.py            # simulación
    python scripts/datos_prueba_quimica_5toA.py --aplicar  # crea los datos
    python scripts/datos_prueba_quimica_5toA.py --borrar   # los elimina
"""
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from app.db.database import SessionLocal

ID_CARGA = 269          # Química · SECUNDARIA 5to "A" · 2026
BIMESTRE = 1

APLICAR = "--aplicar" in sys.argv
BORRAR = "--borrar" in sys.argv

# Semilla fija: las mismas notas en cada ejecución, para que las pruebas sean
# repetibles y comparables.
random.seed(2026)

# titulo, tipo, peso, calificados, entregados_sin_nota  (el resto: sin entrega)
ACTIVIDADES = [
    ("Práctica calificada N° 1", "TAREA", 20, "todos", 0),
    ("Informe de laboratorio: reacciones químicas", "TAREA", 30, 20, 8),
    ("Examen bimestral", "EXAMEN_BIMESTRAL", 50, 12, 6),
    ("Repaso de nomenclatura (no cuenta para la nota)", "TAREA", 0, 0, 9),
]


def alumnos_de_la_carga(db):
    return [r[0] for r in db.execute(text("""
        SELECT a.id_alumno
        FROM carga_academica ca
        JOIN matricula m ON m.id_seccion = ca.id_seccion
                        AND m.id_anio_escolar = ca.id_anio_escolar
        JOIN alumno a ON a.id_alumno = m.id_alumno
        WHERE ca.id_carga_academica = :c
        ORDER BY a.apellidos, a.nombres"""), {"c": ID_CARGA})]


def nota_verosimil():
    """Notas repartidas como en un salón real: la mayoría aprueba."""
    tramo = random.random()
    if tramo < 0.12:
        return random.randint(6, 10)      # desaprobados
    if tramo < 0.55:
        return random.randint(11, 15)     # aprobados justos
    return random.randint(16, 20)         # buenos


def borrar(db):
    tareas = [r[0] for r in db.execute(text(
        "SELECT id_tarea FROM tarea WHERE id_carga_academica = :c"), {"c": ID_CARGA})]
    if not tareas:
        print("No hay tareas en esta carga: no hay nada que borrar.")
        return

    n_entregas = db.execute(text(
        "SELECT COUNT(*) FROM entrega_tarea WHERE id_tarea IN :t"
    ).bindparams(**{}), {"t": tuple(tareas)}).scalar() if tareas else 0

    print(f"Se eliminarán {len(tareas)} tareas y {n_entregas} entregas de la carga {ID_CARGA}.")
    for t in tareas:
        print(f"  - tarea {t}")

    if not APLICAR and not BORRAR:
        return
    db.execute(text("DELETE FROM entrega_tarea WHERE id_tarea IN :t"), {"t": tuple(tareas)})
    db.execute(text("DELETE FROM tarea WHERE id_carga_academica = :c"), {"c": ID_CARGA})
    # Las notas de cierre de bimestre, si se llegó a cerrar durante las pruebas
    db.execute(text("""
        DELETE n FROM nota n
        JOIN carga_academica ca ON ca.id_curso = n.id_curso
        JOIN matricula m ON m.id_matricula = n.id_matricula
                        AND m.id_seccion = ca.id_seccion
        WHERE ca.id_carga_academica = :c"""), {"c": ID_CARGA})
    db.commit()
    print(">>> DATOS DE PRUEBA ELIMINADOS")


def crear(db):
    alumnos = alumnos_de_la_carga(db)
    print(f"Alumnos en la sección: {len(alumnos)}")

    existentes = db.execute(text(
        "SELECT COUNT(*) FROM tarea WHERE id_carga_academica = :c"), {"c": ID_CARGA}).scalar()
    if existentes:
        print(f"[!] La carga ya tiene {existentes} tareas. Ejecuta --borrar antes de volver a crear.")
        return

    ahora = datetime.now()
    total_peso = 0

    for titulo, tipo, peso, n_calif, n_entreg in ACTIVIDADES:
        total_peso += peso
        calificados = len(alumnos) if n_calif == "todos" else n_calif
        sin_entrega = len(alumnos) - calificados - n_entreg

        print(f"\n  «{titulo}»")
        print(f"     tipo={tipo} · peso={peso}%")
        print(f"     {calificados} calificados · {n_entreg} entregados sin nota · "
              f"{max(0, sin_entrega)} sin entrega")

        if not APLICAR:
            continue

        fecha_entrega = (ahora + timedelta(days=7)) if tipo == "TAREA" and peso else None
        db.execute(text("""
            INSERT INTO tarea (id_carga_academica, titulo, descripcion, fecha_publicacion,
                               fecha_entrega, estado, tipo_evaluacion, bimestre, peso)
            VALUES (:c, :t, :d, :fp, :fe, 'ACTIVO', :tipo, :b, :p)"""), {
            "c": ID_CARGA, "t": titulo,
            "d": "Actividad de prueba generada para validar el registro de notas.",
            "fp": ahora, "fe": fecha_entrega, "tipo": tipo, "b": BIMESTRE, "p": peso})
        id_tarea = db.execute(text("SELECT LAST_INSERT_ID()")).scalar()

        barajados = alumnos[:]
        random.shuffle(barajados)
        con_nota = barajados[:calificados]
        solo_entrega = barajados[calificados:calificados + n_entreg]

        for id_alumno in con_nota:
            db.execute(text("""
                INSERT INTO entrega_tarea (id_tarea, id_alumno, archivo_url, comentario_alumno,
                                           calificacion, retroalimentacion_docente)
                VALUES (:t, :a, :url, :com, :cal, :retro)"""), {
                "t": id_tarea, "a": id_alumno,
                "url": "media/pruebas/entrega-ficticia.pdf",
                "com": "Entrega de prueba.",
                "cal": nota_verosimil(),
                "retro": "Observación de prueba." if random.random() < 0.3 else None})

        for id_alumno in solo_entrega:
            db.execute(text("""
                INSERT INTO entrega_tarea (id_tarea, id_alumno, archivo_url, comentario_alumno,
                                           calificacion)
                VALUES (:t, :a, :url, :com, NULL)"""), {
                "t": id_tarea, "a": id_alumno,
                "url": "media/pruebas/entrega-ficticia.pdf",
                "com": "Entrega de prueba pendiente de calificar."})

    print(f"\n  Peso total del bimestre {BIMESTRE}: {total_peso}% "
          f"({'se podrá cerrar' if total_peso == 100 else 'NO se podrá cerrar'})")

    if APLICAR:
        db.commit()
        print("\n>>> DATOS DE PRUEBA CREADOS")
    else:
        db.rollback()
        print("\n>>> SIMULACIÓN: no se escribió nada. Repite con --aplicar.")


def main():
    db = SessionLocal()
    try:
        curso = db.execute(text("""
            SELECT c.nombre, g.nombre, s.nombre, d.nombres, d.apellidos
            FROM carga_academica ca
            JOIN curso c ON c.id_curso = ca.id_curso
            JOIN seccion s ON s.id_seccion = ca.id_seccion
            JOIN grado g ON g.id_grado = s.id_grado
            JOIN docente d ON d.id_docente = ca.id_docente
            WHERE ca.id_carga_academica = :c"""), {"c": ID_CARGA}).fetchone()
        if not curso:
            print(f"No existe la carga académica {ID_CARGA}.")
            return
        print(f"Carga {ID_CARGA}: {curso[0]} · {curso[1]} \"{curso[2]}\" · "
              f"docente {curso[3]} {curso[4]}\n")

        if BORRAR:
            borrar(db)
        else:
            crear(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
