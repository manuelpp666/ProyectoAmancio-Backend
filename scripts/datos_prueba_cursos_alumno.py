"""
DATOS DE PRUEBA — Apartado «Cursos» del panel del estudiante.

Llena el aula virtual de los 16 cursos del alumno con contenido de clase,
tareas, entregas y clases virtuales, para poder grabar el video manual sin que
la pantalla salga vacía.

EL PROBLEMA QUE RESUELVE
    El aula virtual de cada curso pinta SIEMPRE los cuatro bimestres, y dentro
    de cada uno dos apartados: «Contenido de clase» y «Tareas y exámenes». Hoy
    la mayoría de cursos tiene una o dos tareas sueltas y ningún material, así
    que al abrir un curso se ven ocho recuadros de «Aún no hay contenido» y uno
    con datos. En un video eso parece que el sistema no funciona.

QUÉ CREA, POR CURSO
    Bimestres I, II y III (el IV se deja vacío a propósito: aún no ha llegado)

        2 materiales de clase   uno por cada tema de la unidad
        3 actividades           dos prácticas y un examen bimestral
        entregas del alumno     I y II completos y calificados;
                                del III, solo la primera entregada
        2 clases virtuales      una ya dictada y otra por venir

    Los temas son propios de cada materia: en Aritmética habla de fracciones y
    en Plan Lector de comprensión de textos. Con títulos genéricos tipo
    «Tarea 1» el video se nota falso enseguida.

    En el III bimestre queda a propósito una tarea PENDIENTE con fecha futura,
    para poder enseñar en el video cómo se ve algo por entregar.

ESTO NO ES DATO REAL. Es para la base de desarrollo. No ejecutar en el
servidor.

A QUIÉN AFECTA
    Las tareas, los materiales y las clases virtuales cuelgan de la carga
    académica, no del alumno: los verá toda la sección. Las entregas y sus
    notas sí son solo de este alumno. En desarrollo da igual, pero conviene
    saberlo.

CÓMO SE DESHACE
    Nada de lo que se escribe lleva una marca de «esto es de prueba»: se vería
    en pantalla. Las claves de todo lo insertado se anotan en

        scripts/datos_prueba_cursos_alumno.ids.json

    y --borrar quita exactamente esas filas, ni una más. Si se pierde ese
    archivo el borrado ya no puede distinguir lo de prueba de lo real, y avisa
    en vez de adivinar.

POR QUÉ BUSCA POR id_alumno Y NO POR DNI
    El DNI de este alumno se cambió temporalmente para grabar el video, así que
    buscarlo por DNI dejaría de funcionar en cuanto se restaure. El id no
    cambia nunca.

Uso:
    python scripts/datos_prueba_cursos_alumno.py            # simulación
    python scripts/datos_prueba_cursos_alumno.py --aplicar  # crea los datos
    python scripts/datos_prueba_cursos_alumno.py --borrar   # los elimina
"""
import json
import os
import random
import sys
import unicodedata
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.db.database import SessionLocal, SQLALCHEMY_DATABASE_URL  # noqa: E402

# Cinturón de seguridad: este script escribe datos falsos a nombre de un alumno
# que existe. Si algún día alguien lo lanza apuntando al servidor, que reviente
# aquí y no a mitad de la inserción.
assert "amancio_bd_servidor" in SQLALCHEMY_DATABASE_URL, \
    "Este script solo se ejecuta contra la base LOCAL de desarrollo."

ID_ALUMNO = 82
ANIO = "2026"

REGISTRO = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "datos_prueba_cursos_alumno.ids.json")

# El IV bimestre se deja fuera: hoy estamos en el III y un bimestre futuro con
# tareas ya entregadas no tendría ningún sentido.
BIMESTRES = (1, 2, 3)

# Rango de fechas de cada bimestre del 2026. La tabla `bimestre` está vacía en
# esta base, así que las fechas van aquí en vez de consultarse.
FECHAS = {
    1: (datetime(2026, 3, 9), datetime(2026, 5, 15)),
    2: (datetime(2026, 5, 18), datetime(2026, 7, 24)),
    3: (datetime(2026, 8, 10), datetime(2026, 10, 16)),
}

# Dos temas por bimestre y por curso. De aquí salen los títulos de los
# materiales, de las tareas y de las clases virtuales.
TEMARIO = {
    "aritmetica": {
        1: ("Números naturales y sus operaciones", "Divisibilidad y números primos"),
        2: ("Fracciones y números decimales", "Razones y proporciones"),
        3: ("Potenciación y radicación", "Regla de tres y porcentajes"),
    },
    "algebra": {
        1: ("Expresiones algebraicas y términos semejantes", "Productos notables"),
        2: ("Factorización de polinomios", "Ecuaciones de primer grado"),
        3: ("Sistemas de ecuaciones", "Inecuaciones de primer grado"),
    },
    "geometria": {
        1: ("Rectas, ángulos y su medida", "Triángulos y sus propiedades"),
        2: ("Congruencia de triángulos", "Cuadriláteros y polígonos"),
        3: ("Circunferencia y círculo", "Áreas de regiones planas"),
    },
    "razonamiento matematico": {
        1: ("Sucesiones y series", "Operadores matemáticos"),
        2: ("Planteo de ecuaciones", "Edades y móviles"),
        3: ("Conteo de figuras", "Problemas sobre cronometría"),
    },
    "razonamiento verbal": {
        1: ("Sinónimos y antónimos", "Analogías verbales"),
        2: ("Comprensión de lectura", "Términos excluidos"),
        3: ("Conectores lógicos", "Plan de redacción"),
    },
    "comunicacion": {
        1: ("El texto narrativo", "Sujeto y predicado"),
        2: ("El texto descriptivo", "Uso de la tilde"),
        3: ("El texto argumentativo", "Signos de puntuación"),
    },
    "plan lector": {
        1: ("Lectura: «Paco Yunque»", "Ficha de comprensión lectora"),
        2: ("Lectura: «Cuentos andinos»", "Resumen y personajes"),
        3: ("Lectura: «El principito»", "Opinión crítica del texto"),
    },
    "ciencia y tecnologia": {
        1: ("La célula y sus partes", "Los seres vivos y su clasificación"),
        2: ("El sistema digestivo", "El sistema respiratorio"),
        3: ("La materia y sus estados", "Fuerza y movimiento"),
    },
    "personal social": {
        1: ("La familia y la comunidad", "Los derechos del niño"),
        2: ("Las regiones del Perú", "La independencia del Perú"),
        3: ("El Estado peruano y sus poderes", "Convivencia y ciudadanía"),
    },
    "religion": {
        1: ("La creación", "Los valores cristianos"),
        2: ("La familia de Nazaret", "Las parábolas de Jesús"),
        3: ("Los sacramentos", "La solidaridad con el prójimo"),
    },
    "ingles": {
        1: ("Greetings and personal information", "The verb to be"),
        2: ("Family and daily routines", "Present simple"),
        3: ("Food and quantities", "Present continuous"),
    },
    "computacion": {
        1: ("Partes de la computadora", "El escritorio y las carpetas"),
        2: ("Procesador de textos", "Tablas e imágenes en el documento"),
        3: ("Hoja de cálculo", "Presentaciones digitales"),
    },
    "arte": {
        1: ("Los colores primarios y secundarios", "El dibujo de la figura humana"),
        2: ("Técnicas con témpera", "El collage"),
        3: ("Modelado en arcilla", "El mural colectivo"),
    },
    "educacion fisica": {
        1: ("Calentamiento y elongación", "Coordinación y equilibrio"),
        2: ("Fundamentos del vóley", "Fundamentos del básquet"),
        3: ("Atletismo: carreras y saltos", "Juegos predeportivos"),
    },
    "ajedrez": {
        1: ("El tablero y las piezas", "Movimiento de peones y torres"),
        2: ("Aperturas básicas", "El jaque y el jaque mate"),
        3: ("Finales de rey y peón", "Táctica: clavadas y horquillas"),
    },
    "violin": {
        1: ("Postura y sujeción del arco", "Las cuerdas al aire"),
        2: ("Primera posición", "Lectura de partitura sencilla"),
        3: ("Escalas mayores", "Repertorio para la actuación"),
    },
}

TEMARIO_GENERICO = {
    1: ("Primera unidad del curso", "Segunda unidad del curso"),
    2: ("Tercera unidad del curso", "Cuarta unidad del curso"),
    3: ("Quinta unidad del curso", "Sexta unidad del curso"),
}


def plano(texto):
    """Sin tildes y en minúsculas, para buscar en TEMARIO."""
    limpio = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in limpio if not unicodedata.combining(c)).lower().strip()


def temas_de(curso, bimestre):
    return TEMARIO.get(plano(curso), TEMARIO_GENERICO)[bimestre]


def cargas_del_alumno(db):
    """Los cursos de la sección del alumno, con su carga académica."""
    fila = db.execute(text(
        "SELECT id_matricula, id_seccion FROM matricula "
        "WHERE id_alumno = :a AND id_anio_escolar = :y"),
        {"a": ID_ALUMNO, "y": ANIO}).first()
    if not fila:
        return None, None, []
    id_matricula, id_seccion = fila
    cargas = db.execute(text(
        "SELECT ca.id_carga_academica, c.id_curso, c.nombre "
        "  FROM carga_academica ca JOIN curso c ON c.id_curso = ca.id_curso "
        " WHERE ca.id_seccion = :s AND ca.id_anio_escolar = :y "
        " ORDER BY c.nombre"),
        {"s": id_seccion, "y": ANIO}).all()
    return id_matricula, id_seccion, [tuple(r) for r in cargas]


# ---------------------------------------------------------------------------
#  DESHACER
# ---------------------------------------------------------------------------

def borrar(db):
    if not os.path.exists(REGISTRO):
        print("[!] No existe el registro de lo que se creó:")
        print(f"    {REGISTRO}")
        print("\n    Sin él no se puede distinguir lo de prueba de lo real, y")
        print("    borrar a ciegas se llevaría por delante datos buenos.")
        return

    with open(REGISTRO, encoding="utf-8") as f:
        ids = json.load(f)

    total = 0
    # Las entregas van primero: cuelgan de las tareas.
    for tabla, clave, etiqueta in (
            ("entrega_tarea", "id_entrega", "entregas del alumno"),
            ("tarea", "id_tarea", "tareas y exámenes"),
            ("material_clase", "id_material", "materiales de clase"),
            ("clase_virtual", "id_clase_virtual", "clases virtuales")):
        lista = ids.get(tabla) or []
        if not lista:
            continue
        n = db.execute(
            text(f"DELETE FROM {tabla} WHERE {clave} IN :ids"),
            {"ids": tuple(lista)}).rowcount
        total += n
        print(f"  {etiqueta:<26} {n}")

    db.commit()
    os.remove(REGISTRO)
    print(f"\n>>> {total} FILAS DESHECHAS")


# ---------------------------------------------------------------------------
#  CREAR
# ---------------------------------------------------------------------------

def crear(db, cargas, aplicar):
    # Semilla fija: dos ejecuciones dan las mismas notas. Si el video hay que
    # regrabarlo, la pantalla se ve igual que la primera vez.
    az = random.Random(ID_ALUMNO)
    ids = {"material_clase": [], "tarea": [], "entrega_tarea": [],
           "clase_virtual": []}
    cuenta = {"materiales": 0, "tareas": 0, "entregas": 0, "clases": 0}

    for id_carga, _id_curso, nombre_curso in cargas:
        for b in BIMESTRES:
            inicio, fin = FECHAS[b]
            temas = temas_de(nombre_curso, b)

            # ---- contenido de clase: un material por tema
            for i, tema in enumerate(temas):
                publicado = inicio + timedelta(days=7 + i * 21)
                titulo = (f"Separata — {tema}" if i == 0
                          else f"Diapositivas de clase — {tema}")
                descripcion = (f"Teoría y ejercicios resueltos de {tema.lower()}."
                               if i == 0
                               else f"Material proyectado en clase sobre {tema.lower()}.")
                cuenta["materiales"] += 1
                if aplicar:
                    db.execute(text(
                        "INSERT INTO material_clase "
                        "(id_carga_academica, titulo, descripcion, archivo_url, "
                        " bimestre, fecha_publicacion) "
                        "VALUES (:c, :t, :d, NULL, :b, :f)"),
                        {"c": id_carga, "t": titulo[:150], "d": descripcion,
                         "b": b, "f": publicado})
                    ids["material_clase"].append(
                        db.execute(text("SELECT LAST_INSERT_ID()")).scalar())

            # ---- actividades: dos prácticas y un examen
            actividades = [
                (f"Práctica calificada — {temas[0]}", "TAREA", 30,
                 inicio + timedelta(days=18)),
                (f"Trabajo grupal — {temas[1]}", "TAREA", 30,
                 inicio + timedelta(days=39)),
                (f"Examen del {['I', 'II', 'III'][b - 1]} bimestre",
                 "EXAMEN_BIMESTRAL", 40, fin - timedelta(days=3)),
            ]

            for pos, (titulo, tipo, peso, entrega) in enumerate(actividades):
                entrega = entrega.replace(hour=23, minute=59, second=0)
                cuenta["tareas"] += 1
                if aplicar:
                    db.execute(text(
                        "INSERT INTO tarea "
                        "(id_carga_academica, titulo, descripcion, "
                        " fecha_publicacion, fecha_entrega, estado, "
                        " tipo_evaluacion, bimestre, peso) "
                        "VALUES (:c, :t, :d, :fp, :fe, 'ACTIVO', :tp, :b, :p)"),
                        {"c": id_carga, "t": titulo[:150],
                         "d": f"Actividad de {nombre_curso} correspondiente al "
                              f"bimestre {b}.",
                         "fp": entrega - timedelta(days=10), "fe": entrega,
                         "tp": tipo, "b": b, "p": peso})
                    id_tarea = db.execute(
                        text("SELECT LAST_INSERT_ID()")).scalar()
                    ids["tarea"].append(id_tarea)
                else:
                    id_tarea = None

                # ---- entrega del alumno
                #
                # Bimestres I y II: todo entregado y calificado, que ya
                # terminaron. Bimestre III: solo la primera. Las otras dos
                # quedan PENDIENTES, que es justo lo que hay que poder enseñar
                # en el video.
                if b == 3 and pos > 0:
                    continue

                cuenta["entregas"] += 1
                if aplicar:
                    db.execute(text(
                        "INSERT INTO entrega_tarea "
                        "(id_tarea, id_alumno, archivo_url, comentario_alumno, "
                        " fecha_envio, calificacion, retroalimentacion_docente) "
                        "VALUES (:t, :a, NULL, NULL, :f, :n, :r)"),
                        {"t": id_tarea, "a": ID_ALUMNO,
                         "f": entrega - timedelta(days=1),
                         "n": az.randint(12, 18),
                         "r": az.choice([
                             "Buen trabajo, cuida la presentación.",
                             "Correcto. Revisa la ortografía.",
                             "Cumple con lo pedido.",
                             None])})
                    ids["entrega_tarea"].append(
                        db.execute(text("SELECT LAST_INSERT_ID()")).scalar())

        # ---- clases virtuales: una ya dictada y otra por venir
        for etiqueta, cuando in (
                ("dictada", datetime.now() - timedelta(days=6)),
                ("próxima", datetime.now() + timedelta(days=3))):
            tema = temas_de(nombre_curso, 3)[0 if etiqueta == "dictada" else 1]
            cuenta["clases"] += 1
            if aplicar:
                db.execute(text(
                    "INSERT INTO clase_virtual "
                    "(id_carga_academica, tema, fecha, enlace) "
                    "VALUES (:c, :t, :f, :e)"),
                    {"c": id_carga, "t": tema[:150],
                     "f": cuando.replace(hour=10, minute=0, second=0,
                                         microsecond=0),
                     "e": "https://meet.google.com/lookup/amancio-demo"})
                ids["clase_virtual"].append(
                    db.execute(text("SELECT LAST_INSERT_ID()")).scalar())

    if aplicar:
        db.commit()
        with open(REGISTRO, "w", encoding="utf-8") as f:
            json.dump(ids, f, indent=2)

    return cuenta


# ---------------------------------------------------------------------------
#  PRINCIPAL
# ---------------------------------------------------------------------------

def main():
    db = SessionLocal()
    try:
        alumno = db.execute(text(
            "SELECT dni, nombres, apellidos FROM alumno WHERE id_alumno = :a"),
            {"a": ID_ALUMNO}).first()
        if not alumno:
            print(f"[!] No existe el alumno {ID_ALUMNO}.")
            return
        dni, nombres, apellidos = alumno

        id_matricula, id_seccion, cargas = cargas_del_alumno(db)
        if not id_matricula:
            print(f"[!] El alumno {ID_ALUMNO} no tiene matrícula en {ANIO}.")
            return

        print(f"Alumno:    {apellidos}, {nombres}  (DNI {dni} · id {ID_ALUMNO})")
        print(f"Matrícula: {id_matricula} · sección {id_seccion} · año {ANIO}")
        print(f"Cursos:    {len(cargas)}\n")

        if "--borrar" in sys.argv:
            print("DESHACIENDO LOS DATOS DE PRUEBA\n")
            borrar(db)
            return

        if os.path.exists(REGISTRO):
            print("[!] Ya hay datos de prueba creados (existe el registro de")
            print("    ids). Ejecuta --borrar antes de volver a crearlos.")
            return

        if not cargas:
            print("[!] La sección no tiene carga académica. Nada que hacer.")
            return

        aplicar = "--aplicar" in sys.argv
        cuenta = crear(db, cargas, aplicar)

        print("Se va a crear:" if not aplicar else "Creado:")
        print(f"  {cuenta['materiales']:>4}  materiales de clase")
        print(f"  {cuenta['tareas']:>4}  tareas y exámenes")
        print(f"  {cuenta['entregas']:>4}  entregas del alumno, con nota")
        print(f"  {cuenta['clases']:>4}  clases virtuales")
        print(f"  {'':>4}  ({len(cargas)} cursos × bimestres I, II y III)")

        if not aplicar:
            print("\nSIMULACIÓN. Nada se ha escrito.")
            print("Para crearlo de verdad:  --aplicar")
        else:
            print(f"\n>>> LISTO. Registro de ids en:\n    {REGISTRO}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
