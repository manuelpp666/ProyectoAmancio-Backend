import os
import uuid
import shutil
import calendar
from fastapi import APIRouter, Depends, HTTPException, status,File, UploadFile, Form
from sqlalchemy.orm import Session, joinedload
from datetime import datetime, date, timedelta
from typing import List,Optional
from sqlalchemy import func, extract
from app.db.database import get_db
from . import models, schemas
from app.modules.academic import models as academic_models
from app.modules.users.alumno import models as user_models
from app.modules.enrollment import models as er_models
from .service import FinanceService
from app.core.util.security import get_current_user, require_roles, require_service_key


router = APIRouter(prefix="/finance", tags=["Finanzas"])


# Configuración básica (puedes moverla a tu archivo de constantes)
# 1. Obtenemos la ruta de este archivo (virtual)
FILE_DIR = os.path.dirname(os.path.abspath(__file__)) 

# 2. Subimos 3 niveles: virtual -> modules -> app -> Backend
# Esto garantiza que BASE_DIR sea la carpeta raíz del proyecto Backend
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(FILE_DIR)))
UPLOAD_DIR = "media/tramites_adjuntos"
ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
# ==========================================
# 1. GESTIÓN DE TIPOS DE TRÁMITE (ADMIN)
# ==========================================

@router.get("/tramites-tipos/", response_model=List[schemas.TipoTramiteResponse])
def listar_tipos_tramite(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes ver esta información")
    """Lista todos los tipos de trámite configurados en el sistema."""
    return db.query(models.TipoTramite).all()

@router.get("/tramites-tipos/alumnos", response_model=List[schemas.TipoTramiteResponse])
def listar_tipos_tramite_alumnos(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ALUMNO":
        raise HTTPException(status_code=403, detail="No puedes ver esta información")
    """
    Lista los tipos de trámite visibles para los alumnos.
    Filtra automáticamente procesos de Matrícula y Vacante para evitar confusiones.
    """
    return db.query(models.TipoTramite).filter(
        models.TipoTramite.activo == True,
        ~models.TipoTramite.nombre.ilike("%VACANTE%"),
        ~models.TipoTramite.nombre.ilike("%MATRICULA%")
    ).all()

@router.post("/tramites-tipos/", response_model=schemas.TipoTramiteResponse)
def crear_tipo_tramite(tramite: schemas.TipoTramiteCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes ver esta información")
    """Crea un nuevo tipo de trámite con validación de unicidad para VACANTE."""
    
    # 1. Convertimos el nombre a Mayúsculas para una comparación segura
    nombre_nuevo = tramite.nombre.upper()

    # 2. Validamos si el nombre contiene la palabra clave restrictiva
    if "VACANTE" in nombre_nuevo:
        # Buscamos en la base de datos si ya existe algún trámite que contenga 'VACANTE'
        existe_vacante = db.query(models.TipoTramite).filter(
            models.TipoTramite.nombre.ilike("%VACANTE%")
        ).first()
        
        if existe_vacante:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Operación denegada: Ya existe el trámite '{existe_vacante.nombre}'. "
                       f"Solo se permite un tipo de trámite de VACANTE."
            )

    # 3. Si pasa la validación, creamos el registro
    nuevo = models.TipoTramite(**tramite.model_dump())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

@router.put("/tramites-tipos/{id}", response_model=schemas.TipoTramiteResponse)
def editar_tipo_tramite(id: int, tramite: schemas.TipoTramiteCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes ver esta información")
    """Edita un tipo de trámite existente con validación de integridad para VACANTE."""
    db_tramite = db.query(models.TipoTramite).filter(models.TipoTramite.id_tipo_tramite == id).first()
    
    if not db_tramite:
        raise HTTPException(status_code=404, detail="Trámite no encontrado")
    
    # 1. Convertimos el nuevo nombre a mayúsculas para comparar
    nombre_nuevo = tramite.nombre.upper()

    # 2. Si el usuario intenta ponerle "VACANTE" a un trámite...
    if "VACANTE" in nombre_nuevo:
        # Buscamos si ya existe OTRO trámite (con ID diferente) que tenga la palabra VACANTE
        existe_otro = db.query(models.TipoTramite).filter(
            models.TipoTramite.nombre.ilike("%VACANTE%"),
            models.TipoTramite.id_tipo_tramite != id  # Crucial: que no sea el mismo que estamos editando
        ).first()
        
        if existe_otro:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Conflicto de integridad: No se puede renombrar como '{tramite.nombre}' "
                       f"porque ya existe el trámite '{existe_otro.nombre}' configurado para procesos automáticos."
            )

    # 3. Aplicamos los cambios
    update_data = tramite.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_tramite, key, value)
    
    db.commit()
    db.refresh(db_tramite)
    return db_tramite

@router.patch("/tramites-tipos/{id}/estado")
def cambiar_estado_tramite(id: int, activo: bool, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes ver esta información")
    """Activa o desactiva un trámite."""
    db_tramite = db.query(models.TipoTramite).filter(models.TipoTramite.id_tipo_tramite == id).first()
    if not db_tramite:
        raise HTTPException(status_code=404, detail="Trámite no encontrado")
    
    db_tramite.activo = activo
    db.commit()
    return {"message": "Estado actualizado"}


# ==========================================
# 2. SOLICITUDES DE TRÁMITE (ALUMNOS)
# ==========================================

@router.post("/solicitudes/", response_model=schemas.SolicitudTramiteResponse)
async def solicitar_tramite(
    id_alumno: int = Form(...),
    id_tipo_tramite: int = Form(...),
    comentario_usuario: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db), 
    current_user: dict = Depends(get_current_user)  
):
    if current_user.get("rol") != "ALUMNO":
        raise HTTPException(status_code=403, detail="No puedes ver esta información")
    
    """
    Registra la solicitud, guarda el archivo adjunto si existe 
    y genera el pago si el trámite tiene costo.
    """
    # 1. Validar Tipo de Trámite
    tipo_tramite = db.query(models.TipoTramite).filter(models.TipoTramite.id_tipo_tramite == id_tipo_tramite).first()
    if not tipo_tramite:
        raise HTTPException(status_code=404, detail="Tipo de trámite no encontrado")

    # 2. Gestión de Archivo (Lógica similar a entregas-tarea)
    url_db = None
    if file:
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail="Formato de archivo no permitido.")
        
        # Crear carpeta si no existe
        absolute_folder = os.path.join(BASE_DIR, UPLOAD_DIR)
        os.makedirs(absolute_folder, exist_ok=True)

        # Nombre único
        unique_filename = f"tramite_{id_alumno}_{uuid.uuid4().hex[:8]}{file_ext}"
        file_path = os.path.join(absolute_folder, unique_filename)

        # Guardado físico
        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            url_db = f"/{UPLOAD_DIR}/{unique_filename}".replace("\\", "/")
        except Exception as e:
            raise HTTPException(status_code=500, detail="Error al guardar el archivo adjunto.")

    # 3. Determinar estado inicial
    estado_inicial = "PAGADO_PENDIENTE_REV" if tipo_tramite.costo <= 0 else "PENDIENTE_PAGO"

    # 4. Crear la Solicitud en DB
    nueva_solicitud = models.SolicitudTramite(
        id_alumno=id_alumno,
        id_tipo_tramite=id_tipo_tramite,
        comentario_usuario=comentario_usuario,
        archivo_adjunto=url_db, # Este campo debe existir en tu modelo models.SolicitudTramite
        estado=estado_inicial
    )
    db.add(nueva_solicitud)
    db.commit()
    db.refresh(nueva_solicitud)

    # 5. Lógica de Pago: genera el pago pendiente del trámite
    if tipo_tramite.costo > 0:
        alumno = db.query(user_models.Alumno).filter(user_models.Alumno.id_alumno == id_alumno).first()
        id_usuario_responsable = alumno.id_usuario if alumno else None

        # El período puede ser un Enum; usamos su .value para el concepto legible
        periodo = getattr(tipo_tramite.periodo_academico, "value", tipo_tramite.periodo_academico)

        nuevo_pago = models.Pago(
            id_usuario=id_usuario_responsable,
            id_alumno=id_alumno,
            id_solicitud_tramite=nueva_solicitud.id_solicitud_tramite,
            concepto=f"TRAMITE: {tipo_tramite.nombre} ({periodo})",
            monto=tipo_tramite.costo,
            monto_total=tipo_tramite.costo,
            estado="PENDIENTE",
            mora=0,
            # Fecha de vencimiento para que el pago sea visible en Recaudación
            # y pueda confirmarse (además del pago vía BCP). El plazo lo define
            # el tipo de trámite (dias_vencimiento).
            fecha_vencimiento=date.today() + timedelta(days=(tipo_tramite.dias_vencimiento or 15)),
        )
        db.add(nuevo_pago)
        db.commit()

    return nueva_solicitud

@router.get("/solicitudes/alumno/{id_alumno}", response_model=List[schemas.SolicitudTramiteResponse])
def listar_mis_solicitudes(id_alumno: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ALUMNO":
        raise HTTPException(status_code=403, detail="No puedes ver esta información")

    return db.query(models.SolicitudTramite)\
             .options(joinedload(models.SolicitudTramite.tipo))\
             .filter(models.SolicitudTramite.id_alumno == id_alumno)\
             .order_by(models.SolicitudTramite.fecha_solicitud.desc())\
             .all()

# ==========================================
# 3. PAGOS
# ==========================================

@router.post("/pagos/", response_model=schemas.PagoResponse)
def crear_pago(pago: schemas.PagoCreate, db: Session = Depends(get_db), current_user: dict = Depends(require_roles("ADMIN"))):
    nuevo = models.Pago(**pago.model_dump())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

@router.get("/bcp/consulta/{dni}", response_model=List[schemas.PagoResponse])
def consulta_deuda_bcp(dni: str, db: Session = Depends(get_db), _svc: bool = Depends(require_service_key("BCP_API_KEY"))):
    """
    Endpoint que consumirá el BCP para consultar deudas pendientes por DNI.
    Requiere la credencial de servicio del banco (header X-Service-Key).
    """
    # Buscamos al alumno por DNI
    alumno = db.query(user_models.Alumno).filter(user_models.Alumno.dni == dni).first()
    if not alumno:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    # Buscamos todos sus pagos pendientes
    pagos_pendientes = db.query(models.Pago).filter(
        models.Pago.id_alumno == alumno.id_alumno,
        models.Pago.estado == "PENDIENTE"
    ).all()
    
    return pagos_pendientes

@router.post("/bcp/notificar-pago")
def notificar_pago_bcp(payload: schemas.BCPWebhookPayload, db: Session = Depends(get_db), _svc: bool = Depends(require_service_key("BCP_API_KEY"))):
    """
    Recibe la confirmación de pago del banco y actualiza el sistema.
    Requiere la credencial de servicio del banco (header X-Service-Key).
    """
    # 1. Buscar el pago en la base de datos (puedes buscar por ID o por concepto/alumno)
    # Aquí usamos una lógica simplificada: buscar el pago pendiente más antiguo del alumno
    alumno = db.query(user_models.Alumno).filter(user_models.Alumno.dni == payload.dni_alumno).first()
    if not alumno:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    pago = db.query(models.Pago).filter(
        models.Pago.id_alumno == alumno.id_alumno,
        models.Pago.estado == "PENDIENTE",
        models.Pago.monto_total == payload.monto_pagado
    ).first()

    if not pago:
        raise HTTPException(status_code=404, detail="No se encontró un pago pendiente que coincida")

    # 2. Actualizar el pago
    pago.estado = "PAGADO"
    pago.fecha_pago = payload.fecha_operacion
    pago.codigo_operacion_bcp = payload.codigo_operacion
    pago.json_respuesta_banco = str(payload.model_dump()) # Guardamos el log completo

    # 3. SI EL PAGO ERA UN TRÁMITE, actualizar la solicitud
    if pago.id_solicitud_tramite:
        solicitud = db.query(models.SolicitudTramite).filter(
            models.SolicitudTramite.id_solicitud_tramite == pago.id_solicitud_tramite
        ).first()
        if solicitud:
            solicitud.estado = "PAGADO_PENDIENTE_REV"

    db.commit()
    return {"status": "SUCCESS", "message": "Sistema actualizado"}


@router.patch("/admin/actualizar-precios-masivo")
def actualizar_precios_pension(payload: schemas.ActualizacionCostosMasiva, db: Session = Depends(get_db), current_user: dict = Depends(require_roles("ADMIN"))):
    """
    Actualiza el costo de las pensiones restantes del año escolar activo.
    """
    # 1. Obtener el año escolar actual dinámicamente
    # Suponiendo que tienes un modelo AnioEscolar
    anio_activo = db.query(academic_models.AnioEscolar).filter(academic_models.AnioEscolar.estado == 'ACTIVO').first()
    
    if not anio_activo:
        # Fallback al año actual si no hay uno marcado como activo
        anio_id = payload.id_anio_escolar 
    else:
        anio_id = anio_activo.id_anio_escolar

    # 2. Update masivo usando JOIN con matricula para asegurar el año correcto
    query = db.query(models.Pago).join(er_models.Matricula).filter(
        er_models.Matricula.id_anio_escolar == anio_id,
        models.Pago.concepto.contains(payload.concepto_filtro),
        models.Pago.estado == "PENDIENTE",
        func.extract('month', models.Pago.fecha_vencimiento) >= payload.mes_inicio
    )

    count = query.update({
        "monto": payload.nuevo_monto,
        "monto_total": payload.nuevo_monto + models.Pago.mora
    }, synchronize_session=False)

    db.commit()
    return {"message": f"Se actualizaron {count} registros de pago para el ciclo {anio_id}"}

@router.get("/solicitudes/pendientes-revision", response_model=List[schemas.SolicitudTramiteResponse])
def listar_solicitudes_pendientes(db: Session = Depends(get_db), current_user: dict = Depends(require_roles("ADMIN"))):
    """Lista las solicitudes que ya fueron pagadas pero aún no tienen dictamen administrativo."""
    return db.query(models.SolicitudTramite)\
             .options(joinedload(models.SolicitudTramite.tipo),
                 joinedload(models.SolicitudTramite.alumno))\
             .filter(models.SolicitudTramite.estado == "PAGADO_PENDIENTE_REV")\
             .all()

@router.get("/pagos/", response_model=List[schemas.PagoResponse])
def listar_pagos_filtrados(
    busqueda: str = None,
    tipo: str = None,
    anio: int = None,
    criterio_fecha: str = "pago",
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles("ADMIN"))
):
    # Aplicar moras antes de devolver resultados para que los montos estén siempre actualizados
    FinanceService.aplicar_moras_pagos_vencidos(db)

    query = db.query(models.Pago)
    filtro_anio = anio if anio else datetime.now().year

    # 1. Filtro por Año dinámico
    if criterio_fecha == "vencimiento":
        query = query.filter(
            extract('year', models.Pago.fecha_vencimiento) == filtro_anio,
            models.Pago.estado == "PENDIENTE"
        )
        orden = models.Pago.fecha_vencimiento.asc()
    else:
        query = query.filter(extract('year', models.Pago.fecha_pago) == filtro_anio)
        orden = models.Pago.fecha_pago.desc()

    # 2. Búsqueda Avanzada (Concepto o DNI)
    if busqueda:
        # Usamos outerjoin para evitar perder pagos sin alumno asignado por error
        query = query.outerjoin(user_models.Alumno, models.Pago.id_alumno == user_models.Alumno.id_alumno).filter(
            (models.Pago.concepto.ilike(f"%{busqueda}%")) |
            (user_models.Alumno.dni.ilike(f"%{busqueda}%"))
        )

    # 3. Filtro Exacto por CATEGORÍA (NUEVO)
    if tipo and tipo != "TODOS":
        query = query.outerjoin(models.TipoPago, models.Pago.id_tipo_pago == models.TipoPago.id_tipo_pago).filter(
            models.TipoPago.categoria == tipo
        )

    return query.order_by(orden).all()

@router.patch("/solicitudes/{id}/dictamen")
def dar_dictamen_solicitud(id: int, payload: schemas.DictamenSolicitud, db: Session = Depends(get_db), current_user: dict = Depends(require_roles("ADMIN"))):
    solicitud = db.query(models.SolicitudTramite).filter(models.SolicitudTramite.id_solicitud_tramite == id).first()
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    
    solicitud.estado = payload.estado  # "APROBADO" o "RECHAZADO"
    solicitud.respuesta_administrativa = payload.respuesta_administrativa
    db.commit()
    return {"message": "Dictamen registrado correctamente"}

def calcular_fecha_real(mm_dd_str: str) -> date:
    mes, dia = map(int, mm_dd_str.split("-"))
    hoy = date.today()
    anio_pago = hoy.year
    if hoy.month >= 10 and mes <= 6:
        anio_pago += 1
    try:
        return date(anio_pago, mes, dia)
    except ValueError:
        return date(anio_pago, mes, dia - 1)

NOMBRES_MES = ["", "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
               "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]

@router.patch("/pagos/{id_pago}/confirmar-manual")
def confirmar_pago_manual(id_pago: int, db: Session = Depends(get_db), current_user: dict = Depends(require_roles("ADMIN"))):
    pago = db.query(models.Pago).filter(models.Pago.id_pago == id_pago).first()

    if not pago:
        raise HTTPException(status_code=404, detail="Pago no encontrado")

    if pago.estado == "PAGADO":
        raise HTTPException(status_code=400, detail="Este pago ya fue procesado")

    pago.estado = "PAGADO"
    pago.fecha_pago = datetime.now()
    pago.codigo_operacion_bcp = "MANUAL-CAJA"

    if pago.id_solicitud_tramite:
        solicitud = db.query(models.SolicitudTramite).filter(
            models.SolicitudTramite.id_solicitud_tramite == pago.id_solicitud_tramite
        ).first()
        if solicitud:
            solicitud.estado = "PAGADO_PENDIENTE_REV"

    tipo_pago = db.query(models.TipoPago).filter(models.TipoPago.id_tipo_pago == pago.id_tipo_pago).first()

    if tipo_pago and tipo_pago.categoria == 'MATRICULA':
        anio_escolar = db.query(academic_models.AnioEscolar).filter(
            academic_models.AnioEscolar.activo == True
        ).first()

        if not anio_escolar:
            db.commit()
            return {"message": "Pago confirmado. No hay año escolar activo para generar pensiones."}

        # --- PENSIONES: un pago por cada mes del año escolar ---
        plantillas_pension = db.query(models.TipoPago).filter(
            models.TipoPago.categoria == 'PENSION',
            models.TipoPago.activo == True
        ).all()

        for plantilla in plantillas_pension:
            # El DD de fecha_vencimiento define el día de vencimiento de cada mes
            _, dia_venc = map(int, plantilla.fecha_vencimiento.split("-"))

            fecha_iter = anio_escolar.fecha_inicio.replace(day=1)
            fecha_fin_ae = anio_escolar.fecha_fin.replace(day=1)

            while fecha_iter <= fecha_fin_ae:
                mes = fecha_iter.month
                anio = fecha_iter.year
                concepto = f"PENSION {NOMBRES_MES[mes]} {anio}"

                ultimo_dia = calendar.monthrange(anio, mes)[1]
                fecha_venc_real = date(anio, mes, min(dia_venc, ultimo_dia))

                existe = db.query(models.Pago).filter(
                    models.Pago.id_alumno == pago.id_alumno,
                    models.Pago.concepto == concepto
                ).first()

                if not existe:
                    db.add(models.Pago(
                        id_alumno=pago.id_alumno,
                        id_tipo_pago=plantilla.id_tipo_pago,
                        concepto=concepto,
                        monto=plantilla.costo,
                        mora=0,
                        monto_total=plantilla.costo,
                        estado="PENDIENTE",
                        fecha_vencimiento=fecha_venc_real
                    ))

                if mes == 12:
                    fecha_iter = date(anio + 1, 1, 1)
                else:
                    fecha_iter = date(anio, mes + 1, 1)

        # --- MÓDULOS: un pago único por cada plantilla activa ---
        plantillas_modulo = db.query(models.TipoPago).filter(
            models.TipoPago.categoria == 'MODULO',
            models.TipoPago.activo == True
        ).all()

        for plantilla in plantillas_modulo:
            mes_venc, dia_venc = map(int, plantilla.fecha_vencimiento.split("-"))
            anio_venc = anio_escolar.fecha_inicio.year
            ultimo_dia = calendar.monthrange(anio_venc, mes_venc)[1]
            fecha_venc_real = date(anio_venc, mes_venc, min(dia_venc, ultimo_dia))

            existe = db.query(models.Pago).filter(
                models.Pago.id_alumno == pago.id_alumno,
                models.Pago.id_tipo_pago == plantilla.id_tipo_pago
            ).first()

            if not existe:
                db.add(models.Pago(
                    id_alumno=pago.id_alumno,
                    id_tipo_pago=plantilla.id_tipo_pago,
                    concepto=plantilla.nombre,
                    monto=plantilla.costo,
                    mora=0,
                    monto_total=plantilla.costo,
                    estado="PENDIENTE",
                    fecha_vencimiento=fecha_venc_real
                ))

    db.commit()
    return {"message": "Pago confirmado y pagos del año generados."}

@router.put("/pagos/{id_pago}", response_model=schemas.PagoResponse)
def editar_pago(id_pago: int, pago_data: schemas.PagoUpdate, db: Session = Depends(get_db), current_user: dict = Depends(require_roles("ADMIN"))):
    pago = db.query(models.Pago).filter(models.Pago.id_pago == id_pago).first()
    if not pago:
        raise HTTPException(status_code=404, detail="Pago no encontrado")
    for key, value in pago_data.model_dump(exclude_unset=True).items():
        setattr(pago, key, value)
    db.commit()
    db.refresh(pago)
    return pago

@router.delete("/pagos/{id_pago}")
def eliminar_pago(id_pago: int, db: Session = Depends(get_db), current_user: dict = Depends(require_roles("ADMIN"))):
    pago = db.query(models.Pago).filter(models.Pago.id_pago == id_pago).first()
    if not pago:
        raise HTTPException(status_code=404, detail="Pago no encontrado")
    db.delete(pago)
    db.commit()
    return {"message": "Pago eliminado correctamente"}


def _validar_acceso_pagos_alumno(id_alumno: int, current_user: dict, db: Session):
    """ADMIN puede ver los pagos de cualquier alumno; un ALUMNO solo los suyos."""
    if current_user.get("rol") == "ADMIN":
        return
    alumno = db.query(user_models.Alumno).filter(user_models.Alumno.id_alumno == id_alumno).first()
    if not alumno or alumno.id_usuario != current_user.get("id"):
        raise HTTPException(status_code=403, detail="No puedes ver los pagos de otro alumno")


@router.get("/alumnos/{id_alumno}/deudas")
def obtener_deudas_alumno(id_alumno: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    _validar_acceso_pagos_alumno(id_alumno, current_user, db)
    deudas = db.query(models.Pago).filter(
        models.Pago.id_alumno == id_alumno,
        models.Pago.estado == "PENDIENTE"
    ).order_by(models.Pago.fecha_vencimiento.asc()).all()
    return deudas

# Para el historial (Pagados)
@router.get("/pagos/historial/{id_alumno}")
def obtener_historial_alumno(id_alumno: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    _validar_acceso_pagos_alumno(id_alumno, current_user, db)
    return db.query(models.Pago).filter(
        models.Pago.id_alumno == id_alumno,
        models.Pago.estado == "PAGADO" # Asumo que cambias el estado a 'PAGADO' tras el pago
    ).order_by(models.Pago.fecha_pago.desc()).all()

#-- Estos deberiamos ajustarlos en el cron pero nse como hacerlo :C
@router.post("/tareas/generar-pensiones-mes")
def ejecutar_generacion_mensual(db: Session = Depends(get_db), _svc: bool = Depends(require_service_key("CRON_SECRET"))):
    """
    Endpoint diseñado para ser llamado por un Cron Job el día 1 de cada mes.
    """
    hoy = datetime.now()
    
    # 1. Buscamos años escolares que estén marcados como activos
    anios_activos = db.query(academic_models.AnioEscolar).filter(
        academic_models.AnioEscolar.activo == True
    ).all()
    
    if not anios_activos:
        return {"message": "No hay años escolares activos para generar pensiones."}

    total_generados = 0
    
    for anio in anios_activos:
        # 2. Buscamos todas las matrículas vigentes de ese año
        matriculas = db.query(er_models.Matricula).filter(
            er_models.Matricula.id_anio_escolar == anio.id_anio_escolar,
            er_models.Matricula.estado == "MATRICULADO"
        ).all()

        for m in matriculas:
            # 3. Usamos el Service para generar la pensión (el service ya evita duplicados)
            FinanceService.generar_pension_mensual(
                db=db,
                id_alumno=m.id_alumno,
                id_matricula=m.id_matricula,
                tipo_periodo=m.tipo_matricula, # REGULAR o VERANO
                mes=hoy.month,
                anio=hoy.year
            )
            total_generados += 1

    return {"message": f"Proceso completado. Se revisaron {total_generados} alumnos."}

@router.post("/tareas/actualizar-moras")
def actualizar_moras_diarias(db: Session = Depends(get_db), _svc: bool = Depends(require_service_key("CRON_SECRET"))):
    """
    Endpoint para ser llamado por un Cron Job diariamente a medianoche.
    """
    cantidad = FinanceService.aplicar_moras_pagos_vencidos(db)
    return {"message": f"Se aplicó mora a {cantidad} pagos vencidos."}

# ==========================================
# 5. TIPOS DE PAGO (Pensiones, Matriculas, etc)
# ==========================================
@router.get("/tipos-pago", response_model=List[schemas.TipoPagoResponse])
def listar_tipos_pago(db: Session = Depends(get_db), current_user: dict = Depends(require_roles("ADMIN"))):
    return db.query(models.TipoPago).all()

@router.post("/tipos-pago", response_model=schemas.TipoPagoResponse)
def crear_tipo_pago(tipo: schemas.TipoPagoCreate, db: Session = Depends(get_db), current_user: dict = Depends(require_roles("ADMIN"))):
    nuevo_tipo = models.TipoPago(**tipo.model_dump())
    db.add(nuevo_tipo)
    db.commit()
    db.refresh(nuevo_tipo)
    return nuevo_tipo

@router.put("/tipos-pago/{id}", response_model=schemas.TipoPagoResponse)
def editar_tipo_pago(id: int, tipo: schemas.TipoPagoCreate, db: Session = Depends(get_db), current_user: dict = Depends(require_roles("ADMIN"))):
    db_tipo = db.query(models.TipoPago).filter(models.TipoPago.id_tipo_pago == id).first()
    if not db_tipo:
        raise HTTPException(status_code=404, detail="Tipo de pago no encontrado")
    
    for key, value in tipo.model_dump().items():
        setattr(db_tipo, key, value)
        
    db.commit()
    db.refresh(db_tipo)
    return db_tipo

@router.delete("/tipos-pago/{id}")
def eliminar_tipo_pago(id: int, db: Session = Depends(get_db), current_user: dict = Depends(require_roles("ADMIN"))):
    db_tipo = db.query(models.TipoPago).filter(models.TipoPago.id_tipo_pago == id).first()
    if not db_tipo:
        raise HTTPException(status_code=404, detail="No encontrado")
    db.delete(db_tipo)
    db.commit()
    return {"message": "Eliminado correctamente"}