"""
VACIA las tablas de evaluacion: notas, promedios, tareas y entregas.

Deja en cero:

    entrega_tarea   la nota de cada alumno en cada evaluacion
    tarea           las evaluaciones creadas por los docentes
    resumen_nota    la boleta (bimestre 1..4 y promedio final)
    nota            el promedio de cada bimestre

Se borra en ese orden porque entrega_tarea depende de tarea.

NO toca la carga academica, el plan de estudio, las matriculas, la asistencia
ni los materiales de clase.

Antes de usarlo conviene ejecutar:
    python scripts/respaldar_notas.py

Uso:
    python scripts/vaciar_notas.py            # simulacion, no borra nada
    python scripts/vaciar_notas.py --aplicar  # borra de verdad
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from app.db.database import SessionLocal

# El orden importa: primero las tablas que apuntan a otras.
TABLAS = ["entrega_tarea", "tarea", "resumen_nota", "nota"]

APLICAR = "--aplicar" in sys.argv


def main():
    db = SessionLocal()
    try:
        print("Contenido actual:")
        antes = {}
        for tabla in TABLAS:
            antes[tabla] = db.execute(text(f"SELECT COUNT(*) FROM {tabla}")).scalar()
            print(f"  {tabla:<15} {antes[tabla]:>7} filas")

        # Los archivos que subieron los alumnos quedarian huerfanos en disco
        archivos = db.execute(text(
            "SELECT archivo_url FROM entrega_tarea "
            "WHERE archivo_url IS NOT NULL AND archivo_url <> ''")).fetchall()
        if archivos:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            en_disco = sum(
                1 for (url,) in archivos
                if os.path.exists(os.path.join(base, str(url).lstrip("/")))
            )
            print(f"\n  entregas con archivo adjunto: {len(archivos)}")
            print(f"  de esos, existen en disco   : {en_disco}")
            print("  (los archivos NO se borran; solo se van los registros)")

        if not APLICAR:
            print("\n>>> SIMULACION: no se borro nada. Repite con --aplicar.")
            return

        for tabla in TABLAS:
            db.execute(text(f"DELETE FROM {tabla}"))
        db.commit()

        print("\nDespues:")
        for tabla in TABLAS:
            n = db.execute(text(f"SELECT COUNT(*) FROM {tabla}")).scalar()
            estado = "OK" if n == 0 else "!! NO QUEDO VACIA"
            print(f"  {tabla:<15} {n:>7} filas   {estado}")
        print("\n>>> TABLAS DE EVALUACION VACIADAS")
    finally:
        db.close()


if __name__ == "__main__":
    main()
