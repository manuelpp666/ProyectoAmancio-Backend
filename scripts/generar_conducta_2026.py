# -*- coding: utf-8 -*-
"""
generar_conducta_2026.py
I.E.P. Amancio Varona - Generador del SQL de migración de CONDUCTA 2026

QUÉ HACE
--------
Lee la conducta del sistema antiguo (base local `amanciov_2018_analisis`,
tabla `notas` con `codigoAsig = 24`, año 2026) y la cruza con el DNI del
sistema nuevo usando el CSV YA VALIDADO
`Extraccion_Notas_Antiguas\\notas_2026_bim1_bim2_detalle.csv`
(columnas `id_alumno_antiguo` / `dni_sistema_nuevo`). Con eso escribe un
archivo .sql con los valores ya resueltos como literales.

Por qué un generador y no SQL a mano: el cliente pega el .sql en phpMyAdmin
contra su hosting, donde la base antigua NO existe. El .sql final tiene que
poder ejecutarse solo, sin volver a tocar `amanciov_2018_analisis`.

NO se cruza por nombre: los nombres del CSV traen mojibake ("IDROGO FARRO
ITZEL ABIGAÃL") y acentos inconsistentes. El único cruce válido es por
`id_alumno_antiguo` -> `dni_sistema_nuevo`, tal cual quedó en el CSV.

QUÉ NO HACE
-----------
Este script no escribe nada en ninguna base de datos: solo LEE (la base
antigua, la nueva y el CSV) y genera el archivo .sql. Los alumnos con
conducta que no aparecen en el CSV se listan en pantalla y quedan fuera del
.sql, documentados en un comentario dentro del propio archivo.

SALIDA
------
    ...\\Extraccion_Notas_Antiguas\\sql\\20_conducta_2026.sql

USO
---
    cd "ProyectoAmancio-Backend"
    .venv\\Scripts\\python.exe scripts\\generar_conducta_2026.py
"""

import os
import sys
import csv

BACK = r"C:\Users\jesus\OneDrive\Documentos\Proyecto Amancio Varona\ProyectoAmancio-Backend"
os.chdir(BACK)
sys.path.insert(0, BACK)
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(BACK, ".env"))

from sqlalchemy import create_engine, text  # noqa: E402

# ---------------------------------------------------------------------------
# Conexión a las dos bases LOCALES a la vez: la antigua para leer la
# conducta, la nueva solo para comprobar el cruce antes de escribir el .sql
# (esa comprobación es un plus del generador; el .sql final trae sus propias
# comprobaciones y no depende de que esto se haya corrido antes).
# ---------------------------------------------------------------------------
USUARIO = os.getenv("DB_USER")
CLAVE = os.getenv("DB_PASS") or ""
HOST = (os.getenv("DB_HOST") or "").strip()

engine_antigua = create_engine(f"mysql+pymysql://{USUARIO}:{CLAVE}@{HOST}/amanciov_2018_analisis")
engine_nueva = create_engine(f"mysql+pymysql://{USUARIO}:{CLAVE}@{HOST}/amanciov_hosting")

RUTA_CSV = (
    r"C:\Users\jesus\OneDrive\Documentos\Proyecto Amancio Varona"
    r"\Extraccion_Notas_Antiguas\notas_2026_bim1_bim2_detalle.csv"
)
RUTA_SQL_SALIDA = (
    r"C:\Users\jesus\OneDrive\Documentos\Proyecto Amancio Varona"
    r"\Extraccion_Notas_Antiguas\sql\20_conducta_2026.sql"
)

CODIGO_ASIG_CONDUCTA = 24
ANIO = 2026
FILAS_POR_INSERT = 200  # tamaño de cada bloque VALUES, para que el .sql sea legible

# Los dos alumnos de la prueba de humo (conducta 16 en bimestre 1, sacada de
# su libreta oficial en PDF). Se usan solo para el comentario del .sql.
ALUMNOS_PRUEBA = {
    "78793982": "CAMBILLO CARHUA GINO ANCEL (6to Azul primaria)",
    "78369886": "IDROGO FARRO ITZEL ABIGAIL (1ero B secundaria)",
}


def cargar_cruce_csv():
    """Construye {id_alumno_antiguo: dni_sistema_nuevo} desde el CSV ya
    validado. Separador ';', encoding utf-8-sig (trae BOM)."""
    mapping = {}
    with open(RUTA_CSV, encoding="utf-8-sig", newline="") as f:
        lector = csv.DictReader(f, delimiter=";")
        for fila in lector:
            id_antiguo = (fila.get("id_alumno_antiguo") or "").strip()
            dni = (fila.get("dni_sistema_nuevo") or "").strip()
            if id_antiguo and dni:
                mapping[id_antiguo] = dni
    return mapping


def leer_conducta_antigua():
    """Todas las filas de conducta (codigoAsig=24) del año 2026 en la base
    antigua, con el nombre del alumno antiguo para poder documentar a los
    que se queden sin cruce."""
    with engine_antigua.connect() as con:
        filas = con.execute(
            text(
                """
                SELECT n.id_alumno, n.bimestre, n.nota, a.apellidos, a.nombres
                  FROM notas n
                  JOIN alumno a ON a.id_alumno = n.id_alumno
                 WHERE n.codigoAsig = :codigo
                   AND n.anio_escolar = :anio
                """
            ),
            {"codigo": CODIGO_ASIG_CONDUCTA, "anio": ANIO},
        ).fetchall()
    return filas


def dnis_sin_matricula_2026(dnis):
    """De una lista de DNIs, cuáles NO tienen matrícula 2026 en la base
    nueva local. Sirve para avisar ANTES de generar el .sql si el cruce del
    CSV quedó desactualizado."""
    if not dnis:
        return []
    faltantes = []
    with engine_nueva.connect() as con:
        for i in range(0, len(dnis), 200):
            trozo = dnis[i : i + 200]
            marcadores = ", ".join(f"'{d}'" for d in trozo)
            encontrados = {
                r[0]
                for r in con.execute(
                    text(
                        f"""
                        SELECT a.dni
                          FROM alumno a
                          JOIN matricula m ON m.id_alumno = a.id_alumno
                         WHERE m.id_anio_escolar = '2026'
                           AND a.dni IN ({marcadores})
                        """
                    )
                ).fetchall()
            }
            faltantes.extend(d for d in trozo if d not in encontrados)
    return faltantes


def formatear_valores(resueltas):
    """Bloques 'VALUES (...), (...), ...' de a lo sumo FILAS_POR_INSERT filas,
    listos para pegar en INSERT INTO tmp_conducta_2026."""
    bloques = []
    for i in range(0, len(resueltas), FILAS_POR_INSERT):
        trozo = resueltas[i : i + FILAS_POR_INSERT]
        lineas = [
            f"  ('{dni}', {bimestre}, {nota:.2f})" for dni, bimestre, nota in trozo
        ]
        bloques.append(",\n".join(lineas))
    return bloques


def generar_sql(resueltas, sin_cruce, faltantes_matricula):
    total = len(resueltas)
    por_bimestre = {}
    for _, bimestre, _ in resueltas:
        por_bimestre[bimestre] = por_bimestre.get(bimestre, 0) + 1
    resumen_bimestres = ", ".join(
        f"bimestre {b}: {c}" for b, c in sorted(por_bimestre.items())
    )

    if sin_cruce:
        lineas_sin_cruce = "\n".join(
            f"--   id_alumno_antiguo={id_alumno}  bimestre={bimestre}  nota={nota}  "
            f"{apellidos.strip()}, {nombres.strip()}"
            for id_alumno, bimestre, nota, apellidos, nombres in sin_cruce
        )
    else:
        lineas_sin_cruce = "--   (ninguno: todos los alumnos con conducta tuvieron cruce en el CSV)"

    bloques_values = formatear_valores(resueltas)
    inserts_tmp = "\n\n".join(
        f"INSERT INTO `tmp_conducta_2026` (`dni`, `bimestre`, `valor`) VALUES\n{bloque};"
        for bloque in bloques_values
    )

    aviso_matricula = (
        "-- AVISO: al generar este archivo, estos DNIs del cruce NO tenían matrícula\n"
        "-- 2026 en la base nueva local. Si sigue apareciendo algo en el bloque 6 de\n"
        "-- abajo al ejecutar contra el hosting, hay que investigarlo antes de dar por\n"
        "-- buena la migración:\n"
        + "\n".join(f"--   {d}" for d in faltantes_matricula)
        if faltantes_matricula
        else "-- Ninguno: al generar este archivo, los %d DNIs del cruce tenían matrícula 2026." % total
    )

    lineas_prueba = "\n".join(
        f"--   {dni}  ->  {desc}" for dni, desc in ALUMNOS_PRUEBA.items()
    )
    dnis_prueba_sql = ", ".join(f"'{dni}'" for dni in ALUMNOS_PRUEBA)

    return f"""-- =====================================================================
-- 20_conducta_2026.sql
-- I.E.P. Amancio Varona - Migración de CONDUCTA 2026 (sistema antiguo -> nuevo)
-- =====================================================================
--
-- GENERADO AUTOMÁTICAMENTE por scripts/generar_conducta_2026.py. No editar a
-- mano los bloques de VALUES: si hace falta corregir algo, se corrige el
-- cruce (el CSV) o el generador, y se vuelve a generar el archivo.
--
-- QUÉ HACE
-- --------
--   1. Crea la tabla `nota_conducta` (si no existe).
--   2. Carga la conducta migrada del sistema antiguo: {total} filas
--      ({resumen_bimestres}).
--
-- DE DÓNDE SALEN LOS {total}
-- -----------------------------
-- En la base antigua (`amanciov_2018_analisis`, tabla `notas`,
-- `codigoAsig = 24`, `anio_escolar = 2026`) hay 556 alumnos en bimestre 1 y
-- 20 en bimestre 2 (576 filas en total). De esas, {len(sin_cruce)} no
-- aparecen en el CSV de cruce ya validado
-- (`notas_2026_bim1_bim2_detalle.csv`) y se quedan FUERA de este .sql:
--
{lineas_sin_cruce}
--
-- Si alguno de estos alumnos sí tiene matrícula 2026, hay que añadirlo al
-- CSV de cruce (con su DNI correcto) y volver a generar este archivo.
--
-- POR QUÉ UNA TABLA NUEVA Y NO LA TABLA `nota`
-- ---------------------------------------------
-- La conducta no es una nota de curso: en la libreta va en una fila aparte
-- y no entra ni en el puntaje acumulado ni en el promedio de áreas. Meterla
-- en `nota` la mezclaría con los cursos y rompería esos cálculos.
--
-- LA COLUMNA `origen`
-- --------------------
--   'MIGRADO'   -> viene de este script, del sistema antiguo (bimestres 1 y 2).
--   'CALCULADO' -> la pondrá el backend más adelante, a partir de los reportes
--                  de conducta: 20 menos los puntos de cada falta. Ese cálculo
--                  NO es parte de este script.
--
-- QUÉ NO HACE
-- -----------
--   * No toca la tabla `nota`.
--   * No calcula conducta desde reportes de faltas (columna `origen` =
--     'CALCULADO'): eso lo hará el backend más adelante.
--   * No crea matrículas ni alumnos: si un DNI del cruce no tiene matrícula
--     2026, esa fila simplemente no encuentra `id_matricula` y no se inserta
--     (ver comprobación del bloque 6).
--   * No pisa conducta ya cargada a mano: `INSERT IGNORE` + la clave única
--     (`id_matricula`, `bimestre`) hacen que, si ya hay una fila para ese
--     alumno y ese bimestre, esta migración no la toca.
--
-- CÓMO EJECUTARLO
-- ---------------
-- phpMyAdmin -> base del hosting -> pestaña SQL -> pegar este archivo entero
-- -> Continuar. Se puede ejecutar más de una vez sin duplicar nada (la
-- segunda vez, este mismo bloque 3 da 0 filas a crear).
--
-- No usa information_schema: en este hosting ese permiso no es fiable.
-- No compara ninguna columna contra una variable de usuario (@algo): eso da
-- #1267 Illegal mix of collations. Todo va contra literales.
-- =====================================================================


-- ---------------------------------------------------------------------
-- 1) LA TABLA
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `nota_conducta` (
  `id_nota_conducta` INT(11) NOT NULL AUTO_INCREMENT,
  `id_matricula` INT(11) NOT NULL,
  `bimestre` INT(11) NOT NULL,
  `valor` DECIMAL(4,2) NOT NULL,
  `origen` VARCHAR(20) NOT NULL DEFAULT 'MIGRADO',
  `fecha_registro` DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id_nota_conducta`),
  UNIQUE KEY `uq_conducta_matricula_bim` (`id_matricula`, `bimestre`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ---------------------------------------------------------------------
-- 2) TABLA TEMPORAL CON LOS VALORES YA RESUELTOS (dni, bimestre, valor)
-- ---------------------------------------------------------------------
-- 556 (bimestre 1) + 20 (bimestre 2) filas en la base antigua, menos los
-- {len(sin_cruce)} alumnos sin cruce del bloque de arriba = {total} filas aquí.
--
-- La collation se fija igual a la de `alumno`.`dni` (utf8mb4_unicode_ci)
-- para que los JOIN de los bloques 3 y 4 no revienten con #1267.

DROP TEMPORARY TABLE IF EXISTS `tmp_conducta_2026`;
CREATE TEMPORARY TABLE `tmp_conducta_2026` (
  `dni` VARCHAR(8) COLLATE utf8mb4_unicode_ci NOT NULL,
  `bimestre` INT(11) NOT NULL,
  `valor` DECIMAL(4,2) NOT NULL
) ENGINE=MEMORY;

{inserts_tmp}

-- Comprobación: tiene que salir bimestre 1 con menos filas que bimestre 2,
-- y el total tiene que coincidir con los {total} de la cabecera.
SELECT `bimestre`, COUNT(*) AS filas FROM `tmp_conducta_2026` GROUP BY `bimestre`;


-- ---------------------------------------------------------------------
-- 3) ANTES: cuántas filas se van a crear
-- ---------------------------------------------------------------------
-- La primera vez tiene que dar {total} (o menos, si algún DNI no tiene
-- matrícula 2026 en el hosting: ver bloque 6). Si se vuelve a ejecutar el
-- archivo entero, tiene que dar 0.

SELECT COUNT(*) AS filas_a_crear
  FROM `tmp_conducta_2026` t
  JOIN `alumno` a ON a.`dni` = t.`dni`
  JOIN `matricula` m ON m.`id_alumno` = a.`id_alumno`
                     AND m.`id_anio_escolar` = '2026'
 WHERE NOT EXISTS (
         SELECT 1 FROM `nota_conducta` nc
          WHERE nc.`id_matricula` = m.`id_matricula`
            AND nc.`bimestre`     = t.`bimestre`
       );


-- ---------------------------------------------------------------------
-- 4) EL INSERT
-- ---------------------------------------------------------------------
-- El `id_matricula` se resuelve por DNI y año, no por id: los id_alumno del
-- sistema antiguo no significan nada en el sistema nuevo.

INSERT IGNORE INTO `nota_conducta` (`id_matricula`, `bimestre`, `valor`, `origen`)
SELECT m.`id_matricula`, t.`bimestre`, t.`valor`, 'MIGRADO'
  FROM `tmp_conducta_2026` t
  JOIN `alumno` a ON a.`dni` = t.`dni`
  JOIN `matricula` m ON m.`id_alumno` = a.`id_alumno`
                     AND m.`id_anio_escolar` = '2026';


-- ---------------------------------------------------------------------
-- 5) DESPUÉS: total por bimestre, mínimo, máximo, media
-- ---------------------------------------------------------------------

SELECT `bimestre`,
       COUNT(*) AS total,
       MIN(`valor`) AS minimo,
       MAX(`valor`) AS maximo,
       ROUND(AVG(`valor`), 2) AS promedio
  FROM `nota_conducta`
 WHERE `origen` = 'MIGRADO'
 GROUP BY `bimestre`
 ORDER BY `bimestre`;


-- ---------------------------------------------------------------------
-- 6) DNIs DEL CSV QUE NO ENCONTRARON MATRÍCULA 2026
-- ---------------------------------------------------------------------
-- Tiene que salir vacío ("conjunto vacío") o casi. Si sale algo, ese alumno
-- del cruce no tiene matrícula 2026 en ESTE hosting y su conducta no se
-- cargó (no rompe nada, simplemente se queda fuera).
--
{aviso_matricula}

SELECT DISTINCT t.`dni`
  FROM `tmp_conducta_2026` t
  LEFT JOIN `alumno` a ON a.`dni` = t.`dni`
  LEFT JOIN `matricula` m ON m.`id_alumno` = a.`id_alumno`
                          AND m.`id_anio_escolar` = '2026'
 WHERE m.`id_matricula` IS NULL;


-- ---------------------------------------------------------------------
-- 7) PRUEBA DE HUMO: los dos alumnos de la libreta oficial
-- ---------------------------------------------------------------------
-- Los dos tienen que salir con bimestre 1 = 16.00 (sacado de su libreta
-- oficial en PDF):
{lineas_prueba}

SELECT a.`dni`, CONCAT(a.`apellidos`, ', ', a.`nombres`) AS alumno,
       nc.`bimestre`, nc.`valor`, nc.`origen`
  FROM `nota_conducta` nc
  JOIN `matricula` m ON m.`id_matricula` = nc.`id_matricula`
  JOIN `alumno` a ON a.`id_alumno` = m.`id_alumno`
 WHERE a.`dni` IN ({dnis_prueba_sql})
 ORDER BY a.`dni`, nc.`bimestre`;


-- ---------------------------------------------------------------------
-- 8) LIMPIEZA
-- ---------------------------------------------------------------------

DROP TEMPORARY TABLE IF EXISTS `tmp_conducta_2026`;
"""


def main():
    mapping = cargar_cruce_csv()
    print(f"Cruce cargado del CSV: {len(mapping)} alumnos antiguos con DNI nuevo")

    filas = leer_conducta_antigua()
    print(f"Filas de conducta en la base antigua (año {ANIO}, codigoAsig={CODIGO_ASIG_CONDUCTA}): {len(filas)}")

    resueltas = []  # (dni, bimestre, valor)
    sin_cruce = []  # (id_alumno_antiguo, bimestre, valor, apellidos, nombres)
    for id_alumno, bimestre, nota, apellidos, nombres in filas:
        dni = mapping.get(str(id_alumno))
        if dni:
            resueltas.append((dni, bimestre, nota))
        else:
            sin_cruce.append((id_alumno, bimestre, nota, apellidos, nombres))

    print(f"Resueltas por DNI: {len(resueltas)}")
    print(f"SIN cruce en el CSV (quedan fuera del .sql): {len(sin_cruce)}")
    for id_alumno, bimestre, nota, apellidos, nombres in sin_cruce:
        print(
            f"   id_alumno_antiguo={id_alumno}  bimestre={bimestre}  nota={nota}  "
            f"{apellidos.strip()}, {nombres.strip()}"
        )

    dnis_unicos = sorted({dni for dni, _, _ in resueltas})
    faltantes_matricula = dnis_sin_matricula_2026(dnis_unicos)
    if faltantes_matricula:
        print(f"AVISO: {len(faltantes_matricula)} DNIs del cruce no tienen matrícula 2026 en la base nueva local:")
        for d in faltantes_matricula:
            print(f"   {d}")
    else:
        print(f"Los {len(dnis_unicos)} DNIs del cruce tienen matrícula 2026 en la base nueva local.")

    sql = generar_sql(resueltas, sin_cruce, faltantes_matricula)

    os.makedirs(os.path.dirname(RUTA_SQL_SALIDA), exist_ok=True)
    with open(RUTA_SQL_SALIDA, "w", encoding="utf-8", newline="\n") as f:
        f.write(sql)

    print(f"\nArchivo generado: {RUTA_SQL_SALIDA}")
    print(f"Total de filas que insertará el .sql: {len(resueltas)}")


if __name__ == "__main__":
    main()
