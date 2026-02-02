from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text  # Para escribir SQL puro
from app.db.database import get_db # Ajusta la ruta según tu carpeta
from app.modules.users.docente.router import router as docente_router
from app.modules.users.alumno import router as alumno_router
from app.modules.users.docente import router as docente_router
from app.modules.academic import router as academic_router
from app.modules.finance import router as finance_router
from app.modules.web import router as web_router

app = FastAPI()

# Lista de URLs permitidas (Frontend)
origins = [
    "http://localhost:3000",    # Tu Next.js local
    "https://tu-colegio.com",   # Tu dominio final en DirectAdmin
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,            # Permite estas webs
    allow_credentials=True,
    allow_methods=["*"],              # Permite todos los métodos (GET, POST, etc.)
    allow_headers=["*"],              # Permite todos los encabezados
)

app.include_router(alumno_router.router)
app.include_router(docente_router)
app.include_router(academic_router.router)
app.include_router(finance_router.router)
app.include_router(web_router.router)

@app.get("/")
def check_db_connection(db: Session = Depends(get_db)):
    try:
        # Intentamos ejecutar una consulta simple
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "Conectada correctamente"}
    except Exception as e:
        # Si algo falla (user/pass mal, server apagado), lo veremos aquí
        raise HTTPException(
            status_code=500, 
            detail=f"Error conectando a la base de datos: {str(e)}"
        )