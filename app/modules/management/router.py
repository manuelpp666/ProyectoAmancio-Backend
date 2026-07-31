from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from typing import List
from datetime import datetime, date
from app.db.database import get_db
from app.modules.academic import models as models_ac
from app.modules.users.alumno import models as models_al
from app.modules.users.docente import models as models_doc
from app.modules.enrollment import models as models_en
from app.modules.virtual import models as models_vr
from app.modules.management import models as models_mn
from app.modules.finance import models as models_fi
from app.modules.web import models as models_web
from app.modules.behavior import models as models_psi
from app.modules.users.relacion_familiar import models as models_rel
from app.core.util.security import get_current_user, ensure_owner_or_roles
from .service import enviar_notificaciones_asistencia
from . import models, schemas


router = APIRouter(prefix="/gestion", tags=["Gestión Académica"])

# --- Carga Académica ---
@router.post("/carga/", response_model=schemas.CargaResponse)
def asignar_carga(carga: schemas.CargaCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    
    # VALIDACIÓN DE ROL
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="No tienes permisos para ejecutar esto"
        )
    nueva = models.CargaAcademica(**carga.model_dump())
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva

@router.get("/carga/", response_model=List[schemas.CargaResponse])
def listar_cargas(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    
    # VALIDACIÓN DE ROL
    if current_user.get("rol") not in ["ADMIN", "DOCENTE"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para ver esta sección"
        )
    return db.query(models.CargaAcademica).all()

# --- Notas ---
@router.post("/notas/", response_model=schemas.NotaResponse)
def registrar_nota(nota: schemas.NotaCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    
    if current_user.get("rol") != "DOCENTE":
        raise HTTPException(status_code=403, detail="No puedes acceder a esta información.")
    
    nueva = models.Nota(**nota.model_dump())
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva

# --- Asistencia ---
@router.post("/asistencia/", response_model=schemas.AsistenciaResponse)
def registrar_asistencia(asistencia: schemas.AsistenciaCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") not in ("AUXILIAR", "DOCENTE", "ADMIN"):
        raise HTTPException(status_code=403, detail="No tienes permisos para registrar asistencia")
    nueva = models.Asistencia(**asistencia.model_dump())
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva


@router.post("/asistencia/lote", response_model=schemas.AsistenciaLoteResponse)
def registrar_asistencia_lote(
    payload: schemas.AsistenciaLoteCreate,
    background_tasks: BackgroundTasks,
    notificar: bool = True,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Registra la asistencia de toda una sección en una sola operación y, de forma
    opcional (notificar=True), envía en segundo plano un correo de confirmación
    a cada apoderado de cada alumno.
    """
    if current_user.get("rol") not in ("AUXILIAR", "DOCENTE", "ADMIN"):
        raise HTTPException(status_code=403, detail="No tienes permisos para registrar asistencia")

    if not payload.registros:
        return schemas.AsistenciaLoteResponse(guardados=0, correos_encolados=0, notificar=notificar)

    ids = [r.id_matricula for r in payload.registros]

    # UPSERT: si ya existe un registro para esa matrícula+fecha, se actualiza;
    # así reguardar la asistencia del día no genera duplicados.
    existentes = (
        db.query(models.Asistencia)
        .filter(models.Asistencia.id_matricula.in_(ids), models.Asistencia.fecha == payload.fecha)
        .all()
    )
    mapa_existentes = {a.id_matricula: a for a in existentes}

    for r in payload.registros:
        actual = mapa_existentes.get(r.id_matricula)
        if actual:
            actual.estado = r.estado
            actual.observacion = r.observacion or ""
        else:
            db.add(models.Asistencia(
                id_matricula=r.id_matricula,
                fecha=payload.fecha,
                estado=r.estado,
                observacion=r.observacion or "",
            ))
    db.commit()

    # --- Preparar notificaciones a los apoderados ---
    notificaciones: list[dict] = []
    if notificar:
        matriculas = (
            db.query(models_en.Matricula)
            .options(joinedload(models_en.Matricula.alumno))
            .filter(models_en.Matricula.id_matricula.in_(ids))
            .all()
        )
        mapa_matriculas = {m.id_matricula: m for m in matriculas}
        alumno_ids = [m.alumno.id_alumno for m in matriculas if m.alumno]

        # Correos de los apoderados agrupados por alumno
        emails_por_alumno: dict[int, list[str]] = {}
        if alumno_ids:
            relaciones = (
                db.query(models_rel.RelacionFamiliar)
                .options(joinedload(models_rel.RelacionFamiliar.familiar))
                .filter(models_rel.RelacionFamiliar.id_alumno.in_(alumno_ids))
                .all()
            )
            for rel in relaciones:
                email = rel.familiar.email if rel.familiar else None
                if email:
                    emails_por_alumno.setdefault(rel.id_alumno, []).append(email)

        for r in payload.registros:
            m = mapa_matriculas.get(r.id_matricula)
            if not m or not m.alumno:
                continue
            nombre = f"{m.alumno.nombres} {m.alumno.apellidos}"
            for email in emails_por_alumno.get(m.alumno.id_alumno, []):
                notificaciones.append({
                    "email": email,
                    "alumno_nombre": nombre,
                    "estado": r.estado,
                    "fecha": payload.fecha,
                })

        if notificaciones:
            background_tasks.add_task(enviar_notificaciones_asistencia, notificaciones)

    return schemas.AsistenciaLoteResponse(
        guardados=len(payload.registros),
        correos_encolados=len(notificaciones),
        notificar=notificar,
    )


@router.get("/mis-cursos/{id_usuario}", response_model=List[schemas.CursoEstudianteResponse])
def obtener_cursos_estudiante(
    id_usuario: int, 
    anio: str, 
    db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    
    ensure_owner_or_roles(current_user, id_usuario, "ADMIN")
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
    db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    
    if current_user.get("id") != id_usuario:
        raise HTTPException(status_code=403, detail="No puedes acceder a esta información.")
    
    # 1. Identificar al alumno y su matrícula para ese año
    alumno = db.query(models_al.Alumno).filter(models_al.Alumno.id_usuario == id_usuario).first()
    if not alumno:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    matricula = db.query(models_en.Matricula).filter(
        models_en.Matricula.id_alumno == alumno.id_alumno,
        models_en.Matricula.id_anio_escolar == anio
    ).first()
    if not matricula:
        raise HTTPException(status_code=404, detail="No tienes matrícula registrada en este año escolar")

    # 2. Obtener el curso y la Carga Académica (para las tareas y el docente)
    curso = db.query(models_ac.Curso).filter(models_ac.Curso.id_curso == id_curso).first()
    if not curso:
        raise HTTPException(status_code=404, detail="Curso no encontrado")

    carga = db.query(models.CargaAcademica).filter(
        models.CargaAcademica.id_curso == id_curso,
        models.CargaAcademica.id_seccion == matricula.id_seccion,
        models.CargaAcademica.id_anio_escolar == anio
    ).first()

    docente_nombre = "Docente por asignar"
    if carga and carga.id_docente:
        docente = db.query(models_doc.Docente).filter(models_doc.Docente.id_docente == carga.id_docente).first()
        if docente:
            docente_nombre = f"{docente.nombres} {docente.apellidos}"

    # 3. Obtener Notas (Resumen)
    notas = db.query(models_mn.ResumenNota).filter(
        models_mn.ResumenNota.id_matricula == matricula.id_matricula,
        models_mn.ResumenNota.id_curso == id_curso
    ).first()

    # 4. Obtener Tareas y si el alumno ya entregó
    # Aquí unimos Tarea con EntregaTarea (Left Join)
    tareas_query = []
    if carga:
        tareas_query = db.query(
            models_vr.Tarea,
            models_vr.EntregaTarea.calificacion,
            models_vr.EntregaTarea.fecha_envio
        ).outerjoin(
            models_vr.EntregaTarea,
            (models_vr.EntregaTarea.id_tarea == models_vr.Tarea.id_tarea) &
            (models_vr.EntregaTarea.id_alumno == alumno.id_alumno)
        ).filter(models_vr.Tarea.id_carga_academica == carga.id_carga_academica).all()

    # 5. Materiales / contenido de clase
    materiales_query = []
    if carga:
        materiales_query = db.query(models_vr.MaterialClase).filter(
            models_vr.MaterialClase.id_carga_academica == carga.id_carga_academica
        ).order_by(models_vr.MaterialClase.bimestre, models_vr.MaterialClase.fecha_publicacion).all()

    return {
        "curso_info": {"id": id_curso, "anio": anio},
        "curso_nombre": curso.nombre,
        "docente_nombre": docente_nombre,
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
        ],
        "materiales": [
            {
                "id_material": m.id_material,
                "titulo": m.titulo,
                "descripcion": m.descripcion,
                "archivo_url": m.archivo_url,
                "bimestre": m.bimestre
            } for m in materiales_query
        ]
    }

@router.get("/resumen-notas/{id_usuario}")
def obtener_resumen_notas_estudiante(
    id_usuario: int, 
    anio: str, 
    db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    
    if current_user.get("id") != id_usuario:
        raise HTTPException(status_code=403, detail="No puedes acceder a esta información.")
    # 1. Obtener al alumno
    alumno = db.query(models_al.Alumno).filter(models_al.Alumno.id_usuario == id_usuario).first()
    if not alumno:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    # 2. Obtener matrícula
    matricula = db.query(models_en.Matricula).filter(
        models_en.Matricula.id_alumno == alumno.id_alumno,
        models_en.Matricula.id_anio_escolar == anio
    ).first()

    if not matricula:
        return []

    # 3. Consulta maestra para obtener todos los cursos de la sección del alumno
    # y sus notas (si existen)
    resultados = (
        db.query(
            models_ac.Curso.id_curso,
            models_ac.Curso.nombre.label("curso_nombre"),
            func.coalesce(models_mn.ResumenNota.promedio_final, 0).label("promedio_final"),
            func.coalesce(models_mn.ResumenNota.nota_bimestre1, 0).label("nota_bimestre1"),
            func.coalesce(models_mn.ResumenNota.nota_bimestre2, 0).label("nota_bimestre2"),
            func.coalesce(models_mn.ResumenNota.nota_bimestre3, 0).label("nota_bimestre3"),
            func.coalesce(models_mn.ResumenNota.nota_bimestre4, 0).label("nota_bimestre4")
        )
        .select_from(models_en.Matricula)
        .join(models_ac.Seccion, models_ac.Seccion.id_seccion == models_en.Matricula.id_seccion)
        .join(models_ac.Grado, models_ac.Grado.id_grado == models_ac.Seccion.id_grado)
        .join(models_ac.PlanEstudio, models_ac.PlanEstudio.id_grado == models_ac.Grado.id_grado)
        .join(models_ac.Curso, models_ac.Curso.id_curso == models_ac.PlanEstudio.id_curso)
        # El outerjoin permite que el curso aparezca aunque no tenga notas aún
        .outerjoin(
            models_mn.ResumenNota, 
            (models_mn.ResumenNota.id_curso == models_ac.Curso.id_curso) & 
            (models_mn.ResumenNota.id_matricula == matricula.id_matricula)
        )
        .filter(models_en.Matricula.id_matricula == matricula.id_matricula)
        .all()
    )

    # Convertir a lista de diccionarios para serialización segura
    return [row._asdict() for row in resultados]


@router.post("/cerrar-bimestre/{id_carga}/{bimestre}")
def cerrar_notas_bimestre(
    id_carga: int, 
    bimestre: int, 
    db: Session = Depends(get_db), 
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("rol") != "DOCENTE":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información.")
    # 1. Obtener la carga académica y validar existencia
    carga = db.query(models_mn.CargaAcademica).filter(
        models_mn.CargaAcademica.id_carga_academica == id_carga
    ).first()
    
    if not carga:
        raise HTTPException(status_code=404, detail="Carga académica no encontrada")

    # 2. VALIDACIÓN: Verificar que el peso de las tareas sume 100%
    suma_pesos = db.query(func.sum(models_vr.Tarea.peso)).filter(
        models_vr.Tarea.id_carga_academica == id_carga,
        models_vr.Tarea.bimestre == bimestre,
        models_vr.Tarea.estado == "ACTIVO"
    ).scalar() or 0

    if suma_pesos != 100:
        raise HTTPException(
            status_code=400, 
            detail=f"No se puede cerrar el bimestre. El peso total de las tareas es {suma_pesos}%, debe ser 100%."
        )

    # 3. Obtener todas las tareas del bimestre para el cálculo
    tareas = db.query(models_vr.Tarea).filter(
        models_vr.Tarea.id_carga_academica == id_carga,
        models_vr.Tarea.bimestre == bimestre,
        models_vr.Tarea.estado == "ACTIVO"
    ).all()

    # 4. Obtener alumnos matriculados en esa sección y año
    alumnos_matriculados = db.query(models_al.Alumno, models_en.Matricula).join(
        models_en.Matricula, models_al.Alumno.id_alumno == models_en.Matricula.id_alumno
    ).filter(
        models_en.Matricula.id_seccion == carga.id_seccion,
        models_en.Matricula.id_anio_escolar == carga.id_anio_escolar
    ).all()

    # 5. Procesar cada alumno
    for alumno, matricula in alumnos_matriculados:
        promedio_bimestre = 0.0
        
        # Calcular el promedio ponderado
        for tarea in tareas:
            entrega = db.query(models_vr.EntregaTarea).filter(
                models_vr.EntregaTarea.id_tarea == tarea.id_tarea,
                models_vr.EntregaTarea.id_alumno == alumno.id_alumno
            ).first()
            
            calificacion = float(entrega.calificacion) if entrega and entrega.calificacion else 0.0
            promedio_bimestre += (calificacion * (tarea.peso / 100.0))
        
        promedio_redondeado = round(promedio_bimestre, 2)

        # --- OPERACIÓN EN TABLA 'NOTA' ---
        # Si ya existe el registro de "PROMEDIO" para ese bimestre, se actualiza
        nota_existente = db.query(models_mn.Nota).filter(
            models_mn.Nota.id_matricula == matricula.id_matricula,
            models_mn.Nota.id_curso == carga.id_curso,
            models_mn.Nota.bimestre == bimestre,
            models_mn.Nota.tipo_nota == 'PROMEDIO'
        ).first()

        if nota_existente:
            nota_existente.valor = promedio_redondeado
        else:
            nueva_nota = models_mn.Nota(
                id_matricula=matricula.id_matricula,
                id_curso=carga.id_curso,
                bimestre=bimestre,
                tipo_nota='PROMEDIO',
                valor=promedio_redondeado
            )
            db.add(nueva_nota)

        # --- OPERACIÓN EN TABLA 'RESUMEN_NOTA' ---
        resumen = db.query(models_mn.ResumenNota).filter(
            models_mn.ResumenNota.id_matricula == matricula.id_matricula,
            models_mn.ResumenNota.id_curso == carga.id_curso
        ).first()

        if not resumen:
            resumen = models_mn.ResumenNota(
                id_matricula=matricula.id_matricula,
                id_curso=carga.id_curso
            )
            db.add(resumen)

        # Asignar la nota al campo correspondiente según el bimestre
        setattr(resumen, f"nota_bimestre{bimestre}", promedio_redondeado)

        # --- RECALCULAR PROMEDIO FINAL (Lógica de 25% por bimestre) ---
        # Si la nota es None (porque no se ha cursado el bimestre), la tratamos como 0.0
        b1 = float(resumen.nota_bimestre1 or 0.0)
        b2 = float(resumen.nota_bimestre2 or 0.0)
        b3 = float(resumen.nota_bimestre3 or 0.0)
        b4 = float(resumen.nota_bimestre4 or 0.0)

        # El promedio final es la suma de los 4 bimestres dividida entre 4
        # (Es equivalente a: B1*0.25 + B2*0.25 + B3*0.25 + B4*0.25)
        resumen.promedio_final = round((b1 + b2 + b3 + b4) / 4.0, 2)

    db.commit()
    return {"message": f"Bimestre {bimestre} cerrado exitosamente para la carga {id_carga}"}
# --- Asignación de Docentes ---

@router.get("/vínculos-academicos/{anio_id}", response_model=List[schemas.VinculoAcademicoResponse])
def listar_vinculos_para_asignacion(anio_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """
    Obtiene todos los cursos por sección de un año escolar 
    y muestra qué docente tienen asignado (si lo hay).
    """
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes acceder a esta información.")
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
def listar_docentes_busqueda(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes acceder a esta información.")
    """Lista simple de docentes para el selector de la interfaz"""
    return db.query(models_doc.Docente).all()


#--- Delete y update de la carga academica
@router.delete("/carga/{carga_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_carga(carga_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN" :
        raise HTTPException(status_code=403, detail="No puedes modificar esta información.")
    
    db_carga = db.query(models.CargaAcademica).filter(models.CargaAcademica.id_carga_academica == carga_id).first()
    if not db_carga:
        raise HTTPException(status_code=404, detail="Asignación no encontrada")
    
    db.delete(db_carga)
    db.commit()
    return None

@router.patch("/carga/{carga_id}", response_model=schemas.CargaResponse)
def actualizar_carga(carga_id: int, data: schemas.CargaUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    
    if current_user.get("rol") != "ADMIN" :
        raise HTTPException(status_code=403, detail="No puedes modificar esta información.")

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
    db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    
    ensure_owner_or_roles(current_user, id_usuario, "ADMIN")
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
def obtener_cursos_docente_dashboard(id_usuario: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    
    ensure_owner_or_roles(current_user, id_usuario, "ADMIN")
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
            "curso_nombre": c.curso_nombre,
            "grado_nombre": f"{c.grado_nombre} {c.seccion_nombre}",
        }
        for c in cursos_query
    ]

@router.get("/resumen-docente/{id_usuario}")
def obtener_resumen_docente(id_usuario: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    
    ensure_owner_or_roles(current_user, id_usuario, "ADMIN")
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


@router.get("/notificaciones/{id_usuario}")
def obtener_notificaciones(id_usuario: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    
    if current_user.get("id") != id_usuario:
        raise HTTPException(status_code=403, detail="No puedes ver perfiles ajenos")
    
    # 1. Obtener año activo
    anio_activo = db.query(models_ac.AnioEscolar).filter(models_ac.AnioEscolar.activo == True).first()
    if not anio_activo:
        return {"notificaciones": []}
    
    notificaciones = []
    hoy = datetime.now()

    # --- A. DOCENTE ---
    docente = db.query(models_doc.Docente).filter(models_doc.Docente.id_usuario == id_usuario).first()
    if docente:
        entregas = db.query(models_vr.EntregaTarea).join(models_vr.Tarea).join(models_mn.CargaAcademica)\
            .options(joinedload(models_vr.EntregaTarea.alumno), joinedload(models_vr.EntregaTarea.tarea))\
            .filter(
                models_mn.CargaAcademica.id_docente == docente.id_docente,
                models_mn.CargaAcademica.id_anio_escolar == anio_activo.id_anio_escolar
            ).order_by(models_vr.EntregaTarea.fecha_envio.desc()).limit(5).all()
        
        for e in entregas:
            notificaciones.append({
                "tipo": "entrega",
                "mensaje": f"Nueva entrega: {e.alumno.nombres} en {e.tarea.titulo}",
                "fecha": e.fecha_envio.isoformat()
            })

    # --- B. ALUMNO ---
    alumno = db.query(models_al.Alumno).filter(models_al.Alumno.id_usuario == id_usuario).first()
    if alumno:
        calificaciones = db.query(models_vr.EntregaTarea)\
            .options(joinedload(models_vr.EntregaTarea.tarea))\
            .filter(models_vr.EntregaTarea.id_alumno == alumno.id_alumno, models_vr.EntregaTarea.calificacion != None)\
            .order_by(models_vr.EntregaTarea.fecha_envio.desc()).limit(3).all()
        
        for c in calificaciones:
            notificaciones.append({
                "tipo": "nota",
                "mensaje": f"Nota recibida en {c.tarea.titulo}: {c.calificacion}",
                "fecha": c.fecha_envio.isoformat()
            })
            
        deudas = db.query(models_fi.Pago).join(models_en.Matricula)\
            .filter(
                models_fi.Pago.id_alumno == alumno.id_alumno,
                models_fi.Pago.estado == "PENDIENTE",
                models_en.Matricula.id_anio_escolar == anio_activo.id_anio_escolar
            ).all()
        
        for d in deudas:
            notificaciones.append({
                "tipo": "pago",
                "mensaje": f"Pago pendiente: {d.concepto} (S/ {d.monto_total})",
                "fecha": d.fecha_vencimiento.isoformat() if d.fecha_vencimiento else None
            })

        # --- Situación académica (nivelación / repitencia) ---
        from app.modules.verano import models as models_verano
        evals = db.query(models_verano.EvaluacionFinal).filter(
            models_verano.EvaluacionFinal.id_alumno == alumno.id_alumno,
            models_verano.EvaluacionFinal.resultado != "PROMOVIDO"
        ).order_by(models_verano.EvaluacionFinal.fecha.desc()).limit(2).all()
        for ev in evals:
            if ev.resultado == "REPITE":
                msg = "Repetirás el año académico por desaprobar 4 o más cursos."
            elif ev.resultado == "REQUIERE_NIVELACION":
                msg = (f"Tienes {ev.total_desaprobados} curso(s) desaprobado(s). "
                       "Puedes nivelarlos en el verano desde el apartado de Matrícula.")
            else:
                continue
            notificaciones.append({
                "tipo": "academico",
                "mensaje": msg,
                "fecha": ev.fecha.isoformat() if ev.fecha else None
            })

        # Filtramos por el alumno, estado programado y que la fecha sea hoy
        inicio_hoy = datetime.combine(date.today(), datetime.min.time())
        fin_hoy = datetime.combine(date.today(), datetime.max.time())

        citas_hoy = db.query(models_psi.CitaPsicologia).filter(
            models_psi.CitaPsicologia.id_alumno == alumno.id_alumno,
            models_psi.CitaPsicologia.estado == "PROGRAMADA",
            models_psi.CitaPsicologia.fecha_cita >= inicio_hoy,
            models_psi.CitaPsicologia.fecha_cita <= fin_hoy
        ).all()

        for cita in citas_hoy:
            notificaciones.append({
                "tipo": "cita",
                "mensaje": f"Hoy tienes una cita de psicología: {cita.motivo} a las {cita.fecha_cita.strftime('%H:%M')}",
                "fecha": cita.fecha_cita.isoformat()
            })

    rol = current_user.get("rol")

    # --- C. EVENTOS DEL CALENDARIO ---
    q_eventos = db.query(models_web.Evento).filter(models_web.Evento.activo == True)
    if rol == "ADMIN":
        # El administrador ve TODOS los eventos del calendario
        eventos = q_eventos.order_by(models_web.Evento.fecha_inicio.desc()).all()
    else:
        # El resto solo ve los próximos eventos
        eventos = q_eventos.filter(
            models_web.Evento.fecha_inicio >= date.today()
        ).order_by(models_web.Evento.fecha_inicio.asc()).limit(3).all()

    for ev in eventos:
        notificaciones.append({
            "tipo": "evento",
            "mensaje": f"Evento: {ev.titulo} - {ev.descripcion or ''}",
            "fecha": ev.fecha_inicio.isoformat()
        })

    # --- D. MENSAJES RECIBIDOS (Comunes para todos) ---
    mensajes = db.query(models_vr.Mensaje).join(
        models_vr.Conversacion,
        models_vr.Mensaje.id_conversacion == models_vr.Conversacion.id_conversacion
    ).filter(
        models_vr.Mensaje.remitente_id != id_usuario,
        models_vr.Mensaje.leido == False,
        (models_vr.Conversacion.usuario1_id == id_usuario) |
        (models_vr.Conversacion.usuario2_id == id_usuario)
    ).order_by(models_vr.Mensaje.fecha_envio.desc()).limit(10).all()

    for m in mensajes:
        contenido = m.contenido or ""
        resumen = contenido if len(contenido) <= 60 else contenido[:60] + "..."
        notificaciones.append({
            "tipo": "mensaje",
            "mensaje": f"Nuevo mensaje: {resumen}",
            "fecha": m.fecha_envio.isoformat() if m.fecha_envio else None
        })

    # Ordenamos todas las notificaciones por fecha (más recientes primero)
    notificaciones.sort(key=lambda n: n.get("fecha") or "", reverse=True)

    return {"notificaciones": notificaciones}


@router.get("/notificaciones/{id_usuario}/contador")
def contador_notificaciones(id_usuario: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """
    Versión ligera de las notificaciones: devuelve solo el total, usando COUNT()
    en vez de cargar los objetos y construir los mensajes. Pensada para el polling
    del header (cada 60s por usuario). Respeta los mismos topes que la lista
    completa para que el badge quede consistente.
    """
    if current_user.get("id") != id_usuario:
        raise HTTPException(status_code=403, detail="No puedes ver perfiles ajenos")

    anio_activo = db.query(models_ac.AnioEscolar).filter(models_ac.AnioEscolar.activo == True).first()
    if not anio_activo:
        return {"total": 0}

    total = 0
    rol = current_user.get("rol")

    # --- A. DOCENTE: entregas (tope 5) ---
    docente = db.query(models_doc.Docente).filter(models_doc.Docente.id_usuario == id_usuario).first()
    if docente:
        c = db.query(models_vr.EntregaTarea).join(models_vr.Tarea).join(models_mn.CargaAcademica).filter(
            models_mn.CargaAcademica.id_docente == docente.id_docente,
            models_mn.CargaAcademica.id_anio_escolar == anio_activo.id_anio_escolar
        ).count()
        total += min(c, 5)

    # --- B. ALUMNO: notas (tope 3), deudas, citas de hoy ---
    alumno = db.query(models_al.Alumno).filter(models_al.Alumno.id_usuario == id_usuario).first()
    if alumno:
        total += min(db.query(models_vr.EntregaTarea).filter(
            models_vr.EntregaTarea.id_alumno == alumno.id_alumno,
            models_vr.EntregaTarea.calificacion != None
        ).count(), 3)

        total += db.query(models_fi.Pago).join(models_en.Matricula).filter(
            models_fi.Pago.id_alumno == alumno.id_alumno,
            models_fi.Pago.estado == "PENDIENTE",
            models_en.Matricula.id_anio_escolar == anio_activo.id_anio_escolar
        ).count()

        inicio_hoy = datetime.combine(date.today(), datetime.min.time())
        fin_hoy = datetime.combine(date.today(), datetime.max.time())
        total += db.query(models_psi.CitaPsicologia).filter(
            models_psi.CitaPsicologia.id_alumno == alumno.id_alumno,
            models_psi.CitaPsicologia.estado == "PROGRAMADA",
            models_psi.CitaPsicologia.fecha_cita >= inicio_hoy,
            models_psi.CitaPsicologia.fecha_cita <= fin_hoy
        ).count()

        # Situación académica (nivelación / repitencia), tope 2
        from app.modules.verano import models as models_verano
        total += min(db.query(models_verano.EvaluacionFinal).filter(
            models_verano.EvaluacionFinal.id_alumno == alumno.id_alumno,
            models_verano.EvaluacionFinal.resultado != "PROMOVIDO"
        ).count(), 2)

    # --- C. EVENTOS (todos para ADMIN, próximos 3 para el resto) ---
    q_eventos = db.query(models_web.Evento).filter(models_web.Evento.activo == True)
    if rol == "ADMIN":
        total += q_eventos.count()
    else:
        total += min(q_eventos.filter(models_web.Evento.fecha_inicio >= date.today()).count(), 3)

    # --- D. MENSAJES NO LEÍDOS (tope 10) ---
    total += min(db.query(models_vr.Mensaje).join(
        models_vr.Conversacion,
        models_vr.Mensaje.id_conversacion == models_vr.Conversacion.id_conversacion
    ).filter(
        models_vr.Mensaje.remitente_id != id_usuario,
        models_vr.Mensaje.leido == False,
        (models_vr.Conversacion.usuario1_id == id_usuario) |
        (models_vr.Conversacion.usuario2_id == id_usuario)
    ).count(), 10)

    return {"total": total}


# --- NUEVO: GESTIÓN DE TUTORES DE SECCIÓN ---

@router.get("/tutores/{anio_id}", response_model=List[schemas.TutorResponse])
def listar_tutores(anio_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    tutores = db.query(models.TutorSeccion).filter(models.TutorSeccion.id_anio_escolar == anio_id).all()
    resultado = []
    for t in tutores:
        resultado.append({
            "id_tutor_seccion": t.id_tutor_seccion,
            "id_seccion": t.id_seccion,
            "seccion_nombre": t.seccion.nombre,
            "grado_nombre": t.seccion.grado.nombre,
            "docente": t.docente
        })
    return resultado

@router.post("/tutores/", response_model=schemas.TutorResponse)
def asignar_tutor(data: schemas.TutorSeccionCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    
    if current_user.get("rol") != "ADMIN" :
        raise HTTPException(status_code=403, detail="No puedes modificar esta información.")
    
    existe = db.query(models.TutorSeccion).filter(
        models.TutorSeccion.id_anio_escolar == data.id_anio_escolar,
        models.TutorSeccion.id_seccion == data.id_seccion,
        models.TutorSeccion.id_docente == data.id_docente
    ).first()
    
    if existe:
        raise HTTPException(status_code=400, detail="Este docente ya es tutor de esta sección.")
    
    nuevo = models.TutorSeccion(**data.model_dump())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    
    return {
        "id_tutor_seccion": nuevo.id_tutor_seccion,
        "id_seccion": nuevo.id_seccion,
        "seccion_nombre": nuevo.seccion.nombre,
        "grado_nombre": nuevo.seccion.grado.nombre,
        "docente": nuevo.docente
    }

@router.delete("/tutores/{id_tutor_seccion}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_tutor(id_tutor_seccion: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
       
    if current_user.get("rol") != "ADMIN" :
        raise HTTPException(status_code=403, detail="No puedes modificar esta información.")

    tutor = db.query(models.TutorSeccion).filter(models.TutorSeccion.id_tutor_seccion == id_tutor_seccion).first()
    if not tutor:
        raise HTTPException(status_code=404, detail="Asignación de tutor no encontrada")
    
    db.delete(tutor)
    db.commit()
    return None