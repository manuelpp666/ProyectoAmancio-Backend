"""
Plana administrativa, docentes y auxiliares extraídos del PDF
"3. Directorio 2026 GENERAL.pdf".

Están transcritos a mano y no leídos del PDF a propósito: el directorio mezcla
el orden de los nombres (unas filas son "Apellidos Nombres" y otras
"Nombres Apellidos"), así que separar apellidos de nombres automáticamente
produciría errores. Con ~45 personas, transcribir es más fiable.

DNI FICTICIOS: tres personas del directorio no traen DNI. Se les asignó uno
que empieza por 999 (99900001, 99900002, 99900003) para que puedan crearse y
sus cursos no queden sin docente. Son fáciles de localizar después con:
    SELECT * FROM docente WHERE dni LIKE '999%';
    SELECT * FROM administrador WHERE dni LIKE '999%';

Cada persona lleva su rol de sistema. Un usuario solo puede tener UN rol
(usuario.rol es un ENUM simple), así que cuando alguien cumple dos funciones
—por ejemplo docente y auxiliar— se elige el rol con el que inicia sesión y se
crea igualmente su ficha en la otra tabla para poder asignarle carga o
secciones. Prioridad: ADMIN > PSICOLOGO > AUXILIAR > DOCENTE.
"""

# --- PLANA ADMINISTRATIVA -------------------------------------------------
# rol_sistema: ADMIN
ADMINISTRATIVOS = [
    # (dni, apellidos, nombres, telefono, cargo)
    ("16793446", "Serquén Montehermozo", "Tomás", "954921386", "DIRECTOR"),
    ("99900001", "Serquén Montehermozo", "Juana", "959888399", "ADMINISTRACIÓN"),
    ("16576103", "Bracamonte Takayama", "Delfín", "962884791", "SUBDIRECTOR ADMINISTRATIVO"),
    ("06042798", "Paredes Guanilo", "Silvia Angelina", "991064175", "SUBDIRECTOR"),
    ("73193257", "Marín Tantalean", "Maricielo", "968662055", "SECRETARIA"),
]

# --- PSICOLOGÍA -----------------------------------------------------------
# En el PDF aparece como "Leiva Castillo Brhygitte Belianka Felicita" en la
# plana administrativa y como "Brhillith Castillo Leyva" entre los docentes de
# primaria, ambas con DNI 74877335: es la misma persona.
PSICOLOGOS = [
    ("74877335", "Leiva Castillo", "Brhygitte Belianka Felicita", "974119226"),
]

# --- AUXILIARES -----------------------------------------------------------
AUXILIARES = [
    # (dni, apellidos, nombres, telefono, ambito, turno)
    ("44436396", "Sánchez De La Cruz", "Daysi Massiel", "918607938", "5to de secundaria", "TARDE"),
    ("74984565", "Aguilar Rubio", "Gianella Briseth", "906794526", "Nivel Primaria", "MAÑANA Y TARDE"),
    ("16714260", "Rocha Briones", "Maritza", "979814283", "Nivel Secundaria", "MAÑANA"),
    ("60903085", "Lima Adanaque", "Marleny Mariloly", "977459727", "Nivel Primaria", "MAÑANA"),
    ("75670912", "Cruz Valladolid", "Luis Alberto", "941431731", "Nivel Primaria", "TARDE"),
]

# --- DOCENTES -------------------------------------------------------------
# Un docente aparece una sola vez aquí aunque enseñe en primaria y secundaria.
DOCENTES = [
    # (dni, apellidos, nombres, telefono)
    ("16774730", "Rodrigo Cieza", "Carmen del Rosario", "964594737"),
    ("75054364", "Pisfil Crisanto", "Mirla Liseth", "979871310"),
    ("06042798", "Paredes Guanilo", "Silvia Angelina", "928999429"),
    ("71980199", "Sánchez Centurión", "Lida", "979871310"),
    ("74239266", "Chacón Cieza", "Juliana", "994541748"),
    ("43647259", "Castillo Purisaca", "Nayeli Castillo", "932741103"),
    ("70777841", "Bonilla Villanueva", "Yasmin", "948244481"),
    ("42710922", "Chambergo Chapilliquén", "Denis", "936050310"),
    ("41598397", "Mera Sánchez", "José", "945941448"),
    ("75620109", "Fernández Rodríguez", "Lesli Liliana", "939978313"),
    ("74634911", "Siancas Ymán", "Jesús David", "987488217"),
    ("43034833", "Vizarreta Pissani", "Carla Irina", "934785415"),
    ("75670912", "Cruz Valladolid", "Luis Alberto", "941431731"),
    ("73187085", "Leyva Vílchez", "Katerine Rosa", "927919627"),
    ("76311450", "Bonilla Benites", "Jesús Alberto", "917898800"),
    ("40938136", "Morante Saavedra", "Saul", "921164430"),
    ("76368371", "Vásquez Gómez", "Alexis", "949482717"),
    ("73694984", "Montero Vélez", "Gianella Lucia", "979237755"),
    ("74820040", "Mego Carrasco", "Lennin", "972287939"),
    ("70814176", "Yamunaque Huamán", "Abraham", "990446185"),
    ("70812370", "Paredes Vilcarromero", "Albert", "938259971"),
    ("74772661", "Calopino Fernández", "Cristian", "940426968"),
    ("99900002", "Herrera", "Edgar", "971023139"),
    ("42607380", "Camacho Cruz", "Elard Darlid", "936208523"),
    ("75531276", "Estrada Zambrano", "Felipe", "925237824"),
    ("17452042", "Chepe Mendoza", "Goblis Jesús", "971023139"),
    ("16674809", "Falla Quintana", "Guillermo Fernando", "979958325"),
    ("44321971", "Vélez Marcos", "Jhon Oswaldo", "948566397"),
    ("42851464", "Gamarra Rondón", "Luis Antonio", "942408398"),
    ("76056082", "Celis Seclén", "Luis Enrique", "951700241"),
    ("16768629", "Ruiz Rojas", "Luis", "902244196"),
    ("16714260", "Rocha Briones", "Maritza", "979814283"),
    ("42643068", "Peralta Agip", "Rafael Bernabé", "954655292"),
    ("71491690", "Cieza Herrera", "Rafael", "924135416"),
    ("99900003", "Castillo", "Royer", "952086260"),
    ("16793446", "Serquén Montehermozo", "Tomás", "954921386"),
    ("74877335", "Leiva Castillo", "Brhygitte Belianka Felicita", "974119226"),
]

# --- TUTORÍAS (MAESTRA DE AULA) ------------------------------------------
# dni del docente -> (nivel, grado, seccion)
TUTORES = [
    ("16774730", "PRIMARIA", "1ero", "Amarillo"),
    ("75054364", "PRIMARIA", "1ero", "Azul"),
    ("06042798", "PRIMARIA", "2do", "Amarillo"),
    ("71980199", "PRIMARIA", "2do", "Azul"),
    ("74239266", "PRIMARIA", "3ero", "Amarillo"),
    ("43647259", "PRIMARIA", "3ero", "Azul"),
]

# --- ASIGNACIONES DOCENTE -> CURSO -> GRADOS -----------------------------
# (dni_docente, nivel, nombre_curso, [grados])
# Los rangos del PDF ("4to y 5to", "1ero-5to") ya vienen expandidos.
ASIGNACIONES = [
    # ---- PRIMARIA ----
    ("70777841", "PRIMARIA", "Razonamiento Matemático", ["4to", "5to"]),
    ("70777841", "PRIMARIA", "Aritmética", ["4to", "5to"]),
    ("70777841", "PRIMARIA", "Geometría", ["4to", "5to"]),
    ("70777841", "PRIMARIA", "Álgebra", ["4to", "5to"]),
    ("74239266", "PRIMARIA", "Aritmética", ["4to"]),
    ("74239266", "PRIMARIA", "Geometría", ["4to"]),
    ("74239266", "PRIMARIA", "Álgebra", ["4to"]),
    ("42710922", "PRIMARIA", "Aritmética", ["5to", "6to"]),
    ("42710922", "PRIMARIA", "Geometría", ["5to", "6to"]),
    ("42710922", "PRIMARIA", "Álgebra", ["5to", "6to"]),
    ("41598397", "PRIMARIA", "Razonamiento Matemático", ["4to", "5to", "6to"]),
    ("75620109", "PRIMARIA", "Comunicación", ["4to", "5to"]),
    ("75620109", "PRIMARIA", "Razonamiento Verbal", ["4to", "5to"]),
    ("75620109", "PRIMARIA", "Plan Lector", ["4to", "5to"]),
    ("74634911", "PRIMARIA", "Comunicación", ["6to"]),
    ("74634911", "PRIMARIA", "Razonamiento Verbal", ["6to"]),
    ("74634911", "PRIMARIA", "Plan Lector", ["6to"]),
    ("43034833", "PRIMARIA", "Ciencia y Tecnología", ["4to", "5to", "6to"]),
    ("43034833", "PRIMARIA", "Personal Social", ["4to", "5to", "6to"]),
    ("75670912", "PRIMARIA", "Religión", ["4to", "5to", "6to"]),
    ("73187085", "PRIMARIA", "Computación", ["1ero", "2do", "3ero", "4to", "5to", "6to"]),
    ("76311450", "PRIMARIA", "Educación Física", ["4to", "5to", "6to"]),
    ("40938136", "PRIMARIA", "Ajedrez", ["1ero", "2do", "3ero", "4to", "5to", "6to"]),
    ("76368371", "PRIMARIA", "Violín", ["1ero", "2do", "3ero", "4to", "5to", "6to"]),
    ("74877335", "PRIMARIA", "Psicología", ["4to", "5to", "6to"]),
    ("73694984", "PRIMARIA", "Inglés", ["1ero", "2do", "3ero"]),
    ("74820040", "PRIMARIA", "Inglés", ["4to", "5to", "6to"]),
    # ---- SECUNDARIA ----
    ("70814176", "SECUNDARIA", "Química", ["3ero", "4to", "5to"]),
    ("70812370", "SECUNDARIA", "Geometría", ["1ero", "2do", "3ero", "4to", "5to"]),
    ("43034833", "SECUNDARIA", "Biología", ["1ero", "2do"]),
    ("74772661", "SECUNDARIA", "Geohistoria", ["1ero", "2do"]),
    ("74772661", "SECUNDARIA", "LOPFIS", ["4to", "5to"]),
    ("42710922", "SECUNDARIA", "Álgebra", ["1ero", "2do", "3ero"]),
    ("99900002", "SECUNDARIA", "Biología", ["3ero", "4to", "5to"]),  # Edgar Herrera
    ("42607380", "SECUNDARIA", "Geohistoria", ["3ero"]),
    ("42607380", "SECUNDARIA", "Economía", ["4to", "5to"]),
    ("75531276", "SECUNDARIA", "Computación", ["1ero"]),
    ("17452042", "SECUNDARIA", "Álgebra", ["4to", "5to"]),
    ("16674809", "SECUNDARIA", "Razonamiento Matemático", ["1ero", "2do", "3ero", "4to", "5to"]),
    ("74634911", "SECUNDARIA", "Razonamiento Verbal", ["1ero", "2do"]),
    ("74634911", "SECUNDARIA", "Gramática", ["1ero", "2do", "3ero", "4to", "5to"]),
    ("44321971", "SECUNDARIA", "Anatomía", ["4to", "5to"]),
    ("74820040", "SECUNDARIA", "Inglés", ["1ero", "2do", "3ero", "4to"]),
    ("75620109", "SECUNDARIA", "Literatura", ["1ero", "2do"]),
    ("42851464", "SECUNDARIA", "Aritmética", ["1ero", "2do", "3ero", "4to", "5to"]),
    ("76056082", "SECUNDARIA", "Historia", ["4to", "5to"]),
    ("16768629", "SECUNDARIA", "Química", ["1ero", "2do"]),
    ("16768629", "SECUNDARIA", "Religión", ["1ero", "2do"]),
    ("16714260", "SECUNDARIA", "Educación Física", ["1ero", "2do", "3ero"]),
    ("40938136", "SECUNDARIA", "Ajedrez", ["1ero", "2do", "3ero"]),
    ("42643068", "SECUNDARIA", "Física Elemental", ["1ero", "2do", "3ero", "4to", "5to"]),
    ("71491690", "SECUNDARIA", "Computación", ["2do", "3ero", "4to", "5to"]),
    ("99900003", "SECUNDARIA", "Literatura", ["3ero", "4to", "5to"]),  # Royer Castillo
    ("16793446", "SECUNDARIA", "Razonamiento Verbal", ["3ero", "4to", "5to"]),
]

# Área a la que pertenece cada curso (para la tabla `area`)
AREAS_CURSO = {
    "Razonamiento Matemático": "Matemática",
    "Aritmética": "Matemática",
    "Geometría": "Matemática",
    "Álgebra": "Matemática",
    "Física Elemental": "Ciencias",
    "Química": "Ciencias",
    "Biología": "Ciencias",
    "Anatomía": "Ciencias",
    "Ciencia y Tecnología": "Ciencias",
    "Comunicación": "Comunicación",
    "Razonamiento Verbal": "Comunicación",
    "Plan Lector": "Comunicación",
    "Gramática": "Comunicación",
    "Literatura": "Comunicación",
    "Inglés": "Comunicación",
    "Personal Social": "Ciencias Sociales",
    "Geohistoria": "Ciencias Sociales",
    "Historia": "Ciencias Sociales",
    "Economía": "Ciencias Sociales",
    "LOPFIS": "Ciencias Sociales",
    "Religión": "Formación Integral",
    "Psicología": "Formación Integral",
    "Educación Física": "Formación Integral",
    "Ajedrez": "Talleres",
    "Violín": "Talleres",
    "Computación": "Talleres",
}
