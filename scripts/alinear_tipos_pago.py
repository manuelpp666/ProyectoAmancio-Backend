"""
Deja los tipos de pago de una base igual que los de otra (normalmente los de
`segunda_amancio_bd`, que son los que el colegio tiene configurados de verdad)
y reapunta los pagos existentes a los nuevos identificadores.

Por qué hace falta: la carga inicial inventó sus propios tipos, y uno de ellos
—Matrícula, del 12-02 al 01-31— rompía el endpoint `/finance/tipos-pago`. El
schema `TipoPagoBase` valida que `fecha_vencimiento > fecha_inicio` comparando
cadenas "MM-DD", así que un rango que cruza el fin de año se rechaza y, como
la validación se aplica a cada fila de la respuesta, una sola fila inválida
tumbaba la lista completa.

Correspondencias (categoría a categoría, y los módulos por su concepto):
    VACANTE   -> Vacante
    MATRICULA -> Matricula
    PENSION   -> Pensión regular
    MODULO    -> Modulo 1 / Modulo 2  (según diga "I" o "II" el concepto)

Uso:
    python scripts/alinear_tipos_pago.py segunda_amancio_bd amancio_2026
    python scripts/alinear_tipos_pago.py segunda_amancio_bd amancio_2026 --aplicar
"""
import os
import re
import sys
import argparse

import pymysql
from dotenv import load_dotenv

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(RAIZ, ".env"))

COLUMNAS = ["id_tipo_pago", "categoria", "nombre", "costo", "fecha_inicio",
            "fecha_vencimiento", "mora", "accion_vencimiento", "activo",
            "periodo_academico"]


def conectar():
    host, _, puerto = (os.getenv("DB_HOST") or "127.0.0.1").partition(":")
    return pymysql.connect(host=host.strip(), port=int(puerto or 3306),
                           user=os.getenv("DB_USER"),
                           password=os.getenv("DB_PASS") or "", charset="utf8mb4")


def es_modulo_dos(concepto: str) -> bool:
    """True si el concepto se refiere al módulo II. 'MODULOS II 2025' -> True."""
    return bool(re.search(r"\bII\b", (concepto or "").upper()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("origen")
    ap.add_argument("destino")
    ap.add_argument("--aplicar", action="store_true")
    args = ap.parse_args()

    con = conectar()
    cur = con.cursor()

    campos = ", ".join(f"`{c}`" for c in COLUMNAS)
    cur.execute(f"SELECT {campos} FROM `{args.origen}`.tipo_pago ORDER BY id_tipo_pago")
    nuevos = cur.fetchall()
    if not nuevos:
        print(f"ABORTADO: {args.origen} no tiene tipos de pago.")
        return 1

    cur.execute(f"SELECT id_tipo_pago, categoria, nombre FROM `{args.destino}`.tipo_pago")
    actuales = cur.fetchall()

    print("=" * 72)
    print(f"TIPOS DE PAGO: {args.origen}  ->  {args.destino}")
    print("=" * 72)
    print("\n  Se instalarán:")
    for n in nuevos:
        d = dict(zip(COLUMNAS, n))
        print(f"    id={d['id_tipo_pago']:<3} {d['categoria']:<10} {d['nombre']:<18} "
              f"S/{d['costo']}  {d['fecha_inicio']} -> {d['fecha_vencimiento']}")

    # Índice por categoría del destino
    por_categoria = {}
    for n in nuevos:
        d = dict(zip(COLUMNAS, n))
        por_categoria.setdefault(d["categoria"], []).append(d)

    print("\n  Reapuntado de los pagos existentes:")
    plan = []          # (id_viejo, id_nuevo, condicion_extra, cantidad)
    sin_destino = []
    for id_viejo, categoria, nombre in actuales:
        candidatos = por_categoria.get(categoria, [])
        cur.execute(f"SELECT COUNT(*) FROM `{args.destino}`.pago WHERE id_tipo_pago=%s", (id_viejo,))
        cantidad = cur.fetchone()[0]

        if not candidatos:
            if cantidad == 0:
                print(f"    id={id_viejo} ({categoria}) sin equivalente, pero no tiene pagos: se elimina")
            else:
                sin_destino.append((id_viejo, categoria, cantidad))
                print(f"    id={id_viejo} ({categoria}) SIN EQUIVALENTE y tiene {cantidad} pagos")
            continue

        if categoria == "MODULO" and len(candidatos) > 1:
            # Se reparte según el concepto de cada pago
            cur.execute(
                f"SELECT id_pago, concepto FROM `{args.destino}`.pago WHERE id_tipo_pago=%s",
                (id_viejo,))
            filas = cur.fetchall()
            uno = candidatos[0]["id_tipo_pago"]
            dos = candidatos[1]["id_tipo_pago"]
            ids_dos = [f[0] for f in filas if es_modulo_dos(f[1])]
            ids_uno = [f[0] for f in filas if not es_modulo_dos(f[1])]
            plan.append(("MODULO_SPLIT", id_viejo, uno, dos, ids_uno, ids_dos))
            print(f"    id={id_viejo} ({categoria}) -> {uno} ({len(ids_uno)} pagos) "
                  f"y {dos} ({len(ids_dos)} pagos)")
        else:
            destino_id = candidatos[0]["id_tipo_pago"]
            plan.append(("SIMPLE", id_viejo, destino_id, None, None, None))
            print(f"    id={id_viejo} ({categoria}) -> {destino_id}  ({cantidad} pagos)")

    if sin_destino:
        print("\nABORTADO: hay pagos que quedarían sin tipo. Revisa las categorías.")
        con.close()
        return 1

    if not args.aplicar:
        print("\nSimulación. Repite con --aplicar para ejecutarlo.")
        con.close()
        return 0

    print("\nAplicando...")
    # 1. Insertar los nuevos con ids temporales altos para no chocar
    marcas = ", ".join(["%s"] * len(COLUMNAS))
    for n in nuevos:
        d = dict(zip(COLUMNAS, n))
        cur.execute(f"SELECT COUNT(*) FROM `{args.destino}`.tipo_pago WHERE id_tipo_pago=%s",
                    (d["id_tipo_pago"],))
        if cur.fetchone()[0] == 0:
            cur.execute(f"INSERT INTO `{args.destino}`.tipo_pago ({campos}) VALUES ({marcas})",
                        list(n))
    print(f"  {len(nuevos)} tipos insertados")

    # 2. Reapuntar los pagos
    for entrada in plan:
        if entrada[0] == "SIMPLE":
            _, viejo, nuevo, _, _, _ = entrada
            cur.execute(f"UPDATE `{args.destino}`.pago SET id_tipo_pago=%s WHERE id_tipo_pago=%s",
                        (nuevo, viejo))
            print(f"  {cur.rowcount} pagos: {viejo} -> {nuevo}")
        else:
            _, viejo, uno, dos, ids_uno, ids_dos = entrada
            for ids, destino_id in ((ids_uno, uno), (ids_dos, dos)):
                for i in range(0, len(ids), 500):
                    trozo = ids[i:i + 500]
                    marcas_ids = ",".join(["%s"] * len(trozo))
                    cur.execute(
                        f"UPDATE `{args.destino}`.pago SET id_tipo_pago=%s "
                        f"WHERE id_pago IN ({marcas_ids})", [destino_id] + trozo)
                print(f"  {len(ids)} pagos: {viejo} -> {destino_id}")

    # 3. Borrar los tipos antiguos (ya sin pagos apuntando)
    ids_nuevos = {dict(zip(COLUMNAS, n))["id_tipo_pago"] for n in nuevos}
    for id_viejo, _, _ in actuales:
        if id_viejo in ids_nuevos:
            continue
        cur.execute(f"SELECT COUNT(*) FROM `{args.destino}`.pago WHERE id_tipo_pago=%s", (id_viejo,))
        if cur.fetchone()[0]:
            print(f"  OJO: el tipo {id_viejo} todavía tiene pagos, no se elimina")
            continue
        cur.execute(f"DELETE FROM `{args.destino}`.tipo_pago WHERE id_tipo_pago=%s", (id_viejo,))
    con.commit()

    print("\nResultado en el destino:")
    cur.execute(f"""SELECT tp.id_tipo_pago, tp.categoria, tp.nombre, tp.fecha_inicio,
                           tp.fecha_vencimiento, COUNT(p.id_pago)
                    FROM `{args.destino}`.tipo_pago tp
                    LEFT JOIN `{args.destino}`.pago p ON p.id_tipo_pago = tp.id_tipo_pago
                    GROUP BY tp.id_tipo_pago ORDER BY tp.id_tipo_pago""")
    for r in cur.fetchall():
        print(f"    id={r[0]:<3} {r[1]:<10} {r[2]:<18} {r[3]} -> {r[4]}   {r[5]:>6} pagos")
    cur.execute(f"SELECT COUNT(*) FROM `{args.destino}`.pago p "
                f"LEFT JOIN `{args.destino}`.tipo_pago t ON t.id_tipo_pago=p.id_tipo_pago "
                "WHERE t.id_tipo_pago IS NULL")
    print(f"    pagos huérfanos (sin tipo): {cur.fetchone()[0]}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
