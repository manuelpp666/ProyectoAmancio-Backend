# -*- coding: utf-8 -*-
"""
Genera el script SQL que carga las notas de Geohistoria de 2026.

POR QUÉ FALTABAN
----------------
La carga inicial (script 01) dejó Geohistoria fuera. En la base antigua cada
alumno tiene DOS notas de Geohistoria, una por competencia:

    idcompetencia 15 -> PERSONAL SOCIAL
    idcompetencia 36 -> CIENCIAS SOCIALES

En 158 alumnos las dos coinciden, pero en 32 no, y no había forma de saber
cuál era la buena. Sin ese dato, cargar cualquiera de las dos era jugársela.

CÓMO SE RESOLVIÓ
----------------
Con las libretas oficiales que imprimió el sistema antiguo. Caso decisivo:

    BARBOZA BENAVIDES, GRECIA LUANA (3° A)
        competencia 15 = 16
        competencia 36 = 12
        libreta oficial: GEOHISTORIA = 12   <-- gana la 36

Además, en la libreta Geohistoria aparece bajo el área CIENCIAS SOCIALES, que
es justo el nombre de la competencia 36. Las dos señales apuntan a lo mismo,
así que este generador toma SIEMPRE la competencia 36.

POR QUÉ UN GENERADOR Y NO SQL A SECAS
-------------------------------------
El colegio ejecuta el SQL en phpMyAdmin contra su hosting, donde la base
antigua no existe. Por eso el .sql tiene que llevar los valores ya resueltos.

USO
---
    python scripts/generar_geohistoria_2026.py
"""

import csv
import os
import sys
import urllib.parse as up

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAIZ = os.path.dirname(BASE)
CSV_CRUCE = os.path.join(RAIZ, "Extraccion_Notas_Antiguas",
                         "notas_2026_bim1_bim2_detalle.csv")
SALIDA = os.path.join(RAIZ, "Extraccion_Notas_Antiguas", "sql",
                      "21_geohistoria_2026.sql")

# La asignatura y la competencia de la base antigua, decididas arriba.
COD_GEOHISTORIA = 61
COMPETENCIA_BUENA = 36        # CIENCIAS SOCIALES
ANIO = "2026"


def conectar(nombre_base):
    load_dotenv(os.path.join(BASE, ".env"))
    usuario = os.getenv("DB_USER")
    clave = up.quote_plus(os.getenv("DB_PASSWORD") or "")
    host = os.getenv("DB_HOST")
    return create_engine(
        f"mysql+pymysql://{usuario}:{clave}@{host}/{nombre_base}?charset=utf8mb4"
    ).connect()


def cruce_antiguo_a_dni():
    """{id_alumno_antiguo: dni} sacado del CSV que ya se validó en la carga 01.

    No se cruza por nombre a propósito: los nombres de la base antigua traen
    mojibake ("IDROGO FARRO ITZEL ABIGAÃL") y acentos inconsistentes.
    """
    cruce = {}
    with open(CSV_CRUCE, encoding="utf-8-sig", newline="") as f:
        for fila in csv.DictReader(f, delimiter=";"):
            antiguo = (fila.get("id_alumno_antiguo") or "").strip()
            dni = (fila.get("dni_sistema_nuevo") or "").strip()
            if antiguo and dni:
                cruce[antiguo] = dni
    return cruce


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    cruce = cruce_antiguo_a_dni()
    print(f"cruce del CSV: {len(cruce)} alumnos")

    ant = conectar("amanciov_2018_analisis")
    filas = ant.execute(text("""
        SELECT n.id_alumno, n.bimestre, n.nota
          FROM notas n
         WHERE n.codigoAsig = :cod AND n.anio_escolar = :anio
           AND n.idcompetencia = :comp
         ORDER BY n.bimestre, n.id_alumno
    """), {"cod": COD_GEOHISTORIA, "anio": ANIO, "comp": COMPETENCIA_BUENA}).fetchall()
    print(f"notas de Geohistoria (competencia {COMPETENCIA_BUENA}): {len(filas)}")

    resueltas, sin_cruce = [], []
    for f in filas:
        dni = cruce.get(str(f.id_alumno))
        if dni:
            resueltas.append((dni, int(f.bimestre), float(f.nota)))
        else:
            sin_cruce.append(str(f.id_alumno))
    print(f"resueltas: {len(resueltas)}   ·   sin cruce: {len(sin_cruce)}")

    escribir(resueltas, sin_cruce)
    print(f"escrito: {SALIDA}")


def escribir(resueltas, sin_cruce):
    por_bimestre = {}
    for _, bim, _v in resueltas:
        por_bimestre[bim] = por_bimestre.get(bim, 0) + 1

    lineas = []
    a = lineas.append
    a("-- =====================================================================")
    a("-- 21_geohistoria_2026.sql")
    a("-- I.E.P. Amancio Varona - Las notas de Geohistoria que faltaban")
    a("-- =====================================================================")
    a("--")
    a("-- GENERADO AUTOMÁTICAMENTE por scripts/generar_geohistoria_2026.py")
    a("-- No lo edites a mano: vuelve a generarlo.")
    a("--")
    a("-- QUÉ ARREGLA")
    a("-- -----------")
    a("-- La carga inicial dejó Geohistoria sin notas en 1ero, 2do y 3ero de")
    a("-- secundaria. Sin ellas, el área CIENCIAS SOCIALES sale vacía y la")
    a("-- libreta de esos alumnos da un ponderado equivocado: divide entre 9")
    a("-- áreas en vez de entre 10.")
    a("--")
    a("-- POR QUÉ SE QUEDARON FUERA Y CÓMO SE RESOLVIÓ")
    a("-- --------------------------------------------")
    a("-- En la base antigua cada alumno tenía DOS notas de Geohistoria, una por")
    a("-- competencia: la 15 (PERSONAL SOCIAL) y la 36 (CIENCIAS SOCIALES). En")
    a("-- 32 alumnos las dos no coinciden, y no se sabía cuál era la buena.")
    a("--")
    a("-- Lo resolvió una libreta oficial del sistema antiguo:")
    a("--")
    a("--     BARBOZA BENAVIDES, GRECIA LUANA (3° A)")
    a("--         competencia 15 = 16")
    a("--         competencia 36 = 12")
    a("--         su libreta imprime GEOHISTORIA = 12   <-- gana la 36")
    a("--")
    a("-- Encaja con que en la libreta Geohistoria vaya bajo el área CIENCIAS")
    a("-- SOCIALES, que es el nombre de la competencia 36. Este script carga")
    a("-- siempre esa.")
    a("--")
    a("-- CUÁNTAS NOTAS")
    a("-- -------------")
    for bim in sorted(por_bimestre):
        a(f"--     bimestre {bim}: {por_bimestre[bim]} alumnos")
    a(f"--     total: {len(resueltas)}")
    a("--")
    if sin_cruce:
        a("-- Alumnos de la base antigua sin equivalencia en el sistema nuevo")
        a("-- (ya no están matriculados): quedan fuera, y son")
        a(f"--     ids antiguos: {', '.join(sin_cruce)}")
        a("--")
    a("-- QUÉ NO HACE")
    a("-- -----------")
    a("--   * No pisa ninguna nota que ya exista: el NOT EXISTS del final hace")
    a("--     que solo entre donde no hay nada.")
    a("--   * No toca Historia ni Economía, que sí se cargaron bien.")
    a("--")
    a("-- CÓMO EJECUTARLO")
    a("-- ---------------")
    a("-- phpMyAdmin -> base `amanciov_bd_2026` -> pestaña SQL -> pegar entero")
    a("-- -> Continuar. Se puede ejecutar dos veces sin duplicar nada.")
    a("--")
    a("-- No usa information_schema: en este hosting ese permiso no es fiable.")
    a("-- =====================================================================")
    a("")
    a("")
    a("-- ---------------------------------------------------------------------")
    a("-- 1) LOS DATOS")
    a("-- ---------------------------------------------------------------------")
    a("-- La tabla temporal lleva la colación escrita a mano. Sin eso, comparar")
    a("-- su columna `dni` contra `alumno`.`dni` puede dar")
    a("--     #1267 Illegal mix of collations")
    a("-- cuando la base tiene una colación por defecto distinta.")
    a("")
    a("DROP TEMPORARY TABLE IF EXISTS `tmp_geohistoria`;")
    a("CREATE TEMPORARY TABLE `tmp_geohistoria` (")
    a("  `dni` VARCHAR(8) COLLATE utf8mb4_unicode_ci NOT NULL,")
    a("  `bimestre` INT NOT NULL,")
    a("  `valor` DECIMAL(4,2) NOT NULL,")
    a("  PRIMARY KEY (`dni`, `bimestre`)")
    a(") ENGINE=MEMORY DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;")
    a("")

    # En lotes: una sola sentencia con 400 filas es incómoda de leer y algunas
    # instalaciones de phpMyAdmin la cortan.
    TAM = 200
    for i in range(0, len(resueltas), TAM):
        lote = resueltas[i:i + TAM]
        a("INSERT IGNORE INTO `tmp_geohistoria` (`dni`, `bimestre`, `valor`) VALUES")
        a(",\n".join(f"  ('{d}', {b}, {v:.2f})" for d, b, v in lote) + ";")
        a("")

    a("SELECT `bimestre`, COUNT(*) AS filas FROM `tmp_geohistoria`")
    a(" GROUP BY `bimestre` ORDER BY `bimestre`;")
    a("")
    a("")
    a("-- ---------------------------------------------------------------------")
    a("-- 2) ANTES: cuántas se van a crear")
    a("-- ---------------------------------------------------------------------")
    a("")
    a("SELECT COUNT(*) AS notas_a_crear")
    a("  FROM `tmp_geohistoria` t")
    a("  JOIN `alumno` a ON a.`dni` = t.`dni`")
    a("  JOIN `matricula` m ON m.`id_alumno` = a.`id_alumno`")
    a("                    AND m.`id_anio_escolar` = '2026'")
    a("  JOIN `curso` c ON c.`nombre` = 'Geohistoria'")
    a(" WHERE NOT EXISTS (")
    a("         SELECT 1 FROM `nota` x")
    a("          WHERE x.`id_matricula` = m.`id_matricula`")
    a("            AND x.`id_curso`     = c.`id_curso`")
    a("            AND x.`bimestre`     = t.`bimestre`")
    a("       );")
    a("")
    a("")
    a("-- ---------------------------------------------------------------------")
    a("-- 3) CARGARLAS")
    a("-- ---------------------------------------------------------------------")
    a("")
    a("INSERT INTO `nota` (`id_matricula`, `id_curso`, `bimestre`, `tipo_nota`, `valor`)")
    a("SELECT m.`id_matricula`, c.`id_curso`, t.`bimestre`, 'PROMEDIO', t.`valor`")
    a("  FROM `tmp_geohistoria` t")
    a("  JOIN `alumno` a ON a.`dni` = t.`dni`")
    a("  JOIN `matricula` m ON m.`id_alumno` = a.`id_alumno`")
    a("                    AND m.`id_anio_escolar` = '2026'")
    a("  JOIN `curso` c ON c.`nombre` = 'Geohistoria'")
    a(" WHERE NOT EXISTS (")
    a("         SELECT 1 FROM `nota` x")
    a("          WHERE x.`id_matricula` = m.`id_matricula`")
    a("            AND x.`id_curso`     = c.`id_curso`")
    a("            AND x.`bimestre`     = t.`bimestre`")
    a("       );")
    a("")
    a("")
    a("-- ---------------------------------------------------------------------")
    a("-- 4) COMPROBACIÓN")
    a("-- ---------------------------------------------------------------------")
    a("-- Por grado: cuántos alumnos quedan con nota de Geohistoria.")
    a("")
    a("SELECT g.`nombre` AS grado, nt.`bimestre`,")
    a("       COUNT(DISTINCT m.`id_matricula`) AS alumnos,")
    a("       COUNT(nt.`id_nota`) AS con_nota,")
    a("       MIN(nt.`valor`) AS minimo, MAX(nt.`valor`) AS maximo")
    a("  FROM `curso` c")
    a("  JOIN `plan_estudio` p ON p.`id_curso` = c.`id_curso`")
    a("  JOIN `grado` g ON g.`id_grado` = p.`id_grado`")
    a("  JOIN `seccion` s ON s.`id_grado` = g.`id_grado` AND s.`id_anio_escolar` = '2026'")
    a("  JOIN `matricula` m ON m.`id_seccion` = s.`id_seccion`")
    a("                    AND m.`id_anio_escolar` = '2026'")
    a("  LEFT JOIN `nota` nt ON nt.`id_matricula` = m.`id_matricula`")
    a("                     AND nt.`id_curso` = c.`id_curso`")
    a(" WHERE c.`nombre` = 'Geohistoria'")
    a(" GROUP BY g.`id_grado`, nt.`bimestre`")
    a(" ORDER BY g.`orden`, nt.`bimestre`;")
    a("")
    a("-- DNIs del archivo que no encontraron matrícula en 2026. Debe salir vacío")
    a("-- o casi: serían alumnos que ya no están en el colegio.")
    a("")
    a("SELECT DISTINCT t.`dni`")
    a("  FROM `tmp_geohistoria` t")
    a("  LEFT JOIN `alumno` a ON a.`dni` = t.`dni`")
    a("  LEFT JOIN `matricula` m ON m.`id_alumno` = a.`id_alumno`")
    a("                         AND m.`id_anio_escolar` = '2026'")
    a(" WHERE m.`id_matricula` IS NULL;")
    a("")
    a("-- La alumna que sirvió para decidir la competencia: tiene que salir 12.")
    a("")
    a("SELECT a.`dni`, CONCAT(a.`apellidos`, ', ', a.`nombres`) AS alumno,")
    a("       nt.`bimestre`, nt.`valor`")
    a("  FROM `nota` nt")
    a("  JOIN `matricula` m ON m.`id_matricula` = nt.`id_matricula`")
    a("  JOIN `alumno` a ON a.`id_alumno` = m.`id_alumno`")
    a("  JOIN `curso` c ON c.`id_curso` = nt.`id_curso`")
    a(" WHERE c.`nombre` = 'Geohistoria'")
    a("   AND a.`apellidos` LIKE '%BARBOZA BENAVIDES%'")
    a("   AND m.`id_anio_escolar` = '2026';")
    a("")
    a("DROP TEMPORARY TABLE IF EXISTS `tmp_geohistoria`;")

    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
    with open(SALIDA, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lineas) + "\n")


if __name__ == "__main__":
    main()
