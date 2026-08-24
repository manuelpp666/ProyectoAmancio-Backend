"""
DATOS DE PRUEBA — Panel completo del estudiante (DNI 90313123).

Rellena las pantallas del campus del alumno que hoy salen vacías o a medias,
con contenido que se lee como el de un alumno de verdad: asistencia del año,
notas del segundo bimestre, trámites en distintos estados, citas de psicología,
tareas por entregar y materiales de clase.

ESTO NO ES DATO REAL. Es para la base de desarrollo. No ejecutar en el
servidor: crea citas de psicología, notas y trámites a nombre de un alumno que
existe de verdad.

Lo que toca, y por qué:

    tipo_tramite      El catálogo estaba VACÍO: la pantalla de trámites no
                      funcionaba para ningún alumno, no solo para este. Solo
                      se siembra si la tabla está vacía.
    asistencia        No tenía ni un registro. Se genera de lunes a viernes
                      desde el inicio de clases, saltando feriados y las
                      vacaciones de medio año.
    nota              Le faltaban 15 de los 16 cursos del bimestre 2.
    resumen_nota      Se actualiza la columna del bimestre 2 y el promedio.
    nota_conducta     Le faltaba la del bimestre 2.
    solicitud_tramite Tres trámites en tres estados distintos, con su pago.
    cita_psicologia   Una atendida y una futura, para que el panel tenga
                      "próxima cita" (la que había ya pasó).
    tarea             Las 17 tareas de la sección no tenían fecha de entrega,
                      así que nunca salía ninguna pendiente. Se les pone, y se
                      añaden cuatro nuevas por vencer.
    material_clase    No había ninguno en la sección.

CÓMO SE DESHACE, y por qué así
    Nada de lo que se escribe lleva una marca de "esto es de prueba": el
    encargo era justamente que no se notara, y campos como la descripción del
    material o el motivo de la cita SE VEN en el panel. Así que las claves de
    todo lo insertado se anotan en

        scripts/datos_prueba_liam_90313123.ids.json

    y --borrar quita exactamente esas filas, ni una más. Si se pierde ese
    archivo, el borrado automático ya no puede distinguir lo de prueba de lo
    real, y avisa en vez de adivinar.

Las tareas y los materiales cuelgan de la carga académica, no del alumno: los
verá toda la sección "3ero Amarillo". Es inevitable y en desarrollo da igual,
pero conviene saberlo.

Uso:
    python scripts/datos_prueba_liam_90313123.py            # simulación
    python scripts/datos_prueba_liam_90313123.py --aplicar  # crea los datos
    python scripts/datos_prueba_liam_90313123.py --borrar   # los elimina
"""
import json
import os
import random
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from app.db.database import SessionLocal

DNI_ALUMNO = "90313123"

# Para grabar el video manual se le puso a este alumno un DNI falso, y con solo
# el DNI real el script dejaba de encontrarlo: --borrar se quedaba sin poder
# deshacer nada. Se busca por los dos, y así funciona esté como esté.
DNI_VIDEO = "77112233"

APLICAR = "--aplicar" in sys.argv
BORRAR = "--borrar" in sys.argv

random.seed(90313123)          # el mismo historial en cada ejecución

REGISTRO = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "datos_prueba_liam_90313123.ids.json")

# Feriados de 2026 que caen en día lectivo, y el receso de medio año.
FERIADOS = {
    date(2026, 4, 2),    # Jueves Santo
    date(2026, 4, 3),    # Viernes Santo
    date(2026, 5, 1),    # Día del Trabajo
    date(2026, 6, 29),   # San Pedro y San Pablo
    date(2026, 7, 28),   # Fiestas Patrias
    date(2026, 7, 29),   # Fiestas Patrias
    date(2026, 8, 6),    # Batalla de Junín
}
VACACIONES = (date(2026, 7, 20), date(2026, 7, 31))

# Asiste casi siempre: es un alumno sin problemas de asistencia.
REPARTO = [("P", 0.90), ("T", 0.05), ("F", 0.03), ("J", 0.02)]

OBSERVACIONES = {
    "T": ["Llegó 10 minutos tarde", "Ingresó después del timbre",
          "Tardanza avisada por el apoderado", ""],
    "F": ["", "No se presentó", "Inasistencia sin aviso"],
    "J": ["Cita médica", "Permiso familiar presentado por el apoderado",
          "Certificado médico"],
}

CATALOGO_TRAMITES = [
    ("Certificado de Estudios", 25.00,
     "Copia del DNI del alumno. Estar al día en las pensiones.", "AMBOS", 15),
    ("Constancia de Conducta", 15.00,
     "Solicitud dirigida a la Dirección.", "REGULAR", 15),
    ("Constancia de Estudios", 15.00,
     "Copia del DNI del alumno.", "AMBOS", 15),
    ("Duplicado de Libreta de Notas", 20.00,
     "Declaración de pérdida firmada por el apoderado.", "REGULAR", 15),
    ("Certificado de Traslado", 30.00,
     "Carta de la institución de destino. Estar al día en las pensiones.",
     "REGULAR", 10),
    ("Constancia de No Adeudo", 0.00,
     "Ninguno. Lo emite Tesorería.", "AMBOS", 15),
]

TAREAS_NUEVAS = [
    ("Aritmética", "Práctica calificada de fracciones homogéneas",
     "Resolver los ejercicios del 1 al 20 de la separata. Presentar el "
     "procedimiento completo, no solo el resultado.", 6),
    ("Comunicación", "Lectura: «El zorro y el cuy» — ficha de comprensión",
     "Leer el texto de la separata y responder la ficha. Cuidar la ortografía "
     "y la letra.", 5),
    ("Ciencia y Tecnología", "Maqueta del sistema digestivo",
     "En grupos de tres. Materiales reciclados. Se califica el rótulo de cada "
     "órgano y la exposición.", 12),
    ("Personal Social", "Línea de tiempo: culturas preincas",
     "Elaborar la línea de tiempo en papelógrafo con al menos seis culturas.",
     9),
]

MATERIALES = [
    ("Aritmética", "Separata 04 — Fracciones",
     "Teoría y ejercicios resueltos para la práctica de la próxima semana."),
    ("Comunicación", "Lecturas del bimestre",
     "Los cuatro textos que se trabajarán en clase."),
    ("Ciencia y Tecnología", "Guía del sistema digestivo",
     "Esquema de los órganos y sus funciones."),
    ("Razonamiento Matemático", "Banco de problemas — sucesiones",
     "Treinta problemas ordenados por dificultad."),
    ("Inglés", "Vocabulary list — Unit 3: My family",
     "Lista de vocabulario y expresiones de la unidad."),
    ("Personal Social", "Mapa mudo del Perú",
     "Para imprimir y trabajar las regiones naturales."),
]


def sortear_estado():
    r = random.random()
    acumulado = 0.0
    for estado, prob in REPARTO:
        acumulado += prob
        if r < acumulado:
            return estado
    return "P"


def dias_lectivos(desde, hasta):
    """Lunes a viernes, sin feriados ni vacaciones de medio año."""
    dia = desde
    while dia <= hasta:
        if (dia.weekday() < 5 and dia not in FERIADOS
                and not (VACACIONES[0] <= dia <= VACACIONES[1])):
            yield dia
        dia += timedelta(days=1)


def buscar_alumno(db):
    return db.execute(text("""
        SELECT a.id_alumno, a.nombres, a.apellidos, a.id_usuario,
               m.id_matricula, m.id_seccion, m.id_anio_escolar,
               ae.fecha_inicio, ae.fecha_fin
        FROM alumno a
        JOIN matricula m ON m.id_alumno = a.id_alumno
        JOIN anio_escolar ae ON ae.id_anio_escolar = m.id_anio_escolar
        WHERE a.dni IN (:d, :dv) AND ae.activo = 1"""),
        {"d": DNI_ALUMNO, "dv": DNI_VIDEO}).fetchone()


def cargas_por_curso(db, id_seccion, anio):
    """{'Aritmética': (id_carga, id_curso)} para la sección del alumno."""
    filas = db.execute(text("""
        SELECT c.nombre, ca.id_carga_academica, c.id_curso
        FROM carga_academica ca JOIN curso c ON c.id_curso = ca.id_curso
        WHERE ca.id_seccion = :s AND ca.id_anio_escolar = :a"""),
        {"s": id_seccion, "a": anio}).fetchall()
    return {f[0]: (f[1], f[2]) for f in filas}


def ultimo_id(db):
    return db.execute(text("SELECT LAST_INSERT_ID()")).scalar()


# ---------------------------------------------------------------------------
# Borrado — por clave, leyendo el registro que dejó --aplicar
# ---------------------------------------------------------------------------

def borrar(db):
    if not os.path.exists(REGISTRO):
        print("[!] No existe el registro de lo que se creó:")
        print(f"    {REGISTRO}")
        print("\n    Sin él no se puede distinguir lo de prueba de lo real, y")
        print("    borrar a ciegas se llevaría por delante datos buenos. Si")
        print("    estás seguro de que la base solo tiene datos de prueba,")
        print("    bórralos a mano.")
        return

    with open(REGISTRO, encoding="utf-8") as f:
        reg = json.load(f)

    total = 0

    def quitar(tabla, clave, ids, etiqueta):
        nonlocal total
        if not ids:
            return
        n = db.execute(text(f"DELETE FROM {tabla} WHERE {clave} IN :i"),
                       {"i": tuple(ids)}).rowcount
        total += n
        print(f"  {etiqueta:<34} {n}")

    # Orden: primero lo que apunta a otra cosa.
    quitar("entrega_tarea", "id_entrega", reg.get("entrega_tarea"),
           "entregas de tareas nuevas")
    quitar("pago", "id_pago", reg.get("pago"), "pagos de esos trámites")
    quitar("solicitud_tramite", "id_solicitud_tramite",
           reg.get("solicitud_tramite"), "solicitudes de trámite")
    quitar("tarea", "id_tarea", reg.get("tarea"), "tareas nuevas")
    quitar("material_clase", "id_material", reg.get("material_clase"),
           "materiales de clase")
    quitar("cita_psicologia", "id_cita", reg.get("cita_psicologia"),
           "citas de psicología")
    quitar("asistencia", "id_asistencia", reg.get("asistencia"),
           "registros de asistencia")
    quitar("nota", "id_nota", reg.get("nota"), "notas del bimestre 2")
    quitar("nota_conducta", "id_nota_conducta", reg.get("nota_conducta"),
           "nota de conducta del bimestre 2")

    # Las fechas de entrega que se pusieron a tareas que ya existían.
    sin_fecha = reg.get("tarea_fecha_puesta") or []
    if sin_fecha:
        n = db.execute(text("""UPDATE tarea SET fecha_entrega = NULL
                              WHERE id_tarea IN :i"""),
                       {"i": tuple(sin_fecha)}).rowcount
        total += n
        print(f"  {'fechas de entrega devueltas a NULL':<34} {n}")

    # El resumen de notas se modificó, no se insertó: se restaura fila a fila.
    for fila in reg.get("resumen_nota") or []:
        db.execute(text("""UPDATE resumen_nota
                          SET nota_bimestre2 = :b2, promedio_final = :pf
                          WHERE id_resumen_notas = :i"""),
                   {"b2": fila["nota_bimestre2"], "pf": fila["promedio_final"],
                    "i": fila["id"]})
        total += 1
    if reg.get("resumen_nota"):
        print(f"  {'resumen de notas restaurado':<34} "
              f"{len(reg['resumen_nota'])}")

    # El catálogo solo se quita si nadie más lo está usando.
    tipos = reg.get("tipo_tramite") or []
    if tipos:
        usados = db.execute(text("""
            SELECT COUNT(*) FROM solicitud_tramite WHERE id_tipo_tramite IN :i"""),
            {"i": tuple(tipos)}).scalar()
        if usados:
            print(f"  [!] El catálogo de trámites se conserva: {usados} "
                  f"solicitud(es) lo están usando.")
        else:
            quitar("tipo_tramite", "id_tipo_tramite", tipos,
                   "catálogo de trámites")

    db.commit()
    os.remove(REGISTRO)
    print(f"\n>>> {total} FILAS DESHECHAS")


# ---------------------------------------------------------------------------
# Generación
# ---------------------------------------------------------------------------

def main():
    db = SessionLocal()
    try:
        info = buscar_alumno(db)
        if not info:
            print(f"No hay ningún alumno con DNI {DNI_ALUMNO} matriculado "
                  f"en el año activo.")
            return

        (id_alumno, nombres, apellidos, id_usuario, id_matricula,
         id_seccion, anio, inicio, fin) = info

        print(f"Alumno:    {apellidos}, {nombres}  (id {id_alumno})")
        print(f"Matrícula: {id_matricula} · sección {id_seccion} · año {anio}\n")

        if BORRAR:
            print("DESHACIENDO LOS DATOS DE PRUEBA")
            borrar(db)
            return

        if os.path.exists(REGISTRO) and APLICAR:
            print("[!] Ya hay datos de prueba creados (existe el registro de")
            print(f"    ids). Ejecuta --borrar antes de volver a crearlos.")
            return

        cargas = cargas_por_curso(db, id_seccion, anio)
        if not cargas:
            print("[!] La sección no tiene carga académica. Nada que hacer.")
            return

        hoy = date.today()
        ids_carga = tuple(v[0] for v in cargas.values())

        hay_catalogo = db.execute(
            text("SELECT COUNT(*) FROM tipo_tramite")).scalar()
        ya_asistencia = db.execute(text(
            "SELECT COUNT(*) FROM asistencia WHERE id_matricula = :m"),
            {"m": id_matricula}).scalar()
        ya_tramites = db.execute(text(
            "SELECT COUNT(*) FROM solicitud_tramite WHERE id_alumno = :a"),
            {"a": id_alumno}).scalar()
        hay_conducta2 = db.execute(text(
            "SELECT COUNT(*) FROM nota_conducta WHERE id_matricula=:m AND bimestre=2"),
            {"m": id_matricula}).scalar()
        faltan = db.execute(text("""
            SELECT c.id_curso, c.nombre, n1.valor
            FROM nota n1 JOIN curso c ON c.id_curso = n1.id_curso
            WHERE n1.id_matricula = :m AND n1.bimestre = 1
              AND n1.id_curso NOT IN (SELECT id_curso FROM nota
                                      WHERE id_matricula = :m AND bimestre = 2)
            """), {"m": id_matricula}).fetchall()
        sin_fecha = [f[0] for f in db.execute(text("""
            SELECT id_tarea FROM tarea WHERE id_carga_academica IN :c
            AND fecha_entrega IS NULL"""), {"c": ids_carga}).fetchall()]
        dias = list(dias_lectivos(inicio, min(hoy, fin)))

        print("Se va a crear:")
        if hay_catalogo:
            print(f"        el catálogo de trámites ya tiene {hay_catalogo} "
                  f"tipos: no se toca")
        else:
            print(f"  {len(CATALOGO_TRAMITES):>4}  tipos de trámite "
                  f"(el catálogo está vacío)")
        if ya_asistencia:
            print(f"        ya tiene {ya_asistencia} días de asistencia: "
                  f"no se toca")
        else:
            print(f"  {len(dias):>4}  días de asistencia")
        print(f"  {len(faltan):>4}  notas del bimestre 2")
        if not hay_conducta2:
            print(f"  {1:>4}  nota de conducta del bimestre 2")
        if ya_tramites:
            print(f"        ya tiene {ya_tramites} trámites: no se tocan")
        else:
            print(f"  {3:>4}  solicitudes de trámite, con su pago")
        print(f"  {2:>4}  citas de psicología")
        print(f"  {len(sin_fecha):>4}  tareas a las que se les pone fecha")
        print(f"  {len(TAREAS_NUEVAS):>4}  tareas nuevas por vencer")
        print(f"  {len(MATERIALES):>4}  materiales de clase")

        if dias and not ya_asistencia:
            conteo = {"P": 0, "T": 0, "F": 0, "J": 0}
            for _ in dias:
                conteo[sortear_estado()] += 1
            computables = len(dias) - conteo["J"]
            pct = round((conteo["P"] + conteo["T"]) / computables * 100, 1)
            print(f"\n  Asistencia: {conteo['P']}P · {conteo['T']}T · "
                  f"{conteo['F']}F · {conteo['J']}J  ->  {pct}% en el campus")
            random.seed(90313123)      # se rebobina: arriba solo se contó

        if not APLICAR:
            print("\n>>> SIMULACIÓN: no se escribió nada. Repite con --aplicar.")
            return

        escribir(db, info, cargas, ids_carga, dias, faltan, sin_fecha,
                 ya_asistencia, ya_tramites, hay_catalogo, hay_conducta2, hoy)
    finally:
        db.close()


def escribir(db, info, cargas, ids_carga, dias, faltan, sin_fecha,
             ya_asistencia, ya_tramites, hay_catalogo, hay_conducta2, hoy):
    (id_alumno, _, _, id_usuario, id_matricula, _, anio, _, _) = info

    reg = {"tipo_tramite": [], "asistencia": [], "nota": [], "nota_conducta": [],
           "resumen_nota": [], "solicitud_tramite": [], "pago": [],
           "cita_psicologia": [], "tarea": [], "material_clase": [],
           "entrega_tarea": [], "tarea_fecha_puesta": []}

    # --- Catálogo de trámites --------------------------------------------
    if not hay_catalogo:
        for nombre, costo, requisitos, periodo, dias_venc in CATALOGO_TRAMITES:
            db.execute(text("""
                INSERT INTO tipo_tramite
                  (nombre, costo, requisitos, activo, alcance,
                   grados_permitidos, periodo_academico, dias_vencimiento)
                VALUES (:n, :c, :r, 1, 'TODOS', NULL, :p, :d)"""),
                {"n": nombre, "c": costo, "r": requisitos, "p": periodo,
                 "d": dias_venc})
            reg["tipo_tramite"].append(ultimo_id(db))

    # --- Asistencia ------------------------------------------------------
    if not ya_asistencia:
        for dia in dias:
            estado = sortear_estado()
            obs = (random.choice(OBSERVACIONES.get(estado, [""]))
                   if estado != "P" else "")
            db.execute(text("""
                INSERT INTO asistencia (id_matricula, fecha, estado, observacion)
                VALUES (:m, :f, :e, :o)"""),
                {"m": id_matricula, "f": dia, "e": estado, "o": obs or None})
            reg["asistencia"].append(ultimo_id(db))

    # --- Notas del bimestre 2 --------------------------------------------
    # Se mueven poco respecto al bimestre 1: entre -2 y +2, sin bajar de 11.
    # Un alumno no cambia de carácter de un bimestre a otro.
    for id_curso, nombre_curso, valor_b1 in faltan:
        b1 = float(valor_b1)
        b2 = max(11, min(20, round(b1 + random.choice([-2, -1, -1, 0, 1, 1, 2]))))
        db.execute(text("""
            INSERT INTO nota (id_matricula, id_curso, bimestre, tipo_nota,
                              valor, fecha_registro)
            VALUES (:m, :c, 2, 'PROMEDIO', :v, :f)"""),
            {"m": id_matricula, "c": id_curso, "v": b2,
             "f": datetime(2026, 7, 17, 11, 30)})
        reg["nota"].append(ultimo_id(db))

        anterior = db.execute(text("""
            SELECT id_resumen_notas, nota_bimestre2, promedio_final
            FROM resumen_nota WHERE id_matricula = :m AND id_curso = :c"""),
            {"m": id_matricula, "c": id_curso}).fetchone()
        if anterior:
            reg["resumen_nota"].append({
                "id": anterior[0],
                "nota_bimestre2": float(anterior[1]) if anterior[1] is not None else None,
                "promedio_final": float(anterior[2]) if anterior[2] is not None else None,
            })
            db.execute(text("""
                UPDATE resumen_nota SET nota_bimestre2 = :v,
                       promedio_final = ROUND((nota_bimestre1 + :v) / 2, 2)
                WHERE id_resumen_notas = :i"""), {"v": b2, "i": anterior[0]})

    if not hay_conducta2:
        db.execute(text("""
            INSERT INTO nota_conducta (id_matricula, bimestre, valor, origen,
                                       fecha_registro)
            VALUES (:m, 2, 17.00, 'CALCULADO', :f)"""),
            {"m": id_matricula, "f": datetime(2026, 7, 17, 12, 0)})
        reg["nota_conducta"].append(ultimo_id(db))

    # --- Trámites --------------------------------------------------------
    if not ya_tramites:
        tipos = db.execute(text("""
            SELECT id_tipo_tramite, nombre, costo, dias_vencimiento
            FROM tipo_tramite WHERE activo = 1""")).fetchall()
        guion = [
            ("Constancia de Estudios", "APROBADO", 40, "PAGADO",
             "Lo necesito para la academia de natación.",
             "Documento listo. Recabar en Secretaría de 8:00 a 13:00."),
            ("Certificado de Estudios", "PAGADO_PENDIENTE_REV", 12, "PAGADO",
             "Es para el trámite de la beca.", None),
            ("Duplicado de Libreta de Notas", "PENDIENTE_PAGO", 3, "PENDIENTE",
             "Se traspapeló la libreta del primer bimestre.", None),
        ]
        for nombre, estado, hace, estado_pago, comentario, respuesta in guion:
            tipo = next((t for t in tipos if t[1] == nombre), None)
            if tipo is None:
                continue
            id_tipo, _, costo, dias_venc = tipo
            fecha = (datetime.combine(hoy - timedelta(days=hace),
                                      datetime.min.time()) + timedelta(hours=9))
            db.execute(text("""
                INSERT INTO solicitud_tramite
                  (id_alumno, id_tipo_tramite, fecha_solicitud, estado,
                   archivo_adjunto, comentario_usuario, respuesta_administrativa)
                VALUES (:a, :t, :f, :e, NULL, :c, :r)"""),
                {"a": id_alumno, "t": id_tipo, "f": fecha, "e": estado,
                 "c": comentario, "r": respuesta})
            id_sol = ultimo_id(db)
            reg["solicitud_tramite"].append(id_sol)
            if float(costo) > 0:
                db.execute(text("""
                    INSERT INTO pago (id_usuario, id_alumno, id_solicitud_tramite,
                        concepto, monto, monto_total, mora, estado,
                        fecha_vencimiento, fecha_pago)
                    VALUES (:u, :a, :s, :con, :mo, :mo, 0, :est, :ven, :pag)"""),
                    {"u": id_usuario, "a": id_alumno, "s": id_sol,
                     "con": f"TRAMITE: {nombre} (REGULAR)", "mo": costo,
                     "est": estado_pago,
                     "ven": (fecha + timedelta(days=dias_venc or 15)).date(),
                     "pag": fecha + timedelta(days=1)
                            if estado_pago == "PAGADO" else None})
                reg["pago"].append(ultimo_id(db))

    # --- Citas de psicología ---------------------------------------------
    db.execute(text("""
        INSERT INTO cita_psicologia (id_alumno, id_familiar, motivo, fecha_cita,
                                     estado, resultado_reunion)
        VALUES (:a, NULL, :mo, :f, 'ATENDIDA', :r)"""),
        {"a": id_alumno, "f": datetime(2026, 6, 11, 10, 0),
         "mo": "Entrevista de seguimiento del primer bimestre",
         "r": "Se conversó sobre su participación en clase. El alumno se "
              "muestra colaborador. Se acordó reforzar los hábitos de estudio "
              "en casa con apoyo del apoderado."})
    reg["cita_psicologia"].append(ultimo_id(db))

    db.execute(text("""
        INSERT INTO cita_psicologia (id_alumno, id_familiar, motivo, fecha_cita,
                                     estado, resultado_reunion)
        VALUES (:a, NULL, :mo, :f, 'PROGRAMADA', NULL)"""),
        {"a": id_alumno,
         "f": datetime.combine(hoy + timedelta(days=6), datetime.min.time())
              + timedelta(hours=11, minutes=30),
         "mo": "Taller de habilidades sociales — sesión grupal"})
    reg["cita_psicologia"].append(ultimo_id(db))

    # --- Tareas y materiales ---------------------------------------------
    # Las que existían no tenían fecha, así que nunca salían como pendientes.
    # Se les pone una ya vencida: son de bimestres que ya cerraron.
    if sin_fecha:
        db.execute(text("""
            UPDATE tarea
            SET fecha_entrega = COALESCE(
                DATE_ADD(fecha_publicacion, INTERVAL 7 DAY), :respaldo)
            WHERE id_tarea IN :i"""),
            {"i": tuple(sin_fecha), "respaldo": datetime(2026, 7, 10, 23, 59)})
        reg["tarea_fecha_puesta"] = sin_fecha

    for curso, titulo, descripcion, peso in TAREAS_NUEVAS:
        if curso not in cargas:
            continue
        vence = (datetime.combine(hoy + timedelta(days=random.choice([2, 4, 6, 9])),
                                  datetime.min.time())
                 + timedelta(hours=23, minutes=59))
        db.execute(text("""
            INSERT INTO tarea (id_carga_academica, titulo, descripcion,
                fecha_publicacion, fecha_entrega, archivo_adjunto_url, estado,
                tipo_evaluacion, bimestre, peso)
            VALUES (:c, :t, :d, :pub, :ven, NULL, 'ACTIVO', 'TAREA', 3, :p)"""),
            {"c": cargas[curso][0], "t": titulo, "d": descripcion,
             "pub": (datetime.combine(hoy - timedelta(days=2),
                                      datetime.min.time()) + timedelta(hours=8)),
             "ven": vence, "p": peso})
        reg["tarea"].append(ultimo_id(db))

    for curso, titulo, descripcion in MATERIALES:
        if curso not in cargas:
            continue
        db.execute(text("""
            INSERT INTO material_clase (id_carga_academica, titulo, descripcion,
                archivo_url, bimestre, fecha_publicacion)
            VALUES (:c, :t, :d, NULL, 3, :f)"""),
            {"c": cargas[curso][0], "t": titulo, "d": descripcion,
             "f": (datetime.combine(hoy - timedelta(days=random.choice([1, 3, 5, 8])),
                                    datetime.min.time())
                   + timedelta(hours=7, minutes=30))})
        reg["material_clase"].append(ultimo_id(db))

    db.commit()

    with open(REGISTRO, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=1)

    creadas = sum(len(v) for k, v in reg.items() if k != "resumen_nota")
    print(f"\n>>> {creadas} FILAS CREADAS")
    print(f"    Registro de claves: {os.path.basename(REGISTRO)}")
    print("    Entra al campus como ALU-90313123 y recorre el panel.")
    print("    Para deshacerlo todo: --borrar")


if __name__ == "__main__":
    main()
