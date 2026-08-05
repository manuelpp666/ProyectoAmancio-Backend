"""
Copia el contenido de la página pública de una base a otra:

  · pagina_configuracion  (textos e imágenes de Inicio, Nosotros, Noticias,
                           Docentes, Admisión, Calendario, Footer y Login)
  · noticia               (las publicaciones del portal)
  · evento                (el calendario académico)

La carga inicial (`generar_carga_inicial.py`) NO incluye nada de esto a
propósito: no sale del PDF ni de los Excel del colegio, sino de lo que se fue
editando desde el panel. Por eso se migra aparte, desde la base anterior.

Qué se ajusta al copiar:
  · pagina_configuracion.clave es UNIQUE -> si la clave ya existe se ACTUALIZA
    su valor, no se duplica.
  · noticia.id_autor apunta a un usuario que en la base nueva es otra persona.
    Se reasigna al administrador que se indique (por defecto, el primer ADMIN).
  · evento.id_anio_escolar debe existir en la base destino; los eventos de un
    año que no exista allí se omiten y se avisa.

Uso:
    python scripts/migrar_contenido_web.py segunda_amancio_bd amancio_2026
    python scripts/migrar_contenido_web.py segunda_amancio_bd amancio_2026 --aplicar
"""
import os
import sys
import argparse

import pymysql
from dotenv import load_dotenv

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(RAIZ, ".env"))


def conectar():
    host, _, puerto = (os.getenv("DB_HOST") or "127.0.0.1").partition(":")
    return pymysql.connect(
        host=host.strip(), port=int(puerto or 3306),
        user=os.getenv("DB_USER"), password=os.getenv("DB_PASS") or "",
        charset="utf8mb4",
    )


def columnas(cur, bd, tabla):
    cur.execute("""
        SELECT COLUMN_NAME FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION
    """, (bd, tabla))
    return [r[0] for r in cur.fetchall()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("origen")
    ap.add_argument("destino")
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--autor", type=int, default=None,
                    help="id_usuario que quedará como autor de las noticias")
    args = ap.parse_args()

    con = conectar()
    cur = con.cursor()

    # ── Autor de destino para las noticias ─────────────────────────────────
    id_autor = args.autor
    if id_autor is None:
        cur.execute(f"SELECT id_usuario FROM `{args.destino}`.usuario "
                    "WHERE rol='ADMIN' ORDER BY id_usuario LIMIT 1")
        fila = cur.fetchone()
        id_autor = fila[0] if fila else None
    if id_autor is None:
        print("ABORTADO: la base destino no tiene ningún usuario ADMIN "
              "al que asignar la autoría de las noticias.")
        return 1
    cur.execute(f"SELECT username FROM `{args.destino}`.usuario WHERE id_usuario=%s", (id_autor,))
    nombre_autor = (cur.fetchone() or ["?"])[0]

    print("=" * 70)
    print(f"CONTENIDO WEB: {args.origen}  ->  {args.destino}")
    print("=" * 70)
    print(f"  Autor de las noticias en destino: id={id_autor} ({nombre_autor})\n")

    # ── 1. pagina_configuracion ────────────────────────────────────────────
    cur.execute(f"SELECT seccion, clave, valor, tipo FROM `{args.origen}`.pagina_configuracion")
    config = cur.fetchall()
    cur.execute(f"SELECT clave FROM `{args.destino}`.pagina_configuracion")
    ya_estan = {r[0] for r in cur.fetchall()}
    nuevas = [c for c in config if c[1] not in ya_estan]
    actualizar = [c for c in config if c[1] in ya_estan]
    print(f"  pagina_configuracion: {len(nuevas)} a insertar, "
          f"{len(actualizar)} a actualizar")

    # ── 2. noticia ─────────────────────────────────────────────────────────
    cols_not = [c for c in columnas(cur, args.origen, "noticia") if c != "id_noticia"]
    cur.execute(f"SELECT {', '.join(f'`{c}`' for c in cols_not)} FROM `{args.origen}`.noticia")
    noticias = cur.fetchall()
    cur.execute(f"SELECT COUNT(*) FROM `{args.destino}`.noticia")
    print(f"  noticia: {len(noticias)} a copiar (el destino tiene {cur.fetchone()[0]})")

    # ── 3. evento ──────────────────────────────────────────────────────────
    cols_ev = [c for c in columnas(cur, args.origen, "evento") if c != "id_evento"]
    cur.execute(f"SELECT {', '.join(f'`{c}`' for c in cols_ev)} FROM `{args.origen}`.evento")
    eventos = cur.fetchall()
    cur.execute(f"SELECT id_anio_escolar FROM `{args.destino}`.anio_escolar")
    anios_destino = {r[0] for r in cur.fetchall()}
    i_anio = cols_ev.index("id_anio_escolar")
    eventos_ok = [e for e in eventos if e[i_anio] in anios_destino]
    eventos_no = [e for e in eventos if e[i_anio] not in anios_destino]
    print(f"  evento: {len(eventos_ok)} a copiar"
          + (f", {len(eventos_no)} omitidos por año inexistente" if eventos_no else ""))
    for e in eventos_no:
        print(f"      omitido: año {e[i_anio]!r} no existe en {args.destino}")

    if not args.aplicar:
        print("\nSimulación. Vuelve a ejecutar con --aplicar para copiarlo.")
        con.close()
        return 0

    # ── Aplicar ────────────────────────────────────────────────────────────
    print("\nCopiando...")

    for seccion, clave, valor, tipo in config:
        if clave in ya_estan:
            cur.execute(
                f"UPDATE `{args.destino}`.pagina_configuracion "
                "SET seccion=%s, valor=%s, tipo=%s WHERE clave=%s",
                (seccion, valor, tipo, clave))
        else:
            cur.execute(
                f"INSERT INTO `{args.destino}`.pagina_configuracion "
                "(seccion, clave, valor, tipo) VALUES (%s,%s,%s,%s)",
                (seccion, clave, valor, tipo))
    print(f"  pagina_configuracion: {len(config)} claves")

    if noticias:
        i_autor = cols_not.index("id_autor") if "id_autor" in cols_not else None
        marcas = ", ".join(["%s"] * len(cols_not))
        campos = ", ".join(f"`{c}`" for c in cols_not)
        for n in noticias:
            fila = list(n)
            if i_autor is not None:
                fila[i_autor] = id_autor  # el autor original no existe aquí
            cur.execute(
                f"INSERT INTO `{args.destino}`.noticia ({campos}) VALUES ({marcas})", fila)
        print(f"  noticia: {len(noticias)} publicaciones")

    if eventos_ok:
        marcas = ", ".join(["%s"] * len(cols_ev))
        campos = ", ".join(f"`{c}`" for c in cols_ev)
        for e in eventos_ok:
            cur.execute(
                f"INSERT INTO `{args.destino}`.evento ({campos}) VALUES ({marcas})", list(e))
        print(f"  evento: {len(eventos_ok)} eventos")

    con.commit()

    # ── Verificación ───────────────────────────────────────────────────────
    print("\nVerificando en el destino:")
    for tabla in ("pagina_configuracion", "noticia", "evento"):
        cur.execute(f"SELECT COUNT(*) FROM `{args.destino}`.`{tabla}`")
        print(f"  {tabla:<22} {cur.fetchone()[0]:>4} filas")
    cur.execute(f"SELECT COUNT(*) FROM `{args.destino}`.noticia n "
                f"LEFT JOIN `{args.destino}`.usuario u ON u.id_usuario=n.id_autor "
                "WHERE n.id_autor IS NOT NULL AND u.id_usuario IS NULL")
    print(f"  noticias con autor inválido: {cur.fetchone()[0]}")

    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
