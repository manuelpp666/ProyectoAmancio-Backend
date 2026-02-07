from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.db.database import get_db
from . import models, schemas
from typing import List, Optional



router = APIRouter(prefix="/academic", tags=["Académico"])

# --- AÑO ESCOLAR ---
@router.post("/anios/", response_model=schemas.AnioEscolarResponse, status_code=status.HTTP_201_CREATED)
def crear_anio(anio: schemas.AnioEscolarCreate, db: Session = Depends(get_db)):
    
    # 1. Validación de Fechas
    if anio.fecha_fin and anio.fecha_fin <= anio.fecha_inicio:
        raise HTTPException(
            status_code=400, 
            detail="La fecha de fin debe ser posterior a la fecha de inicio."
        )
    # Opcional: Desactivar cualquier otro año que esté activo antes de crear el nuevo
    db.query(models.AnioEscolar).update({models.AnioEscolar.activo: 0})
    
    db_anio = db.query(models.AnioEscolar).filter(models.AnioEscolar.id_anio_escolar == anio.id_anio_escolar).first()
    if db_anio:
        raise HTTPException(status_code=400, detail="El ID del año escolar ya existe")
    
    nuevo = models.AnioEscolar(**anio.model_dump())
    nuevo.activo = 1 # Por defecto al abrirlo debe estar activo
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

# Cierre de año (Cambio de estado)
@router.patch("/anios/{anio_id}/cerrar")
def cerrar_anio(anio_id: str, db: Session = Depends(get_db)):
    db_anio = db.query(models.AnioEscolar).filter(models.AnioEscolar.id_anio_escolar == anio_id).first()
    if not db_anio:
        raise HTTPException(status_code=404, detail="Año no encontrado")
    
    db_anio.activo = 0 # Cambiamos a inactivo
    db.commit()
    return {"message": f"Año {anio_id} cerrado correctamente"}

@router.get("/anios/", response_model=list[schemas.AnioEscolarResponse])
def listar_anios(db: Session = Depends(get_db)):
    return db.query(models.AnioEscolar).all()


# --- NIVELES ---
@router.post("/niveles/", response_model=schemas.NivelResponse)
def crear_nivel(nivel: schemas.NivelCreate, db: Session = Depends(get_db)):
    nuevo = models.Nivel(**nivel.model_dump())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

@router.get("/niveles/", response_model=list[schemas.NivelResponse])
def listar_niveles(db: Session = Depends(get_db)):
    return db.query(models.Nivel).all()

# --- NIVELES ESPECIALIZADOS ---

# Este es para la página de Cursos y Carga Horaria
@router.get("/niveles-cursos/", response_model=list[schemas.NivelConCursosResponse])
def listar_niveles_con_cursos(db: Session = Depends(get_db)):
    # Usamos all() porque SQLAlchemy cargará las relaciones según tus modelos
    return db.query(models.Nivel).all()


# --- GRADOS ---
@router.post("/grados/", response_model=schemas.GradoResponse)
def crear_grado(grado: schemas.GradoCreate, db: Session = Depends(get_db)):
    nuevo = models.Grado(**grado.model_dump())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

@router.get("/grados/", response_model=list[schemas.GradoResponse])
def listar_grados(db: Session = Depends(get_db)):
    return db.query(models.Grado).all()



@router.put("/grados/{grado_id}", response_model=schemas.GradoResponse)
def actualizar_grado(grado_id: int, grado: schemas.GradoCreate, db: Session = Depends(get_db)):
    db_grado = db.query(models.Grado).filter(models.Grado.id_grado == grado_id).first()
    if not db_grado:
        raise HTTPException(status_code=404, detail="Grado no encontrado")
    
    for key, value in grado.model_dump().items():
        setattr(db_grado, key, value)
    
    db.commit()
    db.refresh(db_grado)
    return db_grado

@router.delete("/grados/{grado_id}")
def eliminar_grado(grado_id: int, db: Session = Depends(get_db)):
    db_grado = db.query(models.Grado).filter(models.Grado.id_grado == grado_id).first()
    if not db_grado:
        raise HTTPException(status_code=404, detail="Grado no encontrado")
    
    # VALIDACIÓN: Verificar si tiene secciones
    if len(db_grado.secciones) > 0:
        raise HTTPException(
            status_code=400, 
            detail=f"No se puede eliminar: El grado tiene {len(db_grado.secciones)} secciones asignadas."
        )
    
    db.delete(db_grado)
    db.commit()
    return {"message": "Grado eliminado"}


# --- SECCIONES ---
@router.post("/secciones/", response_model=schemas.SeccionResponse)
def crear_seccion(seccion: schemas.SeccionCreate, db: Session = Depends(get_db)):
    nuevo = models.Seccion(**seccion.model_dump())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

@router.get("/secciones/", response_model=list[schemas.SeccionResponse])
def listar_secciones(db: Session = Depends(get_db)):
    return db.query(models.Seccion).all()


@router.put("/secciones/{seccion_id}", response_model=schemas.SeccionResponse)
def actualizar_seccion(seccion_id: int, seccion: schemas.SeccionCreate, db: Session = Depends(get_db)):
    db_seccion = db.query(models.Seccion).filter(models.Seccion.id_seccion == seccion_id).first()
    if not db_seccion:
        raise HTTPException(status_code=404, detail="Sección no encontrada")
    
    # Actualizamos los campos
    for key, value in seccion.model_dump().items():
        setattr(db_seccion, key, value)
    
    db.commit()
    db.refresh(db_seccion)
    return db_seccion

@router.delete("/secciones/{seccion_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_seccion(seccion_id: int, db: Session = Depends(get_db)):
    db_seccion = db.query(models.Seccion).filter(models.Seccion.id_seccion == seccion_id).first()
    if not db_seccion:
        raise HTTPException(status_code=404, detail="Sección no encontrada")
    
    db.delete(db_seccion) # Eliminación física
    db.commit()
    return None
# --- ÁREAS ---
@router.post("/areas/", response_model=schemas.AreaResponse)
def crear_area(area: schemas.AreaCreate, db: Session = Depends(get_db)):
    nuevo = models.Area(**area.model_dump())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

@router.get("/areas/", response_model=list[schemas.AreaResponse])
def listar_areas(db: Session = Depends(get_db)):
    return db.query(models.Area).all()

# --- CURSOS ---
@router.post("/cursos/", response_model=schemas.CursoResponse)
def crear_curso(curso: schemas.CursoCreate, db: Session = Depends(get_db)):
    nuevo = models.Curso(**curso.model_dump())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

@router.get("/cursos/", response_model=list[schemas.CursoResponse])
def listar_cursos(db: Session = Depends(get_db)):
    return db.query(models.Curso).all()

# --- ACTUALIZAR CURSO ---
@router.put("/cursos/{curso_id}", response_model=schemas.CursoResponse)
def actualizar_curso(curso_id: int, curso_data: schemas.CursoCreate, db: Session = Depends(get_db)):
    db_curso = db.query(models.Curso).filter(models.Curso.id_curso == curso_id).first()
    if not db_curso:
        raise HTTPException(status_code=404, detail="Curso no encontrado")
    
    for key, value in curso_data.model_dump().items():
        setattr(db_curso, key, value)
    
    db.commit()
    db.refresh(db_curso)
    return db_curso

# --- ELIMINAR CURSO (Físico) ---
@router.delete("/cursos/{curso_id}")
def eliminar_curso(
    curso_id: int, 
    grados_ids: Optional[List[int]] = Query(None), # Recibimos los grados a desvincular
    db: Session = Depends(get_db)
):
    # 1. Verificar si el curso existe
    db_curso = db.query(models.Curso).filter(models.Curso.id_curso == curso_id).first()
    if not db_curso:
        raise HTTPException(status_code=404, detail="Curso no encontrado")
    
    if grados_ids:
        # --- CASO A: DESVINCULAR DE GRADOS ESPECÍFICOS ---
        # Borramos solo las filas en PlanEstudio que coincidan con el curso y los grados enviados
        db.query(models.PlanEstudio).filter(
            models.PlanEstudio.id_curso == curso_id,
            models.PlanEstudio.id_grado.in_(grados_ids)
        ).delete(synchronize_session=False)
        
        mensaje = "Curso desvinculado de los grados seleccionados"
    else:
        # --- CASO B: ELIMINACIÓN TOTAL (Física) ---
        # Si no se mandan grados, se asume que se quiere borrar el curso de todo el sistema
        db.query(models.PlanEstudio).filter(models.PlanEstudio.id_curso == curso_id).delete()
        db.delete(db_curso)
        mensaje = "Curso eliminado por completo del sistema"
    
    db.commit()
    return {"message": mensaje}

# --- RE-ASIGNAR PLAN DE ESTUDIO (Limpiar y Crear) ---
@router.put("/plan-estudio/batch/{curso_id}")
def actualizar_plan_estudio_batch(curso_id: int, grados: list[int], db: Session = Depends(get_db)):
    # 1. Borramos asignaciones actuales de ese curso
    db.query(models.PlanEstudio).filter(models.PlanEstudio.id_curso == curso_id).delete()
    
    # 2. Creamos las nuevas
    for grado_id in grados:
        nuevo = models.PlanEstudio(id_curso=curso_id, id_grado=grado_id)
        db.add(nuevo)
    
    db.commit()
    return {"message": "Plan de estudio actualizado"}

# --- PLAN ESTUDIO (Asignar cursos a grados) ---
@router.post("/plan-estudio/", response_model=schemas.PlanEstudioResponse)
def asignar_curso_a_grado(plan: schemas.PlanEstudioCreate, db: Session = Depends(get_db)):
    # Verificamos si ya existe esa asignación para evitar duplicados
    existe = db.query(models.PlanEstudio).filter(
        models.PlanEstudio.id_curso == plan.id_curso,
        models.PlanEstudio.id_grado == plan.id_grado
    ).first()
    
    if existe:
        raise HTTPException(status_code=400, detail="Este curso ya está asignado a este grado")

    nuevo = models.PlanEstudio(**plan.model_dump())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo