from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.core.util.password import get_password_hash, verify_password
from app.core.util.usuarios import extraer_dni
# Imports corregidos: asegúrate de que las rutas sean las correctas en tu proyecto
from app.modules.users.models import Usuario
from app.modules.users.docente.models import Docente
from app.modules.personal.models import Administrador 
from app.modules.personal.models import Auxiliar 
from app.modules.personal.models import Psicologo
from app.modules.users.alumno.models import Alumno
from app.modules.users.familiar import services as familiar_services
from app.core.util.security import get_current_user
from app.core.util.correo_usuario import obtener_correo, guardar_correo
from app.modules.users.router import _exigir_cambio_password, _exigir_correo
from .schemas import (
    ChangePasswordSchema, ActualizarPerfilAdminSchema,
    ActualizarDireccionSchema, ActualizarMedicosSchema, FamiliarCreateSchema,
    RegistrarCorreoSchema, EstadoPrimerIngresoResponse,
)

router = APIRouter(prefix="/perfil", tags=["Perfil"])

@router.get("/mi-perfil/{username}")
def obtener_perfil_por_nombre(username: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    
    # 1. Buscamos al usuario base
    user = db.query(Usuario).filter(Usuario.username == username).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # 2. Lógica según el Rol
    
    # --- CASO ALUMNO ---
    if user.rol == "ALUMNO":
        alumno = user.alumno 
        if not alumno:
            raise HTTPException(status_code=404, detail="Datos de alumno no encontrados")
        
        familiares_data = familiar_services.listar_familiares_de_alumno(db, alumno.id_alumno)

        return {"rol": user.rol, "datos": alumno, "familiares": familiares_data}

    # --- CASO DOCENTE ---
    elif user.rol == "DOCENTE":
        docente = db.query(Docente).filter(Docente.id_usuario == user.id_usuario).first()
        if not docente:
            raise HTTPException(status_code=404, detail="Datos de docente no encontrados")
        return {"rol": user.rol, "datos": docente}

    # --- CASO ADMINISTRADOR (Nuevo) ---
    elif user.rol == "ADMIN":
        admin = db.query(Administrador).filter(Administrador.id_usuario == user.id_usuario).first()
        if not admin:
            raise HTTPException(status_code=404, detail="Datos de administrador no encontrados")
        return {"rol": user.rol, "datos": admin}

    # --- CASO AUXILIAR (Nuevo) ---
    elif user.rol == "AUXILIAR":
        auxiliar = db.query(Auxiliar).filter(Auxiliar.id_usuario == user.id_usuario).first()
        if not auxiliar:
            raise HTTPException(status_code=404, detail="Datos de auxiliar no encontrados")
        return {"rol": user.rol, "datos": auxiliar}
    # --- CASO PSICOLOGO (Nuevo) ---
    elif user.rol == "PSICOLOGO":
        psicologo = db.query(Psicologo).filter(Psicologo.id_usuario == user.id_usuario).first()
        if not psicologo:
            raise HTTPException(status_code=404, detail="Datos de psicólogo no encontrados")
        return {"rol": user.rol, "datos": psicologo}

    raise HTTPException(status_code=400, detail="Rol no soportado")


@router.patch("/admin/{username}")
def actualizar_perfil_admin(
    username: str,
    data: ActualizarPerfilAdminSchema,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    # Solo el propio administrador puede editar sus datos
    user = db.query(Usuario).filter(Usuario.username == username).first()
    if not user or user.rol != "ADMIN":
        raise HTTPException(status_code=404, detail="Administrador no encontrado")
    if current_user.get("id") != user.id_usuario:
        raise HTTPException(status_code=403, detail="No puedes editar un perfil ajeno")

    admin = db.query(Administrador).filter(Administrador.id_usuario == user.id_usuario).first()
    if not admin:
        raise HTTPException(status_code=404, detail="Datos de administrador no encontrados")

    cambios = data.model_dump(exclude_unset=True)
    for campo, valor in cambios.items():
        setattr(admin, campo, valor)

    db.commit()
    db.refresh(admin)
    return {"message": "Perfil actualizado con éxito", "datos": {
        "telefono": admin.telefono,
        "email": admin.email,
        "url_perfil": admin.url_perfil
    }}


# --- PERFIL DEL ALUMNO ---

def _get_alumno_propio(username: str, current_user: dict, db: Session) -> Alumno:
    """Obtiene el alumno asociado al username, validando que sea el propio usuario."""
    user = db.query(Usuario).filter(Usuario.username == username).first()
    if not user or user.rol != "ALUMNO":
        raise HTTPException(status_code=404, detail="Alumno no encontrado")
    if current_user.get("id") != user.id_usuario:
        raise HTTPException(status_code=403, detail="No puedes editar un perfil ajeno")
    alumno = db.query(Alumno).filter(Alumno.id_usuario == user.id_usuario).first()
    if not alumno:
        raise HTTPException(status_code=404, detail="Datos de alumno no encontrados")
    return alumno


@router.patch("/alumno/{username}/direccion")
def actualizar_direccion_alumno(
    username: str,
    data: ActualizarDireccionSchema,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    alumno = _get_alumno_propio(username, current_user, db)
    alumno.direccion = data.direccion.strip()
    db.commit()
    db.refresh(alumno)
    return {"message": "Dirección actualizada con éxito", "direccion": alumno.direccion}


@router.patch("/alumno/{username}/medicos")
def actualizar_datos_medicos_alumno(
    username: str,
    data: ActualizarMedicosSchema,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    alumno = _get_alumno_propio(username, current_user, db)
    valor = (data.enfermedad or "").strip()
    alumno.enfermedad = valor or None
    db.commit()
    db.refresh(alumno)
    return {"message": "Datos médicos actualizados", "enfermedad": alumno.enfermedad}


@router.post("/alumno/{username}/familiares")
def agregar_familiar_alumno(
    username: str,
    data: FamiliarCreateSchema,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    alumno = _get_alumno_propio(username, current_user, db)

    familiar = familiar_services.vincular_familiar(db, alumno.id_alumno, data)
    db.commit()
    db.refresh(familiar)

    return {
        "message": "Familiar agregado con éxito",
        "familiar": familiar_services.serializar_familiar(familiar, data.tipo_parentesco),
    }


@router.post("/auth/change-password")
async def change_password(data: ChangePasswordSchema, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    # 1. Buscar al usuario
    user = db.query(Usuario).filter(Usuario.username == data.username).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # 1b. Solo puedes cambiar TU propia contraseña (evita cambiar la de otro usuario)
    if user.id_usuario != current_user.get("id"):
        raise HTTPException(status_code=403, detail="No puedes cambiar la contraseña de otro usuario")

    # 2. Verificar si la contraseña actual es correcta
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="La contraseña actual es incorrecta")

    # 3. La nueva no puede ser igual al DNI: es la clave inicial que se reparte
    if data.new_password.strip() == extraer_dni(user.username):
        raise HTTPException(
            status_code=400,
            detail="La nueva contraseña no puede ser tu DNI. Elige una distinta."
        )

    # 4. Encriptar la nueva y guardar. Al definir clave propia se levanta la
    #    obligación de cambiarla en el primer ingreso.
    user.password_hash = get_password_hash(data.new_password)
    user.debe_cambiar_password = False
    db.commit()
    return {"message": "Contraseña actualizada con éxito"}


@router.get("/auth/primer-ingreso", response_model=EstadoPrimerIngresoResponse)
def estado_primer_ingreso(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """
    Qué le falta a esta cuenta para poder usar el campus.

    La pantalla de primer ingreso lo consulta al abrirse, en lugar de fiarse de
    lo que devolvió el login: así sigue siendo correcta tras recargar la página
    y no se le puede saltar cambiando lo guardado en el navegador.
    """
    user = db.query(Usuario).filter(Usuario.id_usuario == current_user.get("id")).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    correo = obtener_correo(db, user)
    return {
        "debe_cambiar_password": bool(user.debe_cambiar_password) and _exigir_cambio_password(db),
        "debe_registrar_correo": _exigir_correo(db) and not correo,
        "es_alumno": user.rol == "ALUMNO",
        "email_actual": correo,
    }


@router.post("/auth/registrar-correo")
def registrar_correo(
    data: RegistrarCorreoSchema,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Guarda el correo de contacto de la cuenta que ha iniciado sesión.

    En el alumno el correo va a su apoderado, que es quien recibe los avisos de
    asistencia y conducta. Ver app/core/util/correo_usuario.py.
    """
    user = db.query(Usuario).filter(Usuario.id_usuario == current_user.get("id")).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    try:
        guardar_correo(db, user, str(data.email))
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    db.commit()
    return {"message": "Correo registrado con éxito", "email": str(data.email)}