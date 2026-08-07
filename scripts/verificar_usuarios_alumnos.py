"""
Comprueba que todo alumno activo tenga su cuenta del campus, y la crea si falta.

Todo alumno ADMITIDO o ESTUDIANTE necesita un usuario para entrar al campus. El
POSTULANTE no: solo envió una solicitud desde la web y puede acabar rechazado.

Revisa seis cosas:
  1. alumnos activos sin cuenta
  2. alumnos que apuntan a un usuario que ya no existe
  3. cuentas de alumno sin ficha (huérfanas)
  4. dos alumnos compartiendo la misma cuenta
  5. usuarios cuyo nombre no concuerda con el DNI del alumno
  6. cuentas de alumno con el rol equivocado

Con --aplicar crea las cuentas que falten (contraseña inicial: su DNI) y
sincroniza los usernames desincronizados. Lo demás solo lo informa: son casos
que conviene mirar a mano antes de tocar nada.

    python scripts/verificar_usuarios_alumnos.py
    python scripts/verificar_usuarios_alumnos.py --aplicar
"""
import os
import sys

import bcrypt
import pymysql
from dotenv import load_dotenv

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(RAIZ, ".env"))

APLICAR = "--aplicar" in sys.argv
ACTIVOS = ("ADMITIDO", "ESTUDIANTE")
RONDAS = int((os.getenv("BCRYPT_ROUNDS") or "12").strip())


def conectar():
    host, _, puerto = (os.getenv("DB_HOST") or "127.0.0.1").strip().partition(":")
    return pymysql.connect(
        host=host or "127.0.0.1", port=int(puerto or 3306),
        user=(os.getenv("DB_USER") or "root").strip(),
        password=os.getenv("DB_PASS") or "",
        database=(os.getenv("DB_NAME") or "amancio_2026").strip(),
        charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
    )


def titulo(n, texto):
    print(f"\n{'='*74}\n{n}. {texto}\n{'='*74}")


con = conectar()
cur = con.cursor()
marcador = ", ".join(["%s"] * len(ACTIVOS))
problemas = 0
reparados = 0

# ------------------------------------------------------------------ 1
titulo(1, "ALUMNOS ACTIVOS SIN CUENTA")
cur.execute(f"""
    SELECT id_alumno, dni, nombres, apellidos, estado_ingreso
    FROM alumno
    WHERE id_usuario IS NULL AND estado_ingreso IN ({marcador})
    ORDER BY id_alumno
""", ACTIVOS)
sin_cuenta = cur.fetchall()
print(f"  {len(sin_cuenta)} casos")
for a in sin_cuenta:
    problemas += 1
    print(f"    id={a['id_alumno']:<5} dni={str(a['dni']):<10} "
          f"{a['apellidos']}, {a['nombres']}  [{a['estado_ingreso']}]")
    if not APLICAR:
        continue
    if not (a["dni"] or "").strip():
        print("             sin DNI: no se le puede generar usuario, revisar a mano")
        continue
    username = f"ALU-{a['dni']}"
    cur.execute("SELECT id_usuario FROM usuario WHERE username = %s", (username,))
    fila = cur.fetchone()
    if fila:
        id_usuario = fila["id_usuario"]
        print(f"             ya existía {username}, se reutiliza")
    else:
        hash_dni = bcrypt.hashpw(a["dni"].encode(), bcrypt.gensalt(rounds=RONDAS)).decode()
        cur.execute("""
            INSERT INTO usuario (username, password_hash, rol, activo,
                                 debe_cambiar_password)
            VALUES (%s, %s, 'ALUMNO', 1, 1)
        """, (username, hash_dni))
        id_usuario = cur.lastrowid
        print(f"             creada {username} (contraseña inicial: su DNI)")
    cur.execute("UPDATE alumno SET id_usuario = %s WHERE id_alumno = %s",
                (id_usuario, a["id_alumno"]))
    reparados += 1

# ------------------------------------------------------------------ 2
titulo(2, "ALUMNOS QUE APUNTAN A UN USUARIO INEXISTENTE")
cur.execute("""
    SELECT a.id_alumno, a.id_usuario, a.dni, a.nombres, a.apellidos
    FROM alumno a LEFT JOIN usuario u ON u.id_usuario = a.id_usuario
    WHERE a.id_usuario IS NOT NULL AND u.id_usuario IS NULL
""")
filas = cur.fetchall()
problemas += len(filas)
print(f"  {len(filas)} casos" + ("  (revisar a mano)" if filas else ""))
for f in filas:
    print("   ", f)

# ------------------------------------------------------------------ 3
titulo(3, "CUENTAS DE ALUMNO SIN FICHA (huérfanas)")
cur.execute("""
    SELECT u.id_usuario, u.username, u.activo
    FROM usuario u LEFT JOIN alumno a ON a.id_usuario = u.id_usuario
    WHERE u.rol = 'ALUMNO' AND a.id_alumno IS NULL
""")
filas = cur.fetchall()
problemas += len(filas)
print(f"  {len(filas)} casos" + ("  (revisar a mano)" if filas else ""))
for f in filas:
    print("   ", f)

# ------------------------------------------------------------------ 4
titulo(4, "DOS ALUMNOS COMPARTIENDO LA MISMA CUENTA")
cur.execute("""
    SELECT id_usuario, COUNT(*) c, GROUP_CONCAT(id_alumno) ids
    FROM alumno WHERE id_usuario IS NOT NULL
    GROUP BY id_usuario HAVING c > 1
""")
filas = cur.fetchall()
problemas += len(filas)
print(f"  {len(filas)} casos" + ("  (revisar a mano)" if filas else ""))
for f in filas:
    print("   ", f)

# ------------------------------------------------------------------ 5
titulo(5, "USERNAME QUE NO CONCUERDA CON EL DNI")
cur.execute("""
    SELECT a.id_alumno, a.dni, a.nombres, a.apellidos,
           u.id_usuario, u.username
    FROM alumno a JOIN usuario u ON u.id_usuario = a.id_usuario
    WHERE u.username <> CONCAT('ALU-', a.dni)
    ORDER BY a.id_alumno
""")
filas = cur.fetchall()
print(f"  {len(filas)} casos")
for f in filas:
    problemas += 1
    esperado = f"ALU-{f['dni']}"
    print(f"    id={f['id_alumno']:<5} dni={f['dni']}  "
          f"{f['username']} -> {esperado}   {f['apellidos']}, {f['nombres']}")
    if not APLICAR:
        continue
    cur.execute("SELECT id_usuario FROM usuario WHERE username = %s AND id_usuario <> %s",
                (esperado, f["id_usuario"]))
    if cur.fetchone():
        print("             ese username ya lo usa otra cuenta: revisar a mano")
        continue
    cur.execute("UPDATE usuario SET username = %s WHERE id_usuario = %s",
                (esperado, f["id_usuario"]))
    reparados += 1

# ------------------------------------------------------------------ 6
titulo(6, "CUENTAS DE ALUMNO CON ROL EQUIVOCADO")
cur.execute("""
    SELECT u.id_usuario, u.username, u.rol, a.id_alumno
    FROM alumno a JOIN usuario u ON u.id_usuario = a.id_usuario
    WHERE u.rol <> 'ALUMNO'
""")
filas = cur.fetchall()
problemas += len(filas)
print(f"  {len(filas)} casos" + ("  (revisar a mano)" if filas else ""))
for f in filas:
    print("   ", f)

# ------------------------------------------------------------------ resumen
print(f"\n{'#'*74}")
if not problemas:
    print("Todo correcto: cada alumno activo tiene su cuenta y es coherente.")
elif APLICAR:
    con.commit()
    print(f"{problemas} incidencias encontradas, {reparados} reparadas.")
    if problemas > reparados:
        print("El resto necesita revisarse a mano (ver arriba).")
else:
    print(f"{problemas} incidencias. Para reparar las que se pueden:")
    print("  python scripts/verificar_usuarios_alumnos.py --aplicar")
print(f"{'#'*74}")

con.close()
