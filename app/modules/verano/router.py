from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import date

from app.db.database import get_db
from app.core.util.security import get_current_user
from app.core.util.email import enviar_correos

from . import models, schemas, service
from app.modules.academic import models as ac_models
from app.modules.enrollment import models as en_models
from app.modules.finance import models as fi_models
from app.modules.users.alumno.models import Alumno
from app.modules.users.familiar.models import Familiar
from app.modules.users.relacion_familiar.models import RelacionFamiliar
from app.modules.admision.router import resolver_familiar, enviar_confirmacion_postulacion

router = APIRouter(prefix="/verano", tags=["Verano"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _anio_verano_vigente(db: Session):
    """Año VERANO con inscripción abierta hoy, o el próximo con inscripción futura."""
    hoy = date.today()
    abierto = db.query(ac_models.AnioEscolar).filter(
        ac_models.AnioEscolar.tipo == "VERANO",
        ac_models.AnioEscolar.inicio_inscripcion != None,  # noqa: E711
        ac_models.AnioEscolar.fin_inscripcion != None,     # noqa: E711
        ac_models.AnioEscolar.inicio_inscripcion <= hoy,
        ac_models.AnioEscolar.fin_inscripcion >= hoy,
    ).order_by(ac_models.AnioEscolar.inicio_inscripcion.asc()).first()
    if abierto:
        return abierto, True
    proximo = db.query(ac_models.AnioEscolar).filter(
        ac_models.AnioEscolar.tipo == "VERANO",
        ac_models.AnioEscolar.inicio_inscripcion != None,  # noqa: E711
        ac_models.AnioEscolar.inicio_inscripcion > hoy,
    ).order_by(ac_models.AnioEscolar.inicio_inscripcion.asc()).first()
    return proximo, False


def _grado_actual_alumno(db: Session, id_alumno: int):
    """Grado de la matrícula REGULAR más reciente del alumno."""
    mat = db.query(en_models.Matricula).options(
        joinedload(en_models.Matricula.grado)
    ).filter(
        en_models.Matricula.id_alumno == id_alumno,
        en_models.Matricula.tipo_matricula != "VERANO",
    ).order_by(en_models.Matricula.id_matricula.desc()).first()
    return mat.grado if mat else None


# ---------------------------------------------------------------------------
# Público (formulario de admisión / web)
# ---------------------------------------------------------------------------
@router.get("/estado")
def estado_verano(db: Session = Depends(get_db)):
    """Indica si hay un año VERANO con inscripción abierta (o próxima) para el
    modo verano del formulario de admisión."""
    anio, abierto = _anio_verano_vigente(db)
    if not anio:
        return {"disponible": False}
    return {
        "disponible": True,
        "abierto": abierto,
        "id_anio_escolar": anio.id_anio_escolar,
        "inicio_inscripcion": anio.inicio_inscripcion.isoformat() if anio.inicio_inscripcion else None,
        "fin_inscripcion": anio.fin_inscripcion.isoformat() if anio.fin_inscripcion else None,
    }


@router.get("/cursos/{id_grado}")
def cursos_verano_por_grado(id_grado: int, db: Session = Depends(get_db)):
    """Cursos fijos del GRUPO/AULA de verano que corresponde al alumno + talleres.
    `id_grado` es el grado ACTUAL del alumno; el aula se calcula por el grado destino."""
    grado_actual = db.query(ac_models.Grado).filter(ac_models.Grado.id_grado == id_grado).first()
    aula, clave, etiqueta = service.grupo_de_alumno(db, grado_actual)

    fijos = []
    if clave:
        fijos = db.query(ac_models.Curso).filter(
            ac_models.Curso.es_verano == True,          # noqa: E712
            ac_models.Curso.tipo_verano == "FIJO",
            ac_models.Curso.grupo_verano == clave,
        ).all()
    talleres = db.query(ac_models.Curso).filter(
        ac_models.Curso.es_verano == True,               # noqa: E712
        ac_models.Curso.tipo_verano == "TALLER",
    ).all()
    return {
        "fijos": [{"id_curso": c.id_curso, "nombre": c.nombre} for c in fijos],
        "talleres": [{"id_curso": c.id_curso, "nombre": c.nombre} for c in talleres],
        "grupo_clave": clave,
        "grupo_label": etiqueta,
        "id_grado_aula": aula.id_grado if aula else None,
    }


@router.post("/postular-externo", status_code=status.HTTP_201_CREATED)
def postular_externo(datos: schemas.PostulanteVeranoExterno, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Inscripción a verano de un alumno EXTERNO desde el formulario de admisión."""
    anio = db.query(ac_models.AnioEscolar).filter(
        ac_models.AnioEscolar.id_anio_escolar == datos.id_anio_escolar,
        ac_models.AnioEscolar.tipo == "VERANO",
    ).first()
    if not anio:
        raise HTTPException(status_code=400, detail="El año de verano indicado no existe.")

    # Control de duplicados: un alumno no puede inscribirse dos veces
    if db.query(Alumno).filter(Alumno.dni == datos.alumno.dni).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un alumno registrado con el DNI {datos.alumno.dni}. No es posible inscribirse dos veces."
        )

    try:
        # 1. Alumno (POSTULANTE, sin usuario todavía)
        nuevo_alumno = Alumno(**datos.alumno.model_dump())
        db.add(nuevo_alumno)
        db.flush()

        # 2. Familiar (se reutiliza si ya existe por DNI) + relación
        familiar = resolver_familiar(db, datos.familiar.model_dump(), datos.alumno.direccion)
        db.add(RelacionFamiliar(
            id_alumno=nuevo_alumno.id_alumno,
            id_familiar=familiar.id_familiar,
            tipo_parentesco=(datos.tipo_parentesco or "OTRO").upper(),
        ))

        # 3. Solicitud de verano + cursos elegidos
        # El aula de verano es el grado al que pasa (destino), no el actual.
        grado_actual = db.query(ac_models.Grado).filter(
            ac_models.Grado.id_grado == datos.alumno.id_grado_ingreso
        ).first()
        aula, _clave, _lbl = service.grupo_de_alumno(db, grado_actual)
        id_grado_aula = aula.id_grado if aula else datos.alumno.id_grado_ingreso

        solicitud = models.SolicitudVerano(
            id_alumno=nuevo_alumno.id_alumno,
            id_anio_escolar=anio.id_anio_escolar,
            id_grado=id_grado_aula,
            origen="EXTERNO",
            modalidad=datos.modalidad,
            estado="PENDIENTE_PAGO",
        )
        db.add(solicitud)
        db.flush()
        _registrar_cursos_solicitud(db, solicitud.id, datos.cursos_ids, datos.talleres_ids)

        # 4. Pago fijo de verano
        pago = service.crear_pago_verano(db, nuevo_alumno, anio)
        solicitud.id_pago = pago.id_pago

        db.commit()

        # 5. Correo de confirmación al apoderado
        background_tasks.add_task(
            enviar_confirmacion_postulacion,
            datos.familiar.email,
            f"{nuevo_alumno.nombres} {nuevo_alumno.apellidos}",
            True,
        )
        return {"status": "success", "id_solicitud": solicitud.id, "id_alumno": nuevo_alumno.id_alumno}
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        mensaje = "Error interno del servidor"
        if "Duplicate entry" in str(e):
            mensaje = "El DNI ingresado ya se encuentra registrado."
        raise HTTPException(status_code=400, detail=mensaje)


def _registrar_cursos_solicitud(db: Session, id_solicitud: int, cursos_ids, talleres_ids):
    for cid in (cursos_ids or []):
        db.add(models.SolicitudVeranoCurso(id_solicitud_verano=id_solicitud, id_curso=cid, es_taller=False))
    for tid in (talleres_ids or []):
        db.add(models.SolicitudVeranoCurso(id_solicitud_verano=id_solicitud, id_curso=tid, es_taller=True))


# ---------------------------------------------------------------------------
# Interno (panel del estudiante)
# ---------------------------------------------------------------------------
@router.get("/estado-inscripcion/{id_usuario}")
def estado_inscripcion_interno(id_usuario: int, db: Session = Depends(get_db),
                               current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN" and current_user.get("id") != id_usuario:
        raise HTTPException(status_code=403, detail="No puedes acceder a esta información")

    alumno = db.query(Alumno).filter(Alumno.id_usuario == id_usuario).first()
    if not alumno:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    anio, abierto = _anio_verano_vigente(db)
    base = {
        "disponible": anio is not None,
        "abierto": abierto,
        "id_anio_escolar": anio.id_anio_escolar if anio else None,
        "inicio_inscripcion": anio.inicio_inscripcion.isoformat() if anio and anio.inicio_inscripcion else None,
        "fin_inscripcion": anio.fin_inscripcion.isoformat() if anio and anio.fin_inscripcion else None,
    }

    # ¿Ya inscrito?
    if anio:
        ya = db.query(models.SolicitudVerano).filter(
            models.SolicitudVerano.id_alumno == alumno.id_alumno,
            models.SolicitudVerano.id_anio_escolar == anio.id_anio_escolar,
        ).first()
        base["ya_inscrito"] = ya is not None
        base["estado_solicitud"] = ya.estado if ya else None
    else:
        base["ya_inscrito"] = False

    # Situación académica
    evaluacion = service.ultima_evaluacion(db, alumno.id_alumno)
    pendientes = service.cursos_desaprobados_pendientes(db, alumno.id_alumno)

    if evaluacion and evaluacion.resultado == "REPITE":
        base["condicion"] = "REPITE"
        base["elegible"] = False
        base["mensaje"] = "Repetirás el año académico por desaprobar 4 o más cursos, no aplica nivelación de verano."
    elif pendientes:
        cursos = []
        for cd in pendientes:
            curso = db.query(ac_models.Curso).filter(ac_models.Curso.id_curso == cd.id_curso).first()
            cursos.append({"id_curso": cd.id_curso, "nombre": curso.nombre if curso else f"Curso {cd.id_curso}"})
        base["condicion"] = "REQUIERE_NIVELACION"
        base["elegible"] = True
        base["cursos_nivelacion"] = cursos
    else:
        base["condicion"] = "NORMAL"
        base["elegible"] = True

    grado = _grado_actual_alumno(db, alumno.id_alumno)
    base["id_grado"] = grado.id_grado if grado else None
    base["grado_nombre"] = grado.nombre if grado else None
    # Aula/grupo de verano (según el grado al que pasa)
    aula, clave, etiqueta = service.grupo_de_alumno(db, grado)
    base["grupo_clave"] = clave
    base["grupo_label"] = etiqueta
    return base


@router.post("/inscribir-interno", status_code=status.HTTP_201_CREATED)
def inscribir_interno(datos: schemas.InscripcionVeranoInterno, background_tasks: BackgroundTasks,
                      db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ALUMNO" or current_user.get("id") != datos.id_usuario:
        raise HTTPException(status_code=403, detail="Solo el propio alumno puede inscribirse")

    alumno = db.query(Alumno).filter(Alumno.id_usuario == datos.id_usuario).first()
    if not alumno:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    anio, abierto = _anio_verano_vigente(db)
    if not anio or not abierto or anio.id_anio_escolar != datos.id_anio_escolar:
        raise HTTPException(status_code=400, detail="Las inscripciones de verano no están abiertas.")

    ya = db.query(models.SolicitudVerano).filter(
        models.SolicitudVerano.id_alumno == alumno.id_alumno,
        models.SolicitudVerano.id_anio_escolar == anio.id_anio_escolar,
    ).first()
    if ya:
        raise HTTPException(status_code=400, detail="Ya tienes una inscripción de verano registrada.")

    evaluacion = service.ultima_evaluacion(db, alumno.id_alumno)
    if evaluacion and evaluacion.resultado == "REPITE":
        raise HTTPException(status_code=400, detail="Repetirás el año académico, no aplica inscripción a verano.")

    pendientes = service.cursos_desaprobados_pendientes(db, alumno.id_alumno)
    es_nivelacion = datos.modalidad == "NIVELACION" or bool(pendientes)

    # Un alumno con cursos desaprobados pendientes solo puede inscribirse en modo nivelación.
    if pendientes and datos.modalidad != "NIVELACION":
        raise HTTPException(
            status_code=400,
            detail="Tienes cursos por nivelar. Debes inscribirte en la modalidad de nivelación."
        )

    grado = _grado_actual_alumno(db, alumno.id_alumno)
    aula, _clave, _lbl = service.grupo_de_alumno(db, grado)

    try:
        solicitud = models.SolicitudVerano(
            id_alumno=alumno.id_alumno,
            id_anio_escolar=anio.id_anio_escolar,
            id_grado=(aula.id_grado if aula else (grado.id_grado if grado else None)),
            origen="NIVELACION" if es_nivelacion else "INTERNO",
            modalidad="NIVELACION" if es_nivelacion else datos.modalidad,
            estado="PENDIENTE_PAGO",
        )
        db.add(solicitud)
        db.flush()

        if es_nivelacion:
            # Cursos precargados = los desaprobados pendientes
            for cd in pendientes:
                db.add(models.SolicitudVeranoCurso(
                    id_solicitud_verano=solicitud.id, id_curso=cd.id_curso, es_taller=False
                ))
        else:
            _registrar_cursos_solicitud(db, solicitud.id, datos.cursos_ids, datos.talleres_ids)

        pago = service.crear_pago_verano(db, alumno, anio)
        solicitud.id_pago = pago.id_pago
        db.commit()

        # Correo de confirmación a los apoderados
        correos = service._correos_apoderados(db, alumno.id_alumno)
        if correos:
            from app.core.util.email import enviar_correos, plantilla_institucional
            cuerpo = (
                f"<p>Se registró la inscripción al año académico de verano de "
                f"<strong>{alumno.nombres} {alumno.apellidos}</strong>.</p>"
                "<p>Recuerde realizar el <strong>pago fijo de verano</strong> por completo para "
                "que la admisión quede confirmada.</p>"
            )
            html = plantilla_institucional("Inscripción a verano registrada", cuerpo)
            background_tasks.add_task(
                enviar_correos,
                [{"destinatario": e, "asunto": "Inscripción a verano - Colegio Amancio Varona", "html": html} for e in correos]
            )
        return {"status": "success", "id_solicitud": solicitud.id, "id_pago": pago.id_pago}
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Error al registrar la inscripción de verano.")


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------
@router.get("/solicitudes", response_model=List[schemas.SolicitudVeranoResponse])
def listar_solicitudes(estado: Optional[str] = None, db: Session = Depends(get_db),
                       current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No tienes permisos para ver esta información")

    q = db.query(models.SolicitudVerano)
    if estado:
        q = q.filter(models.SolicitudVerano.estado == estado)
    solicitudes = q.order_by(models.SolicitudVerano.fecha.desc()).all()

    resultado = []
    for s in solicitudes:
        alumno = db.query(Alumno).filter(Alumno.id_alumno == s.id_alumno).first()
        grado = db.query(ac_models.Grado).filter(ac_models.Grado.id_grado == s.id_grado).first()
        _clave, grupo_label = service.grupo_por_grado(grado)
        pago = db.query(fi_models.Pago).filter(fi_models.Pago.id_pago == s.id_pago).first() if s.id_pago else None
        cursos_rows = db.query(models.SolicitudVeranoCurso).filter(
            models.SolicitudVeranoCurso.id_solicitud_verano == s.id
        ).all()
        nombres = []
        for cr in cursos_rows:
            c = db.query(ac_models.Curso).filter(ac_models.Curso.id_curso == cr.id_curso).first()
            etiqueta = f"{c.nombre}{' (Taller)' if cr.es_taller else ''}" if c else f"Curso {cr.id_curso}"
            nombres.append(etiqueta)
        resultado.append(schemas.SolicitudVeranoResponse(
            id=s.id,
            id_alumno=s.id_alumno,
            alumno_nombre=f"{alumno.nombres} {alumno.apellidos}" if alumno else None,
            alumno_dni=alumno.dni if alumno else None,
            id_anio_escolar=s.id_anio_escolar,
            grado_nombre=grado.nombre if grado else None,
            grupo_label=grupo_label,
            origen=s.origen,
            modalidad=s.modalidad,
            estado=s.estado,
            estado_pago=pago.estado if pago else None,
            monto=float(pago.monto_total) if pago else None,
            id_pago=s.id_pago,
            cursos=nombres,
            fecha=s.fecha,
        ))
    return resultado


@router.post("/solicitudes/{id_solicitud}/admitir")
def admitir_solicitud(id_solicitud: int, db: Session = Depends(get_db),
                      current_user: dict = Depends(get_current_user)):
    """Admisión manual: confirma el pago de verano y matricula al alumno."""
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No tienes permisos para esta acción")

    solicitud = db.query(models.SolicitudVerano).filter(models.SolicitudVerano.id == id_solicitud).first()
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if solicitud.estado == "ADMITIDO":
        raise HTTPException(status_code=400, detail="La solicitud ya fue admitida")

    pago = db.query(fi_models.Pago).filter(fi_models.Pago.id_pago == solicitud.id_pago).first()
    if pago and pago.estado != "PAGADO":
        from datetime import datetime
        pago.estado = "PAGADO"
        pago.fecha_pago = datetime.now()
        pago.codigo_operacion_bcp = "MANUAL-CAJA"
    service.procesar_pago_verano(db, pago) if pago else None
    solicitud.estado = "ADMITIDO"
    db.commit()
    return {"message": "Alumno admitido y matrícula de verano creada"}


@router.post("/evaluar-cierre/{id_anio}")
def evaluar_cierre(id_anio: str, background: BackgroundTasks, db: Session = Depends(get_db),
                   current_user: dict = Depends(get_current_user)):
    """Ejecuta la evaluación de fin de año (desaprobados / clasificación / correos)."""
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No tienes permisos para esta acción")

    resultado = service.evaluar_cierre_anio(db, id_anio)
    if resultado.get("error"):
        raise HTTPException(status_code=404, detail=resultado["error"])
    correos = resultado.get("correos", [])
    if correos:
        background.add_task(enviar_correos, correos)
    return resultado.get("resumen", {})
