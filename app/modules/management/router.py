from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from typing import List
from app.db.database import get_db
from app.modules.academic import models as models_ac
from app.modules.users.alumno import models as models_al
from app.modules.users.docente import models as models_doc
from app.modules.enrollment import models as models_en
from app.modules.virtual import models as models_vr
from app.modules.management import models as models_mn
from . import models, schemas


router = APIRouter(prefix="/gestion", tags=["Gestión Académica"])

# --- Carga Académica ---
@router.post("/carga/", response_model=schemas.CargaResponse)
def asignar_carga(carga: schemas.CargaCreate, db: Session = Depends(get_db)):
    nueva = models.CargaAcademica(**carga.model_dump())
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva

@router.get("/carga/", response_model=List[schemas.CargaResponse])
def listar_cargas(db: Session = Depends(get_db)):
    return db.query(models.CargaAcademica).all()

# --- Notas ---
@router.post("/notas/", response_model=schemas.NotaResponse)
def registrar_nota(nota: schemas.NotaCreate, db: Session = Depends(get_db)):
    nueva = models.Nota(**nota.dict())
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva

# --- Asistencia ---
@router.post("/asistencia/", response_model=schemas.AsistenciaResponse)
def registrar_asistencia(asistencia: schemas.AsistenciaCreate, db: Session = Depends(get_db)):
    nueva = models.Asistencia(**asistencia.model_dump())
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva



@router.get("/mis-cursos/{id_usuario}", response_model=List[schemas.CursoEstudianteResponse])
def obtener_cursos_estudiante(
    id_usuario: int, 
    anio: str, 
    db: Session = Depends(get_db)
):
    # 1. Buscar al alumno
    alumno = db.query(models_al.Alumno).filter(models_al.Alumno.id_usuario == id_usuario).first()
    
    if not alumno:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    # 2. Query siguiendo el camino real de tus tablas
    cursos_query = (
        db.query(
            models_ac.Curso.id_curso,
            models_ac.Curso.nombre.label("curso_nombre"),
            models_doc.Docente.nombres.label("docente_nombres"),
            models_doc.Docente.apellidos.label("docente_apellidos"),
            models_doc.Docente.url_perfil.label("url_perfil")
        )
        .select_from(models_en.Matricula)
        # Unimos Matricula con Seccion
        .join(models_ac.Seccion, models_ac.Seccion.id_seccion == models_en.Matricula.id_seccion)
        # Unimos Seccion con Grado (porque Plan de Estudio usa id_grado)
        .join(models_ac.Grado, models_ac.Grado.id_grado == models_ac.Seccion.id_grado)
        # Unimos Grado con Plan de Estudio para saber qué cursos le tocan
        .join(models_ac.PlanEstudio, models_ac.PlanEstudio.id_grado == models_ac.Grado.id_grado)
        # Unimos Plan de Estudio con Curso
        .join(models_ac.Curso, models_ac.Curso.id_curso == models_ac.PlanEstudio.id_curso)
        
        # OUTER JOIN con Carga Académica para el profesor (esto es lo que puede no existir)
        .outerjoin(models.CargaAcademica, 
            (models.CargaAcademica.id_curso == models_ac.Curso.id_curso) & 
            (models.CargaAcademica.id_seccion == models_ac.Seccion.id_seccion) &
            (models.CargaAcademica.id_anio_escolar == anio)
        )
        # OUTER JOIN con Docente
        .outerjoin(models_doc.Docente, models.CargaAcademica.id_docente == models_doc.Docente.id_docente)
        
        .filter(
            models_en.Matricula.id_alumno == alumno.id_alumno,
            models_en.Matricula.id_anio_escolar == anio
        )
        .all()
    )

    return [
        {
            "id_curso": c.id_curso,
            "curso_nombre": c.curso_nombre,
            "docente_nombres": c.docente_nombres if c.docente_nombres else "Sin asignar",
            "docente_apellidos": c.docente_apellidos if c.docente_apellidos else "",
            "url_perfil_docente": c.url_perfil
        }
        for c in cursos_query
    ]


@router.get("/curso-detalle/{id_curso}/{id_usuario}")
def obtener_detalle_curso_estudiante(
    id_curso: int, 
    id_usuario: int, 
    anio: str, 
    db: Session = Depends(get_db)
):
    # 1. Identificar al alumno y su matrícula para ese año
    alumno = db.query(models_al.Alumno).filter(models_al.Alumno.id_usuario == id_usuario).first()
    matricula = db.query(models_en.Matricula).filter(
        models_en.Matricula.id_alumno == alumno.id_alumno,
        models_en.Matricula.id_anio_escolar == anio
    ).first()

    # 2. Obtener Carga Académica (para las tareas)
    carga = db.query(models.CargaAcademica).filter(
        models.CargaAcademica.id_curso == id_curso,
        models.CargaAcademica.id_seccion == matricula.id_seccion,
        models.CargaAcademica.id_anio_escolar == anio
    ).first()

    # 3. Obtener Notas (Resumen)
    notas = db.query(models_mn.ResumenNota).filter(
        models_mn.ResumenNota.id_matricula == matricula.id_matricula,
        models_mn.ResumenNota.id_curso == id_curso
    ).first()

    # 4. Obtener Tareas y si el alumno ya entregó
    # Aquí unimos Tarea con EntregaTarea (Left Join)
    tareas_query = db.query(
        models_vr.Tarea,
        models_vr.EntregaTarea.calificacion,
        models_vr.EntregaTarea.fecha_envio
    ).outerjoin(
        models_vr.EntregaTarea, 
        (models_vr.EntregaTarea.id_tarea == models_vr.Tarea.id_tarea) & 
        (models_vr.EntregaTarea.id_alumno == alumno.id_alumno)
    ).filter(models_vr.Tarea.id_carga_academica == carga.id_carga_academica).all()

    return {
        "curso_info": {"id": id_curso, "anio": anio},
        "notas": notas,
        "tareas": [
            {
                "id_tarea": t.Tarea.id_tarea,
                "titulo": t.Tarea.titulo,
                "fecha_entrega": t.Tarea.fecha_entrega,
                "entregado": t.fecha_envio is not None,
                "nota": t.calificacion,
                "peso": t.Tarea.peso,
                "bimestre": t.Tarea.bimestre
            } for t in tareas_query
        ]
    }


# --- Asignación de Docentes ---

@router.get("/vínculos-academicos/{anio_id}", response_model=List[schemas.VinculoAcademicoResponse])
def listar_vinculos_para_asignacion(anio_id: str, db: Session = Depends(get_db)):
    """
    Obtiene todos los cursos por sección de un año escolar 
    y muestra qué docente tienen asignado (si lo hay).
    """
    # 1. Buscamos todas las secciones del año escolar
    secciones = db.query(models_ac.Seccion).filter(models_ac.Seccion.id_anio_escolar == anio_id).all()
    
    resultado = []
    for seccion in secciones:
        # 2. Por cada sección, vemos qué cursos le corresponden según su grado (Plan de Estudio)
        cursos_plan = db.query(models_ac.Curso).join(
            models_ac.PlanEstudio, models_ac.PlanEstudio.id_curso == models_ac.Curso.id_curso
        ).filter(models_ac.PlanEstudio.id_grado == seccion.id_grado).all()

        for curso in cursos_plan:
            # 3. Buscamos si ya existe una carga académica (docente asignado)
            carga = db.query(models.CargaAcademica).filter(
                models.CargaAcademica.id_seccion == seccion.id_seccion,
                models.CargaAcademica.id_curso == curso.id_curso,
                models.CargaAcademica.id_anio_escolar == anio_id
            ).first()

            docente = None
            if carga and carga.id_docente:
                docente = db.query(models_doc.Docente).filter(models_doc.Docente.id_docente == carga.id_docente).first()

            resultado.append({
                "id_seccion": seccion.id_seccion,
                "seccion_nombre": seccion.nombre,
                "grado_nombre": seccion.grado.nombre, # Asumiendo relación en el modelo
                "id_curso": curso.id_curso,
                "curso_nombre": curso.nombre,
                "id_carga_academica": carga.id_carga_academica if carga else None,
                "docente": docente # Puede ser None
            })
    
    return resultado

@router.get("/docentes-disponibles/", response_model=List[schemas.DocenteBasicoResponse])
def listar_docentes_busqueda(db: Session = Depends(get_db)):
    """Lista simple de docentes para el selector de la interfaz"""
    return db.query(models_doc.Docente).all()


#--- Delete y update de la carga academica
@router.delete("/carga/{carga_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_carga(carga_id: int, db: Session = Depends(get_db)):
    db_carga = db.query(models.CargaAcademica).filter(models.CargaAcademica.id_carga_academica == carga_id).first()
    if not db_carga:
        raise HTTPException(status_code=404, detail="Asignación no encontrada")
    
    db.delete(db_carga)
    db.commit()
    return None

@router.patch("/carga/{carga_id}", response_model=schemas.CargaResponse)
def actualizar_carga(carga_id: int, data: schemas.CargaUpdate, db: Session = Depends(get_db)):
    db_carga = db.query(models.CargaAcademica).filter(models.CargaAcademica.id_carga_academica == carga_id).first()
    
    if not db_carga:
        raise HTTPException(status_code=404, detail="Asignación no encontrada")
    
    # Actualización dinámica
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_carga, key, value)
    
    db.commit()
    db.refresh(db_carga)
    return db_carga

@router.get("/mis-cursos-docente/{id_usuario}", response_model=List[schemas.CursoDocenteResponse])
def obtener_cursos_docente(
    id_usuario: int, 
    anio: str, 
    db: Session = Depends(get_db)
):
    # 1. Buscar al docente asociado al usuario
    docente = db.query(models_doc.Docente).filter(models_doc.Docente.id_usuario == id_usuario).first()
    
    if not docente:
        raise HTTPException(status_code=404, detail="Docente no encontrado")

    # 2. Query para obtener los cursos asignados y contar alumnos
    # Subquery para contar alumnos por sección
    subquery_alumnos = (
        db.query(
            models_en.Matricula.id_seccion, 
            func.count(models_en.Matricula.id_alumno).label("total_alumnos")
        )
        .filter(models_en.Matricula.id_anio_escolar == anio)
        .group_by(models_en.Matricula.id_seccion)
        .subquery()
    )

    cursos_query = (
        db.query(
            models.CargaAcademica.id_carga_academica,
            models_ac.Curso.nombre.label("curso_nombre"),
            models_ac.Grado.nombre.label("grado_nombre"),
            models_ac.Seccion.nombre.label("seccion_nombre"),
            func.coalesce(subquery_alumnos.c.total_alumnos, 0).label("num_alumnos")
        )
        .join(models_ac.Curso, models.CargaAcademica.id_curso == models_ac.Curso.id_curso)
        .join(models_ac.Seccion, models.CargaAcademica.id_seccion == models_ac.Seccion.id_seccion)
        .join(models_ac.Grado, models_ac.Seccion.id_grado == models_ac.Grado.id_grado)
        .outerjoin(subquery_alumnos, models_ac.Seccion.id_seccion == subquery_alumnos.c.id_seccion)
        .filter(
            models.CargaAcademica.id_docente == docente.id_docente,
            models.CargaAcademica.id_anio_escolar == anio
        )
        .all()
    )

    return [
        {
            "id_carga": c.id_carga_academica,
            "curso_nombre": c.curso_nombre,
            "grado_nombre": c.grado_nombre,
            "seccion_nombre": c.seccion_nombre,
            "alumnos": c.num_alumnos,
            # Puedes asignar una imagen por defecto o lógica según el nombre
            "img": "/matematicas.png" if "Matem" in c.curso_nombre else "/cienciasS.png"
        }
        for c in cursos_query
    ]


@router.get("/mis-cursos-docente-dashboard/{id_usuario}")
def obtener_cursos_docente_dashboard(id_usuario: int, db: Session = Depends(get_db)):
    # 1. Buscar año activo automáticamente
    anio_activo = db.query(models_ac.AnioEscolar).filter(models_ac.AnioEscolar.activo == True).first()
    if not anio_activo:
        raise HTTPException(status_code=404, detail="No hay año escolar activo")
    
    # 2. Buscar docente
    docente = db.query(models_doc.Docente).filter(models_doc.Docente.id_usuario == id_usuario).first()
    if not docente:
        raise HTTPException(status_code=404, detail="Docente no encontrado")

    # 3. Query de cursos
    cursos_query = (
        db.query(
            models_mn.CargaAcademica.id_carga_academica,
            models_ac.Curso.nombre.label("curso_nombre"),
            models_ac.Grado.nombre.label("grado_nombre"),
            models_ac.Seccion.nombre.label("seccion_nombre"),
        )
        .join(models_ac.Curso, models_mn.CargaAcademica.id_curso == models_ac.Curso.id_curso)
        .join(models_ac.Seccion, models_mn.CargaAcademica.id_seccion == models_ac.Seccion.id_seccion)
        .join(models_ac.Grado, models_ac.Seccion.id_grado == models_ac.Grado.id_grado)
        .filter(
            models_mn.CargaAcademica.id_docente == docente.id_docente,
            models_mn.CargaAcademica.id_anio_escolar == anio_activo.id_anio_escolar
        )
        .all()
    )

    return [
        {
            "id_carga": c.id_carga_academica,
            "nombre": c.curso_nombre,
            "grado_seccion": f"{c.grado_nombre} {c.seccion_nombre}",
        }
        for c in cursos_query
    ]

@router.get("/resumen-docente/{id_usuario}")
def obtener_resumen_docente(id_usuario: int, db: Session = Depends(get_db)):
    # 1. Obtener ID del docente
    docente = db.query(models_doc.Docente).filter(models_doc.Docente.id_usuario == id_usuario).first()
    if not docente:
        raise HTTPException(status_code=404, detail="Docente no encontrado")
        
    # 2. Obtener las cargas académicas del docente (que tienen id_seccion)
    cargas = db.query(models_mn.CargaAcademica).filter(models_mn.CargaAcademica.id_docente == docente.id_docente).all()
    
    # Extraer los IDs de las secciones que el docente tiene a su cargo
    ids_secciones = [c.id_seccion for c in cargas]
    ids_cargas = [c.id_carga_academica for c in cargas] # Los guardamos para la consulta de tareas

    # 3. Cursos asignados (es la cantidad de cargas)
    num_cursos = len(cargas)

    # 4. Alumnos totales: Matrículas en esas secciones
    # Filtramos por las secciones que el docente tiene asignadas
    num_alumnos = db.query(models_en.Matricula).filter(models_en.Matricula.id_seccion.in_(ids_secciones)).count()

    # 5. Pendientes de calificar
    # Usamos las IDs de carga académica para buscar las tareas de esas secciones
    num_pendientes = db.query(models_vr.EntregaTarea).join(
        models_vr.Tarea, models_vr.EntregaTarea.id_tarea == models_vr.Tarea.id_tarea
    ).filter(
        models_vr.Tarea.id_carga_academica.in_(ids_cargas),
        models_vr.EntregaTarea.calificacion == None
    ).count()

    return {
        "cursos": num_cursos,
        "alumnos": num_alumnos,
        "pendientes": num_pendientes
    }