from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from typing import List
from datetime import date, datetime
from app.db.database import get_db
from app.modules.users.models import Usuario 
from app.modules.users.relacion_familiar.models import RelacionFamiliar
from app.modules.users import models as al_models
from app.modules.users.familiar.models import Familiar
from app.modules.users.familiar import schemas as familiar_schemas
from app.modules.users.familiar import services as familiar_services
from app.modules.academic.models import Grado
from app.modules.users.alumno import estados
from app.modules.finance import models as finance_models
from app.core.util.security import get_current_user
from app.core.util.password import get_password_hash
from app.core.util.usuarios import generar_username
from app.core.util import busqueda as busqueda_util
from . import models, schemas # Asegúrate de importar los modelos correctos

router = APIRouter(prefix="/alumnos", tags=["Alumnos"])

def _solo_admin(current_user: dict):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No tienes permisos para esta operación")

def _filtrar_por_busqueda(query, termino: str):
    """
    Filtra alumnos por DNI o por nombre.

    Cada palabra escrita debe aparecer en algún dato del alumno, sin importar
    el orden: "castro carlos" encuentra a CASTRO CASTILLO, CARLOS ADRIÁN igual
    que "carlos castro".
    """
    return busqueda_util.filtrar(
        query, termino,
        models.Alumno.nombres, models.Alumno.apellidos, models.Alumno.dni,
    )


def asegurar_usuario(db: Session, alumno: models.Alumno) -> Usuario | None:
    """
    Garantiza que el alumno tenga cuenta para entrar al campus.

    Todo alumno que ya forma parte del colegio (ADMITIDO o ESTUDIANTE) necesita
    su usuario; el POSTULANTE todavía no, porque solo envió una solicitud desde
    la web pública y puede acabar rechazado.

    Se llama desde los tres sitios donde nace un alumno activo: el alta manual
    del panel (con y sin apoderado) y la aprobación de una admisión. Antes cada
    sitio lo resolvía por su cuenta y el alta manual sencillamente no lo hacía,
    así que el alumno quedaba registrado pero sin poder iniciar sesión.

    No hace commit: lo deja en la transacción de quien llama.
    """
    if alumno.id_usuario or alumno.estado_ingreso not in estados.ACTIVOS:
        return None

    username = generar_username(alumno.dni, "ALUMNO")

    # Si ya existe la cuenta (un alumno que vuelve, o una carga previa), se
    # reutiliza en vez de chocar contra el UNIQUE de usuario.username.
    usuario = db.query(Usuario).filter(Usuario.username == username).first()
    if not usuario:
        usuario = Usuario(
            username=username,
            # Contraseña inicial: su propio DNI. debe_cambiar_password queda en
            # su valor por defecto para obligarle a cambiarla al entrar.
            password_hash=get_password_hash(alumno.dni),
            rol="ALUMNO",
            activo=True,
        )
        db.add(usuario)
        db.flush()

    alumno.id_usuario = usuario.id_usuario
    return usuario


def _obtener_alumno(db: Session, id_alumno: int) -> models.Alumno:
    alumno = db.query(models.Alumno).filter(models.Alumno.id_alumno == id_alumno).first()
    if not alumno:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")
    return alumno

#---- Sacar id_usuario de id_alumno
# En tu router de alumnos o académico
@router.get("/alumnos/usuario/{id_usuario}")
def obtener_alumno_por_usuario(id_usuario: int, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    if current_user.get("id") != id_usuario:
        raise HTTPException(status_code=403, detail="No puedes ver perfiles ajenos")
    alumno = db.query(models.Alumno).filter(models.Alumno.id_usuario == id_usuario).first()
    if not alumno:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")
    return {"id_alumno": alumno.id_alumno}

@router.post("/", response_model=schemas.AlumnoResponse)
def crear_alumno(alumno: schemas.AlumnoCreate, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user) ):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes ver modificar esta información")
    db_alumno = models.Alumno(**alumno.model_dump())
    db.add(db_alumno)
    db.flush()
    # Un alumno dado de alta ya admitido tiene que poder entrar al campus.
    asegurar_usuario(db, db_alumno)
    db.commit()
    db.refresh(db_alumno)
    return db_alumno

@router.post("/con-familiar", status_code=status.HTTP_201_CREATED)
def crear_alumno_con_familiar(
    datos: schemas.AlumnoConFamiliarCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Alta de un estudiante junto a su apoderado, en una sola transacción.
    Si falla cualquier paso no se guarda nada: evita dejar al alumno sin
    apoderado o al apoderado sin vincular.
    """
    _solo_admin(current_user)

    dni_ocupado = db.query(models.Alumno).filter(models.Alumno.dni == datos.alumno.dni).first()
    if dni_ocupado:
        raise HTTPException(status_code=400, detail="Ya existe un alumno registrado con ese DNI.")

    if datos.alumno.id_grado_ingreso is not None:
        grado = db.query(Grado).filter(Grado.id_grado == datos.alumno.id_grado_ingreso).first()
        if not grado:
            raise HTTPException(status_code=400, detail="El grado seleccionado no existe.")

    try:
        nuevo_alumno = models.Alumno(**datos.alumno.model_dump())
        db.add(nuevo_alumno)
        db.flush()  # Para obtener id_alumno

        # El panel da de alta al alumno ya ADMITIDO, así que necesita su cuenta
        # aquí mismo: no va a pasar por /decidir-admision.
        asegurar_usuario(db, nuevo_alumno)

        # Si el apoderado no indicó dirección, hereda la del alumno (regla de admisión)
        familiar_data = datos.familiar.model_copy()
        if not (familiar_data.direccion or "").strip():
            familiar_data.direccion = datos.alumno.direccion

        # vincular_familiar reutiliza el apoderado si ya existe por DNI (caso hermanos)
        familiar = familiar_services.vincular_familiar(db, nuevo_alumno.id_alumno, familiar_data)
        db.commit()
        db.refresh(nuevo_alumno)
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        print(f"Error en crear_alumno_con_familiar: {e}")
        raise HTTPException(status_code=400, detail="No se pudo registrar al estudiante. Verifique los datos.")

    return {
        "message": "Estudiante y apoderado registrados correctamente",
        "id_alumno": nuevo_alumno.id_alumno,
        "familiar": familiar_services.serializar_familiar(familiar, datos.familiar.tipo_parentesco),
    }

@router.get("/", response_model=List[schemas.AlumnoResponse])
def listar_alumnos(busqueda: str = None, dni: str = None, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):

    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes ver modificar esta información")

    # joinedload: la tabla muestra el usuario con el que cada alumno inicia
    # sesión. Sin esto, con casi 600 alumnos se lanzaría una consulta por fila
    # solo para leer su username.
    query = (
        db.query(models.Alumno)
        .options(joinedload(models.Alumno.usuario), joinedload(models.Alumno.grado_ingreso))
        .filter(models.Alumno.estado_ingreso != estados.RECHAZADO)
    )

    # `dni` se sigue aceptando por compatibilidad con llamadas antiguas
    termino = (busqueda or dni or "").strip()
    if termino:
        query = _filtrar_por_busqueda(query, termino)

    return query.all()

@router.get("/solicitudes-pendientes", response_model=List[schemas.AlumnoResponse])
def listar_postulantes(
    busqueda: str = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para ver solicitudes de admisión"
        )
    query = db.query(models.Alumno).filter(
        models.Alumno.estado_ingreso == estados.POSTULANTE
    )
    if busqueda and busqueda.strip():
        query = _filtrar_por_busqueda(query, busqueda.strip())
    return query.all()

@router.post("/decidir-admision/{id_alumno}")
def decidir_admision(
    id_alumno: int, 
    aprobado: bool, 
    motivo: str = None, 
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user) 
):
    
    try:
        
        if current_user.get("rol") != "ADMIN":
            raise HTTPException(status_code=403, detail="No puedes ver perfiles ajenos")
        # 1. Buscar al alumno por su ID
        alumno = db.query(models.Alumno).filter(models.Alumno.id_alumno == id_alumno).first()
        if not alumno:
            raise HTTPException(status_code=404, detail="No se encontró el postulante")

        if aprobado:
            # --- LÓGICA DE APROBACIÓN ---
            alumno.estado_ingreso = estados.ADMITIDO
            alumno.motivo_rechazo = None

            # A. Crear su cuenta del campus (misma función que usa el alta manual)
            asegurar_usuario(db, alumno)


            # C. Buscar el tipo de pago de Vacante y Matrícula (NUEVA LÓGICA MM-DD)
            hoy = date.today()
            hoy_md = hoy.strftime("%m-%d")

            tipos_activos = db.query(finance_models.TipoPago).filter(finance_models.TipoPago.activo == True).all()

            def esta_vigente(tipo):
                inicio = tipo.fecha_inicio
                fin = tipo.fecha_vencimiento
                if inicio <= fin:
                    return inicio <= hoy_md <= fin
                else: # Cruza el año (ej: 11-01 a 02-28)
                    return hoy_md >= inicio or hoy_md <= fin

            def calcular_fecha_real(mm_dd: str) -> date:
                mes, dia = map(int, mm_dd.split("-"))
                anio_pago = hoy.year
                # Si hoy es Nov/Dic y el pago es Ene/Feb, el pago es para el año que viene
                if hoy.month >= 10 and mes <= 6:
                    anio_pago += 1
                try:
                    return date(anio_pago, mes, dia)
                except ValueError: # Febrero 29 en año no bisiesto -> Febrero 28
                    return date(anio_pago, mes, dia - 1)

            tipo_vacante = next((t for t in tipos_activos if t.categoria == 'VACANTE' and esta_vigente(t)), None)
            tipo_matricula = next((t for t in tipos_activos if t.categoria == 'MATRICULA' and esta_vigente(t)), None)

            if not tipo_vacante or not tipo_matricula:
                raise Exception("Configuración faltante: Asegúrate de tener una plantilla de 'VACANTE' y una de 'MATRÍCULA' activas para la fecha de hoy.")

            # D. Crear el registro de Pago (Actualizado)
            nuevo_pago_vacante = finance_models.Pago(
                id_alumno=alumno.id_alumno,
                id_tipo_pago=tipo_vacante.id_tipo_pago, # <--- Se asocia al nuevo ID
                concepto=f"{tipo_vacante.nombre} - {alumno.nombres} {alumno.apellidos}",
                monto=tipo_vacante.costo,
                mora=0.00,
                monto_total=tipo_vacante.costo,
                estado="PENDIENTE",
                fecha_vencimiento=calcular_fecha_real(tipo_vacante.fecha_vencimiento) # <--- Toma la fecha del tipo de pago
            )
            db.add(nuevo_pago_vacante)

            nuevo_pago_matricula = finance_models.Pago(
                id_alumno=alumno.id_alumno,
                id_tipo_pago=tipo_matricula.id_tipo_pago,
                concepto=f"{tipo_matricula.nombre} - {alumno.nombres} {alumno.apellidos}",
                monto=tipo_matricula.costo,
                mora=0.00,
                monto_total=tipo_matricula.costo,
                estado="PENDIENTE",
                fecha_vencimiento=calcular_fecha_real(tipo_matricula.fecha_vencimiento) 
            )
            db.add(nuevo_pago_matricula)
            
        else:
            # --- LÓGICA DE RECHAZO ---
            alumno.estado_ingreso = estados.RECHAZADO
            alumno.motivo_rechazo = motivo

        # Guardar todos los cambios de forma atómica
        db.commit()
        return {
            "status": "success", 
            "message": f"El alumno ha sido {'admitido' if aprobado else 'rechazado'} correctamente."
        }

    except Exception as e:
        db.rollback() # Si algo falla (ej: DNI de usuario duplicado), deshace todo
        print(f"Error en decidir_admision: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=str(e) if "Configuración faltante" in str(e) else "Error al procesar la admisión"
        )
    
@router.get("/detalle-completo/{id_alumno}")
def obtener_detalle_postulante(id_alumno: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes ver modificar esta información")


    alumno = db.query(models.Alumno).filter(models.Alumno.id_alumno == id_alumno).first()
    if not alumno:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")
    
    # Obtenemos el nombre del grado si existe la relación
    # Ajusta 'grado_ingreso' al nombre de la relación en tu modelo Alumno
    nombre_grado = "No asignado"
    if alumno.grado_ingreso:
        nombre_grado = f"{alumno.grado_ingreso.nombre} ({alumno.grado_ingreso.nivel.nombre})"

    familiares_data = familiar_services.listar_familiares_de_alumno(db, alumno.id_alumno)

    return {
        "alumno": {
            "id_alumno": alumno.id_alumno,
            "nombres": alumno.nombres,
            "apellidos": alumno.apellidos,
            "dni": alumno.dni,
            "estado_ingreso": alumno.estado_ingreso,
            "grado": nombre_grado, # <--- AGREGAMOS ESTO
            "colegio_procedencia": alumno.colegio_procedencia,
            "enfermedad": alumno.enfermedad,
            "direccion": alumno.direccion,
            "fecha_nacimiento": alumno.fecha_nacimiento.isoformat() if alumno.fecha_nacimiento else None,
            "genero": alumno.genero,
            "talla_polo": alumno.talla_polo,
            "doc_dni_menor": alumno.doc_dni_menor,
            "doc_dni_apoderado": alumno.doc_dni_apoderado,
            "doc_fum": alumno.doc_fum,
            "doc_certificado_estudios": alumno.doc_certificado_estudios,
        },
        "familiares": familiares_data
    }


# ---------- EDICIÓN DEL ALUMNO Y SU USUARIO (PANEL DEL ADMINISTRADOR) ----------

@router.put("/{id_alumno}")
def editar_alumno(
    id_alumno: int,
    data: schemas.AlumnoUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Actualiza los datos del alumno y las credenciales de su usuario."""
    _solo_admin(current_user)
    alumno = _obtener_alumno(db, id_alumno)

    usuario = None
    if alumno.id_usuario:
        usuario = db.query(Usuario).filter(Usuario.id_usuario == alumno.id_usuario).first()

    if data.dni != alumno.dni:
        # El DNI identifica al alumno y es además su nombre de usuario
        dni_ocupado = db.query(models.Alumno).filter(
            models.Alumno.dni == data.dni,
            models.Alumno.id_alumno != id_alumno
        ).first()
        if dni_ocupado:
            raise HTTPException(status_code=400, detail="Ya existe otro alumno con ese DNI.")

        if usuario:
            # El username sigue al DNI, conservando el prefijo del rol
            nuevo_username = generar_username(data.dni, usuario.rol)
            username_ocupado = db.query(Usuario).filter(
                Usuario.username == nuevo_username,
                Usuario.id_usuario != usuario.id_usuario
            ).first()
            if username_ocupado:
                raise HTTPException(status_code=400, detail="Ya existe un usuario con ese DNI.")
            usuario.username = nuevo_username

    if data.id_grado_ingreso is not None:
        grado = db.query(Grado).filter(Grado.id_grado == data.id_grado_ingreso).first()
        if not grado:
            raise HTTPException(status_code=400, detail="El grado seleccionado no existe.")

    # Campos propios del alumno (estado_ingreso, credenciales y documentos de
    # admisión quedan fuera: la edición del admin no debe borrar los documentos).
    campos_alumno = data.model_dump(exclude={
        "password", "activo", "estado_ingreso",
        "doc_dni_menor", "doc_dni_apoderado", "doc_fum", "doc_certificado_estudios",
    })
    for campo, valor in campos_alumno.items():
        setattr(alumno, campo, valor)

    if usuario:
        if data.password:
            usuario.password_hash = get_password_hash(data.password)
        if data.activo is not None:
            usuario.activo = data.activo

    db.commit()
    db.refresh(alumno)

    return {
        "message": "Estudiante actualizado con éxito",
        "id_alumno": alumno.id_alumno,
        "username": usuario.username if usuario else None,
        "activo": usuario.activo if usuario else None,
    }


# ---------- FAMILIARES DEL ALUMNO ----------

@router.get("/{id_alumno}/familiares")
def listar_familiares_alumno(
    id_alumno: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Familiares vinculados a un alumno. Lo consultan admisión, psicología y auxiliares."""
    if current_user.get("rol") not in ("ADMIN", "PSICOLOGO", "AUXILIAR"):
        raise HTTPException(status_code=403, detail="No tienes permisos para ver esta información")
    _obtener_alumno(db, id_alumno)
    return familiar_services.listar_familiares_de_alumno(db, id_alumno)


@router.post("/{id_alumno}/familiares")
def agregar_familiar_alumno(
    id_alumno: int,
    data: familiar_schemas.FamiliarAlumnoCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    _solo_admin(current_user)
    _obtener_alumno(db, id_alumno)

    familiar = familiar_services.vincular_familiar(db, id_alumno, data)
    db.commit()
    db.refresh(familiar)
    return {
        "message": "Familiar agregado con éxito",
        "familiar": familiar_services.serializar_familiar(familiar, data.tipo_parentesco),
    }


@router.put("/{id_alumno}/familiares/{id_familiar}")
def editar_familiar_alumno(
    id_alumno: int,
    id_familiar: int,
    data: familiar_schemas.FamiliarUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    _solo_admin(current_user)
    relacion = familiar_services.obtener_relacion(db, id_alumno, id_familiar)
    familiar = relacion.familiar

    if data.dni != familiar.dni:
        dni_ocupado = db.query(Familiar).filter(
            Familiar.dni == data.dni,
            Familiar.id_familiar != id_familiar
        ).first()
        if dni_ocupado:
            raise HTTPException(status_code=400, detail="Ya existe otro familiar con ese DNI.")

    familiar.dni = data.dni
    familiar.nombres = data.nombres.strip()
    familiar.apellidos = data.apellidos.strip()
    familiar.telefono = data.telefono
    familiar.email = data.email
    familiar.direccion = data.direccion
    # El parentesco vive en la relación: es lo que leen los demás módulos
    relacion.tipo_parentesco = data.tipo_parentesco

    db.commit()
    db.refresh(familiar)
    return {
        "message": "Familiar actualizado con éxito",
        "familiar": familiar_services.serializar_familiar(familiar, relacion.tipo_parentesco),
    }


@router.delete("/{id_alumno}/familiares/{id_familiar}")
def eliminar_familiar_alumno(
    id_alumno: int,
    id_familiar: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    _solo_admin(current_user)
    mensaje = familiar_services.desvincular_familiar(db, id_alumno, id_familiar)
    db.commit()
    return {"message": mensaje}