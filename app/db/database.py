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

# El engine es el puente
engine = create_engine(SQLALCHEMY_DATABASE_URL)

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