from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, and_
from typing import List, Optional
from datetime import date
from decimal import Decimal
from app.db.database import get_db
from . import models, schemas
from app.core.util.security import get_current_user

# Importamos modelos de alumno para asegurar relaciones si es necesario
from app.modules.users.alumno import models as alumno_models
from app.modules.users import models as users_models
from app.modules.academic import models as academic_models
from app.modules.finance import models as finance_models

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
    query = db.query(models.Matricula).join(models.Matricula.alumno).options(
        joinedload(models.Matricula.alumno), # Cargar datos del alumno
        joinedload(models.Matricula.grado),
        joinedload(models.Matricula.seccion)
    ).filter(alumno_models.Alumno.estado_ingreso != "RETIRADO")

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

    # --- Situación académica del año de origen (repite / requiere nivelación) ---
    from app.modules.verano import service as verano_service
    evaluacion = verano_service.ultima_evaluacion(db, alumno.id_alumno, anio_activo.id_anio_escolar)
    condicion_academica = evaluacion.resultado if evaluacion else None
    repite = bool(evaluacion and evaluacion.resultado == "REPITE")

    # Validar si el alumno requiere reincorporación asistida
    # (por estar en RETIRADO o por tener una brecha de años sin matrícula en el año activo)
    ultima_mat_regular = db.query(models.Matricula).options(
        joinedload(models.Matricula.grado)
    ).filter(
        models.Matricula.id_alumno == alumno.id_alumno,
        models.Matricula.tipo_matricula == "REGULAR"
    ).order_by(models.Matricula.id_matricula.desc()).first()

    requiere_reincorporacion = False
    motivo_reincorporacion = None

    if alumno.estado_ingreso == "RETIRADO":
        requiere_reincorporacion = True
        motivo_reincorporacion = (
            "Tu cuenta se encuentra en condición de RETIRADO. Para ingresar al nuevo año lectivo, "
            "debes realizar tu proceso de Reincorporación directamente con la Administración del colegio."
        )
    elif not matricula:
        requiere_reincorporacion = True
        anio_ult = ultima_mat_regular.id_anio_escolar if ultima_mat_regular else "años anteriores"
        motivo_reincorporacion = (
            f"Tu última matrícula regular registrada corresponde al año {anio_ult}. "
            "Al haber una interrupción en tus periodos lectivos o no contar con matrícula en el año activo, "
            "tu grado de ingreso debe ser verificado por la Administración con tu Certificado Oficial de Estudios. "
            "Por favor acércate a Secretaría / Dirección para tu Reincorporación."
        )

    grado_destino = None
    egresa = False
    if matricula and matricula.grado and not requiere_reincorporacion:
        if repite:
            # Repite el año: se queda en el mismo grado
            grado_destino = matricula.grado.nombre
        else:
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

    # --- VENTANA DE INSCRIPCIÓN DEL AÑO DESTINO ---
    hoy = date.today()
    anio_destino_obj = db.query(academic_models.AnioEscolar).filter(
        academic_models.AnioEscolar.id_anio_escolar == anio_destino
    ).first()

    inscripcion_estado = "NO_CONFIGURADO"  # NO_CONFIGURADO / PROXIMAMENTE / ABIERTA / CERRADA
    inscripciones_abiertas = False
    fecha_inicio_insc = None
    fecha_fin_insc = None

    if anio_destino_obj and anio_destino_obj.inicio_inscripcion and anio_destino_obj.fin_inscripcion:
        fecha_inicio_insc = anio_destino_obj.inicio_inscripcion
        fecha_fin_insc = anio_destino_obj.fin_inscripcion
        if hoy < fecha_inicio_insc:
            inscripcion_estado = "PROXIMAMENTE"
        elif hoy > fecha_fin_insc:
            inscripcion_estado = "CERRADA"
        else:
            inscripcion_estado = "ABIERTA"
            inscripciones_abiertas = True

    # --- ESTAR AL DÍA EN LOS PAGOS ---
    pagos_vencidos = db.query(finance_models.Pago).filter(
        finance_models.Pago.id_alumno == alumno.id_alumno,
        or_(
            finance_models.Pago.estado == "VENCIDO",
            and_(
                finance_models.Pago.estado == "PENDIENTE",
                finance_models.Pago.fecha_vencimiento != None,  # noqa: E711
                finance_models.Pago.fecha_vencimiento < hoy,
            ),
        ),
    ).order_by(finance_models.Pago.fecha_vencimiento.asc()).all()

    deuda_vencida = sum((p.monto_total or Decimal("0")) for p in pagos_vencidos)
    al_dia = len(pagos_vencidos) == 0

    detalle_deuda = [
        {
            "id_pago": p.id_pago,
            "concepto": p.concepto,
            "monto": float(p.monto_total or 0),
            "fecha_vencimiento": p.fecha_vencimiento.isoformat() if p.fecha_vencimiento else None,
        }
        for p in pagos_vencidos
    ]

    return {
        "alumno": alumno,
        "anio_activo": anio_activo,
        "matricula": matricula,
        "anio_destino": anio_destino,
        "grado_destino": grado_destino,
        "egresa": egresa,
        "repite": repite,
        "condicion_academica": condicion_academica,
        "ya_matriculado_destino": ya_matriculado_destino,
        "solicitudes": solicitudes,
        "solicitud_en_curso": solicitud_en_curso,
        "inscripcion_estado": inscripcion_estado,
        "inscripciones_abiertas": inscripciones_abiertas,
        "inscripcion_inicio": fecha_inicio_insc.isoformat() if fecha_inicio_insc else None,
        "inscripcion_fin": fecha_fin_insc.isoformat() if fecha_fin_insc else None,
        "al_dia": al_dia,
        "deuda_vencida": float(deuda_vencida),
        "pagos_vencidos": detalle_deuda,
        "requiere_reincorporacion": requiere_reincorporacion,
        "motivo_reincorporacion": motivo_reincorporacion,
        "puede_solicitar": (
            bool(matricula) and not egresa and not ya_matriculado_destino
            and not solicitud_en_curso and inscripciones_abiertas
            and al_dia and not requiere_reincorporacion
        )
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
        "repite": info["repite"],
        "condicion_academica": info["condicion_academica"],
        "ya_matriculado_destino": info["ya_matriculado_destino"],
        "puede_solicitar": info["puede_solicitar"],
        "requiere_reincorporacion": info["requiere_reincorporacion"],
        "motivo_reincorporacion": info["motivo_reincorporacion"],
        "inscripcion_estado": info["inscripcion_estado"],
        "inscripciones_abiertas": info["inscripciones_abiertas"],
        "inscripcion_inicio": info["inscripcion_inicio"],
        "inscripcion_fin": info["inscripcion_fin"],
        # Estado de cuenta: la renovación exige no tener cargos vencidos
        "al_dia": info["al_dia"],
        "deuda_vencida": info["deuda_vencida"],
        "pagos_vencidos": info["pagos_vencidos"],
        "solicitudes": [
            schemas.SolicitudMatriculaResponse.model_validate(s) for s in info["solicitudes"]
        ]
    }


@router.post("/renovacion/", response_model=schemas.SolicitudMatriculaResponse, status_code=status.HTTP_201_CREATED)
def solicitar_renovacion(data: schemas.SolicitudMatriculaCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ALUMNO" or current_user.get("id") != data.id_usuario:
        raise HTTPException(status_code=403, detail="Solo el propio alumno puede solicitar su renovación")

    info = _info_renovacion(db, data.id_usuario)

    if info.get("requiere_reincorporacion"):
        raise HTTPException(
            status_code=400,
            detail=info.get("motivo_reincorporacion") or "Tu situación académica requiere un proceso de reincorporación asistido por Administración."
        )

    if not info["matricula"]:
        raise HTTPException(status_code=400, detail="No tienes una matrícula activa este año, no es posible renovar")
    if info["egresa"]:
        raise HTTPException(status_code=400, detail="Estás culminando el último grado, no aplica renovación de matrícula")
    if info["ya_matriculado_destino"]:
        raise HTTPException(status_code=400, detail=f"Ya tienes matrícula registrada para el año {info['anio_destino']}")
    if info["solicitud_en_curso"]:
        raise HTTPException(status_code=400, detail="Ya tienes una solicitud de renovación en curso para el próximo año")
    if not info["inscripciones_abiertas"]:
        if info["inscripcion_estado"] == "PROXIMAMENTE":
            raise HTTPException(status_code=400, detail="Las inscripciones para el próximo año aún no están abiertas")
        elif info["inscripcion_estado"] == "CERRADA":
            raise HTTPException(status_code=400, detail="El periodo de inscripciones para el próximo año ya cerró")
        else:
            raise HTTPException(status_code=400, detail="Las inscripciones del próximo año aún no han sido habilitadas por el colegio")
    if not info["al_dia"]:
        cantidad = len(info["pagos_vencidos"])
        raise HTTPException(
            status_code=400,
            detail=(
                f"Tienes {cantidad} pago(s) vencido(s) por S/ {info['deuda_vencida']:.2f}. "
                "Debes regularizar tu deuda antes de renovar la matrícula."
            ),
        )
    if not info["puede_solicitar"]:
        raise HTTPException(status_code=400, detail="No es posible registrar tu solicitud de renovación en este momento")

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


# --- GESTIÓN DE RENOVACIONES (ADMIN) ---

@router.get("/renovacion-solicitudes/")
def listar_solicitudes_renovacion(
    estado: Optional[str] = None,
    anio_destino: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Lista todas las solicitudes de renovación de matrícula para el panel de administración."""
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No tienes permisos para ver esta información")

    query = db.query(models.SolicitudMatricula).options(
        joinedload(models.SolicitudMatricula.alumno)
    )
    if estado:
        query = query.filter(models.SolicitudMatricula.estado == estado)
    if anio_destino:
        query = query.filter(models.SolicitudMatricula.anio_destino == anio_destino)

    solicitudes = query.order_by(models.SolicitudMatricula.fecha_solicitud.desc()).all()

    resultado = []
    for s in solicitudes:
        alumno = s.alumno
        # Grado y sección actuales (del año de origen)
        grado_actual = None
        if s.id_anio_escolar_origen and alumno:
            mat_origen = db.query(models.Matricula).options(
                joinedload(models.Matricula.grado)
            ).filter(
                models.Matricula.id_alumno == alumno.id_alumno,
                models.Matricula.id_anio_escolar == s.id_anio_escolar_origen
            ).first()
            if mat_origen and mat_origen.grado:
                grado_actual = mat_origen.grado.nombre

        resultado.append({
            "id_solicitud_matricula": s.id_solicitud_matricula,
            "id_alumno": s.id_alumno,
            "alumno_nombre": f"{alumno.nombres} {alumno.apellidos}" if alumno else "—",
            "alumno_dni": alumno.dni if alumno else None,
            "anio_origen": s.id_anio_escolar_origen,
            "anio_destino": s.anio_destino,
            "grado_actual": grado_actual,
            "grado_destino": s.grado_destino,
            "comentario": s.comentario,
            "estado": s.estado,
            "respuesta_admin": s.respuesta_admin,
            "fecha_solicitud": s.fecha_solicitud.isoformat() if s.fecha_solicitud else None
        })
    return resultado


@router.patch("/renovacion-solicitudes/{id_solicitud}/decidir")
def decidir_solicitud_renovacion(
    id_solicitud: int,
    decision: schemas.DecisionRenovacion,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """El administrador aprueba o rechaza una solicitud de renovación.
    Al aprobar, se crea automáticamente la matrícula del año destino (sin sección,
    para que luego se asigne en 'Asignar Estudiante')."""
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No tienes permisos para esta acción")

    solicitud = db.query(models.SolicitudMatricula).filter(
        models.SolicitudMatricula.id_solicitud_matricula == id_solicitud
    ).first()
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    if solicitud.estado != "PENDIENTE":
        raise HTTPException(status_code=400, detail=f"La solicitud ya fue {solicitud.estado.lower()}")

    if not decision.aprobado:
        solicitud.estado = "RECHAZADA"
        solicitud.respuesta_admin = decision.respuesta_admin or "Solicitud rechazada por la administración."
        db.commit()
        db.refresh(solicitud)
        return {"mensaje": "Solicitud rechazada", "estado": solicitud.estado}

    # --- APROBAR: crear matrícula en el año destino ---
    # 1. Verificar que el año destino exista (debe existir si se abrió la inscripción)
    anio_destino_obj = db.query(academic_models.AnioEscolar).filter(
        academic_models.AnioEscolar.id_anio_escolar == solicitud.anio_destino
    ).first()
    if not anio_destino_obj:
        raise HTTPException(
            status_code=400,
            detail=f"El año escolar {solicitud.anio_destino} no existe. Créalo antes de aprobar la renovación."
        )

    # 2. Evitar duplicar matrícula
    ya_existe = db.query(models.Matricula).filter(
        models.Matricula.id_alumno == solicitud.id_alumno,
        models.Matricula.id_anio_escolar == solicitud.anio_destino
    ).first()

    if not ya_existe:
        # 3. Calcular el grado destino a partir de la matrícula de origen
        mat_origen = db.query(models.Matricula).options(
            joinedload(models.Matricula.grado)
        ).filter(
            models.Matricula.id_alumno == solicitud.id_alumno,
            models.Matricula.id_anio_escolar == solicitud.id_anio_escolar_origen
        ).first()

        # Situación académica: repite (mismo grado) o requiere nivelación (condicionada)
        from app.modules.verano import service as verano_service
        evaluacion = verano_service.ultima_evaluacion(db, solicitud.id_alumno, solicitud.id_anio_escolar_origen)
        repite = bool(evaluacion and evaluacion.resultado == "REPITE")

        id_grado_destino = None
        tipo_matricula = "REGULAR"
        condicion_nueva = "NORMAL"
        if mat_origen:
            tipo_matricula = mat_origen.tipo_matricula or "REGULAR"
            if mat_origen.grado:
                if repite:
                    id_grado_destino = mat_origen.grado.id_grado  # se queda en el mismo grado
                    condicion_nueva = "REPITE"
                else:
                    siguiente = _calcular_siguiente_grado(db, mat_origen.grado)
                    if siguiente:
                        id_grado_destino = siguiente.id_grado
                    # Si no se niveló (aún tiene cursos desaprobados pendientes),
                    # pasa de año con matrícula condicionada (apoyo adicional).
                    if verano_service.tiene_desaprobados_pendientes(db, solicitud.id_alumno):
                        condicion_nueva = "CONDICIONADA"

        if not id_grado_destino:
            raise HTTPException(
                status_code=400,
                detail="No se pudo determinar el grado destino del alumno."
            )

        nueva_matricula = models.Matricula(
            id_anio_escolar=solicitud.anio_destino,
            id_alumno=solicitud.id_alumno,
            id_seccion=None,  # El admin asigna la sección luego en 'Asignar Estudiante'
            id_grado=id_grado_destino,
            estado="MATRICULADO",
            tipo_matricula=tipo_matricula,
            condicion=condicion_nueva
        )
        db.add(nueva_matricula)

    solicitud.estado = "APROBADA"
    solicitud.respuesta_admin = decision.respuesta_admin or "Renovación aprobada. Tu matrícula para el próximo año fue registrada."
    db.commit()
    db.refresh(solicitud)
    return {"mensaje": "Solicitud aprobada y matrícula registrada", "estado": solicitud.estado}


# --- EXONERACIONES ---
@router.post("/exoneracion/", response_model=schemas.ExoneracionResponse)
def crear_exoneracion(exoneracion: schemas.ExoneracionCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    nueva = models.Exoneracion(**exoneracion.model_dump())
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva


# --- CONTROL Y RETIRO DE NO RENOVADOS (ADMIN) ---

@router.get("/no-renovados/")
def listar_no_renovados(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Lista todos los alumnos que estuvieron como ESTUDIANTE en el año activo
    pero que no tienen matrícula registrada para el siguiente año escolar (excluyendo egresados).
    """
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No tienes permisos para ver esta información")

    anio_activo = db.query(academic_models.AnioEscolar).filter(
        academic_models.AnioEscolar.activo == True,
        academic_models.AnioEscolar.tipo == "REGULAR"
    ).first()
    if not anio_activo:
        anio_activo = db.query(academic_models.AnioEscolar).filter(academic_models.AnioEscolar.activo == True).first()
    if not anio_activo:
        return {
            "anio_activo": None,
            "anio_destino": None,
            "inscripcion_estado": "NO_CONFIGURADO",
            "fin_inscripcion": None,
            "total_no_renovados": 0,
            "alumnos": []
        }

    try:
        anio_destino = str(int(str(anio_activo.id_anio_escolar)[:4]) + 1)
        anio_anterior = str(int(str(anio_activo.id_anio_escolar)[:4]) - 1)
    except ValueError:
        anio_destino = None
        anio_anterior = None

    anio_destino_obj = None
    inscripcion_estado = "NO_CONFIGURADO"
    fin_inscripcion = None
    if anio_destino:
        anio_destino_obj = db.query(academic_models.AnioEscolar).filter(
            academic_models.AnioEscolar.id_anio_escolar == anio_destino
        ).first()

    hoy = date.today()
    if anio_destino_obj and anio_destino_obj.inicio_inscripcion and anio_destino_obj.fin_inscripcion:
        fin_inscripcion = anio_destino_obj.fin_inscripcion.isoformat()
        if hoy < anio_destino_obj.inicio_inscripcion:
            inscripcion_estado = "PROXIMAMENTE"
        elif hoy > anio_destino_obj.fin_inscripcion:
            inscripcion_estado = "CERRADA"
        else:
            inscripcion_estado = "ABIERTA"

    # Evaluamos si el periodo de inscripciones del próximo año ya cerró:
    if inscripcion_estado == "CERRADA":
        # CASO 1: El periodo de inscripciones para el próximo año (ej: 2027) YA CERRÓ formalmente.
        # Identificamos qué alumnos del año activo no renovaron.
        anio_origen_eval = anio_activo.id_anio_escolar
        anio_destino_eval = anio_destino
        mensaje = f"Periodo de renovación para {anio_destino} cerrado el {fin_inscripcion}. Los siguientes estudiantes no registraron matrícula."
    elif anio_anterior and db.query(models.Matricula).filter(models.Matricula.id_anio_escolar == anio_anterior).first():
        # CASO 2: Revisar rezagados del año anterior (ej: 2025) que nunca se matricularon en el año activo actual (2026).
        anio_origen_eval = anio_anterior
        anio_destino_eval = anio_activo.id_anio_escolar
        mensaje = f"Alumnos matriculados en {anio_anterior} que no registraron matrícula para el año activo {anio_activo.id_anio_escolar}."
    else:
        # CASO 3: Las inscripciones para el próximo año aún no existen o están abiertas/por abrir.
        # Los estudiantes activos del año en curso no deben marcarse como no renovados para no retirarlos prematuramente.
        return {
            "anio_activo": anio_activo.id_anio_escolar,
            "anio_destino": anio_destino,
            "inscripcion_estado": inscripcion_estado,
            "fin_inscripcion": fin_inscripcion,
            "total_no_renovados": 0,
            "mensaje": (
                f"El periodo de inscripciones para {anio_destino or 'el próximo año'} se encuentra '{inscripcion_estado}'. "
                "Los estudiantes activos continúan cursando sus clases normalmente hasta que venza el plazo de renovación."
            ),
            "alumnos": []
        }

    # 1. Obtener todas las matrículas del año origen de alumnos que siguen como ESTUDIANTE
    matriculas_origen = (
        db.query(models.Matricula)
        .options(
            joinedload(models.Matricula.alumno).joinedload(alumno_models.Alumno.usuario),
            joinedload(models.Matricula.grado),
            joinedload(models.Matricula.seccion),
        )
        .join(alumno_models.Alumno, alumno_models.Alumno.id_alumno == models.Matricula.id_alumno)
        .filter(
            models.Matricula.id_anio_escolar == anio_origen_eval,
            alumno_models.Alumno.estado_ingreso == "ESTUDIANTE"
        )
        .all()
    )

    # 2. Ids de alumnos que ya tienen matrícula en el año destino
    ids_matriculados_destino = set()
    if anio_destino_eval:
        ids_matriculados_destino = {
            m.id_alumno for m in db.query(models.Matricula.id_alumno)
            .filter(models.Matricula.id_anio_escolar == anio_destino_eval)
            .all()
        }

    alumnos_no_renovados = []
    for m in matriculas_origen:
        alumno = m.alumno
        if not alumno or alumno.id_alumno in ids_matriculados_destino:
            continue

        # Verificar si egresa (si terminó el último grado de secundaria)
        if m.grado:
            siguiente_grado = _calcular_siguiente_grado(db, m.grado)
            if siguiente_grado is None:
                # Egresó del colegio (terminó 5to secundaria) -> no cuenta como no renovado
                continue

        grado_nombre = m.grado.nombre if m.grado else "—"
        seccion_nombre = m.seccion.nombre if m.seccion else "—"

        alumnos_no_renovados.append({
            "id_alumno": alumno.id_alumno,
            "id_matricula": m.id_matricula,
            "dni": alumno.dni or "—",
            "nombres": alumno.nombres or "",
            "apellidos": alumno.apellidos or "",
            "nombre_completo": f"{alumno.apellidos or ''}, {alumno.nombres or ''}".strip(),
            "grado_actual": grado_nombre,
            "seccion_actual": seccion_nombre,
            "anio_origen": anio_origen_eval,
            "anio_destino": anio_destino_eval,
            "tiene_usuario": alumno.id_usuario is not None,
        })

    # Ordenar alfabéticamente por apellidos
    alumnos_no_renovados.sort(key=lambda a: a["nombre_completo"])

    return {
        "anio_activo": anio_activo.id_anio_escolar,
        "anio_destino": anio_destino_eval,
        "anio_origen": anio_origen_eval,
        "inscripcion_estado": inscripcion_estado,
        "fin_inscripcion": fin_inscripcion,
        "total_no_renovados": len(alumnos_no_renovados),
        "mensaje": mensaje,
        "alumnos": alumnos_no_renovados
    }


@router.post("/procesar-no-renovados/")
def procesar_retiro_no_renovados(
    payload: Optional[dict] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Procesa el retiro de los alumnos no renovados:
    - Marca su estado_ingreso como 'RETIRADO'
    - Desactiva su cuenta de usuario
    - Elimina pagos pendientes no vencidos
    """
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No tienes permisos para esta operación")

    ids_alumnos_solicitados = (payload or {}).get("ids_alumnos")

    # Obtener el listado de no renovados
    data_no_renovados = listar_no_renovados(db=db, current_user=current_user)
    lista_candidatos = data_no_renovados.get("alumnos", [])

    if ids_alumnos_solicitados:
        ids_set = set(ids_alumnos_solicitados)
        candidatos_a_procesar = [a for a in lista_candidatos if a["id_alumno"] in ids_set]
    else:
        candidatos_a_procesar = lista_candidatos

    if not candidatos_a_procesar:
        return {
            "message": "No hay alumnos pendientes por procesar",
            "procesados": 0
        }

    ids_a_retirar = [a["id_alumno"] for a in candidatos_a_procesar]
    hoy = date.today()

    alumnos_db = db.query(alumno_models.Alumno).filter(alumno_models.Alumno.id_alumno.in_(ids_a_retirar)).all()
    
    # 1. Eliminar pagos pendientes no vencidos de estos alumnos
    db.query(finance_models.Pago).filter(
        finance_models.Pago.id_alumno.in_(ids_a_retirar),
        finance_models.Pago.estado == "PENDIENTE",
        or_(
            finance_models.Pago.fecha_vencimiento >= hoy,
            finance_models.Pago.fecha_vencimiento.is_(None)
        )
    ).delete(synchronize_session=False)

    # 2. Desactivar usuarios y cambiar estado a RETIRADO
    for al in alumnos_db:
        al.estado_ingreso = "RETIRADO"
        if al.id_usuario:
            usuario = db.query(users_models.Usuario).filter(users_models.Usuario.id_usuario == al.id_usuario).first()
            if usuario:
                usuario.activo = False

    db.commit()

    return {
        "message": f"Se procesó el retiro de {len(alumnos_db)} estudiante(s) no renovados exitosamente.",
        "procesados": len(alumnos_db),
        "ids_procesados": ids_a_retirar
    }