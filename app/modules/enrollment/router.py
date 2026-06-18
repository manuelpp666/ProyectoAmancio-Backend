from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from app.db.database import get_db
from . import models, schemas
from app.core.util.security import get_current_user

# Importamos modelos de alumno para asegurar relaciones si es necesario
from app.modules.users.alumno import models as alumno_models
from app.modules.academic import models as academic_models

# CAMBIO CLAVE: Prefijo "/enrollment" para coincidir con el frontend
router = APIRouter(prefix="/enrollment", tags=["Matrícula"])

# --- CREAR MATRÍCULA ---
@router.post("/matriculas/", response_model=schemas.MatriculaResponse, status_code=status.HTTP_201_CREATED)
def crear_matricula(matricula: schemas.MatriculaCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
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
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
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
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
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

# --- RENOVACIÓN DE MATRÍCULA (ALUMNO) ---

def _calcular_siguiente_grado(db: Session, grado_actual: academic_models.Grado):
    """Calcula el grado al que pasaría el alumno el próximo año (o None si egresa)."""
    # 1. Siguiente grado dentro del mismo nivel
    siguiente = db.query(academic_models.Grado).filter(
        academic_models.Grado.id_nivel == grado_actual.id_nivel,
        academic_models.Grado.orden == grado_actual.orden + 1
    ).first()
    if siguiente:
        return siguiente

    # 2. Si terminó Primaria, pasa al primer grado de Secundaria
    nivel_actual = db.query(academic_models.Nivel).filter(
        academic_models.Nivel.id_nivel == grado_actual.id_nivel
    ).first()
    if nivel_actual and "primaria" in nivel_actual.nombre.lower():
        nivel_secundaria = db.query(academic_models.Nivel).filter(
            academic_models.Nivel.nombre.ilike("%secundaria%")
        ).first()
        if nivel_secundaria:
            return db.query(academic_models.Grado).filter(
                academic_models.Grado.id_nivel == nivel_secundaria.id_nivel,
                academic_models.Grado.orden == 1
            ).first()

    # 3. Terminó Secundaria: egresa
    return None


def _info_renovacion(db: Session, id_usuario: int):
    """Arma toda la información de renovación para un alumno."""
    alumno = db.query(alumno_models.Alumno).filter(alumno_models.Alumno.id_usuario == id_usuario).first()
    if not alumno:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    anio_activo = db.query(academic_models.AnioEscolar).filter(
        academic_models.AnioEscolar.activo == True,
        academic_models.AnioEscolar.tipo == "REGULAR"
    ).first()
    if not anio_activo:
        anio_activo = db.query(academic_models.AnioEscolar).filter(academic_models.AnioEscolar.activo == True).first()
    if not anio_activo:
        raise HTTPException(status_code=400, detail="No hay un año escolar activo")

    matricula = db.query(models.Matricula).options(
        joinedload(models.Matricula.grado), joinedload(models.Matricula.seccion)
    ).filter(
        models.Matricula.id_alumno == alumno.id_alumno,
        models.Matricula.id_anio_escolar == anio_activo.id_anio_escolar
    ).first()

    # El año destino es el siguiente año calendario al activo (ej: 2026 -> 2027)
    try:
        anio_destino = str(int(str(anio_activo.id_anio_escolar)[:4]) + 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="No se pudo calcular el próximo año escolar")

    grado_destino = None
    egresa = False
    if matricula and matricula.grado:
        siguiente = _calcular_siguiente_grado(db, matricula.grado)
        if siguiente:
            grado_destino = siguiente.nombre
        else:
            egresa = True

    ya_matriculado_destino = db.query(models.Matricula).filter(
        models.Matricula.id_alumno == alumno.id_alumno,
        models.Matricula.id_anio_escolar == anio_destino
    ).first() is not None

    solicitudes = db.query(models.SolicitudMatricula).filter(
        models.SolicitudMatricula.id_alumno == alumno.id_alumno
    ).order_by(models.SolicitudMatricula.fecha_solicitud.desc()).all()

    solicitud_en_curso = any(
        s.anio_destino == anio_destino and s.estado in ["PENDIENTE", "APROBADA"]
        for s in solicitudes
    )

    return {
        "alumno": alumno,
        "anio_activo": anio_activo,
        "matricula": matricula,
        "anio_destino": anio_destino,
        "grado_destino": grado_destino,
        "egresa": egresa,
        "ya_matriculado_destino": ya_matriculado_destino,
        "solicitudes": solicitudes,
        "puede_solicitar": bool(matricula) and not egresa and not ya_matriculado_destino and not solicitud_en_curso
    }


@router.get("/renovacion/{id_usuario}")
def obtener_info_renovacion(id_usuario: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN" and current_user.get("id") != id_usuario:
        raise HTTPException(status_code=403, detail="No puedes acceder a esta información")

    info = _info_renovacion(db, id_usuario)
    alumno = info["alumno"]
    matricula = info["matricula"]

    return {
        "alumno": {
            "id_alumno": alumno.id_alumno,
            "nombres": alumno.nombres,
            "apellidos": alumno.apellidos,
            "dni": alumno.dni
        },
        "matricula_actual": {
            "id_matricula": matricula.id_matricula,
            "anio": matricula.id_anio_escolar,
            "grado": matricula.grado.nombre if matricula.grado else None,
            "seccion": matricula.seccion.nombre if matricula.seccion else "Por asignar",
            "estado": matricula.estado,
            "tipo": matricula.tipo_matricula
        } if matricula else None,
        "anio_destino": info["anio_destino"],
        "grado_destino": info["grado_destino"],
        "egresa": info["egresa"],
        "ya_matriculado_destino": info["ya_matriculado_destino"],
        "puede_solicitar": info["puede_solicitar"],
        "solicitudes": [
            schemas.SolicitudMatriculaResponse.model_validate(s) for s in info["solicitudes"]
        ]
    }


@router.post("/renovacion/", response_model=schemas.SolicitudMatriculaResponse, status_code=status.HTTP_201_CREATED)
def solicitar_renovacion(data: schemas.SolicitudMatriculaCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ALUMNO" or current_user.get("id") != data.id_usuario:
        raise HTTPException(status_code=403, detail="Solo el propio alumno puede solicitar su renovación")

    info = _info_renovacion(db, data.id_usuario)

    if not info["matricula"]:
        raise HTTPException(status_code=400, detail="No tienes una matrícula activa este año, no es posible renovar")
    if info["egresa"]:
        raise HTTPException(status_code=400, detail="Estás culminando el último grado, no aplica renovación de matrícula")
    if info["ya_matriculado_destino"]:
        raise HTTPException(status_code=400, detail=f"Ya tienes matrícula registrada para el año {info['anio_destino']}")
    if not info["puede_solicitar"]:
        raise HTTPException(status_code=400, detail="Ya tienes una solicitud de renovación en curso para el próximo año")

    nueva = models.SolicitudMatricula(
        id_alumno=info["alumno"].id_alumno,
        id_anio_escolar_origen=info["anio_activo"].id_anio_escolar,
        anio_destino=info["anio_destino"],
        grado_destino=info["grado_destino"],
        comentario=data.comentario,
        estado="PENDIENTE"
    )
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva


# --- EXONERACIONES ---
@router.post("/exoneracion/", response_model=schemas.ExoneracionResponse)
def crear_exoneracion(exoneracion: schemas.ExoneracionCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    nueva = models.Exoneracion(**exoneracion.model_dump())
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva