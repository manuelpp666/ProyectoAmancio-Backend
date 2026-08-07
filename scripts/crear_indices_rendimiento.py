"""
Crea los índices que faltan para que las consultas del campus sigan siendo
rápidas cuando las tablas se llenen.

Hoy casi todas están vacías, así que cualquier consulta parece instantánea. El
problema aparece en marcha: `asistencia` crece a unas 110.000 filas por curso
(577 alumnos x ~190 días lectivos) y `nota` y `entrega_tarea` a decenas de
miles. Sin índice, cada consulta pasa a leer la tabla entera.

Cada índice de aquí sale de una consulta concreta del código, no de indexar por
si acaso: los índices también cuestan en cada escritura.

Es idempotente: si el índice ya existe, lo salta.

Uso:
    python scripts/crear_indices_rendimiento.py            # muestra el plan
    python scripts/crear_indices_rendimiento.py --aplicar  # lo ejecuta
"""
import os
import sys

import pymysql
from dotenv import load_dotenv

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(RAIZ, ".env"))

APLICAR = "--aplicar" in sys.argv

# (tabla, nombre del índice, columnas, por qué)
INDICES = [
    ("asistencia", "ix_asistencia_fecha_matricula", "fecha, id_matricula",
     "Pasar lista y el panel del auxiliar filtran por fecha del día, y el "
     "guardado comprueba (fecha, id_matricula in ...). Es la tabla que más crece."),

    ("asistencia", "ix_asistencia_matricula_fecha", "id_matricula, fecha",
     "El historial de asistencia de un alumno: sus filas ya ordenadas por fecha."),

    ("nota", "ix_nota_matricula_curso_bim", "id_matricula, id_curso, bimestre",
     "El cálculo de promedios filtra por matrícula + curso + bimestre."),

    ("resumen_nota", "ix_resumen_matricula_curso", "id_matricula, id_curso",
     "La libreta del alumno busca el resumen de cada curso."),

    ("mensaje", "ix_mensaje_conversacion_fecha", "id_conversacion, fecha_envio",
     "Abrir un chat pide sus mensajes ordenados por fecha, y la lista de "
     "contactos pide el último de cada conversación."),

    ("mensaje", "ix_mensaje_leido_remitente", "leido, remitente_id",
     "El contador de no leídos del header, que consultan todos los usuarios."),

    ("entrega_tarea", "ix_entrega_tarea_alumno", "id_tarea, id_alumno",
     "Ver las entregas de una tarea y saber si un alumno ya entregó."),

    ("pago", "ix_pago_alumno_estado", "id_alumno, estado",
     "Las deudas del alumno: aparece en su panel y en el contador de avisos."),

    ("pago", "ix_pago_estado_vencimiento", "estado, fecha_vencimiento",
     "Caja y recaudación filtra por estado y por fecha; ya son 13.600 filas."),

    ("evento", "ix_evento_activo_inicio", "activo, fecha_inicio",
     "Los próximos eventos, que entran en el contador de avisos de todos."),

    ("cita_psicologia", "ix_cita_alumno_estado_fecha", "id_alumno, estado, fecha_cita",
     "Las citas de hoy del alumno, dentro del contador de avisos."),

    ("reporte_conducta", "ix_reporte_alumno_fecha", "id_alumno, fecha_reporte",
     "El historial de conducta de un alumno, ordenado por fecha."),

    ("solicitud_tramite", "ix_solicitud_tramite_estado", "estado, fecha_solicitud",
     "La bandeja de trámites pendientes de atender."),
]


def conectar():
    host, _, puerto = (os.getenv("DB_HOST") or "127.0.0.1").partition(":")
    return pymysql.connect(
        host=host.strip(), port=int(puerto or 3306),
        user=os.getenv("DB_USER"), password=os.getenv("DB_PASS") or "",
        database=os.getenv("DB_NAME"), charset="utf8mb4",
    )


def main():
    cx = conectar()
    cur = cx.cursor()
    bd = os.getenv("DB_NAME")

    cur.execute("""SELECT TABLE_NAME, INDEX_NAME FROM information_schema.STATISTICS
                   WHERE TABLE_SCHEMA = %s""", (bd,))
    existentes = {(t, i) for t, i in cur.fetchall()}
    cur.execute("""SELECT TABLE_NAME FROM information_schema.TABLES
                   WHERE TABLE_SCHEMA = %s""", (bd,))
    tablas = {t for (t,) in cur.fetchall()}

    creados = omitidos = 0
    for tabla, nombre, columnas, motivo in INDICES:
        if tabla not in tablas:
            print(f"  [!] no existe la tabla {tabla}, se omite {nombre}")
            continue
        if (tabla, nombre) in existentes:
            print(f"  = {tabla}.{nombre} ya existe")
            omitidos += 1
            continue
        print(f"  + {tabla}.{nombre} ({columnas})")
        print(f"      {motivo}")
        creados += 1
        if APLICAR:
            cur.execute(f"CREATE INDEX {nombre} ON {tabla} ({columnas})")

    if APLICAR:
        cx.commit()
        print(f"\n>>> {creados} índices creados, {omitidos} ya estaban.")
    else:
        print(f"\n>>> SIMULACIÓN: se crearían {creados} índices ({omitidos} ya están).")
        print("    Repite con --aplicar para ejecutarlo.")
    cx.close()


if __name__ == "__main__":
    main()
