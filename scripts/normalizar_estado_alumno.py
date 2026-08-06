"""
Deja `alumno.estado_ingreso` con los valores canónicos del sistema.

La carga inicial de 2026 escribió 'ACEPTADO', un estado que no usa ninguna otra
parte del código: los alumnos no encajaban en ninguna condición y en el panel
salían con la etiqueta azul de "pendiente" en vez de la verde de matriculado.

Convierte cualquier variante (minúsculas, espacios, nombres antiguos) al valor
que define app/modules/users/alumno/estados.py. Sin --aplicar solo informa.

    python scripts/normalizar_estado_alumno.py
    python scripts/normalizar_estado_alumno.py --aplicar
"""
import datetime as dt
import os
import sys

import pymysql
from dotenv import load_dotenv

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from app.modules.users.alumno import estados  # noqa: E402

BD = "amancio_2026"
for arg in sys.argv[1:]:
    if arg.startswith("--bd="):
        BD = arg.split("=", 1)[1]
APLICAR = "--aplicar" in sys.argv

load_dotenv(os.path.join(RAIZ, ".env"))
host, _, puerto = (os.getenv("DB_HOST") or "localhost").strip().partition(":")
con = pymysql.connect(host=host, port=int(puerto or 3306), user=os.getenv("DB_USER"),
                      password=os.getenv("DB_PASS") or "", database=BD, charset="utf8mb4")
cur = con.cursor()

cur.execute("SELECT estado_ingreso, COUNT(*) FROM alumno GROUP BY estado_ingreso")
actuales = cur.fetchall()

print(f"Base: {BD}")
print(f"Estados válidos: {', '.join(estados.ESTADOS)}\n")
print("Estado actual de la tabla:")

cambios = {}
sin_equivalente = []
for valor, cuantos in actuales:
    canonico = estados.normalizar(valor)
    if canonico is None:
        sin_equivalente.append((valor, cuantos))
        print(f"   {str(valor)!r:<16} {cuantos:>4}   ¡SIN EQUIVALENTE!")
    elif canonico != valor:
        cambios[valor] = (canonico, cuantos)
        print(f"   {str(valor)!r:<16} {cuantos:>4}   ->  {canonico}")
    else:
        print(f"   {str(valor)!r:<16} {cuantos:>4}   ya correcto")

if sin_equivalente:
    print("\nHay valores que no sé traducir. Añádelos a EQUIVALENCIAS en")
    print("app/modules/users/alumno/estados.py antes de continuar.")
    con.close()
    sys.exit(1)

if not cambios:
    print("\nNada que cambiar: todos los estados ya son canónicos.")
    con.close()
    sys.exit(0)

if not APLICAR:
    print("\nSimulación. Repite con --aplicar para escribir.")
    con.close()
    sys.exit(0)

# Respaldo de los valores antiguos, por si hubiera que revertir
carpeta = os.path.join(RAIZ, "scripts", "respaldos")
os.makedirs(carpeta, exist_ok=True)
sello = dt.datetime.now().strftime("%Y%m%d_%H%M")
ruta = os.path.join(carpeta, f"{BD}_estado_ingreso_ANTES_{sello}.sql")
cur.execute("SELECT id_alumno, estado_ingreso FROM alumno")
filas = cur.fetchall()
with open(ruta, "w", encoding="utf8") as fh:
    fh.write(f"-- estado_ingreso de {BD} antes de normalizar ({dt.datetime.now():%Y-%m-%d %H:%M})\n")
    for id_alumno, valor in filas:
        v = "NULL" if valor is None else "'" + str(valor).replace("'", "\\'") + "'"
        fh.write(f"UPDATE alumno SET estado_ingreso={v} WHERE id_alumno={id_alumno};\n")
print(f"\nRespaldo de los {len(filas)} valores anteriores en:\n   {ruta}")

total = 0
for viejo, (nuevo, _) in cambios.items():
    cur.execute("UPDATE alumno SET estado_ingreso=%s WHERE estado_ingreso=%s", (nuevo, viejo))
    print(f"   {viejo!r} -> {nuevo}: {cur.rowcount} filas")
    total += cur.rowcount
con.commit()

cur.execute("SELECT estado_ingreso, COUNT(*) FROM alumno GROUP BY estado_ingreso")
print(f"\nActualizadas {total} filas. Estado final:")
for valor, cuantos in cur.fetchall():
    marca = "ok" if valor in estados.ESTADOS else "REVISAR"
    print(f"   {str(valor)!r:<16} {cuantos:>4}   {marca}")
con.close()
