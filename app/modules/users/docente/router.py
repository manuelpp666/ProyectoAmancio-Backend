from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.database import get_db
from .schemas import DocenteCreate, DocenteResponse
from .models import Docente

# Creamos el router. 'prefix' evita repetir "/docentes" en cada ruta.
router = APIRouter(
    prefix="/docentes",
    tags=["Docentes"] # Esto los agrupa en la documentación /docs
)

@router.post("/", response_model=DocenteResponse, status_code=status.HTTP_201_CREATED)
def crear_docente(docente: DocenteCreate, db: Session = Depends(get_db)):
    docente_existente = db.query(Docente).filter(Docente.dni == docente.dni).first()
    if docente_existente:
        raise HTTPException(status_code=400, detail="El DNI ya existe")
    
    db_docente = Docente(**docente.model_dump())
    db.add(db_docente)
    db.commit()
    db.refresh(db_docente)
    return db_docente

@router.get("/{id}", response_model=DocenteResponse)
def obtener_docente(id: int, db: Session = Depends(get_db)):
    docente = db.query(Docente).filter(Docente.id_docente == id).first()
    if not docente:
        raise HTTPException(status_code=404, detail="Docente no encontrado")
    return docente