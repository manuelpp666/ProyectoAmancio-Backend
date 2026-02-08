from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from app.db.database import get_db
from . import models, schemas
from typing import List, Optional
from datetime import date

from app.modules.management.models import CargaAcademica  # <--- Importar CargaAcademica
from app.modules.users.models import Usuario, RolEnum     # <--- Importar Usuario y RolEnum
from app.modules.users.docente.models import Docente      # <--- Importar Docente

router = APIRouter(prefix="/academic", tags=["Académico"])

# --- AÑO ESCOLAR ---
def actualizar_estado_anios(db: Session):
    """
    Recorre todos los años y actualiza su estado 'activo'
    basándose en la fecha actual.
    """
    hoy = date.today()
    anios = db.query(models.AnioEscolar).all()
    cambios = False

    for anio in anios:
        # Lógica: Está activo SI hoy es >= inicio Y hoy <= fin
        deberia_estar_activo = anio.fecha_inicio <= hoy <= anio.fecha_fin
        
        if anio.activo != deberia_estar_activo:
            anio.activo = deberia_estar_activo
            cambios = True
    
    if cambios:
        db.commit()

@router.post("/anios/", response_model=schemas.AnioEscolarResponse, status_code=status.HTTP_201_CREATED)
def crear_anio(anio: schemas.AnioEscolarCreate, db: Session = Depends(get_db)):
    # 1. Validación de Fechas
    if anio.fecha_fin and anio.fecha_fin <= anio.fecha_inicio:
        raise HTTPException(
            status_code=400, 
            detail="La fecha de fin debe ser posterior a la fecha de inicio."
        )
    
    try:
        # 2. Calcular estado inicial según la fecha de hoy
        hoy = date.today()
        estado_inicial = anio.fecha_inicio <= hoy <= anio.fecha_fin

        # 3. Intentar Crear
        # Ignoramos el campo 'activo' que viene del front, usamos el calculado
        datos_anio = anio.model_dump()
        datos_anio['activo'] = estado_inicial
        
        nuevo = models.AnioEscolar(**datos_anio)
        db.add(nuevo)
        db.commit()
        db.refresh(nuevo)
        
        # Ejecutamos la revisión general por si hay solapamientos (opcional)
        actualizar_estado_anios(db)
        
        return nuevo

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400, 
            detail=f"El ID '{anio.id_anio_escolar}' ya existe. Por favor usa otro."
        )
    except Exception as e:
        db.rollback()
        print(f"Error no controlado: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")

@router.patch("/anios/{anio_id}/cerrar")
def cerrar_anio(anio_id: str, db: Session = Depends(get_db)):
    # Esta función ahora sirve para un cierre MANUAL FORZADO antes de tiempo
    db_anio = db.query(models.AnioEscolar).filter(models.AnioEscolar.id_anio_escolar == anio_id).first()
    if not db_anio:
        raise HTTPException(status_code=404, detail="Año no encontrado")
    
    if not db_anio.activo:
        return {"message": "El año ya estaba cerrado"}

    db_anio.activo = False

    # Lógica de inhabilitar docentes (se mantiene igual)
    docentes_ids = db.query(CargaAcademica.id_docente).filter(
        CargaAcademica.id_anio_escolar == anio_id
    ).distinct().all()
    
    ids = [d[0] for d in docentes_ids]

    if ids:
        subquery_usuarios = db.query(Docente.id_usuario).filter(Docente.id_docente.in_(ids))
        db.query(Usuario).filter(
            Usuario.id_usuario.in_(subquery_usuarios),
            Usuario.rol == RolEnum.DOCENTE 
        ).update({Usuario.activo: False}, synchronize_session=False)

    db.commit()
    return {"message": f"Año {anio_id} cerrado manualmente."}

@router.post("/anios/copiar-estructura")
def copiar_estructura(data: schemas.CopiarEstructuraRequest, db: Session = Depends(get_db)):
    # 1. Validar destino
    anio_dest = db.query(models.AnioEscolar).filter_by(id_anio_escolar=data.anio_destino).first()
    if not anio_dest:
        raise HTTPException(status_code=404, detail="Año destino no existe")

    # 2. Obtener secciones origen
    secciones_origen = db.query(models.Seccion).filter_by(id_anio_escolar=data.anio_origen).all()
    
    if not secciones_origen:
        raise HTTPException(status_code=400, detail="El año origen no tiene secciones")

    count = 0
    for sec in secciones_origen:
        # Verificar si ya existe para no duplicar
        existe = db.query(models.Seccion).filter_by(
            id_anio_escolar=data.anio_destino,
            id_grado=sec.id_grado,
            nombre=sec.nombre
        ).first()

        if not existe:
            nueva = models.Seccion(
                id_grado=sec.id_grado,
                id_anio_escolar=data.anio_destino,
                nombre=sec.nombre,
                vacantes=sec.vacantes
            )
            db.add(nueva)
            count += 1
    
    db.commit()
    return {"message": f"Se copiaron {count} secciones correctamente."}

@router.get("/anios/", response_model=List[schemas.AnioEscolarResponse])
def listar_anios(db: Session = Depends(get_db)):
    # ¡MAGIA AQUÍ! 
    # Antes de devolver la lista, actualizamos los estados automáticamente
    actualizar_estado_anios(db)
    
    return db.query(models.AnioEscolar).all()


# --- NIVELES ---
@router.post("/niveles/", response_model=schemas.NivelResponse)
def crear_nivel(nivel: schemas.NivelCreate, db: Session = Depends(get_db)):
    nuevo = models.Nivel(**nivel.model_dump())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

@router.get("/niveles/", response_model=List[schemas.NivelResponse])
def listar_niveles(db: Session = Depends(get_db)):
    return db.query(models.Nivel).all()

@router.get("/niveles-cursos/", response_model=List[schemas.NivelConCursosResponse])
def listar_niveles_con_cursos(db: Session = Depends(get_db)):
    return db.query(models.Nivel).all()


# --- GRADOS ---
@router.post("/grados/", response_model=schemas.GradoResponse)
def crear_grado(grado: schemas.GradoCreate, db: Session = Depends(get_db)):
    nuevo = models.Grado(**grado.model_dump())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

@router.get("/grados/", response_model=List[schemas.GradoResponse])
def listar_grados(nivel_id: int = None, db: Session = Depends(get_db)):
    # Agregamos filtro por nivel si se necesita
    query = db.query(models.Grado).options(joinedload(models.Grado.nivel))
    if nivel_id:
        query = query.filter(models.Grado.id_nivel == nivel_id)
    return query.all()

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
    
    # Verificar si tiene secciones (relación backref en models)
    # Nota: Asegúrate de que tu modelo Grado tenga la relación 'secciones' o haz query manual
    secciones_count = db.query(models.Seccion).filter(models.Seccion.id_grado == grado_id).count()
    if secciones_count > 0:
         raise HTTPException(
            status_code=400, 
            detail=f"No se puede eliminar: El grado tiene {secciones_count} secciones asignadas."
        )
    
    db.delete(db_grado)
    db.commit()
    return {"message": "Grado eliminado"}


# --- SECCIONES (¡MODIFICADO!) ---
@router.post("/secciones/", response_model=schemas.SeccionResponse)
def crear_seccion(seccion: schemas.SeccionCreate, db: Session = Depends(get_db)):
    # 1. Validar que el año escolar exista (CRÍTICO para tu lógica)
    anio = db.query(models.AnioEscolar).filter(models.AnioEscolar.id_anio_escolar == seccion.id_anio_escolar).first()
    if not anio:
        raise HTTPException(status_code=404, detail="El año escolar indicado no existe")

    nuevo = models.Seccion(**seccion.model_dump())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

@router.get("/secciones/", response_model=List[schemas.SeccionResponse])
def listar_secciones(
    grado_id: int = None, 
    anio_id: str = None, 
    db: Session = Depends(get_db)
):
    """
    Lista secciones con filtros obligatorios para el frontend:
    - grado_id: Para ver secciones de 1er grado.
    - anio_id: Para ver solo las de 2026.
    """
    query = db.query(models.Seccion).options(joinedload(models.Seccion.grado))
    
    if grado_id:
        query = query.filter(models.Seccion.id_grado == grado_id)
    
    if anio_id:
        query = query.filter(models.Seccion.id_anio_escolar == anio_id)
        
    return query.all()

@router.put("/secciones/{seccion_id}", response_model=schemas.SeccionResponse)
def actualizar_seccion(seccion_id: int, seccion: schemas.SeccionCreate, db: Session = Depends(get_db)):
    db_seccion = db.query(models.Seccion).filter(models.Seccion.id_seccion == seccion_id).first()
    if not db_seccion:
        raise HTTPException(status_code=404, detail="Sección no encontrada")
    
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
    
    db.delete(db_seccion)
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

@router.get("/areas/", response_model=List[schemas.AreaResponse])
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

@router.get("/cursos/", response_model=List[schemas.CursoResponse])
def listar_cursos(db: Session = Depends(get_db)):
    # Puedes agregar joinedload(models.Curso.area) si quieres ver el nombre del área
    return db.query(models.Curso).all()

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

@router.delete("/cursos/{curso_id}")
def eliminar_curso(
    curso_id: int, 
    grados_ids: Optional[List[int]] = Query(None), 
    db: Session = Depends(get_db)
):
    db_curso = db.query(models.Curso).filter(models.Curso.id_curso == curso_id).first()
    if not db_curso:
        raise HTTPException(status_code=404, detail="Curso no encontrado")
    
    if grados_ids:
        # Desvincular de grados específicos
        db.query(models.PlanEstudio).filter(
            models.PlanEstudio.id_curso == curso_id,
            models.PlanEstudio.id_grado.in_(grados_ids)
        ).delete(synchronize_session=False)
        mensaje = "Curso desvinculado de los grados seleccionados"
    else:
        # Eliminación total
        db.query(models.PlanEstudio).filter(models.PlanEstudio.id_curso == curso_id).delete(synchronize_session=False)
        db.delete(db_curso)
        mensaje = "Curso eliminado por completo del sistema"
    
    db.commit()
    return {"message": mensaje}


# --- PLAN ESTUDIO (Asignación Masiva) ---
@router.put("/plan-estudio/batch/{curso_id}")
def actualizar_plan_estudio_batch(
    curso_id: int, 
    grados: List[int] = Body(...), # Usamos Body explícito para recibir la lista [1, 2, 3]
    db: Session = Depends(get_db)
):
    # 1. Limpiar asignaciones previas
    db.query(models.PlanEstudio).filter(
        models.PlanEstudio.id_curso == curso_id
    ).delete(synchronize_session=False)
    
    # 2. Insertar nuevas
    for grado_id in grados:
        nuevo = models.PlanEstudio(id_curso=curso_id, id_grado=grado_id)
        db.add(nuevo)
    
    db.commit()
    return {"message": "Plan de estudio actualizado correctamente"}

@router.post("/plan-estudio/", response_model=schemas.PlanEstudioResponse)
def asignar_curso_a_grado(plan: schemas.PlanEstudioCreate, db: Session = Depends(get_db)):
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