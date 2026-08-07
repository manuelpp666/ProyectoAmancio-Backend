"""
Devuelve a su valor correcto los DNI de personal que fueron sobrescritos.

QUÉ PASÓ
--------
La carga inicial (scripts/carga_inicial_2026.sql, 03/08/2026) insertó los DNI
correctos, tomados del directorio del colegio y transcritos en
scripts/datos_personal.py. Después, cinco fichas quedaron con el mismo valor
'99999901', que no aparece en ningún punto del código ni del directorio. Y no
son cinco cualesquiera: es la PRIMERA ficha (id=1) de cada una de las cinco
tablas de personas.

    administrador id=1  Tomás Serquén Montehermozo       99999901 -> 16793446
    psicologo     id=1  Brhygitte Leiva Castillo         99999901 -> 74877335
    auxiliar      id=1  Daysi Massiel Sánchez De La Cruz 99999901 -> 44436396
    docente       id=1  Carmen del Rosario Rodrigo Cieza 99999901 -> 16774730
    alumno        id=1  Gadiel Emilio Aquino Navarro     99999901 -> 91489647

El resto está intacto: las otras 44 fichas de personal, sus 45 teléfonos y los
576 alumnos restantes coinciden exactamente con la carga inicial.

Como el username se deriva del DNI, esas cinco personas quedaron sin poder
entrar con el usuario que les corresponde. Este script corrige el DNI y
regenera el username, igual que hace la aplicación al editar una ficha.

NO toca las contraseñas: siguen siendo las mismas de siempre.

USO
---
    python scripts/corregir_dni_personal.py            # solo muestra el plan
    python scripts/corregir_dni_personal.py --aplicar  # respalda y corrige
"""
import datetime
import os
import sys

import pymysql
from dotenv import load_dotenv

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "scripts"))
load_dotenv(os.path.join(RAIZ, ".env"))

PREFIJO_POR_ROL = {"ADMIN": "ADM", "DOCENTE": "DOC", "AUXILIAR": "AUX",
                   "PSICOLOGO": "PSI", "ALUMNO": "ALU"}

# (tabla, clave primaria, id del registro, dni correcto)
# Los cuatro primeros salen del directorio 2026 (scripts/datos_personal.py);
# el del alumno, de la carga inicial (scripts/carga_inicial_2026.sql, línea 969).
CORRECCIONES = [
    ("administrador", "id_admin", 1, "16793446"),
    ("psicologo", "id_psicologo", 1, "74877335"),
    ("auxiliar", "id_auxiliar", 1, "44436396"),
    ("docente", "id_docente", 1, "16774730"),
    ("alumno", "id_alumno", 1, "91489647"),
]


def conectar():
    host_completo = (os.getenv("DB_HOST") or "127.0.0.1").strip()
    host, _, puerto = host_completo.partition(":")
    return pymysql.connect(
        host=host or "127.0.0.1",
        port=int(puerto or 3306),
        user=(os.getenv("DB_USER") or "root").strip(),
        password=os.getenv("DB_PASS") or "",
        database=(os.getenv("DB_NAME") or "amancio_2026").strip(),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def plan(cur):
    """Calcula qué hay que cambiar y comprueba que nada choque."""
    pasos, problemas = [], []
    for tabla, pk, idr, dni_correcto in CORRECCIONES:
        cur.execute(f"""
            SELECT t.{pk} AS id, t.dni, t.nombres, t.apellidos,
                   u.id_usuario, u.username, u.rol
            FROM `{tabla}` t JOIN usuario u ON u.id_usuario = t.id_usuario
            WHERE t.{pk} = %s
        """, (idr,))
        f = cur.fetchone()
        if not f:
            problemas.append(f"{tabla} id={idr} no existe")
            continue
        if f["dni"] == dni_correcto:
            print(f"  [YA CORRECTO] {tabla} id={idr}: {dni_correcto}")
            continue

        username_nuevo = f"{PREFIJO_POR_ROL[f['rol']]}-{dni_correcto}"

        # ¿El DNI destino ya lo usa otra ficha de la misma tabla?
        cur.execute(f"SELECT {pk} AS id FROM `{tabla}` WHERE dni = %s AND {pk} <> %s",
                    (dni_correcto, idr))
        choque = cur.fetchone()
        if choque:
            problemas.append(f"{tabla}: el DNI {dni_correcto} ya lo tiene id={choque['id']}")
            continue

        # ¿El username destino ya existe en otra cuenta?
        cur.execute("SELECT id_usuario FROM usuario WHERE username = %s AND id_usuario <> %s",
                    (username_nuevo, f["id_usuario"]))
        choque = cur.fetchone()
        if choque:
            problemas.append(f"usuario: {username_nuevo} ya lo usa id_usuario="
                             f"{choque['id_usuario']}")
            continue

        pasos.append({
            "tabla": tabla, "pk": pk, "id": idr,
            "quien": f"{f['apellidos']}, {f['nombres']}",
            "dni_actual": f["dni"], "dni_nuevo": dni_correcto,
            "id_usuario": f["id_usuario"],
            "username_actual": f["username"], "username_nuevo": username_nuevo,
        })
    return pasos, problemas


def respaldar(cur, pasos, destino):
    """Guarda los UPDATE que deshacen exactamente estos cambios."""
    lineas = [
        f"-- Respaldo previo a corregir DNI de personal, "
        f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}",
        "-- Ejecutar este archivo revierte la corrección.",
        "",
    ]
    for p in pasos:
        lineas.append(
            f"UPDATE `{p['tabla']}` SET `dni` = '{p['dni_actual']}' "
            f"WHERE `{p['pk']}` = {p['id']};")
        lineas.append(
            f"UPDATE `usuario` SET `username` = '{p['username_actual']}' "
            f"WHERE `id_usuario` = {p['id_usuario']};")
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lineas) + "\n")


def main():
    aplicar = "--aplicar" in sys.argv
    con = conectar()
    try:
        with con.cursor() as cur:
            pasos, problemas = plan(cur)

            if problemas:
                print("\nNo se puede continuar:")
                for p in problemas:
                    print("  -", p)
                return 1

            if not pasos:
                print("\nNo hay nada que corregir.")
                return 0

            print(f"\n{'':2}{'FICHA':<32}{'DNI':<24}{'USUARIO'}")
            print("  " + "-" * 92)
            for p in pasos:
                print(f"  {p['quien'][:30]:<32}"
                      f"{p['dni_actual']} -> {p['dni_nuevo']:<10}"
                      f"{p['username_actual']} -> {p['username_nuevo']}")

            if not aplicar:
                print("\nSimulación. Para aplicarlo de verdad:")
                print("  python scripts/corregir_dni_personal.py --aplicar")
                return 0

            destino = os.path.join(
                RAIZ, "scripts", "respaldos",
                f"dni_personal_ANTES_{datetime.datetime.now():%Y%m%d_%H%M}.sql")
            respaldar(cur, pasos, destino)
            print(f"\nRespaldo escrito en:\n  {destino}")

            for p in pasos:
                cur.execute(
                    f"UPDATE `{p['tabla']}` SET dni = %s WHERE `{p['pk']}` = %s",
                    (p["dni_nuevo"], p["id"]))
                cur.execute(
                    "UPDATE usuario SET username = %s WHERE id_usuario = %s",
                    (p["username_nuevo"], p["id_usuario"]))
            con.commit()
            print(f"\n{len(pasos)} fichas corregidas.")

            # Comprobación posterior: leer de vuelta lo que quedó escrito.
            print("\nComprobación:")
            for p in pasos:
                cur.execute(f"""
                    SELECT t.dni, u.username FROM `{p['tabla']}` t
                    JOIN usuario u ON u.id_usuario = t.id_usuario
                    WHERE t.`{p['pk']}` = %s
                """, (p["id"],))
                f = cur.fetchone()
                ok = f["dni"] == p["dni_nuevo"] and f["username"] == p["username_nuevo"]
                print(f"  {'OK ' if ok else 'MAL'} {p['quien'][:34]:<36}"
                      f"dni={f['dni']}  usuario={f['username']}")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
