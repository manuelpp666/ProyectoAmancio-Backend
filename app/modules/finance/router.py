from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import List
from app.db.database import get_db
from . import models, schemas

from app.modules.users import models as user_models

router = APIRouter(prefix="/finance", tags=["Finanzas"])

# ==========================================
# 1. GESTIÓN DE TIPOS DE TRÁMITE (ADMIN)
# ==========================================

@router.get("/tramites-tipos/", response_model=List[schemas.TipoTramiteResponse])
def listar_tipos_tramite(db: Session = Depends(get_db)):
    """Lista todos los tipos de trámite configurados en el sistema."""
    return db.query(models.TipoTramite).all()

@router.post("/tramites-tipos/", response_model=schemas.TipoTramiteResponse)
def crear_tipo_tramite(tramite: schemas.TipoTramiteCreate, db: Session = Depends(get_db)):
    """Crea un nuevo tipo de trámite (Ej: Certificado de Estudios)."""
    nuevo = models.TipoTramite(**tramite.model_dump())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

@router.put("/tramites-tipos/{id}", response_model=schemas.TipoTramiteResponse)
def editar_tipo_tramite(id: int, tramite: schemas.TipoTramiteCreate, db: Session = Depends(get_db)):
    """Edita un tipo de trámite existente."""
    db_tramite = db.query(models.TipoTramite).filter(models.TipoTramite.id_tipo_tramite == id).first()
    if not db_tramite:
        raise HTTPException(status_code=404, detail="Trámite no encontrado")
    
    db_tramite.nombre = tramite.nombre
    db_tramite.costo = tramite.costo
    db_tramite.requisitos = tramite.requisitos
    db_tramite.alcance = tramite.alcance
    db_tramite.grados_permitidos = tramite.grados_permitidos
    db_tramite.activo = tramite.activo
    
    db.commit()
    db.refresh(db_tramite)
    return db_tramite

@router.patch("/tramites-tipos/{id}/estado")
def cambiar_estado_tramite(id: int, activo: bool, db: Session = Depends(get_db)):
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
def solicitar_tramite(solicitud: schemas.SolicitudTramiteCreate, db: Session = Depends(get_db)):
    """
    Registra la solicitud y GENERA AUTOMÁTICAMENTE EL PAGO PENDIENTE.
    """
    # 1. Obtener costo del trámite
    tipo_tramite = db.query(models.TipoTramite).filter(models.TipoTramite.id_tipo_tramite == solicitud.id_tipo_tramite).first()
    if not tipo_tramite:
        raise HTTPException(status_code=404, detail="Tipo de trámite no encontrado")

    # 2. Crear Solicitud (Estado: PENDIENTE_PAGO)
    nueva_solicitud = models.SolicitudTramite(**solicitud.model_dump())
    nueva_solicitud.estado = "PENDIENTE_PAGO"
    db.add(nueva_solicitud)
    db.commit()
    db.refresh(nueva_solicitud)

    # 3. Obtener ID de usuario del alumno (para el registro del pago)
    # Buscamos al alumno para saber su id_usuario
    alumno = db.query(user_models.Alumno).filter(user_models.Alumno.id_alumno == solicitud.id_alumno).first()
    id_usuario_responsable = alumno.id_usuario if alumno else None

    # 4. Crear Pago (Estado: PENDIENTE)
    nuevo_pago = models.Pago(
        id_usuario=id_usuario_responsable, # El sistema o el propio alumno lo generó
        id_alumno=solicitud.id_alumno,
        id_solicitud_tramite=nueva_solicitud.id_solicitud_tramite,
        concepto=f"TRAMITE: {tipo_tramite.nombre}",
        monto=tipo_tramite.costo,
        monto_total=tipo_tramite.costo,
        estado="PENDIENTE",
        mora=0
    )
    db.add(nuevo_pago)
    db.commit()

    return nueva_solicitud

@router.get("/solicitudes/alumno/{id_alumno}", response_model=List[schemas.SolicitudTramiteResponse])
def listar_mis_solicitudes(id_alumno: int, db: Session = Depends(get_db)):
    return db.query(models.SolicitudTramite)\
             .options(joinedload(models.SolicitudTramite.tipo_tramite))\
             .filter(models.SolicitudTramite.id_alumno == id_alumno)\
             .order_by(models.SolicitudTramite.fecha_solicitud.desc())\
             .all()

# ==========================================
# 3. PAGOS
# ==========================================

@router.post("/pagos/", response_model=schemas.PagoResponse)
def crear_pago(pago: schemas.PagoCreate, db: Session = Depends(get_db)):
    nuevo = models.Pago(**pago.model_dump())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo