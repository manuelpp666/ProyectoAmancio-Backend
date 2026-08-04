"""
Aplica a una base existente los cambios de estructura introducidos en agosto 2026:

  1. usuario.debe_cambiar_password  (nueva)  -> cambio de clave en el primer ingreso
  2. seccion.nombre  VARCHAR(5) -> VARCHAR(30)  -> nombres "Amarillo"/"Azul" completos
  3. Se elimina la columna `sueldo` de docente, administrador, auxiliar y psicologo

Es idempotente: si un cambio ya está aplicado, lo salta. No toca ninguna otra
columna ni tabla, ni siquiera las que difieren por motivos históricos
(CHAR vs VARCHAR, ENUM vs VARCHAR, la tabla bitacora_admin, etc.).

Los usuarios que YA existen quedan con debe_cambiar_password = 0, para no
romper las sesiones de prueba en curso. Los que se creen desde ahora nacen
con 1 y tendrán que definir su clave al entrar.

Uso:
    python scripts/migrar_esquema.py <nombre_bd>            # muestra el plan
    python scripts/migrar_esquema.py <nombre_bd> --aplicar  # lo ejecuta
"""
import os
import sys
import argparse

import pymysql
from dotenv import load_dotenv

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(RAIZ, ".env"))

TABLAS_SUELDO = ("docente", "administrador", "auxiliar", "psicologo")


def conectar(bd):
    host, _, puerto = (os.getenv("DB_HOST") or "127.0.0.1").partition(":")
    return pymysql.connect(
        host=host.strip(), port=int(puerto or 3306),
        user=os.getenv("DB_USER"), password=os.getenv("DB_PASS") or "",
        database=bd, charset="utf8mb4",
    )


def existe_columna(cur, bd, tabla, columna):
    cur.execute("""
        SELECT COUNT(*) FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME=%s
    """, (bd, tabla, columna))
    return cur.fetchone()[0] > 0


def tipo_columna(cur, bd, tabla, columna):
    cur.execute("""
        SELECT COLUMN_TYPE FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME=%s
    """, (bd, tabla, columna))
    fila = cur.fetchone()
    return fila[0] if fila else None


def construir_plan(cur, bd):
    """Devuelve [(descripcion, [sentencias...])] con lo que falta por hacer."""
    plan = []

    # 1. usuario.debe_cambiar_password
    if existe_columna(cur, bd, "usuario", "debe_cambiar_password"):
        plan.append(("usuario.debe_cambiar_password ya existe", []))
    else:
        plan.append((
            "AÑADIR usuario.debe_cambiar_password (los usuarios actuales quedan en 0)",
            [
                "ALTER TABLE `usuario` ADD COLUMN `debe_cambiar_password` "
                "TINYINT(1) NOT NULL DEFAULT 1",
                "UPDATE `usuario` SET `debe_cambiar_password` = 0",
            ],
        ))

    # 2. seccion.nombre
    actual = tipo_columna(cur, bd, "seccion", "nombre")
    if actual and actual.lower().startswith("varchar(") and actual != "varchar(30)":
        plan.append((
            f"AMPLIAR seccion.nombre de {actual} a varchar(30)",
            ["ALTER TABLE `seccion` MODIFY COLUMN `nombre` VARCHAR(30) NOT NULL"],
        ))
    else:
        plan.append((f"seccion.nombre ya es {actual}", []))

    # 3. eliminar sueldo
    for tabla in TABLAS_SUELDO:
        if existe_columna(cur, bd, tabla, "sueldo"):
            cur.execute(f"SELECT COUNT(*) FROM `{tabla}` WHERE `sueldo` > 0")
            con_valor = cur.fetchone()[0]
            nota = f" (OJO: {con_valor} fila(s) con sueldo > 0)" if con_valor else ""
            plan.append((
                f"ELIMINAR {tabla}.sueldo{nota}",
                [f"ALTER TABLE `{tabla}` DROP COLUMN `sueldo`"],
            ))
        else:
            plan.append((f"{tabla}.sueldo ya no existe", []))

    return plan


def volcar_sueldos(cur, bd, destino):
    """Guarda los sueldos actuales antes de borrarlos, por si hacen falta."""
    lineas = [f"-- Sueldos de {bd} rescatados antes de eliminar la columna", ""]
    hubo = False
    for tabla in TABLAS_SUELDO:
        if not existe_columna(cur, bd, tabla, "sueldo"):
            continue
        clave = {"docente": "id_docente", "administrador": "id_admin",
                 "auxiliar": "id_auxiliar", "psicologo": "id_psicologo"}[tabla]
        cur.execute(f"SELECT `{clave}`, dni, apellidos, nombres, sueldo FROM `{tabla}`")
        filas = cur.fetchall()
        if not filas:
            continue
        hubo = True
        lineas.append(f"-- {tabla}")
        for _id, dni, ape, nom, sueldo in filas:
            lineas.append(f"--   id={_id}  dni={dni}  {ape}, {nom}  sueldo={sueldo}")
        lineas.append("")
    if hubo:
        with open(destino, "w", encoding="utf-8") as f:
            f.write("\n".join(lineas))
        return destino
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bd", help="Nombre de la base de datos a migrar")
    ap.add_argument("--aplicar", action="store_true", help="Ejecuta los cambios")
    args = ap.parse_args()

    con = conectar(args.bd)
    cur = con.cursor()

    plan = construir_plan(cur, args.bd)
    pendientes = [(d, s) for d, s in plan if s]

    print("=" * 66)
    print(f"PLAN DE MIGRACIÓN PARA: {args.bd}")
    print("=" * 66)
    for desc, sentencias in plan:
        marca = "PENDIENTE" if sentencias else "  ya ok  "
        print(f"  [{marca}] {desc}")
        for s in sentencias:
            print(f"              {s}")

    if not pendientes:
        print("\nNada que hacer: la base ya tiene todos los cambios.")
        con.close()
        return 0

    if not args.aplicar:
        print(f"\n{len(pendientes)} cambio(s) pendiente(s). "
              f"Vuelve a ejecutar con --aplicar para hacerlos efectivos.")
        con.close()
        return 0

    # Rescatar los sueldos antes de perderlos
    destino = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "respaldos", f"sueldos_{args.bd}.txt")
    guardado = volcar_sueldos(cur, args.bd, destino)
    if guardado:
        print(f"\nSueldos guardados en: {guardado}")

    print("\nAplicando...")
    for desc, sentencias in pendientes:
        for s in sentencias:
            cur.execute(s)
        print(f"  hecho: {desc}")
    con.commit()

    # Verificación
    print("\nVerificando...")
    restante = [d for d, s in construir_plan(cur, args.bd) if s]
    if restante:
        print("  QUEDAN CAMBIOS SIN APLICAR:")
        for d in restante:
            print(f"    - {d}")
        con.close()
        return 1
    print("  Todos los cambios están aplicados.")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
