import os, sys
sys.path.insert(0, '.')
os.environ['GOOGLE_API_KEY'] = 'test_key'
import app.modules.users.models
import app.modules.users.alumno.models
import app.modules.behavior.models as bm
from app.db.database import engine
from sqlalchemy import text
from datetime import datetime, timedelta

with engine.connect() as conn:
    print("=== 1. Loading tipo_falta first ===")
    with open('scripts/respaldos/segunda_amancio_bd_ANTES_migracion_20260803_1152.sql', 'r', encoding='utf-8', errors='ignore') as f:
        sql_content = f.read()

    # 1. Load tipo_falta first
    for line in sql_content.splitlines():
        if line.startswith('INSERT INTO `tipo_falta`'):
            conn.execute(text(line))
            conn.commit()
            print("Loaded tipo_falta count:", conn.execute(text("SELECT COUNT(*) FROM tipo_falta")).scalar())

    # 2. Load nivel_conducta second
    for line in sql_content.splitlines():
        if line.startswith('INSERT INTO `nivel_conducta`'):
            conn.execute(text(line))
            conn.commit()
            print("Loaded nivel_conducta count:", conn.execute(text("SELECT COUNT(*) FROM nivel_conducta")).scalar())

    print("\n=== 2. Inspecting available infractions ===")
    infractions = conn.execute(text("""
        SELECT nc.id_nivel_conducta, tf.nombre AS tipo, nc.nombre AS falta, nc.puntos, nc.medida, nc.cambio_ie, nc.descripcion
        FROM nivel_conducta nc
        JOIN tipo_falta tf ON tf.id_tipo_falta = nc.id_tipo_falta
        ORDER BY tf.id_tipo_falta, nc.puntos
    """)).fetchall()
    for inf in infractions[:12]:
        print(f"[{inf[1]}] ID {inf[0]}: {inf[2]} (-{inf[3]} pts, cambio_ie={inf[5]})")

    print("\n=== 3. Selecting sample active students ===")
    alumnos = conn.execute(text("""
        SELECT a.id_alumno, a.dni, a.apellidos, a.nombres, g.nombre AS grado, s.nombre AS seccion, n.nombre AS nivel
        FROM alumno a
        JOIN matricula m ON m.id_alumno = a.id_alumno
        JOIN seccion s ON s.id_seccion = m.id_seccion
        JOIN grado g ON g.id_grado = s.id_grado
        JOIN nivel n ON n.id_nivel = g.id_nivel
        WHERE m.id_anio_escolar = '2026'
        ORDER BY g.orden, s.nombre, a.apellidos
    """)).fetchall()

    print(f"Total students available: {len(alumnos)}")
    
    # Let's select 6 distinct students across primary and secondary
    estudiantes_prueba = [
        alumnos[0],   # Primaria 1ero Azul
        alumnos[15],  # Primaria 1ero Rojo
        alumnos[45],  # Primaria 2do
        alumnos[150], # Primaria 5to
        alumnos[320], # Secundaria 1ero
        alumnos[480], # Secundaria 4to
    ]

    for ep in estudiantes_prueba:
        print(f" - ID: {ep[0]} | DNI: {ep[1]} | {ep[2]}, {ep[3]} ({ep[6]} {ep[4]} {ep[5]})")

    print("\n=== 4. Inserting realistic test reports ===")
    # Clear any prior test reports tagged with [PRUEBA]
    conn.execute(text("DELETE FROM reporte_conducta WHERE descripcion_suceso LIKE '%[DATO DE PRUEBA]%'"))
    conn.commit()

    # Now insert 6 test reports
    ahora = datetime.now()
    reportes_a_insertar = [
        {
            "id_alumno": estudiantes_prueba[0][0], # Alumno 1
            "id_nivel_conducta": infractions[0][0], # Tardanza / Asistencia
            "descripcion": "[DATO DE PRUEBA] El estudiante llegó 25 minutos tarde a la primera hora de clase sin justificación escrita del apoderado.",
            "fecha": ahora - timedelta(days=2, hours=3)
        },
        {
            "id_alumno": estudiantes_prueba[1][0], # Alumno 2
            "id_nivel_conducta": infractions[3][0], # Mobiliario
            "descripcion": "[DATO DE PRUEBA] Se encontró al estudiante rayando una carpeta con corrector durante el receso en el patio de primaria.",
            "fecha": ahora - timedelta(days=1, hours=5)
        },
        {
            "id_alumno": estudiantes_prueba[2][0], # Alumno 3
            "id_nivel_conducta": infractions[5][0], # Civismo / Honradez
            "descripcion": "[DATO DE PRUEBA] No portó el uniforme escolar reglamentario de acuerdo con el horario de formación institucional.",
            "fecha": ahora - timedelta(hours=6)
        },
        {
            "id_alumno": estudiantes_prueba[3][0], # Alumno 4
            "id_nivel_conducta": infractions[8][0], # Respeto
            "descripcion": "[DATO DE PRUEBA] Fomentó indisciplina y desorden reiterado durante el cambio de hora en el pabellón de 5to grado.",
            "fecha": ahora - timedelta(hours=2)
        },
        {
            "id_alumno": estudiantes_prueba[4][0], # Alumno 5
            "id_nivel_conducta": infractions[1][0], # Asistencia
            "descripcion": "[DATO DE PRUEBA] Se retiró del aula de clases antes del toque de timbre sin autorización del auxiliar de turno.",
            "fecha": ahora - timedelta(minutes=45)
        },
        {
            "id_alumno": estudiantes_prueba[5][0], # Alumno 6
            "id_nivel_conducta": infractions[10][0] if len(infractions) > 10 else infractions[0][0], # Respeto / Falta grave
            "descripcion": "[DATO DE PRUEBA] Incumplimiento reiterado de las normas de convivencia escolar en el laboratorio durante la sesión de clase.",
            "fecha": ahora - timedelta(minutes=15)
        }
    ]

    for r in reportes_a_insertar:
        conn.execute(text("""
            INSERT INTO reporte_conducta (id_alumno, id_nivel_conducta, descripcion_suceso, fecha_reporte)
            VALUES (:id_alumno, :id_nivel_conducta, :descripcion, :fecha)
        """), {
            "id_alumno": r["id_alumno"],
            "id_nivel_conducta": r["id_nivel_conducta"],
            "descripcion": r["descripcion"],
            "fecha": r["fecha"]
        })
    conn.commit()

    total_rep = conn.execute(text("SELECT COUNT(*) FROM reporte_conducta")).scalar()
    print(f"\nSUCCESS: Inserted 6 test reports. Total reports in system: {total_rep}")

    # Inspect the reports in bandeja
    ultimos = conn.execute(text("""
        SELECT rc.id_reporte, a.dni, CONCAT(a.apellidos, ' ', a.nombres) AS alumno, nc.nombre AS falta, nc.puntos, rc.fecha_reporte
        FROM reporte_conducta rc
        JOIN alumno a ON a.id_alumno = rc.id_alumno
        JOIN nivel_conducta nc ON nc.id_nivel_conducta = rc.id_nivel_conducta
        ORDER BY rc.fecha_reporte DESC
        LIMIT 6
    """)).fetchall()

    print("\n=== Bandeja de Reportes Recientes ===")
    for u in ultimos:
        print(f" Reporte #{u[0]} | {u[1]} - {u[2]} | Falta: {u[3]} (-{u[4]} pts) | Fecha: {u[5]}")
