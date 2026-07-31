from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.core.util.security import get_current_user
from app.core.util.email import enviar_correo, plantilla_institucional
from app.modules.users.alumno.models import Alumno
from app.modules.users.familiar.models import Familiar
from app.modules.users.relacion_familiar.models import RelacionFamiliar # El que creamos antes
from . import schemas

router = APIRouter(prefix="/admision", tags=["Admisión"])


def resolver_familiar(db: Session, datos_fam: dict, direccion_alumno: str) -> Familiar:
    """Devuelve el Familiar por su DNI: si ya existe lo reutiliza (para no duplicar
    apoderados ni romper el registro de un segundo hijo), si no, lo crea."""
    datos_fam = dict(datos_fam)
    datos_fam.pop("tipo_parentesco", None)
    if not datos_fam.get("direccion") or (datos_fam.get("direccion") or "").strip() == "":
        datos_fam["direccion"] = direccion_alumno

    existente = db.query(Familiar).filter(Familiar.dni == datos_fam.get("dni")).first()
    if existente:
        return existente
    nuevo_familiar = Familiar(**datos_fam)
    db.add(nuevo_familiar)
    db.flush()
    return nuevo_familiar


def enviar_confirmacion_postulacion(email: str, nombre_alumno: str, es_verano: bool = False):
    """Envía (en background) el correo de confirmación de postulación al apoderado."""
    if not email:
        return
    tipo = "al año académico de verano" if es_verano else "de admisión"
    cuerpo = (
        f"<p>Hemos recibido correctamente la postulación {tipo} de "
        f"<strong>{nombre_alumno}</strong>.</p>"
        "<p>Nuestra oficina revisará la solicitud y se pondrá en contacto con usted "
        "por este medio o por teléfono en los próximos días.</p>"
    )
    enviar_correo(
        destinatario=email,
        asunto="Postulación recibida - Colegio Amancio Varona",
        html=plantilla_institucional("¡Postulación recibida!", cuerpo),
    )


@router.post("/postular", status_code=status.HTTP_201_CREATED)
def postular_alumno(datos: schemas.AdmisionPostulante, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    # 0. Control de duplicados: un alumno no puede inscribirse dos veces
    ya_existe = db.query(Alumno).filter(Alumno.dni == datos.alumno.dni).first()
    if ya_existe:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un alumno registrado con el DNI {datos.alumno.dni}. No es posible postular dos veces."
        )
    try:
        # 1. Crear Alumno
        nuevo_alumno = Alumno(**datos.alumno.model_dump())
        db.add(nuevo_alumno)
        db.flush() # Para obtener nuevo_alumno.id_alumno

        # 2. Familiar (se reutiliza si ya existe por DNI)
        familiar = resolver_familiar(db, datos.familiar.model_dump(), datos.alumno.direccion)

        # 3. Relación y Parentesco (evitar duplicar la relación)
        val_parentesco = (datos.tipo_parentesco or "OTRO").upper()
        rel_existe = db.query(RelacionFamiliar).filter(
            RelacionFamiliar.id_alumno == nuevo_alumno.id_alumno,
            RelacionFamiliar.id_familiar == familiar.id_familiar,
        ).first()
        if not rel_existe:
            db.add(RelacionFamiliar(
                id_alumno=nuevo_alumno.id_alumno,
                id_familiar=familiar.id_familiar,
                tipo_parentesco=val_parentesco
            ))

        db.commit()

        # 4. Correo de confirmación al apoderado
        background_tasks.add_task(
            enviar_confirmacion_postulacion,
            datos.familiar.email,
            f"{nuevo_alumno.nombres} {nuevo_alumno.apellidos}",
            False,
        )

        return {
            "status": "success",
            "message": "Postulación registrada",
            "id_alumno": nuevo_alumno.id_alumno
        }

    except Exception as e:
        db.rollback()
        mensaje = "Error interno del servidor"
        if "Duplicate entry" in str(e):
            mensaje = "El DNI ingresado ya se encuentra registrado."
        elif "foreign key constraint" in str(e):
            mensaje = "Error de integridad en los datos proporcionados."
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=mensaje
        )


