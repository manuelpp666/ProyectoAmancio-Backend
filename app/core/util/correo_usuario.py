"""
Correo de contacto de una cuenta, sea cual sea su rol.

El colegio necesita un correo por cuenta para avisar de asistencia, notas y
trámites. Dónde vive ese correo depende del rol:

  * Personal (docente, administrador, auxiliar, psicólogo): en su propio perfil.
  * Alumno: la tabla `alumno` no tiene correo a propósito, porque quien recibe
    los avisos es el apoderado. Se guarda en `familiar.email`.

Este módulo es el único sitio que conoce esa diferencia; el resto del backend
pregunta "¿tiene correo?" y "guárdale este correo" sin saber dónde acaba.
"""
from app.modules.users.alumno.models import Alumno
from app.modules.users.docente.models import Docente
from app.modules.users.familiar.models import Familiar
from app.modules.users.relacion_familiar.models import RelacionFamiliar
from app.modules.personal.models import Administrador, Auxiliar, Psicologo

# Perfil donde vive el correo de cada rol del personal
PERFIL_POR_ROL = {
    "DOCENTE": Docente,
    "ADMIN": Administrador,
    "AUXILIAR": Auxiliar,
    "PSICOLOGO": Psicologo,
}

# Parentescos que se prefieren al elegir a quién se le anota el correo
PRIORIDAD_PARENTESCO = ("APODERADO", "MADRE", "PADRE")


def _familiares_del_alumno(db, id_alumno):
    """Apoderados del alumno, con los parentescos principales primero."""
    relaciones = (
        db.query(RelacionFamiliar)
        .filter(RelacionFamiliar.id_alumno == id_alumno)
        .all()
    )

    def orden(rel):
        tipo = (rel.tipo_parentesco or "").strip().upper()
        return PRIORIDAD_PARENTESCO.index(tipo) if tipo in PRIORIDAD_PARENTESCO else len(PRIORIDAD_PARENTESCO)

    return sorted(relaciones, key=orden)


def obtener_correo(db, usuario) -> str | None:
    """Correo registrado para esta cuenta, o None si todavía no tiene."""
    if usuario.rol == "ALUMNO":
        alumno = db.query(Alumno).filter(Alumno.id_usuario == usuario.id_usuario).first()
        if not alumno:
            return None
        for rel in _familiares_del_alumno(db, alumno.id_alumno):
            correo = (rel.familiar.email or "").strip() if rel.familiar else ""
            if correo:
                return correo
        return None

    modelo = PERFIL_POR_ROL.get(usuario.rol)
    if not modelo:
        return None
    perfil = db.query(modelo).filter(modelo.id_usuario == usuario.id_usuario).first()
    correo = (perfil.email or "").strip() if perfil else ""
    return correo or None


def tiene_correo(db, usuario) -> bool:
    return bool(obtener_correo(db, usuario))


def guardar_correo(db, usuario, correo: str) -> None:
    """
    Anota el correo donde corresponda según el rol. No hace commit: lo deja
    al llamador para que pueda agrupar el cambio con otros de la misma request.
    """
    correo = correo.strip()

    if usuario.rol == "ALUMNO":
        alumno = db.query(Alumno).filter(Alumno.id_usuario == usuario.id_usuario).first()
        if not alumno:
            raise ValueError("La cuenta no tiene una ficha de alumno asociada")

        relaciones = _familiares_del_alumno(db, alumno.id_alumno)
        if relaciones and relaciones[0].familiar:
            relaciones[0].familiar.email = correo
            return

        # Alumno sin apoderado registrado: se crea uno mínimo con el correo,
        # para no perder el dato mientras el colegio completa su ficha.
        familiar = Familiar(email=correo)
        db.add(familiar)
        db.flush()
        db.add(RelacionFamiliar(
            id_alumno=alumno.id_alumno,
            id_familiar=familiar.id_familiar,
            tipo_parentesco="APODERADO",
        ))
        return

    modelo = PERFIL_POR_ROL.get(usuario.rol)
    if not modelo:
        raise ValueError(f"El rol {usuario.rol} no tiene un perfil donde guardar el correo")
    perfil = db.query(modelo).filter(modelo.id_usuario == usuario.id_usuario).first()
    if not perfil:
        raise ValueError("La cuenta no tiene un perfil asociado")
    perfil.email = correo
