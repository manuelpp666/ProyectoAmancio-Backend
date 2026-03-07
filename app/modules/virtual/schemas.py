from pydantic import BaseModel, ConfigDict,Field, field_validator
from typing import Optional, List, Dict,Literal
from datetime import datetime

class TareaCreate(BaseModel):
    id_carga_academica: int
    titulo: str = Field(..., min_length=3, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=500)
    fecha_entrega: datetime
    tipo_evaluacion: Literal["TAREA", "EXAMEN_PARCIAL", "EXAMEN_BIMESTRAL"] = "TAREA" # TAREA, EXAMEN_PARCIAL o EXAMEN_BIMESTRAL
    bimestre: int = Field(..., ge=1, le=4)
    peso: int = Field(default=1, ge=1, le=100)

class TareaResponse(TareaCreate):
    id_tarea: int
    titulo: str
    descripcion: Optional[str] 
    fecha_entrega: datetime
    tipo_evaluacion: str
    bimestre: int
    estado: str
    archivo_adjunto_url: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

# --- Esquemas de Sábana de Notas (Modificados) ---

class EvaluacionInfo(BaseModel):
    id_tarea: int
    titulo: str
    tipo: str
    descripcion: Optional[str]
    fecha_entrega: datetime
    bimestre: int
    peso: int
    total_entregas: int  # Para mostrar cuántos archivos se han subido
    editable_total: bool # Para que el front sepa si bloquea campos o permite borrar
    archivo_adjunto_url: Optional[str] = None

class NotaAlumnoResponse(BaseModel):
    id_alumno: int
    nombres_completos: str
    notas: Dict[str, float]  # Cambiado a Dict[str, float] para mayor precisión
    promedio: float

class SabanaNotasResponse(BaseModel):
    evaluaciones: List[EvaluacionInfo] # Ahora usamos el modelo detallado
    alumnos_notas: List[NotaAlumnoResponse]


class NotasMasivasCreate(BaseModel):
    id_tarea: int
    notas: Dict[str, float] # { "15": 18.5, "16": 20.0 } donde la llave es el id_alumno como string
    @field_validator('notas')
    @classmethod
    def validar_rango_notas(cls, v):
        for alumno_id, nota in v.items():
            if not (0 <= nota <= 20):
                raise ValueError(f"La nota {nota} para el alumno {alumno_id} está fuera de rango (0-20)")
        return v
# --- Esquemas de Chat ---
class EntregaCreate(BaseModel):
    id_tarea: int
    id_alumno: int
    archivo_url: Optional[str]
    comentario_alumno: Optional[str] = Field(None, max_length=300)

class ConversacionCreate(BaseModel):
    usuario1_id: int
    usuario2_id: int

class MensajeCreate(BaseModel):
    id_conversacion: int
    remitente_id: int
    contenido: str

# --- Esquema para listar entregas con archivos (Nuevo) ---
class EntregaDetalleResponse(BaseModel):
    id_entrega: int
    alumno: str
    archivo_url: str
    comentario: Optional[str]
    fecha_envio: str
    calificacion: Optional[float]


#-- Esquema para la pagina principal
class ConfigBase(BaseModel):
    seccion: str
    clave: str
    valor: str
    tipo: str

class ConfigCreate(ConfigBase):
    pass

class ConfigUpdate(BaseModel):
    valor: str

class ConfigRead(ConfigBase):
    id: int
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)