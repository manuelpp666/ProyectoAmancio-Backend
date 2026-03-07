from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from decimal import Decimal
from typing import Optional, Literal
from datetime import date, datetime
from enum import Enum as PyEnum
# =======================
# 1. TIPOS DE TRÁMITE (Configuración - Admin)
# =======================
class PeriodoAcademicoSchema(str, PyEnum):
    REGULAR = "REGULAR"
    VERANO = "VERANO"
    AMBOS = "AMBOS"


class TipoTramiteBase(BaseModel):
    nombre: str
    costo: Decimal
    requisitos: Optional[str] = None
    alcance: Literal["TODOS", "GRADOS"] = "TODOS"
    grados_permitidos: Optional[str] = None
    activo: bool = True
    periodo_academico: PeriodoAcademicoSchema = PeriodoAcademicoSchema.REGULAR

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
    concepto: str = Field(..., min_length=3, max_length=150)
    monto: Decimal = Field(..., ge=0, decimal_places=2)
    mora: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)
    monto_total: Decimal = Field(..., ge=0, decimal_places=2)

    @model_validator(mode='after')
    def verificar_suma_total(self) -> 'PagoBase':
        if self.monto_total != (self.monto + self.mora):
            raise ValueError("El monto total debe ser la suma del monto y la mora")
        return self

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
    id_transaccion_banco: str = Field(..., min_length=5)
    dni_alumno: str = Field(..., pattern=r"^\d{8}$") # Fuerza que sean exactamente 8 dígitos
    monto_pagado: Decimal = Field(..., gt=0)
    fecha_operacion: datetime
    codigo_operacion: str = Field(..., min_length=1)
    canal: str 
    checksum: str = Field(..., min_length=32)

class BCPResponse(BaseModel):
    status: str = "SUCCESS"
    message: str = "Pago procesado correctamente"

class ConsultaDeudaAlumno(BaseModel):
    dni: str
    nombre_alumno: str
    total_pendiente: Decimal
    proximo_vencimiento: Optional[date]

class ActualizacionCostosMasiva(BaseModel):
    mes_inicio: int = Field(..., ge=1, le=12)
    nuevo_monto: Decimal = Field(..., gt=0)
    concepto_filtro: str = "PENSION"
    # Usamos un factory para que por defecto sea el año actual, 
    # pero permita que el Admin elija otro si es necesario.
    id_anio_escolar: str = str(datetime.now().year)

class DictamenSolicitud(BaseModel):
    estado: Literal["APROBADO", "RECHAZADO"]
    respuesta_administrativa: Optional[str] = None