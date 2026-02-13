from pydantic import BaseModel, ConfigDict
from decimal import Decimal
from typing import Optional
from datetime import date, datetime

# =======================
# 1. TIPOS DE TRÁMITE (Configuración - Admin)
# =======================
class TipoTramiteBase(BaseModel):
    nombre: str
    costo: Decimal
    requisitos: Optional[str] = None
    alcance: str = "TODOS"
    grados_permitidos: Optional[str] = None
    activo: bool = True

class TipoTramiteCreate(TipoTramiteBase):
    pass

class TipoTramiteResponse(TipoTramiteBase):
    id_tipo_tramite: int
    model_config = ConfigDict(from_attributes=True)


# =======================
# 2. SOLICITUDES (Uso - Alumno)
# =======================
class SolicitudTramiteBase(BaseModel):
    id_alumno: int
    id_tipo_tramite: int
    comentario_usuario: Optional[str] = None

class SolicitudTramiteCreate(SolicitudTramiteBase):
    pass

class SolicitudTramiteResponse(SolicitudTramiteBase):
    id_solicitud_tramite: int
    fecha_solicitud: datetime
    estado: str
    archivo_adjunto: Optional[str] = None
    respuesta_administrativa: Optional[str] = None
    
    # Opcional: Para mostrar detalles del tipo de trámite en la respuesta
    tipo_tramite: Optional[TipoTramiteResponse] = None
    
    model_config = ConfigDict(from_attributes=True)

# --- PAGO ---
class PagoBase(BaseModel):
    id_alumno: int
    id_matricula: Optional[int] = None
    concepto: str
    monto: Decimal
    mora: Decimal = Decimal(0)
    monto_total: Decimal

class PagoCreate(PagoBase):
    id_usuario: int # Quien registra (cajero)
    id_solicitud_tramite: Optional[int] = None

class PagoResponse(PagoBase):
    id_pago: int
    fecha_pago: Optional[datetime] = None
    estado: str
    codigo_operacion_bcp: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)