"""
Lógica compartida de familiares de un alumno.

La usan el panel del administrador (gestión de estudiantes) y el perfil del
propio alumno, para que ambos construyan la misma forma de datos y apliquen
las mismas reglas al vincular familiares.
"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from .models import Familiar
from app.modules.users.relacion_familiar.models import RelacionFamiliar


def serializar_familiar(familiar: Familiar, parentesco: str | None = None) -> dict:
    """Forma común de un familiar. `parentesco` viene de la relación con el alumno."""
    return {
        "id_familiar": familiar.id_familiar,
        "nombre": f"{familiar.nombres} {familiar.apellidos}",
        "nombres": familiar.nombres,
        "apellidos": familiar.apellidos,
        "dni": familiar.dni,
        "parentesco": parentesco if parentesco is not None else familiar.tipo_parentesco,
        "telefono": familiar.telefono,
        "email": familiar.email,
        "direccion": familiar.direccion,
    }


def listar_familiares_de_alumno(db: Session, id_alumno: int) -> list[dict]:
    relaciones = db.query(RelacionFamiliar).filter(
        RelacionFamiliar.id_alumno == id_alumno
    ).all()
    return [serializar_familiar(r.familiar, r.tipo_parentesco) for r in relaciones if r.familiar]


def obtener_relacion(db: Session, id_alumno: int, id_familiar: int) -> RelacionFamiliar:
    """Relación alumno-familiar, o 404 si el familiar no pertenece a ese alumno."""
    relacion = db.query(RelacionFamiliar).filter(
        RelacionFamiliar.id_alumno == id_alumno,
        RelacionFamiliar.id_familiar == id_familiar
    ).first()
    if not relacion:
        raise HTTPException(status_code=404, detail="El familiar no está registrado para este alumno")
    return relacion


def vincular_familiar(db: Session, id_alumno: int, data) -> Familiar:
    """
    Vincula un familiar al alumno: reutiliza el registro si el DNI ya existe
    (caso hermanos) o lo crea. No hace commit; lo decide quien llama.
    """
    familiar = db.query(Familiar).filter(Familiar.dni == data.dni).first()
    if not familiar:
        familiar = Familiar(
            dni=data.dni,
            nombres=data.nombres.strip(),
            apellidos=data.apellidos.strip(),
            telefono=data.telefono,
            email=data.email,
            direccion=data.direccion,
            tipo_parentesco=data.tipo_parentesco,
        )
        db.add(familiar)
        db.flush()  # Para obtener id_familiar

    ya_vinculado = db.query(RelacionFamiliar).filter(
        RelacionFamiliar.id_alumno == id_alumno,
        RelacionFamiliar.id_familiar == familiar.id_familiar
    ).first()
    if ya_vinculado:
        raise HTTPException(status_code=400, detail="Este familiar ya está registrado para el alumno")

    db.add(RelacionFamiliar(
        id_alumno=id_alumno,
        id_familiar=familiar.id_familiar,
        tipo_parentesco=data.tipo_parentesco,
    ))
    return familiar


def desvincular_familiar(db: Session, id_alumno: int, id_familiar: int) -> str:
    """
    Quita el familiar del alumno. Si ya no le queda ningún alumno vinculado,
    elimina también su registro, salvo que tenga citas psicológicas asociadas
    (en ese caso se conserva por integridad del historial). No hace commit.
    """
    # Import local: evita un ciclo de importación entre los módulos behavior y users.
    from app.modules.behavior.models import CitaPsicologia

    relacion = obtener_relacion(db, id_alumno, id_familiar)
    db.delete(relacion)
    db.flush()

    otras_relaciones = db.query(RelacionFamiliar).filter(
        RelacionFamiliar.id_familiar == id_familiar
    ).first()
    if otras_relaciones:
        return "El familiar se quitó de este alumno y sigue vinculado a otro estudiante."

    tiene_citas = db.query(CitaPsicologia.id_cita).filter(
        CitaPsicologia.id_familiar == id_familiar
    ).first()
    if tiene_citas:
        return "El familiar se quitó del alumno. Su registro se conserva porque tiene citas en el historial."

    familiar = db.query(Familiar).filter(Familiar.id_familiar == id_familiar).first()
    if familiar:
        db.delete(familiar)
    return "Familiar eliminado correctamente."
