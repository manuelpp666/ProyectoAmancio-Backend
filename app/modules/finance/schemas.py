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

class AlumnoSimpleResponse(BaseModel):
    id_alumno: int
    nombres: str
    dni: str
    model_config = ConfigDict(from_attributes=True)

class SolicitudTramiteResponse(SolicitudTramiteBase):
    id_solicitud_tramite: int
    fecha_solicitud: datetime
    estado: str
    archivo_adjunto: Optional[str] = None
    respuesta_administrativa: Optional[str] = None
    
    # Opcional: Para mostrar detalles del tipo de trámite en la respuesta
    tipo: Optional[TipoTramiteResponse] = None
    alumno: Optional[AlumnoSimpleResponse]
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
    fecha_vencimiento: Optional[date] = None # <-- CRÍTICO para el cronograma 2025
    fecha_pago: Optional[datetime] = None
    estado: str
    codigo_operacion_bcp: Optional[str] = None
    # Incluir el log del banco solo para el Admin (puedes crear un PagoDetalleAdminResponse)
    json_respuesta_banco: Optional[str] = None 
    
    model_config = ConfigDict(from_attributes=True)

# =======================
# 3. INTEGRACIÓN BCP
# =======================
class BCPWebhookPayload(BaseModel):
    id_transaccion_banco: str
    dni_alumno: str
    monto_pagado: Decimal
    fecha_operacion: datetime
    codigo_operacion: str
    canal: str  # Agente, App, Ventanilla
    checksum: str # Por seguridad, el BCP suele enviar un hash de validación

class BCPResponse(BaseModel):
    status: str = "SUCCESS"
    message: str = "Pago procesado correctamente"

class ConsultaDeudaAlumno(BaseModel):
    dni: str
    nombre_alumno: str
    total_pendiente: Decimal
    proximo_vencimiento: Optional[date]

class ActualizacionCostosMasiva(BaseModel):
    mes_inicio: int 
    nuevo_monto: Decimal
    concepto_filtro: str = "PENSION"
    # Usamos un factory para que por defecto sea el año actual, 
    # pero permita que el Admin elija otro si es necesario.
    id_anio_escolar: str = str(datetime.now().year)

class DictamenSolicitud(BaseModel):
    estado: str  # "APROBADO" o "RECHAZADO"
    respuesta_administrativa: Optional[str] = None