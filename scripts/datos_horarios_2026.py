"""
Bloques semanales de cada curso por grado, leídos de los horarios 2026.

Fuentes:
  * HORARIOS_FINALES_2026.pdf          -> primaria (12 aulas, bloques de 45')
  * HORARIOS SECUNDARIA 2026 ... .pdf  -> secundaria (10 aulas, bloques de 50')

Los números son BLOQUES por semana, no minutos: el minuto sale de multiplicar
por la duración del bloque de cada nivel. Se guardan así porque es lo que se lee
directamente del horario y permite recalcular si cambia la duración del bloque.

Todas las aulas suman 30 bloques semanales (6 al día x 5 días), que es la
comprobación que valida la extracción.
"""

MINUTOS_BLOQUE = {"PRIMARIA": 45, "SECUNDARIA": 50}

# --- PRIMARIA -------------------------------------------------------------
# Las dos secciones (Amarillo y Azul) de cada grado coinciden en bloques, así
# que se guarda un único reparto por grado.
PRIMARIA = {
    "1ero": {
        "Ajedrez": 2, "Álgebra": 2, "Aritmética": 2, "Arte": 2,
        "Ciencia y Tecnología": 2, "Computación": 2, "Comunicación": 2,
        "Educación Física": 1, "Geometría": 2, "Inglés": 3,
        "Personal Social": 2, "Plan Lector": 1, "Razonamiento Matemático": 2,
        "Razonamiento Verbal": 2, "Religión": 1, "Violín": 2,
    },
    "2do": {
        "Ajedrez": 2, "Álgebra": 2, "Aritmética": 2, "Arte": 2,
        "Ciencia y Tecnología": 2, "Computación": 2, "Comunicación": 2,
        "Educación Física": 1, "Geometría": 2, "Inglés": 3,
        "Personal Social": 2, "Plan Lector": 1, "Razonamiento Matemático": 2,
        "Razonamiento Verbal": 2, "Religión": 1, "Violín": 2,
    },
    "3ero": {
        "Ajedrez": 2, "Álgebra": 2, "Aritmética": 2, "Arte": 2,
        "Ciencia y Tecnología": 2, "Computación": 2, "Comunicación": 2,
        "Educación Física": 1, "Geometría": 2, "Inglés": 3,
        "Personal Social": 2, "Plan Lector": 1, "Razonamiento Matemático": 2,
        "Razonamiento Verbal": 2, "Religión": 1, "Violín": 2,
    },
    "4to": {
        "Ajedrez": 2, "Álgebra": 2, "Aritmética": 2,
        "Ciencia y Tecnología": 2, "Computación": 2, "Comunicación": 2,
        "Educación Física": 2, "Geometría": 2, "Inglés": 3,
        "Personal Social": 2, "Plan Lector": 1, "Razonamiento Matemático": 2,
        "Razonamiento Verbal": 2, "Religión": 1, "Tutoría": 1, "Violín": 2,
    },
    "5to": {
        "Ajedrez": 2, "Álgebra": 2, "Aritmética": 2,
        "Ciencia y Tecnología": 2, "Computación": 2, "Comunicación": 2,
        "Educación Física": 2, "Geometría": 2, "Inglés": 3,
        "Personal Social": 2, "Plan Lector": 1, "Razonamiento Matemático": 2,
        "Razonamiento Verbal": 2, "Religión": 1, "Tutoría": 1, "Violín": 2,
    },
    "6to": {
        "Ajedrez": 2, "Álgebra": 2, "Aritmética": 2,
        "Ciencia y Tecnología": 2, "Computación": 2, "Comunicación": 2,
        "Educación Física": 2, "Geometría": 2, "Inglés": 3,
        "Personal Social": 2, "Plan Lector": 1, "Razonamiento Matemático": 2,
        "Razonamiento Verbal": 2, "Religión": 1, "Tutoría": 1, "Violín": 2,
    },
}

# --- SECUNDARIA -----------------------------------------------------------
SECUNDARIA = {
    "1ero": {
        "Ajedrez": 2, "Álgebra": 2, "Aritmética": 2, "Biología": 2,
        "Computación": 2, "Educación Física": 2, "Física Elemental": 2,
        "Geometría": 2, "Gramática": 2, "Historia": 2, "Inglés": 2,
        "Literatura": 2, "Química": 1, "Razonamiento Matemático": 2,
        "Razonamiento Verbal": 2, "Religión": 1,
    },
    "2do": {
        "Ajedrez": 2, "Álgebra": 2, "Aritmética": 2, "Biología": 2,
        "Computación": 2, "Educación Física": 1, "Física Elemental": 2,
        "Geometría": 2, "Gramática": 2, "Historia": 2, "Inglés": 2,
        "Literatura": 2, "Química": 2, "Razonamiento Matemático": 2,
        "Razonamiento Verbal": 2, "Religión": 1,
    },
    "3ero": {
        "Ajedrez": 2, "Álgebra": 2, "Aritmética": 2, "Biología": 2,
        "Computación": 2, "Educación Física": 2, "Física Elemental": 2,
        "Geohistoria": 2, "Geometría": 2, "Gramática": 2, "Inglés": 2,
        "Literatura": 2, "Química": 2, "Razonamiento Matemático": 2,
        "Razonamiento Verbal": 2,
    },
    "4to": {
        "Álgebra": 2, "Anatomía": 2, "Aritmética": 2, "Biología": 2,
        "Economía": 2, "Física Elemental": 2, "Geometría": 2, "Gramática": 2,
        "Historia": 2, "Inglés": 2, "Literatura": 2, "LOPFIS": 2,
        "Química": 2, "Razonamiento Matemático": 2, "Razonamiento Verbal": 2,
    },
    "5to": {
        "Álgebra": 2, "Anatomía": 2, "Aritmética": 2, "Biología": 2,
        "Economía": 2, "Física Elemental": 2, "Geometría": 2, "Gramática": 2,
        "Historia": 2, "Literatura": 2, "LOPFIS": 2, "Química": 2,
        "Razonamiento Matemático": 2, "Razonamiento Verbal": 2,
    },
}

BLOQUES = {"PRIMARIA": PRIMARIA, "SECUNDARIA": SECUNDARIA}

# Cursos que existen en la base pero no aparecen en ningún horario 2026.
# Se dejan como están: no hay dato del que sacar sus minutos.
SIN_HORARIO = ["Psicología"]

# Diferencias entre secciones del mismo grado que quedaron sin resolver.
# 5to "A" de secundaria dedica 4 bloques a Física Elemental y 5to "B" solo 2;
# se toma el reparto de 5to "B", que es el que coincide con el resto de grados.
NOTAS = [
    "5to secundaria: la sección A da 4 bloques de Física Elemental y la B da 2. "
    "Se usa 2, como en 1ero a 4to.",
    "4to A y 5to B de secundaria tienen una franja sin materia en el PDF "
    "('ENTRAN 3:30PM' y una celda vacía): esos bloques no se reparten.",
]
