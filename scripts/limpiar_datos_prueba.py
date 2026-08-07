"""
Elimina de la base las cuentas y datos de prueba, respaldándolos antes.

Sin --aplicar solo enseña lo que encontraría. Con --aplicar guarda un .sql con
los INSERT de todo lo que va a borrar y luego lo borra, así que revertir es
volcar ese archivo.

Solo toca lo que reconoce como prueba:
  · cuentas cuyo DNI empieza por 9999 (los que se usan al verificar el sistema)
  · cuentas con nombre o correo de relleno: "prueba", "temporal", "example.com"
  · conversaciones vacías y mensajes de un solo saludo ("hola", "test"...)

    python scripts/limpiar_datos_prueba.py
    python scripts/limpiar_datos_prueba.py --aplicar
"""
import datetime as dt
import os
import sys

import pymysql
from dotenv import load_dotenv

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BD = "amancio_2026"
for arg in sys.argv[1:]:
    if arg.startswith("--bd="):
        BD = arg.split("=", 1)[1]
APLICAR = "--aplicar" in sys.argv

# Un DNI peruano real nunca empieza por 9999; ese prefijo se reserva para las
# cuentas que se crean al verificar el sistema.
PREFIJO_DNI_PRUEBA = "9999"
TEXTOS_DE_RELLENO = ("prueba", "temporal", "example.com", "test@")
SALUDOS_DE_PRUEBA = ("hola", "test", "prueba", "hola hola", "aaa", "1", "asd")

# PERO hay personal REAL del colegio con DNI inventado: el directorio 2026 trae
# tres personas sin DNI (Juana Serquén, Edgar Herrera, Royer Castillo) y la
# carga inicial les asignó 99900001/2/3. Con el prefijo actual ("9999") no las
# alcanza —empiezan por 9990—, pero basta acortarlo a "999" para borrar a tres
# empleados y sus cursos asignados. La excepción evita que eso dependa de una
# cifra. La lista se lee del propio directorio para no mantenerla a mano.
def _dnis_del_directorio() -> set:
    sys.path.insert(0, os.path.join(RAIZ, "scripts"))
    try:
        import datos_personal
    except ImportError:
        # Sin el directorio a mano, lo prudente es no borrar ninguna cuenta
        # por su DNI: se seguirá detectando la de prueba por nombre y correo.
        print("[AVISO] No se encontró scripts/datos_personal.py: no se borrará "
              "ninguna cuenta por el prefijo del DNI.")
        return None
    reales = set()
    for lista in (datos_personal.ADMINISTRATIVOS, datos_personal.PSICOLOGOS,
                  datos_personal.AUXILIARES, datos_personal.DOCENTES):
        reales.update(registro[0] for registro in lista)
    return reales


DNIS_REALES = _dnis_del_directorio()

PERFILES = [
    ("administrador", "id_admin"),
    ("docente", "id_docente"),
    ("psicologo", "id_psicologo"),
    ("auxiliar", "id_auxiliar"),
    ("alumno", "id_alumno"),
]

load_dotenv(os.path.join(RAIZ, ".env"))
host, _, puerto = (os.getenv("DB_HOST") or "localhost").strip().partition(":")
con = pymysql.connect(host=host, port=int(puerto or 3306), user=os.getenv("DB_USER"),
                      password=os.getenv("DB_PASS") or "", database=BD, charset="utf8mb4")
cur = con.cursor()


def sql(valor):
    if valor is None:
        return "NULL"
    if isinstance(valor, (int, float)):
        return str(valor)
    texto = str(valor).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{texto}'"


def columnas(tabla):
    cur.execute(f"SHOW COLUMNS FROM `{tabla}`")
    return [c[0] for c in cur.fetchall()]


def insert_de(tabla, fila, cols):
    campos = ", ".join(f"`{c}`" for c in cols)
    valores = ", ".join(sql(v) for v in fila)
    return f"INSERT INTO `{tabla}` ({campos}) VALUES ({valores});"


def tiene_vida_academica(id_alumno) -> bool:
    """¿El alumno tiene matrícula o pagos? Entonces es real, no una prueba."""
    for tabla in ("matricula", "pago"):
        cur.execute(f"SELECT 1 FROM `{tabla}` WHERE id_alumno = %s LIMIT 1",
                    (id_alumno,))
        if cur.fetchone():
            return True
    return False


# ---------------------------------------------------------------- 1. cuentas
cuentas = []          # (tabla_perfil, pk, id_perfil, id_usuario, descripcion)
for tabla, pk in PERFILES:
    cols = columnas(tabla)
    if "dni" not in cols:
        continue
    condiciones = []
    if DNIS_REALES is not None:
        condiciones.append(f"dni LIKE '{PREFIJO_DNI_PRUEBA}%'")
    for campo in ("nombres", "apellidos", "email"):
        if campo in cols:
            condiciones += [f"LOWER(`{campo}`) LIKE '%{t}%'" for t in TEXTOS_DE_RELLENO]
    if not condiciones:
        continue
    cur.execute(
        f"SELECT {pk}, id_usuario, dni, nombres, apellidos FROM `{tabla}` "
        f"WHERE {' OR '.join(condiciones)}"
    )
    for id_perfil, id_usuario, dni, nom, ape in cur.fetchall():
        # Quien figura en el directorio del colegio es personal real, tenga el
        # DNI que tenga.
        if DNIS_REALES and dni in DNIS_REALES:
            print(f"[PROTEGIDO] {tabla} · DNI {dni} · {nom} {ape} "
                  f"— está en el directorio, no se toca.")
            continue
        # Un alumno matriculado o con pagos registrados no es una cuenta de
        # prueba por mucho que su DNI parezca de relleno: lo que está mal es el
        # DNI, no la persona. (Le pasó a Gadiel Aquino Navarro, id_alumno 1.)
        if tabla == "alumno" and tiene_vida_academica(id_perfil):
            print(f"[PROTEGIDO] alumno · DNI {dni} · {nom} {ape} "
                  f"— tiene matrícula o pagos, no se toca.")
            continue
        cuentas.append((tabla, pk, id_perfil, id_usuario,
                        f"{tabla} · DNI {dni} · {nom} {ape}"))

# ------------------------------------------------- 2. conversaciones/mensajes
cur.execute("""
    SELECT m.id_mensaje, m.id_conversacion, m.contenido
    FROM mensaje m
""")
mensajes_prueba = [
    (idm, idc) for idm, idc, texto in cur.fetchall()
    if (texto or "").strip().lower() in SALUDOS_DE_PRUEBA
]

cur.execute("""
    SELECT c.id_conversacion
    FROM conversacion c
    LEFT JOIN mensaje m ON m.id_conversacion = c.id_conversacion
    GROUP BY c.id_conversacion
    HAVING COUNT(m.id_mensaje) = 0
""")
conversaciones_vacias = [f[0] for f in cur.fetchall()]

# Una conversación cuyo único mensaje era de prueba queda vacía: también sobra
ids_prueba = {idc for _, idc in mensajes_prueba}
for idc in ids_prueba:
    cur.execute("SELECT COUNT(*) FROM mensaje WHERE id_conversacion=%s", (idc,))
    total = cur.fetchone()[0]
    propios = sum(1 for _, c in mensajes_prueba if c == idc)
    if total == propios and idc not in conversaciones_vacias:
        conversaciones_vacias.append(idc)

# ------------------------------------------------------------------ informe
print(f"Base: {BD}\n")
print("=== Cuentas de prueba ===")
if not cuentas:
    print("   ninguna")
for _, _, _, id_usuario, desc in cuentas:
    print(f"   usuario {id_usuario}: {desc}")

print("\n=== Mensajes de prueba ===")
if not mensajes_prueba:
    print("   ninguno")
for idm, idc in mensajes_prueba:
    cur.execute("SELECT contenido FROM mensaje WHERE id_mensaje=%s", (idm,))
    print(f"   mensaje {idm} (conversación {idc}): {cur.fetchone()[0]!r}")

print("\n=== Conversaciones sin ningún mensaje ===")
print(f"   {conversaciones_vacias or 'ninguna'}")

if not (cuentas or mensajes_prueba or conversaciones_vacias):
    print("\nNada que limpiar.")
    con.close()
    sys.exit(0)

if not APLICAR:
    print("\nSimulación. Repite con --aplicar para borrar (se respalda antes).")
    con.close()
    sys.exit(0)

# ------------------------------------------------------------------ respaldo
carpeta = os.path.join(RAIZ, "scripts", "respaldos")
os.makedirs(carpeta, exist_ok=True)
sello = dt.datetime.now().strftime("%Y%m%d_%H%M")
ruta = os.path.join(carpeta, f"{BD}_datos_prueba_ANTES_{sello}.sql")

with open(ruta, "w", encoding="utf8") as fh:
    fh.write(f"-- Datos de prueba borrados de {BD} el {dt.datetime.now():%Y-%m-%d %H:%M}\n")
    fh.write("-- Volcar este archivo restaura exactamente lo eliminado.\n\n")
    for tabla, pk, id_perfil, id_usuario, _ in cuentas:
        for t, clave, valor in (("usuario", "id_usuario", id_usuario),
                                (tabla, pk, id_perfil)):
            cols = columnas(t)
            cur.execute(f"SELECT * FROM `{t}` WHERE `{clave}`=%s", (valor,))
            for fila in cur.fetchall():
                fh.write(insert_de(t, fila, cols) + "\n")
    for idm, _ in mensajes_prueba:
        cols = columnas("mensaje")
        cur.execute("SELECT * FROM mensaje WHERE id_mensaje=%s", (idm,))
        for fila in cur.fetchall():
            fh.write(insert_de("mensaje", fila, cols) + "\n")
    for idc in conversaciones_vacias:
        cols = columnas("conversacion")
        cur.execute("SELECT * FROM conversacion WHERE id_conversacion=%s", (idc,))
        for fila in cur.fetchall():
            fh.write(insert_de("conversacion", fila, cols) + "\n")

print(f"\nRespaldo escrito en:\n   {ruta}")

# ------------------------------------------------------------------- borrado
for idm, _ in mensajes_prueba:
    cur.execute("DELETE FROM mensaje WHERE id_mensaje=%s", (idm,))
print(f"\nMensajes borrados: {len(mensajes_prueba)}")

for idc in conversaciones_vacias:
    cur.execute("DELETE FROM conversacion WHERE id_conversacion=%s", (idc,))
print(f"Conversaciones borradas: {len(conversaciones_vacias)}")

for tabla, pk, id_perfil, id_usuario, desc in cuentas:
    # El perfil primero: apunta al usuario con clave foránea
    cur.execute(f"DELETE FROM `{tabla}` WHERE `{pk}`=%s", (id_perfil,))
    cur.execute("DELETE FROM usuario WHERE id_usuario=%s", (id_usuario,))
    print(f"Cuenta borrada: {desc}")

con.commit()

print("\n=== Totales después de limpiar ===")
for t in ("usuario", "alumno", "docente", "administrador", "psicologo",
          "auxiliar", "conversacion", "mensaje", "pago"):
    cur.execute(f"SELECT COUNT(*) FROM `{t}`")
    print(f"   {t:<14} {cur.fetchone()[0]}")
con.close()
