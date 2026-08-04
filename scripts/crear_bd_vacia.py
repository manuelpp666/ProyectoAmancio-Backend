"""
Crea una base de datos NUEVA y VACÍA con la misma estructura que la aplicación.

Genera las tablas a partir de los modelos SQLAlchemy, así que la estructura
queda idéntica a la que espera el backend. No toca ninguna base existente:
si el nombre indicado ya existe, se detiene sin hacer nada.

Uso:
    python scripts/crear_bd_vacia.py nombre_de_la_nueva_bd
"""
import os
import sys

import pymysql
from dotenv import load_dotenv
from sqlalchemy import create_engine

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
load_dotenv(os.path.join(RAIZ, ".env"))

from app.db.database import Base  # noqa: E402

# Importar todos los módulos registra sus modelos en Base.metadata
import app.modules.users.models            # noqa: F401,E402
import app.modules.users.alumno.models     # noqa: F401,E402
import app.modules.users.familiar.models   # noqa: F401,E402
import app.modules.users.relacion_familiar.models  # noqa: F401,E402
import app.modules.users.docente.models    # noqa: F401,E402
import app.modules.personal.models         # noqa: F401,E402
import app.modules.academic.models         # noqa: F401,E402
import app.modules.enrollment.models       # noqa: F401,E402
import app.modules.finance.models          # noqa: F401,E402
import app.modules.management.models       # noqa: F401,E402
import app.modules.behavior.models         # noqa: F401,E402
import app.modules.horario.models          # noqa: F401,E402
import app.modules.virtual.models          # noqa: F401,E402
import app.modules.web.models              # noqa: F401,E402
import app.modules.pagina_principal.models  # noqa: F401,E402
import app.modules.chatbot.models          # noqa: F401,E402
import app.modules.verano.models           # noqa: F401,E402


def partir_host(host):
    h, _, p = (host or "127.0.0.1").partition(":")
    return h, int(p or 3306)


def main(nombre):
    usuario = os.getenv("DB_USER")
    clave = os.getenv("DB_PASS") or ""
    host, puerto = partir_host(os.getenv("DB_HOST"))

    con = pymysql.connect(host=host, port=puerto, user=usuario, password=clave)
    cur = con.cursor()
    cur.execute("SHOW DATABASES")
    existentes = {r[0] for r in cur.fetchall()}

    if nombre in existentes:
        print(f"ABORTADO: la base '{nombre}' ya existe. No se toca nada.")
        print("Elige otro nombre para no arriesgar datos.")
        return 1

    cur.execute(
        f"CREATE DATABASE `{nombre}` "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )
    con.commit()
    con.close()
    print(f"Base '{nombre}' creada.")

    url = f"mysql+pymysql://{usuario}:{clave}@{host}:{puerto}/{nombre}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)

    with engine.connect() as c:
        n = len(Base.metadata.tables)
    print(f"Estructura creada: {n} tablas.")
    print(f"\nAhora carga los datos con:")
    print(f"  mysql -u {usuario} -P {puerto} -h {host} {nombre} < scripts/carga_inicial_2026.sql")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    sys.exit(main(sys.argv[1]))
