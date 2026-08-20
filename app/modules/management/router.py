from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, extract, or_
from sqlalchemy.exc import OperationalError, ProgrammingError
from typing import List, Optional
from datetime import datetime, date, timedelta
from app.db.database import get_db
from app.modules.academic import models as models_ac
from app.modules.academic import consultas as consultas_ac
from app.modules.users.alumno import models as models_al
from app.modules.users.docente import models as models_doc
from app.modules.enrollment import models as models_en
from app.modules.virtual import models as models_vr
from app.modules.management import models as models_mn
from app.modules.finance import models as models_fi
from app.modules.web import models as models_web
from app.modules.behavior import models as models_psi
from app.modules.horario import models as models_hr
from app.modules.users.relacion_familiar import models as models_rel
from app.core.util.security import get_current_user, ensure_owner_or_roles
from .service import enviar_notificaciones_asistencia, ESTADOS_NOTIFICABLES
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
    
    # Si ya existe una asignación para esta sección, curso y año, actualizar el docente
    existente = db.query(models.CargaAcademica).filter(
        models.CargaAcademica.id_anio_escolar == carga.id_anio_escolar,
        models.CargaAcademica.id_seccion == carga.id_seccion,
        models.CargaAcademica.id_curso == carga.id_curso
    ).first()

    if existente:
        existente.id_docente = carga.id_docente
        db.commit()
        db.refresh(existente)
        return existente

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
        # Solo notificamos los estados relevantes (tardanza/falta/justificado).
        # Filtramos ANTES de consultar apoderados: en un aula de 30 alumnos se
        # pasa de 30 correos diarios a 2 o 3, y la consulta a la BD se reduce igual.
        registros_notificables = [
            r for r in payload.registros if r.estado in ESTADOS_NOTIFICABLES
        ]

        if registros_notificables:
            ids_notificables = [r.id_matricula for r in registros_notificables]
            matriculas = (
                db.query(models_en.Matricula)
                .options(joinedload(models_en.Matricula.alumno))
                .filter(models_en.Matricula.id_matricula.in_(ids_notificables))
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
                    if email and "@" in email:
                        emails_por_alumno.setdefault(rel.id_alumno, []).append(email)

            for r in registros_notificables:
                m = mapa_matriculas.get(r.id_matricula)
                if not m or not m.alumno:
                    continue
                nombre = f"{m.alumno.nombres} {m.alumno.apellidos}"
                # dict.fromkeys: si un apoderado figura dos veces en las relaciones
                # del mismo alumno, recibe un solo correo
                for email in dict.fromkeys(emails_por_alumno.get(m.alumno.id_alumno, [])):
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


@router.get("/asistencia/seccion/{id_seccion}")
def obtener_asistencia_seccion(
    id_seccion: int,
    fecha: str = Query(..., description="Fecha en formato YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("rol") not in ("AUXILIAR", "DOCENTE", "ADMIN"):
        raise HTTPException(status_code=403, detail="No tienes permisos para ver la asistencia")

    matriculas = db.query(models_en.Matricula.id_matricula).filter(
        models_en.Matricula.id_seccion == id_seccion
    ).all()
    ids_matricula = [m[0] for m in matriculas]

    if not ids_matricula:
        return {"fecha": fecha, "asistencias": {}, "registros": []}

    registros = db.query(models.Asistencia).filter(
        models.Asistencia.id_matricula.in_(ids_matricula),
        models.Asistencia.fecha == fecha
    ).all()

    mapa_asistencias = {r.id_matricula: r.estado for r in registros}
    lista_registros = [
        {
            "id_asistencia": r.id_asistencia,
            "id_matricula": r.id_matricula,
            "fecha": str(r.fecha),
            "estado": r.estado,
            "observacion": r.observacion or ""
        }
        for r in registros
    ]

    return {
        "fecha": fecha,
        "asistencias": mapa_asistencias,
        "registros": lista_registros
    }


@router.get("/asistencia/reporte-resumen")
def reporte_resumen_asistencia(
    anio_id: Optional[str] = Query(None),
    bimestre: Optional[int] = Query(None),
    nivel_id: Optional[int] = Query(None),
    grado_id: Optional[int] = Query(None),
    seccion_id: Optional[int] = Query(None),
    dni: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("rol") not in ("AUXILIAR", "DOCENTE", "ADMIN"):
        raise HTTPException(status_code=403, detail="No tienes permisos para ver el reporte de asistencia")

    if not anio_id:
        ae_activo = db.query(models_ac.AnioEscolar).filter(models_ac.AnioEscolar.activo == True).first()
        anio_id = ae_activo.id_anio_escolar if ae_activo else str(datetime.now().year)

    query = (
        db.query(
            models_en.Matricula.id_matricula,
            models_en.Matricula.id_alumno,
            models_al.Alumno.nombres,
            models_al.Alumno.apellidos,
            models_al.Alumno.dni,
            models_ac.Nivel.nombre.label("nivel_nombre"),
            models_ac.Grado.nombre.label("grado_nombre"),
            models_ac.Grado.id_grado,
            models_ac.Seccion.nombre.label("seccion_nombre"),
            models_ac.Seccion.id_seccion,
        )
        .join(models_al.Alumno, models_en.Matricula.id_alumno == models_al.Alumno.id_alumno)
        .join(models_ac.Seccion, models_en.Matricula.id_seccion == models_ac.Seccion.id_seccion)
        .join(models_ac.Grado, models_ac.Seccion.id_grado == models_ac.Grado.id_grado)
        .join(models_ac.Nivel, models_ac.Grado.id_nivel == models_ac.Nivel.id_nivel)
        .filter(
            models_en.Matricula.id_anio_escolar == anio_id,
            models_al.Alumno.estado_ingreso != "RETIRADO"
        )
    )

    if nivel_id and isinstance(nivel_id, int):
        query = query.filter(models_ac.Grado.id_nivel == nivel_id)
    if grado_id and isinstance(grado_id, int):
        query = query.filter(models_ac.Grado.id_grado == grado_id)
    if seccion_id and isinstance(seccion_id, int):
        query = query.filter(models_ac.Seccion.id_seccion == seccion_id)
    if dni and isinstance(dni, str) and dni.strip():
        query = query.filter(models_al.Alumno.dni.like(f"%{dni.strip()}%"))
    if q and isinstance(q, str) and q.strip():
        termino = q.strip()
        query = query.filter(
            or_(
                models_al.Alumno.nombres.like(f"%{termino}%"),
                models_al.Alumno.apellidos.like(f"%{termino}%"),
                models_al.Alumno.dni.like(f"%{termino}%")
            )
        )

    matriculas = query.order_by(
        models_ac.Grado.id_nivel,
        models_ac.Grado.orden,
        models_ac.Seccion.nombre,
        models_al.Alumno.apellidos,
        models_al.Alumno.nombres
    ).all()

    from app.modules.behavior.bimestres import calendario
    ae_obj = db.query(models_ac.AnioEscolar).filter(models_ac.AnioEscolar.id_anio_escolar == anio_id).first()
    ini_date = ae_obj.fecha_inicio if ae_obj else date(int(anio_id) if str(anio_id).isdigit() else datetime.now().year, 3, 1)
    fin_date = ae_obj.fecha_fin if ae_obj and ae_obj.fecha_fin else date(int(anio_id) if str(anio_id).isdigit() else datetime.now().year, 12, 20)
    tramos = calendario(db, anio_id, ini_date, fin_date)
    tramo_sel = None
    if bimestre and isinstance(bimestre, int) and bimestre > 0:
        tramo_sel = next((t for t in tramos if t[0] == bimestre), None)

    bimestres_info = [
        {
            "numero": t[0],
            "fecha_inicio": str(t[1]),
            "fecha_fin": str(t[2]),
            "nombre": f"{t[0]}° Bimestre"
        }
        for t in tramos
    ]

    if not matriculas:
        return {
            "total": 0,
            "anio_id": anio_id,
            "bimestre": bimestre,
            "bimestres": bimestres_info,
            "alumnos": []
        }

    ids_matricula = [m.id_matricula for m in matriculas]

    conteos_query = (
        db.query(
            models.Asistencia.id_matricula,
            models.Asistencia.estado,
            func.count(models.Asistencia.id_asistencia).label("conteo")
        )
        .filter(models.Asistencia.id_matricula.in_(ids_matricula))
    )

    if tramo_sel:
        conteos_query = conteos_query.filter(
            models.Asistencia.fecha >= tramo_sel[1],
            models.Asistencia.fecha <= tramo_sel[2]
        )

    conteos_list = conteos_query.group_by(
        models.Asistencia.id_matricula, models.Asistencia.estado
    ).all()

    mapa_conteos: dict[int, dict[str, int]] = {}
    for c in conteos_list:
        if c.id_matricula not in mapa_conteos:
            mapa_conteos[c.id_matricula] = {"P": 0, "T": 0, "F": 0, "J": 0}
        mapa_conteos[c.id_matricula][c.estado] = int(c.conteo)

    resultados = []
    for m in matriculas:
        cnt = mapa_conteos.get(m.id_matricula, {"P": 0, "T": 0, "F": 0, "J": 0})
        p = cnt.get("P", 0)
        t = cnt.get("T", 0)
        f = cnt.get("F", 0)
        j = cnt.get("J", 0)
        total_dias = p + t + f + j
        porcentaje = round(((p + t) / total_dias) * 100, 1) if total_dias > 0 else 100.0

        resultados.append({
            "id_matricula": m.id_matricula,
            "id_alumno": m.id_alumno,
            "alumno": f"{m.apellidos} {m.nombres}".strip(),
            "dni": m.dni or "—",
            "nivel": m.nivel_nombre,
            "grado": m.grado_nombre,
            "id_grado": m.id_grado,
            "seccion": m.seccion_nombre,
            "id_seccion": m.id_seccion,
            "presentes": p,
            "tardanzas": t,
            "faltas": f,
            "justificaciones": j,
            "total_dias": total_dias,
            "porcentaje_asistencia": porcentaje
        })

    return {
        "total": len(resultados),
        "anio_id": anio_id,
        "bimestre": bimestre,
        "bimestres": bimestres_info,
        "alumnos": resultados
    }


def _es_anio_verano(db: Session, anio: str) -> bool:
    """Si un año escolar es de tipo VERANO."""
    fila = db.query(models_ac.AnioEscolar.tipo).filter(
        models_ac.AnioEscolar.id_anio_escolar == anio
    ).first()
    return bool(fila) and (fila[0] or "REGULAR").strip().upper() == "VERANO"


def _cursos_verano_estudiante(db: Session, id_alumno: int, anio: str) -> List[dict]:
    """Cursos de verano del alumno con su docente, si ya hay alguno asignado.

    El docente se busca por la carga académica de la sección de verano del
    alumno; en verano es normal que todavía no la haya, y en ese caso el curso
    igual tiene que aparecer (con "Sin asignar"), como pasa en el año regular.
    """
    from app.modules.verano import service as verano_service

    cursos = verano_service.cursos_de_verano_del_alumno(db, id_alumno, anio)
    if not cursos:
        return []

    matricula = db.query(models_en.Matricula).filter(
        models_en.Matricula.id_alumno == id_alumno,
        models_en.Matricula.id_anio_escolar == anio,
    ).first()

    docentes: dict = {}
    if matricula is not None and matricula.id_seccion:
        filas = (db.query(models.CargaAcademica.id_curso,
                          models_doc.Docente.nombres,
                          models_doc.Docente.apellidos,
                          models_doc.Docente.url_perfil)
                 .join(models_doc.Docente,
                       models_doc.Docente.id_docente == models.CargaAcademica.id_docente)
                 .filter(models.CargaAcademica.id_anio_escolar == anio,
                         models.CargaAcademica.id_seccion == matricula.id_seccion,
                         models.CargaAcademica.id_curso.in_([c["id_curso"] for c in cursos]))
                 .all())
        docentes = {f.id_curso: f for f in filas}

    salida = []
    for c in cursos:
        d = docentes.get(c["id_curso"])
        salida.append({
            "id_curso": c["id_curso"],
            # El taller se marca en el nombre, como en el panel de admisión.
            "curso_nombre": f"{c['nombre']} (Taller)" if c["es_taller"] else c["nombre"],
            "docente_nombres": d.nombres if d else "Sin asignar",
            "docente_apellidos": d.apellidos if d else "",
            "url_perfil_docente": d.url_perfil if d else None,
        })
    return salida


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

    # En verano los cursos no salen del plan de estudio del grado: el alumno
    # elige los suyos al inscribirse. Ver `cursos_de_verano_del_alumno`.
    if _es_anio_verano(db, anio):
        return _cursos_verano_estudiante(db, alumno.id_alumno, anio)

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

    # En verano los cursos son los que el alumno eligió al inscribirse, no los
    # del plan de estudio del grado, y la nota es una sola (no hay bimestres).
    if _es_anio_verano(db, anio):
        from app.modules.verano import service as verano_service

        cursos = verano_service.cursos_de_verano_del_alumno(db, alumno.id_alumno, anio)
        if not cursos:
            return []
        notas = {
            rn.id_curso: rn for rn in db.query(models_mn.ResumenNota).filter(
                models_mn.ResumenNota.id_matricula == matricula.id_matricula
            ).all()
        }
        salida = []
        for c in cursos:
            rn = notas.get(c["id_curso"])
            promedio = float(rn.promedio_final) if rn and rn.promedio_final is not None else 0
            salida.append({
                "id_curso": c["id_curso"],
                "curso_nombre": f"{c['nombre']} (Taller)" if c["es_taller"] else c["nombre"],
                "promedio_final": promedio,
                # El verano es un periodo único: la nota va en el primero y los
                # otros tres se mandan en 0 para no romper a quien los lea.
                "nota_bimestre1": promedio,
                "nota_bimestre2": 0,
                "nota_bimestre3": 0,
                "nota_bimestre4": 0,
            })
        return salida

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

    # 4. Obtener alumnos matriculados en esa sección y año (excluyendo retirados)
    alumnos_matriculados = db.query(models_al.Alumno, models_en.Matricula).join(
        models_en.Matricula, models_al.Alumno.id_alumno == models_en.Matricula.id_alumno
    ).filter(
        models_en.Matricula.id_seccion == carga.id_seccion,
        models_en.Matricula.id_anio_escolar == carga.id_anio_escolar,
        models_al.Alumno.estado_ingreso != "RETIRADO"
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

# La ruta buena es la de abajo, sin tilde. La versión con tilde se mantiene
# registrada solo por compatibilidad: el navegador la envía codificada como
# /gestion/v%C3%ADnculos-academicos/... y, al pasar por el proxy de Apache en
# cPanel, no llega igual que en local, así que FastAPI no la reconocía y
# devolvía 404 solo en producción. Las URL de la API se dejan en ASCII.
@router.get("/vinculos-academicos/{anio_id}", response_model=List[schemas.VinculoAcademicoResponse])
@router.get("/vínculos-academicos/{anio_id}", response_model=List[schemas.VinculoAcademicoResponse],
            include_in_schema=False)
def listar_vinculos_para_asignacion(anio_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """
    Obtiene todos los cursos por sección de un año escolar
    y muestra qué docente tienen asignado (si lo hay).
    Soporta años regulares (por Plan de Estudio) y de verano (por Cursos de Verano).
    """
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes acceder a esta información.")

    anio = db.query(models_ac.AnioEscolar).filter(models_ac.AnioEscolar.id_anio_escolar == anio_id).first()
    es_verano = bool(anio and anio.tipo == "VERANO")

    # 1. Buscamos todas las secciones del año escolar con su grado y nivel
    secciones = (
        db.query(models_ac.Seccion)
        .options(joinedload(models_ac.Seccion.grado).joinedload(models_ac.Grado.nivel))
        .filter(models_ac.Seccion.id_anio_escolar == anio_id)
        .all()
    )

    from app.modules.verano import service as verano_service
    
    resultado = []
    for seccion in secciones:
        if es_verano:
            grupo_clave, grupo_etiqueta = verano_service.grupo_por_grado(seccion.grado)
            query_cursos = db.query(models_ac.Curso).filter(models_ac.Curso.es_verano == True)
            if grupo_clave:
                cursos_asignables = query_cursos.filter(
                    (models_ac.Curso.grupo_verano == grupo_clave) | (models_ac.Curso.tipo_verano == "TALLER")
                ).all()
            else:
                cursos_asignables = query_cursos.all()
            nombre_grado_mostrar = grupo_etiqueta or (seccion.grado.nombre if seccion.grado else "General")
        else:
            # Año regular: según Plan de Estudio
            cursos_asignables = (
                db.query(models_ac.Curso)
                .join(models_ac.PlanEstudio, models_ac.PlanEstudio.id_curso == models_ac.Curso.id_curso)
                .filter(models_ac.PlanEstudio.id_grado == seccion.id_grado)
                .all()
            )
            nombre_grado_mostrar = seccion.grado.nombre if seccion.grado else "Grado"

        for curso in cursos_asignables:
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
                "grado_nombre": nombre_grado_mostrar,
                "id_curso": curso.id_curso,
                "curso_nombre": curso.nombre,
                "id_carga_academica": carga.id_carga_academica if carga else None,
                "docente": docente
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
    
    # 1. Verificar si existen notas registradas en esta sección y curso
    tiene_notas = (
        db.query(models.Nota.id_nota)
        .join(models_en.Matricula, models_en.Matricula.id_matricula == models.Nota.id_matricula)
        .filter(
            models.Nota.id_curso == db_carga.id_curso,
            models_en.Matricula.id_seccion == db_carga.id_seccion,
            models_en.Matricula.id_anio_escolar == db_carga.id_anio_escolar
        )
        .first()
    )
    if tiene_notas:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Una asignación que tiene notas registradas no se puede borrar, solo se puede actualizar."
        )

    # 2. Verificar si tiene tareas o evaluaciones asociadas
    tiene_tareas = db.query(models_vr.Tarea.id_tarea).filter(models_vr.Tarea.id_carga_academica == carga_id).first()
    if tiene_tareas:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Una asignación que tiene tareas o evaluaciones no se puede borrar, solo se puede actualizar."
        )

    try:
        db.delete(db_carga)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Una asignación con registros asociados no se puede borrar, solo se puede actualizar."
        )
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

    # 2. Query para obtener los cursos asignados y contar alumnos activos
    anio_obj = db.query(models_ac.AnioEscolar).filter(models_ac.AnioEscolar.id_anio_escolar == anio).first()
    es_verano = anio_obj is not None and anio_obj.tipo == "VERANO"

    # Subquery para contar alumnos por sección
    subquery_alumnos = (
        db.query(
            models_en.Matricula.id_seccion, 
            func.count(models_en.Matricula.id_alumno).label("total_alumnos")
        )
        .join(models_al.Alumno, models_al.Alumno.id_alumno == models_en.Matricula.id_alumno)
        .filter(
            models_en.Matricula.id_anio_escolar == anio,
            models_al.Alumno.estado_ingreso != "RETIRADO"
        )
        .group_by(models_en.Matricula.id_seccion)
        .subquery()
    )

    cursos_query = (
        db.query(
            models.CargaAcademica.id_carga_academica,
            models_ac.Curso.nombre.label("curso_nombre"),
            models_ac.Grado.id_grado.label("id_grado"),
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

    def _formatear_grado(id_grado: int, nombre_orig: str) -> str:
        if es_verano:
            if id_grado == 1: return "1ro y 2do de Primaria"
            if id_grado == 3: return "3ro y 4to de Primaria"
            if id_grado == 5: return "5to y 6to de Primaria"
            if id_grado == 7: return "1ro de Secundaria"
            if id_grado == 8: return "2do de Secundaria"
            if id_grado == 9: return "3ro de Secundaria"
            if id_grado in (10, 11): return "Pre Academia"
        return nombre_orig or ""

    return [
        schemas.CursoDocenteResponse(
            id_carga=c.id_carga_academica,
            curso_nombre=c.curso_nombre,
            grado_nombre=_formatear_grado(c.id_grado, c.grado_nombre),
            seccion_nombre=c.seccion_nombre,
            alumnos=int(c.num_alumnos or 0),
            img=""
        )
        for c in cursos_query
    ]


@router.get("/mis-cursos-docente-dashboard/{id_usuario}")
def obtener_cursos_docente_dashboard(id_usuario: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    
    ensure_owner_or_roles(current_user, id_usuario, "ADMIN")
    # 1. Buscar año activo automáticamente
    anio_activo = db.query(models_ac.AnioEscolar).filter(models_ac.AnioEscolar.activo == True).first()
    if not anio_activo:
        raise HTTPException(status_code=404, detail="No hay año escolar activo")
    
    es_verano = anio_activo.tipo == "VERANO"

    # 2. Buscar docente
    docente = db.query(models_doc.Docente).filter(models_doc.Docente.id_usuario == id_usuario).first()
    if not docente:
        raise HTTPException(status_code=404, detail="Docente no encontrado")

    # 3. Query de cursos
    cursos_query = (
        db.query(
            models_mn.CargaAcademica.id_carga_academica,
            models_ac.Curso.nombre.label("curso_nombre"),
            models_ac.Grado.id_grado.label("id_grado"),
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

    def _formatear_grado_dash(id_grado: int, nombre_orig: str, sec_nom: str) -> str:
        if es_verano:
            if id_grado == 1: return f"1ro y 2do Primaria {sec_nom}"
            if id_grado == 3: return f"3ro y 4to Primaria {sec_nom}"
            if id_grado == 5: return f"5to y 6to Primaria {sec_nom}"
            if id_grado == 7: return f"1ro Secundaria {sec_nom}"
            if id_grado == 8: return f"2do Secundaria {sec_nom}"
            if id_grado == 9: return f"3ro Secundaria {sec_nom}"
            if id_grado in (10, 11): return f"Pre Academia {sec_nom}"
        return f"{nombre_orig} {sec_nom}"

    return [
        {
            "id_carga": c.id_carga_academica,
            "curso_nombre": c.curso_nombre,
            "grado_nombre": _formatear_grado_dash(c.id_grado, c.grado_nombre, c.seccion_nombre),
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

    # 4. Alumnos totales: Matrículas activas en esas secciones (excluyendo retirados)
    num_alumnos = (
        db.query(models_en.Matricula)
        .join(models_al.Alumno, models_al.Alumno.id_alumno == models_en.Matricula.id_alumno)
        .filter(
            models_en.Matricula.id_seccion.in_(ids_secciones),
            models_al.Alumno.estado_ingreso != "RETIRADO"
        )
        .count()
    )

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


# --- Notificaciones -------------------------------------------------------
#
# Hay dos endpoints sobre los mismos datos: la lista (que arma los mensajes) y
# el contador (que solo suma, para el badge de la campana). El badge se apaga
# cuando el total coincide con lo que el usuario ya vio, así que si los dos
# endpoints cuentan cosas distintas el badge se queda encendido para siempre.
# Por eso los topes son constantes compartidas y los filtros se arman una sola
# vez en las funciones de abajo: la lista les pide .all() y el contador
# .count(), pero el CONJUNTO de filas es exactamente el mismo.

TOPE_ENTREGAS_DOCENTE = 5
TOPE_NOTAS_ALUMNO = 3
TOPE_EVALUACIONES = 2
TOPE_CONDUCTA = 5
TOPE_CITAS = 5
TOPE_EVENTOS = 3
TOPE_MENSAJES = 10


def _q_reportes_conducta(db: Session, id_alumno: int, ae):
    """Reportes de conducta del alumno dentro del año escolar `ae`.

    `reporte_conducta` no guarda el año escolar, solo la fecha, así que el
    tramo se acota con las fechas del año. Sin ese filtro un alumno de
    secundaria arrastraría los reportes de todos sus años anteriores.
    """
    q = db.query(models_psi.ReporteConducta).filter(
        models_psi.ReporteConducta.id_alumno == id_alumno
    )
    inicio = getattr(ae, "fecha_inicio", None)
    fin = getattr(ae, "fecha_fin", None)
    if inicio:
        q = q.filter(models_psi.ReporteConducta.fecha_reporte >= datetime.combine(inicio, datetime.min.time()))
    if fin:
        q = q.filter(models_psi.ReporteConducta.fecha_reporte <= datetime.combine(fin, datetime.max.time()))
    return q


def _q_citas_programadas(db: Session, id_alumno: int):
    """Citas de psicología ya programadas y que todavía no han pasado.

    Antes solo se avisaba de las citas del MISMO día: si al alumno le
    programaban una cita para la semana siguiente no se enteraba hasta esa
    mañana. Ahora aparece desde que se registra y deja de aparecer cuando el
    día pasa (o cuando la cita cambia de estado).
    """
    inicio_hoy = datetime.combine(date.today(), datetime.min.time())
    return db.query(models_psi.CitaPsicologia).filter(
        models_psi.CitaPsicologia.id_alumno == id_alumno,
        models_psi.CitaPsicologia.estado == "PROGRAMADA",
        models_psi.CitaPsicologia.fecha_cita >= inicio_hoy,
    )


def _anios_inscripcion_abierta(db: Session, id_alumno: Optional[int] = None):
    """Años escolares cuyo plazo de inscripción está abierto hoy.

    Si se pasa `id_alumno` se descartan los años en los que ese alumno ya se
    inscribió: no tiene sentido avisar de una matrícula que ya hizo. Para los
    años de verano la inscripción vive en `solicitud_verano` (la matrícula
    recién se crea al admitir), así que se miran las dos tablas.
    """
    hoy = date.today()
    anios = db.query(models_ac.AnioEscolar).filter(
        models_ac.AnioEscolar.inicio_inscripcion.isnot(None),
        models_ac.AnioEscolar.fin_inscripcion.isnot(None),
        models_ac.AnioEscolar.inicio_inscripcion <= hoy,
        models_ac.AnioEscolar.fin_inscripcion >= hoy,
    ).order_by(models_ac.AnioEscolar.id_anio_escolar.asc()).all()

    if not anios or id_alumno is None:
        return anios

    ids = [a.id_anio_escolar for a in anios]
    ya = {
        m[0] for m in db.query(models_en.Matricula.id_anio_escolar).filter(
            models_en.Matricula.id_alumno == id_alumno,
            models_en.Matricula.id_anio_escolar.in_(ids),
        ).all()
    }
    # `solicitud_verano` la crea el script del módulo de verano; si la base aún
    # no lo tiene, se avisa igual en vez de tumbar todas las notificaciones.
    try:
        from app.modules.verano import models as models_verano
        ya |= {
            s[0] for s in db.query(models_verano.SolicitudVerano.id_anio_escolar).filter(
                models_verano.SolicitudVerano.id_alumno == id_alumno,
                models_verano.SolicitudVerano.id_anio_escolar.in_(ids),
            ).all()
        }
    except (ProgrammingError, OperationalError):
        db.rollback()

    return [a for a in anios if a.id_anio_escolar not in ya]


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
            ).order_by(models_vr.EntregaTarea.fecha_envio.desc()).limit(TOPE_ENTREGAS_DOCENTE).all()
        
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
            .order_by(models_vr.EntregaTarea.fecha_envio.desc()).limit(TOPE_NOTAS_ALUMNO).all()
        
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
        ).order_by(models_verano.EvaluacionFinal.fecha.desc()).limit(TOPE_EVALUACIONES).all()
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

        # --- Reportes de conducta ---
        # El alumno se entera por aquí de cada falta que le registran el
        # auxiliar o su tutor, con la falta y los puntos que le cuesta.
        reportes = (_q_reportes_conducta(db, alumno.id_alumno, anio_activo)
                    .options(joinedload(models_psi.ReporteConducta.nivel))
                    .order_by(models_psi.ReporteConducta.fecha_reporte.desc())
                    .limit(TOPE_CONDUCTA).all())
        for r in reportes:
            falta = r.nivel.nombre if r.nivel else "Falta de conducta"
            puntos = r.nivel.puntos if r.nivel else None
            detalle = f" (-{puntos} puntos)" if puntos else ""
            notificaciones.append({
                "tipo": "conducta",
                "mensaje": f"Nuevo reporte de conducta: {falta}{detalle}",
                "fecha": r.fecha_reporte.isoformat() if r.fecha_reporte else None,
            })

        # --- Citas de psicología programadas ---
        citas = (_q_citas_programadas(db, alumno.id_alumno)
                 .order_by(models_psi.CitaPsicologia.fecha_cita.asc())
                 .limit(TOPE_CITAS).all())
        hoy_dia = date.today()
        for cita in citas:
            cuando = ("hoy" if cita.fecha_cita.date() == hoy_dia
                      else f"el {cita.fecha_cita.strftime('%d/%m/%Y')}")
            notificaciones.append({
                "tipo": "cita",
                "mensaje": (f"Tienes una cita de psicología {cuando} a las "
                            f"{cita.fecha_cita.strftime('%H:%M')}: {cita.motivo}"),
                "fecha": cita.fecha_cita.isoformat()
            })

        # --- Inscripciones abiertas (verano o nuevo año académico) ---
        for a in _anios_inscripcion_abierta(db, alumno.id_alumno):
            if (a.tipo or "REGULAR").strip().upper() == "VERANO":
                mensaje = (f"Están abiertas las inscripciones del año académico de verano "
                           f"{a.id_anio_escolar}. Puedes inscribirte desde Matrícula.")
            else:
                mensaje = (f"Está abierta la matrícula del año académico {a.id_anio_escolar}. "
                           "Puedes revisarla desde Matrícula.")
            notificaciones.append({
                "tipo": "inscripcion",
                "mensaje": mensaje,
                # La fecha de la notificación es el cierre del plazo, que es el
                # dato que al alumno le importa y lo mantiene arriba en la lista
                # a medida que se acerca.
                "fecha": a.fin_inscripcion.isoformat() if a.fin_inscripcion else None,
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
        ).order_by(models_web.Evento.fecha_inicio.asc()).limit(TOPE_EVENTOS).all()

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
    ).order_by(models_vr.Mensaje.fecha_envio.desc()).limit(TOPE_MENSAJES).all()

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

    # El año activo se lee de la caché: este endpoint lo consultaban los 650
    # usuarios cada minuto para leer siempre la misma fila.
    id_anio_activo = consultas_ac.id_anio_activo(db)
    if not id_anio_activo:
        return {"total": 0}

    total = 0
    rol = current_user.get("rol")

    # El rol viene del token firmado, así que se puede usar para buscar solo el
    # perfil que corresponde. Antes se consultaban docente Y alumno en todas las
    # llamadas, y una de las dos siempre sobraba.

    # --- A. DOCENTE: entregas (tope 5) ---
    docente = None
    if rol == "DOCENTE":
        docente = db.query(models_doc.Docente).filter(models_doc.Docente.id_usuario == id_usuario).first()
    if docente:
        c = db.query(models_vr.EntregaTarea).join(models_vr.Tarea).join(models_mn.CargaAcademica).filter(
            models_mn.CargaAcademica.id_docente == docente.id_docente,
            models_mn.CargaAcademica.id_anio_escolar == id_anio_activo
        ).count()
        total += min(c, TOPE_ENTREGAS_DOCENTE)

    # --- B. ALUMNO: notas, deudas, conducta, citas e inscripciones ---
    alumno = None
    if rol == "ALUMNO":
        alumno = db.query(models_al.Alumno).filter(models_al.Alumno.id_usuario == id_usuario).first()
    if alumno:
        total += min(db.query(models_vr.EntregaTarea).filter(
            models_vr.EntregaTarea.id_alumno == alumno.id_alumno,
            models_vr.EntregaTarea.calificacion != None
        ).count(), TOPE_NOTAS_ALUMNO)

        total += db.query(models_fi.Pago).join(models_en.Matricula).filter(
            models_fi.Pago.id_alumno == alumno.id_alumno,
            models_fi.Pago.estado == "PENDIENTE",
            models_en.Matricula.id_anio_escolar == id_anio_activo
        ).count()

        # Los mismos filtros que la lista, pero contando en vez de traer filas.
        ae_activo = consultas_ac.anio_activo(db)
        total += min(_q_reportes_conducta(db, alumno.id_alumno, ae_activo).count(), TOPE_CONDUCTA)
        total += min(_q_citas_programadas(db, alumno.id_alumno).count(), TOPE_CITAS)
        total += len(_anios_inscripcion_abierta(db, alumno.id_alumno))

        # Situación académica (nivelación / repitencia), tope 2
        from app.modules.verano import models as models_verano
        total += min(db.query(models_verano.EvaluacionFinal).filter(
            models_verano.EvaluacionFinal.id_alumno == alumno.id_alumno,
            models_verano.EvaluacionFinal.resultado != "PROMOVIDO"
        ).count(), TOPE_EVALUACIONES)

    # --- C. EVENTOS (todos para ADMIN, próximos 3 para el resto) ---
    q_eventos = db.query(models_web.Evento).filter(models_web.Evento.activo == True)
    if rol == "ADMIN":
        total += q_eventos.count()
    else:
        total += min(q_eventos.filter(models_web.Evento.fecha_inicio >= date.today()).count(), TOPE_EVENTOS)

    # --- D. MENSAJES NO LEÍDOS (tope 10) ---
    total += min(db.query(models_vr.Mensaje).join(
        models_vr.Conversacion,
        models_vr.Mensaje.id_conversacion == models_vr.Conversacion.id_conversacion
    ).filter(
        models_vr.Mensaje.remitente_id != id_usuario,
        models_vr.Mensaje.leido == False,
        (models_vr.Conversacion.usuario1_id == id_usuario) |
        (models_vr.Conversacion.usuario2_id == id_usuario)
    ).count(), TOPE_MENSAJES)

    return {"total": total}


# --- NUEVO: GESTIÓN DE TUTORES DE SECCIÓN ---

def es_curso_excluido_tutor(nombre_curso: str | None) -> bool:
    """Verifica si un curso debe excluirse de la asignación automática al tutor
    (Violín, Inglés, Computación y Ajedrez)."""
    if not nombre_curso:
        return False
    import unicodedata
    n = unicodedata.normalize('NFKD', str(nombre_curso)).encode('ASCII', 'ignore').decode('utf-8').lower()
    excluidos = {'violin', 'ingles', 'computacion', 'ajedrez'}
    return any(exc in n for exc in excluidos)


def sincronizar_cursos_tutor(db: Session, id_anio_escolar: str, id_seccion: int, id_docente: int):
    """Asigna automáticamente al docente tutor todos los cursos del grado y sección,
    excepto los cursos de Violín, Inglés, Computación y Ajedrez."""
    seccion = db.query(models_ac.Seccion).filter(models_ac.Seccion.id_seccion == id_seccion).first()
    if not seccion:
        return

    # 1. Cursos del plan de estudio para este grado
    cursos_plan = (
        db.query(models_ac.Curso)
        .join(models_ac.PlanEstudio, models_ac.PlanEstudio.id_curso == models_ac.Curso.id_curso)
        .filter(models_ac.PlanEstudio.id_grado == seccion.id_grado)
        .all()
    )

    # 2. Cargas académicas ya existentes para esta sección y año
    cargas_existentes = (
        db.query(models.CargaAcademica)
        .filter(
            models.CargaAcademica.id_anio_escolar == id_anio_escolar,
            models.CargaAcademica.id_seccion == id_seccion,
        )
        .all()
    )
    mapa_cargas = {c.id_curso: c for c in cargas_existentes}

    # Consolidar catálogo de cursos a considerar
    cursos_dict = {c.id_curso: c for c in cursos_plan}
    for c in cargas_existentes:
        if c.curso and c.id_curso not in cursos_dict:
            cursos_dict[c.id_curso] = c.curso

    for id_curso, curso in cursos_dict.items():
        if es_curso_excluido_tutor(curso.nombre):
            continue

        if id_curso in mapa_cargas:
            mapa_cargas[id_curso].id_docente = id_docente
        else:
            db.add(models.CargaAcademica(
                id_anio_escolar=id_anio_escolar,
                id_seccion=id_seccion,
                id_curso=id_curso,
                id_docente=id_docente,
            ))
    db.flush()


@router.get("/tutores/{anio_id}", response_model=List[schemas.TutorResponse])
def listar_tutores(anio_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    tutores = db.query(models.TutorSeccion).filter(models.TutorSeccion.id_anio_escolar == anio_id).all()
    resultado = []
    for t in tutores:
        resultado.append({
            "id_tutor_seccion": t.id_tutor_seccion,
            "id_seccion": t.id_seccion,
            "seccion_nombre": t.seccion.nombre if t.seccion else "—",
            "grado_nombre": t.seccion.grado.nombre if t.seccion and t.seccion.grado else "—",
            "docente": t.docente
        })
    return resultado

@router.post("/tutores/", response_model=schemas.TutorResponse)
def asignar_tutor(data: schemas.TutorSeccionCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    
    if current_user.get("rol") != "ADMIN" :
        raise HTTPException(status_code=403, detail="No puedes modificar esta información.")
    
    # Si ya existe asignación de tutor para esta sección y año, se actualiza el docente
    tutor_existente = db.query(models.TutorSeccion).filter(
        models.TutorSeccion.id_anio_escolar == data.id_anio_escolar,
        models.TutorSeccion.id_seccion == data.id_seccion,
    ).first()
    
    if tutor_existente:
        tutor_existente.id_docente = data.id_docente
        tutor_obj = tutor_existente
    else:
        tutor_obj = models.TutorSeccion(**data.model_dump())
        db.add(tutor_obj)
        db.flush()
    
    # Sincronizar automáticamente todos los cursos del aula excepto Violín, Inglés, Computación y Ajedrez
    sincronizar_cursos_tutor(db, data.id_anio_escolar, data.id_seccion, data.id_docente)
    db.commit()
    db.refresh(tutor_obj)
    
    return {
        "id_tutor_seccion": tutor_obj.id_tutor_seccion,
        "id_seccion": tutor_obj.id_seccion,
        "seccion_nombre": tutor_obj.seccion.nombre if tutor_obj.seccion else "—",
        "grado_nombre": tutor_obj.seccion.grado.nombre if tutor_obj.seccion and tutor_obj.seccion.grado else "—",
        "docente": tutor_obj.docente
    }

@router.put("/tutores/{id_tutor_seccion}", response_model=schemas.TutorResponse)
def actualizar_tutor(
    id_tutor_seccion: int,
    data: schemas.TutorSeccionCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información.")

    tutor = db.query(models.TutorSeccion).filter(models.TutorSeccion.id_tutor_seccion == id_tutor_seccion).first()
    if not tutor:
        raise HTTPException(status_code=404, detail="Asignación de tutor no encontrada")

    tutor.id_docente = data.id_docente
    if data.id_seccion:
        tutor.id_seccion = data.id_seccion
    if data.id_anio_escolar:
        tutor.id_anio_escolar = data.id_anio_escolar

    db.flush()

    # Reasignar automáticamente los cursos no excluidos al nuevo tutor
    sincronizar_cursos_tutor(db, tutor.id_anio_escolar, tutor.id_seccion, tutor.id_docente)
    db.commit()
    db.refresh(tutor)

    return {
        "id_tutor_seccion": tutor.id_tutor_seccion,
        "id_seccion": tutor.id_seccion,
        "seccion_nombre": tutor.seccion.nombre if tutor.seccion else "—",
        "grado_nombre": tutor.seccion.grado.nombre if tutor.seccion and tutor.seccion.grado else "—",
        "docente": tutor.docente
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


@router.get("/dashboard-admin")
def dashboard_admin(
    anio: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Resumen operativo del colegio para el panel del administrador.

    Reúne en UNA sola petición lo que está repartido por los demás paneles
    (finanzas, asistencia del auxiliar, conducta y citas del psicólogo), para
    que el administrador vea de un vistazo qué necesita atención hoy.
    """
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No autorizado")

    hoy = date.today()
    # Matrículas del año consultado: base de casi todo lo demás
    matriculas = (
        db.query(models_en.Matricula)
        .filter(models_en.Matricula.id_anio_escolar == anio)
        .all()
    )
    ids_matricula = [m.id_matricula for m in matriculas]
    ids_alumno = list({m.id_alumno for m in matriculas})

    # El dashboard no devuelve nada económico (recaudación, deuda, morosos).
    # Esa información es sensible y se consulta en Trámites y Finanzas, donde
    # el acceso se controla por permiso. Aquí ni siquiera se calcula, para que
    # no viaje al navegador de quien abre el panel.

    # ── ASISTENCIA DE HOY ───────────────────────────────────────────────────
    conteo_hoy = {"P": 0, "T": 0, "F": 0, "J": 0}
    secciones_registradas = 0
    secciones_con_lista: set = set()
    if ids_matricula:
        filas_hoy = (
            db.query(models.Asistencia.estado, func.count(models.Asistencia.id_asistencia))
            .filter(
                models.Asistencia.fecha == hoy,
                models.Asistencia.id_matricula.in_(ids_matricula),
            )
            .group_by(models.Asistencia.estado)
            .all()
        )
        for estado, n in filas_hoy:
            if estado in conteo_hoy:
                conteo_hoy[estado] = n

        # Qué secciones ya pasaron lista hoy. Antes solo se contaban; ahora se
        # guardan sus ids porque el panel marca aula por aula con un punto
        # verde o rojo, y con un número suelto no se sabe cuál falta.
        filas_sec = (
            db.query(func.distinct(models_en.Matricula.id_seccion))
            .join(models.Asistencia, models.Asistencia.id_matricula == models_en.Matricula.id_matricula)
            .filter(
                models.Asistencia.fecha == hoy,
                models_en.Matricula.id_anio_escolar == anio,
            )
            .all()
        )
        secciones_con_lista = {f[0] for f in filas_sec if f[0] is not None}
        secciones_registradas = len(secciones_con_lista)

    secciones_total = (
        db.query(func.count(models_ac.Seccion.id_seccion))
        .filter(models_ac.Seccion.id_anio_escolar == anio)
        .scalar() or 0
    )

    # ── CONDUCTA ────────────────────────────────────────────────────────────
    # Se replica el criterio de behavior/constants: cada reporte descuenta
    # puntos y por debajo del umbral el alumno entra en observación.
    #
    # El puntaje se reinicia cada bimestre (es la nota de conducta de la
    # libreta, sobre 20), así que solo cuentan los reportes del bimestre en
    # curso. El cambio de I.E., en cambio, se arrastra todo el año.
    from app.modules.behavior.constants import calcular_puntaje, UMBRAL_OBSERVACION, UMBRAL_CRITICO
    from app.modules.behavior import bimestres as bimestres_util

    en_observacion = en_critico = 0
    if ids_alumno:
        reportes = (
            db.query(models_psi.ReporteConducta)
            .options(joinedload(models_psi.ReporteConducta.nivel))
            .filter(
                models_psi.ReporteConducta.id_alumno.in_(ids_alumno),
                extract("year", models_psi.ReporteConducta.fecha_reporte) == hoy.year,
            )
            .all()
        )
        tramos = bimestres_util.calendario(db, str(anio))
        actual = bimestres_util.bimestre_de(hoy, tramos) if tramos else None
        perdidos, cambio_ie = {}, set()
        for r in reportes:
            if not r.nivel:
                continue
            del_bimestre = (
                actual is None
                or bimestres_util.bimestre_de(r.fecha_reporte, tramos) == actual
            )
            if del_bimestre:
                perdidos[r.id_alumno] = perdidos.get(r.id_alumno, 0) + r.nivel.puntos
            if r.nivel.cambio_ie:
                cambio_ie.add(r.id_alumno)
        # Se recorre la unión de los dos conjuntos: un alumno con una falta de
        # cambio de I.E. en un bimestre anterior no tiene puntos descontados en
        # el actual, y si solo se mirase `perdidos` se quedaría fuera del conteo.
        for id_al in set(perdidos) | cambio_ie:
            puntaje = calcular_puntaje(perdidos.get(id_al, 0))
            if puntaje < UMBRAL_CRITICO or id_al in cambio_ie:
                en_critico += 1
            elif puntaje < UMBRAL_OBSERVACION:
                en_observacion += 1

    reportes_semana = (
        db.query(func.count(models_psi.ReporteConducta.id_reporte))
        .filter(models_psi.ReporteConducta.fecha_reporte >= hoy - timedelta(days=7))
        .scalar() or 0
    )

    # ── PSICOLOGÍA ──────────────────────────────────────────────────────────
    citas_hoy = (
        db.query(func.count(models_psi.CitaPsicologia.id_cita))
        .filter(
            func.date(models_psi.CitaPsicologia.fecha_cita) == hoy,
            models_psi.CitaPsicologia.estado == "PROGRAMADA",
        )
        .scalar() or 0
    )
    citas_semana = (
        db.query(func.count(models_psi.CitaPsicologia.id_cita))
        .filter(
            models_psi.CitaPsicologia.fecha_cita >= hoy,
            models_psi.CitaPsicologia.fecha_cita <= hoy + timedelta(days=7),
            models_psi.CitaPsicologia.estado == "PROGRAMADA",
        )
        .scalar() or 0
    )

    # ── TRÁMITES ────────────────────────────────────────────────────────────
    tramites_pendientes = (
        db.query(func.count(models_fi.SolicitudTramite.id_solicitud_tramite))
        .filter(models_fi.SolicitudTramite.estado.in_(["PENDIENTE_REVISION", "EN_REVISION"]))
        .scalar() or 0
    )

    # ── OCUPACIÓN DE AULAS ──────────────────────────────────────────────────
    ocupacion = []
    filas_oc = (
        db.query(
            models_ac.Seccion.id_seccion,
            models_ac.Nivel.nombre,
            models_ac.Grado.nombre,
            models_ac.Seccion.nombre,
            models_ac.Seccion.vacantes,
            models_ac.Grado.orden,
            models_ac.Nivel.id_nivel,
        )
        .join(models_ac.Grado, models_ac.Grado.id_grado == models_ac.Seccion.id_grado)
        .join(models_ac.Nivel, models_ac.Nivel.id_nivel == models_ac.Grado.id_nivel)
        .filter(models_ac.Seccion.id_anio_escolar == anio)
        .order_by(models_ac.Nivel.id_nivel, models_ac.Grado.orden, models_ac.Seccion.nombre)
        .all()
    )
    por_seccion = {}
    for m in matriculas:
        por_seccion[m.id_seccion] = por_seccion.get(m.id_seccion, 0) + 1
    for id_sec, niv, gr, sec, vac, _orden, _idn in filas_oc:
        ocupacion.append({
            "id_seccion": id_sec,
            "nivel": niv,
            "grado": gr,
            "seccion": sec,
            "matriculados": por_seccion.get(id_sec, 0),
            "vacantes": vac or 0,
            # Si hoy se registró asistencia en esta aula. El panel lo pinta
            # como un punto verde o rojo junto al nombre de la sección.
            "paso_lista": id_sec in secciones_con_lista,
        })

    return {
        "asistencia_hoy": {
            "presentes": conteo_hoy["P"],
            "tardanzas": conteo_hoy["T"],
            "faltas": conteo_hoy["F"],
            "justificados": conteo_hoy["J"],
            "secciones_registradas": secciones_registradas,
            "secciones_total": secciones_total,
        },
        "conducta": {
            "en_observacion": en_observacion,
            "en_critico": en_critico,
            "reportes_semana": reportes_semana,
        },
        "psicologia": {"citas_hoy": citas_hoy, "citas_semana": citas_semana},
        "tramites": {"pendientes": tramites_pendientes},
        "ocupacion": ocupacion,
        "totales": {
            "alumnos": len(ids_alumno),
            "secciones": secciones_total,
            "docentes": db.query(func.count(models_doc.Docente.id_docente)).scalar() or 0,
        },
    }


@router.get("/mi-asistencia/{id_usuario}")
def obtener_asistencia_estudiante(
    id_usuario: int,
    anio: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Historial de asistencia del alumno en un año escolar, con su resumen.

    Solo el propio alumno puede consultarlo (mismo criterio que resumen-notas).
    """
    if current_user.get("id") != id_usuario:
        raise HTTPException(status_code=403, detail="No puedes acceder a esta información.")

    alumno = db.query(models_al.Alumno).filter(models_al.Alumno.id_usuario == id_usuario).first()
    if not alumno:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    matricula = db.query(models_en.Matricula).filter(
        models_en.Matricula.id_alumno == alumno.id_alumno,
        models_en.Matricula.id_anio_escolar == anio,
    ).first()

    # Sin matrícula en ese año no hay historial: se devuelve vacío, no un error
    if not matricula:
        return {"resumen": {"P": 0, "T": 0, "F": 0, "J": 0, "total": 0, "porcentaje": None}, "registros": []}

    registros = (
        db.query(models.Asistencia)
        .filter(models.Asistencia.id_matricula == matricula.id_matricula)
        .order_by(models.Asistencia.fecha.desc())
        .all()
    )

    conteo = {"P": 0, "T": 0, "F": 0, "J": 0}
    for r in registros:
        if r.estado in conteo:
            conteo[r.estado] += 1

    total = sum(conteo.values())
    # Asistencia efectiva: presentes y tardanzas cuentan como asistió;
    # las faltas justificadas no penalizan el porcentaje.
    computables = total - conteo["J"]
    porcentaje = round((conteo["P"] + conteo["T"]) / computables * 100, 1) if computables else None

    return {
        "resumen": {**conteo, "total": total, "porcentaje": porcentaje},
        "registros": [
            {
                "id_asistencia": r.id_asistencia,
                "fecha": r.fecha.isoformat() if r.fecha else None,
                "estado": r.estado,
                "observacion": r.observacion or "",
            }
            for r in registros
        ],
    }