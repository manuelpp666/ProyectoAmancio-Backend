"""
Rellena `curso.minutos_semanales` y alinea el plan de estudio con los horarios
2026 (ver scripts/datos_horarios_2026.py).

Qué hace:
  1. Da de alta los cursos que aparecen en los horarios y no están en la base.
  2. Añade al plan de estudio las parejas curso-grado que faltan.
  3. Calcula los minutos semanales de cada curso y los guarda.

Sobre el punto 3: `curso.minutos_semanales` es una sola columna por curso, pero
un mismo curso puede durar distinto según el grado (Inglés son 135' en primaria
y 100' en secundaria, porque el bloque de primaria es de 45' y el de secundaria
de 50'). Como no se toca el esquema, se guarda el valor que corresponde a MÁS
grados de los que tiene asignados; los cursos donde hay discrepancia se listan
al final para poder revisarlos a mano.

Uso:
    python scripts/cargar_minutos_horarios.py            # simulación, no escribe
    python scripts/cargar_minutos_horarios.py --aplicar  # escribe en la base
"""
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from app.db.database import SessionLocal
from scripts.datos_horarios_2026 import BLOQUES, MINUTOS_BLOQUE, SIN_HORARIO, NOTAS

APLICAR = "--aplicar" in sys.argv

# Área de los cursos que hay que dar de alta. Se eligen las mismas que usan los
# cursos equivalentes: Arte va con Violín y Ajedrez, y Tutoría con Religión,
# Psicología y Educación Física.
AREA_DE_CURSO = {
    "Arte": "Talleres",
    "Tutoría": "Formación Integral",
}


def main():
    db = SessionLocal()
    try:
        niveles = {n: i for i, n in db.execute(text("SELECT id_nivel, nombre FROM nivel"))}
        grados = {}     # (nivel, nombre) -> id_grado
        for id_grado, nombre_grado, id_nivel in db.execute(text(
                "SELECT id_grado, nombre, id_nivel FROM grado")):
            nombre_nivel = next(n for n, i in niveles.items() if i == id_nivel)
            grados[(nombre_nivel, nombre_grado)] = id_grado

        cursos = {nombre: id_curso for id_curso, nombre in
                  db.execute(text("SELECT id_curso, nombre FROM curso"))}
        plan = {(c, g) for c, g in db.execute(text(
            "SELECT id_curso, id_grado FROM plan_estudio"))}

        # --- 1. cursos que faltan ---------------------------------------
        # Todo curso tiene que llevar área: el esquema de respuesta la declara
        # obligatoria, así que un curso con id_area a NULL hace fallar entero el
        # listado de Gestión de Cursos con un 500.
        areas = {n: i for i, n in db.execute(text("SELECT id_area, nombre FROM area"))}
        necesarios = {c for nivel in BLOQUES.values()
                      for reparto in nivel.values() for c in reparto}
        nuevos = sorted(necesarios - set(cursos))
        print("=== CURSOS NUEVOS ===")
        if not nuevos:
            print("  (ninguno)")
        for nombre in nuevos:
            nombre_area = AREA_DE_CURSO.get(nombre)
            id_area = areas.get(nombre_area)
            if id_area is None:
                print(f"  [!] {nombre}: no sé en qué área ponerlo "
                      f"(añádelo a AREA_DE_CURSO). No se crea.")
                continue
            print(f"  + {nombre}  (área: {nombre_area})")
            if APLICAR:
                db.execute(text("INSERT INTO curso (nombre, id_area, minutos_semanales, es_verano) "
                                "VALUES (:n, :a, 0, 0)"), {"n": nombre, "a": id_area})
                cursos[nombre] = db.execute(text("SELECT LAST_INSERT_ID()")).scalar()

        # --- 2. plan de estudio ------------------------------------------
        print("\n=== PLAN DE ESTUDIO: ASIGNACIONES QUE FALTAN ===")
        faltan = []
        for nombre_nivel, por_grado in BLOQUES.items():
            for nombre_grado, reparto in por_grado.items():
                id_grado = grados.get((nombre_nivel, nombre_grado))
                if id_grado is None:
                    print(f"  [!] no existe el grado {nombre_nivel} {nombre_grado}")
                    continue
                for curso in reparto:
                    id_curso = cursos.get(curso)
                    if id_curso is None:      # recién creado en modo simulación
                        continue
                    if (id_curso, id_grado) not in plan:
                        faltan.append((curso, nombre_nivel, nombre_grado, id_curso, id_grado))
        if not faltan:
            print("  (ninguna)")
        for curso, nivel, grado, id_curso, id_grado in faltan:
            print(f"  + {curso:<26} -> {nivel} {grado}")
            if APLICAR:
                db.execute(text("INSERT INTO plan_estudio (id_curso, id_grado) "
                                "VALUES (:c, :g)"), {"c": id_curso, "g": id_grado})

        # --- 3. minutos semanales ----------------------------------------
        # minutos que le tocan a cada curso en cada grado donde se dicta
        por_curso = defaultdict(list)
        for nombre_nivel, por_grado in BLOQUES.items():
            minutos_bloque = MINUTOS_BLOQUE[nombre_nivel]
            for nombre_grado, reparto in por_grado.items():
                for curso, bloques in reparto.items():
                    por_curso[curso].append(
                        (f"{nombre_nivel[:4].lower()} {nombre_grado}", bloques * minutos_bloque))

        print("\n=== MINUTOS SEMANALES ===")
        discrepantes = []
        actuales = {n: m for n, m in db.execute(text(
            "SELECT nombre, minutos_semanales FROM curso"))}
        for curso in sorted(por_curso):
            valores = [m for _, m in por_curso[curso]]
            conteo = Counter(valores)
            # Gana el valor que cubre más grados. Si empatan (Educación Física
            # son 45' en 1ero-3ero de primaria y 90' en 4to-6to, tres grados
            # cada uno) se toma el mayor: es preferible que el horario aparezca
            # incompleto a que se dé por cubierto antes de tiempo.
            elegido = max(conteo, key=lambda m: (conteo[m], m))
            antes = actuales.get(curso, 0)
            marca = " " if len(conteo) == 1 else "*"
            print(f" {marca}{curso:<26} {antes!s:>5} -> {elegido:<5} "
                  f"({', '.join(f'{g}:{m}' for g, m in por_curso[curso])})")
            if len(conteo) > 1:
                discrepantes.append((curso, dict(conteo)))
            if APLICAR:
                db.execute(text("UPDATE curso SET minutos_semanales = :m WHERE nombre = :n"),
                           {"m": elegido, "n": curso})

        if discrepantes:
            print("\n  (*) Estos cursos NO duran lo mismo en todos sus grados. Se guardó el "
                  "valor más repetido:")
            for curso, conteo in discrepantes:
                detalle = ", ".join(f"{m}' en {n} grado(s)" for m, n in sorted(conteo.items()))
                print(f"      {curso}: {detalle}")

        print("\n=== CURSOS SIN HORARIO (se dejan como están) ===")
        for c in SIN_HORARIO:
            print(f"  - {c}: {actuales.get(c, '?')} min")

        print("\n=== NOTAS DE LA EXTRACCIÓN ===")
        for n in NOTAS:
            print(f"  - {n}")

        if APLICAR:
            db.commit()
            print("\n>>> CAMBIOS GUARDADOS")
        else:
            db.rollback()
            print("\n>>> SIMULACIÓN: no se escribió nada. Repite con --aplicar para guardar.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
