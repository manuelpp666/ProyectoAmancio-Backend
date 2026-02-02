from pydantic import BaseModel
from decimal import Decimal
from typing import Optional
from datetime import date

class PagoCreate(BaseModel):
    id_alumno: int
    concepto: str
    monto: Decimal
    mora: Decimal = Decimal(0)
    monto_total: Decimal
    id_matricula: Optional[int] = None
    id_solicitud_tramite: Optional[int] = None

class PagoResponse(PagoCreate):
    id_pago: int
    estado: str
    class Config: from_attributes = True

class TramiteCreate(BaseModel):
    id_alumno: int
    id_tipo_tramite: int
    comentario_usuario: Optional[str] = None

class TramiteResponse(TramiteCreate):
    id_solicitud_tramite: int
    estado: str
    class Config: from_attributes = True