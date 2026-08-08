"""
DATOS DE PRUEBA — Asistencia del alumno con DNI 73715514.

Genera un historial de asistencia para el año escolar en curso, de lunes a
viernes desde el inicio de clases hasta hoy, con los cuatro estados que maneja
el sistema:

    P  Presente      T  Tardanza      F  Falta      J  Justificado

El reparto imita un caso realista: asiste casi siempre, con algunas tardanzas,
unas pocas faltas y un par de días justificados. Así el porcentaje de asistencia
del alumno queda en un valor creíble y se puede comprobar que las faltas
justificadas no lo penalizan.

Se escribe directamente en la base, sin pasar por la API, de modo que NO se
envía ningún correo a los apoderados.

ESTO NO ES DATO REAL. Para borrarlo todo:

    python scripts/datos_prueba_asistencia.py --borrar

Uso:
    python scripts/datos_prueba_asistencia.py            # simulación
    python scripts/datos_prueba_asistencia.py --aplicar  # crea los datos
    python scripts/datos_prueba_asistencia.py --borrar   # los elimina
"""
import os
import random
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from app.db.database import SessionLocal

DNI_ALUMNO = "73715514"

APLICAR = "--aplicar" in sys.argv
BORRAR = "--borrar" in sys.argv

random.seed(73715514)   # mismo historial en cada ejecución

# Probabilidad de cada estado en un día cualquiera
REPARTO = [("P", 0.86), ("T", 0.08), ("F", 0.04), ("J", 0.02)]

OBSERVACIONES = {
    "T": ["Llegó 10 minutos tarde", "Ingresó después del timbre", "Tardanza justificada por el apoderado", ""],
    "F": ["", "No se presentó", "Inasistencia sin aviso"],
    "J": ["Cita médica", "Permiso familiar presentado por el apoderado", "Certificado médico"],
}


def sortear_estado():
    r = random.random()
    acumulado = 0.0
    for estado, prob in REPARTO:
        acumulado += prob
        if r < acumulado:
            return estado
    return "P"


def datos_alumno(db):
    return db.execute(text("""
        SELECT a.id_alumno, a.nombres, a.apellidos, m.id_matricula, m.id_anio_escolar,
               ae.fecha_inicio, ae.fecha_fin
        FROM alumno a
        JOIN matricula m ON m.id_alumno = a.id_alumno
        JOIN anio_escolar ae ON ae.id_anio_escolar = m.id_anio_escolar
        WHERE a.dni = :d AND ae.activo = 1"""), {"d": DNI_ALUMNO}).fetchone()


def dias_lectivos(desde, hasta):
    """Lunes a viernes entre las dos fechas, ambas incluidas."""
    dia = desde
    while dia <= hasta:
        if dia.weekday() < 5:          # 0=lunes ... 4=viernes
            yield dia
        dia += timedelta(days=1)


def main():
    db = SessionLocal()
    try:
        info = datos_alumno(db)
        if not info:
            print(f"No se encontró un alumno con DNI {DNI_ALUMNO} matriculado en el año activo.")
            return

        id_alumno, nombres, apellidos, id_matricula, anio, inicio, fin = info
        print(f"Alumno: {apellidos}, {nombres} (DNI {DNI_ALUMNO})")
        print(f"Matrícula {id_matricula} · año {anio}\n")

        if BORRAR:
            n = db.execute(text(
                "SELECT COUNT(*) FROM asistencia WHERE id_matricula = :m"),
                {"m": id_matricula}).scalar()
            print(f"Se eliminarán {n} registros de asistencia.")
            if n:
                db.execute(text("DELETE FROM asistencia WHERE id_matricula = :m"),
                           {"m": id_matricula})
                db.commit()
            print(">>> DATOS DE PRUEBA ELIMINADOS")
            return

        existentes = db.execute(text(
            "SELECT COUNT(*) FROM asistencia WHERE id_matricula = :m"),
            {"m": id_matricula}).scalar()
        if existentes:
            print(f"[!] El alumno ya tiene {existentes} registros. Ejecuta --borrar antes de volver a crear.")
            return

        # Desde el inicio de clases hasta hoy (o hasta que acabe el año, si ya pasó)
        hasta = min(date.today(), fin)
        dias = list(dias_lectivos(inicio, hasta))

        conteo = {"P": 0, "T": 0, "F": 0, "J": 0}
        filas = []
        for dia in dias:
            estado = sortear_estado()
            conteo[estado] += 1
            observacion = random.choice(OBSERVACIONES.get(estado, [""])) if estado != "P" else ""
            filas.append((dia, estado, observacion or None))

        total = len(filas)
        computables = total - conteo["J"]
        porcentaje = round((conteo["P"] + conteo["T"]) / computables * 100, 1) if computables else None

        print(f"Días lectivos entre {inicio} y {hasta}: {total}")
        print(f"  Presente     {conteo['P']:>4}")
        print(f"  Tardanza     {conteo['T']:>4}")
        print(f"  Falta        {conteo['F']:>4}")
        print(f"  Justificado  {conteo['J']:>4}   (no penalizan el porcentaje)")
        print(f"\n  Porcentaje de asistencia que mostrará el campus: {porcentaje}%")
        print(f"  (se calcula como (P + T) / (total - J) = "
              f"({conteo['P']} + {conteo['T']}) / {computables})")

        if not APLICAR:
            print("\n>>> SIMULACIÓN: no se escribió nada. Repite con --aplicar.")
            return

        for dia, estado, observacion in filas:
            db.execute(text("""
                INSERT INTO asistencia (id_matricula, fecha, estado, observacion)
                VALUES (:m, :f, :e, :o)"""),
                {"m": id_matricula, "f": dia, "e": estado, "o": observacion})
        db.commit()
        print(f"\n>>> {total} REGISTROS DE ASISTENCIA CREADOS")
    finally:
        db.close()


if __name__ == "__main__":
    main()
