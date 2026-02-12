from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from app.db.database import get_db
from . import models, schemas

# Importamos modelos de alumno para asegurar relaciones si es necesario
from app.modules.users.alumno import models as alumno_models

# CAMBIO CLAVE: Prefijo "/enrollment" para coincidir con el frontend
router = APIRouter(prefix="/enrollment", tags=["Matrícula"])

# --- CREAR MATRÍCULA ---
@router.post("/matriculas/", response_model=schemas.MatriculaResponse, status_code=status.HTTP_201_CREATED)
def crear_matricula(matricula: schemas.MatriculaCreate, db: Session = Depends(get_db)):
    # 1. Verificar si ya existe matrícula para ese alumno en ese año
    existe = db.query(models.Matricula).filter(
        models.Matricula.id_alumno == matricula.id_alumno,
        models.Matricula.id_anio_escolar == matricula.id_anio_escolar
    ).first()

    if existe:
        raise HTTPException(status_code=400, detail="El alumno ya está matriculado en este año escolar.")

    # 2. Crear
    nueva = models.Matricula(**matricula.model_dump())
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva

# --- LISTAR MATRÍCULAS (ESTE ES EL QUE FALTABA PARA EL ERROR 404) ---
@router.get("/matriculas/", response_model=List[schemas.MatriculaResponse])
def listar_matriculas(
    anio_id: str = None, 
    grado_id: int = None, 
    seccion_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Lista las matrículas filtrando por Año y Grado.
    Esencial para la pantalla de 'Asignación de Estudiantes'.
    """
    query = db.query(models.Matricula).options(
        joinedload(models.Matricula.alumno), # Cargar datos del alumno
        joinedload(models.Matricula.grado),
        joinedload(models.Matricula.seccion)
    )

    if anio_id:
        query = query.filter(models.Matricula.id_anio_escolar == anio_id)
    
    if grado_id:
        query = query.filter(models.Matricula.id_grado == grado_id)
        
    if seccion_id:
        query = query.filter(models.Matricula.id_seccion == seccion_id)

    return query.all()

# --- ACTUALIZAR MATRÍCULA (Para asignar sección) ---
@router.put("/matriculas/{matricula_id}", response_model=schemas.MatriculaResponse)
def actualizar_matricula(
    matricula_id: int, 
    datos: schemas.MatriculaCreate, 
    db: Session = Depends(get_db)
):
    matricula = db.query(models.Matricula).filter(models.Matricula.id_matricula == matricula_id).first()
    if not matricula:
        raise HTTPException(status_code=404, detail="Matrícula no encontrada")
    
    # Actualizamos campos
    matricula.id_seccion = datos.id_seccion
    # Mantenemos otros datos para evitar inconsistencias
    if datos.id_grado: matricula.id_grado = datos.id_grado
    
    db.commit()
    db.refresh(matricula)
    return matricula

# --- EXONERACIONES ---
@router.post("/exoneracion/", response_model=schemas.ExoneracionResponse)
def crear_exoneracion(exoneracion: schemas.ExoneracionCreate, db: Session = Depends(get_db)):
    nueva = models.Exoneracion(**exoneracion.model_dump())
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva