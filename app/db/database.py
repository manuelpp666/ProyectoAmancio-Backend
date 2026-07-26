import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

load_dotenv()

# Construimos la URL
USER = os.getenv("DB_USER")
PASS = os.getenv("DB_PASS")
HOST = os.getenv("DB_HOST")
NAME = os.getenv("DB_NAME")

# Agregamos un fallback por si PASS está vacío (como en local)
SQLALCHEMY_DATABASE_URL = f"mysql+pymysql://{USER}:{PASS}@{HOST}/{NAME}"

# El engine es el puente.
# Configuración del pool pensada para carga sostenida:
#  - pool_pre_ping: verifica que la conexión siga viva antes de usarla (evita
#    el clásico "MySQL server has gone away" tras periodos de inactividad).
#  - pool_recycle: recicla conexiones antes de que MySQL las cierre por timeout.
#  - pool_size / max_overflow: capacidad de conexiones concurrentes.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_timeout=30,
)

# La sesión es lo que usaremos para consultas
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# La base para nuestros modelos
Base = declarative_base()

# Esta función es la que "inyectaremos" en FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()