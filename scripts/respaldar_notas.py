"""
RESPALDO de las tablas de evaluacion antes de vaciarlas.

Vuelca a un archivo .sql el contenido completo de:

    nota            promedios por bimestre
    resumen_nota    boleta por alumno y curso
    tarea           evaluaciones del docente
    entrega_tarea   la nota de cada alumno en cada evaluacion

El archivo que genera se puede pegar tal cual en phpMyAdmin para dejar las
tablas como estaban. Incluye los id originales, de modo que las referencias
entre tarea y entrega_tarea se mantienen.

Uso:
    python scripts/respaldar_notas.py
"""
import os
import sys
from datetime import datetime
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from app.db.database import SessionLocal

TABLAS = ["nota", "resumen_nota", "tarea", "entrega_tarea"]

CARPETA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "respaldos")


def literal(valor):
    """Convierte un valor de Python en literal SQL."""
    if valor is None:
        return "NULL"
    if isinstance(valor, (int, float, Decimal)):
        return str(valor)
    if isinstance(valor, datetime):
        return "'" + valor.strftime("%Y-%m-%d %H:%M:%S") + "'"
    texto = str(valor).replace("\\", "\\\\").replace("'", "\\'")
    return "'" + texto + "'"


def main():
    os.makedirs(CARPETA, exist_ok=True)
    sello = datetime.now().strftime("%Y%m%d_%H%M")
    destino = os.path.join(CARPETA, f"evaluacion_ANTES_{sello}.sql")

    db = SessionLocal()
    try:
        with open(destino, "w", encoding="utf-8") as f:
            f.write("-- Respaldo de las tablas de evaluacion\n")
            f.write(f"-- Generado: {datetime.now():%Y-%m-%d %H:%M}\n")
            f.write("-- Para restaurar: pegar este archivo entero en phpMyAdmin.\n\n")
            f.write("SET FOREIGN_KEY_CHECKS = 0;\n")
            f.write("START TRANSACTION;\n\n")

            for tabla in TABLAS:
                filas = db.execute(text(f"SELECT * FROM {tabla}")).fetchall()
                columnas = list(filas[0]._mapping.keys()) if filas else []
                print(f"  {tabla:<15} {len(filas):>6} filas")

                f.write(f"-- {'-' * 60}\n-- {tabla}\n-- {'-' * 60}\n")
                f.write(f"DELETE FROM `{tabla}`;\n")
                if not filas:
                    f.write("-- (tabla vacia)\n\n")
                    continue

                lista = ", ".join(f"`{c}`" for c in columnas)
                # Se parte en bloques para que phpMyAdmin no rechace la consulta
                for inicio in range(0, len(filas), 500):
                    bloque = filas[inicio:inicio + 500]
                    f.write(f"INSERT INTO `{tabla}` ({lista}) VALUES\n")
                    valores = [
                        "  (" + ", ".join(literal(v) for v in fila) + ")"
                        for fila in bloque
                    ]
                    f.write(",\n".join(valores) + ";\n")
                f.write("\n")

            f.write("COMMIT;\nSET FOREIGN_KEY_CHECKS = 1;\n")
    finally:
        db.close()

    tam = os.path.getsize(destino) / 1024
    print(f"\n>>> Respaldo guardado: {destino}  ({tam:,.0f} KB)")


if __name__ == "__main__":
    main()
