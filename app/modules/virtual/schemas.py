from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict
from datetime import datetime
from typing import List, Optional

class TareaCreate(BaseModel):
    id_carga_academica: int
    titulo: str
    descripcion: Optional[str]
    fecha_entrega: datetime
    tipo_evaluacion: str = "TAREA" # TAREA, EXAMEN_PARCIAL o EXAMEN_BIMESTRAL
    bimestre: int
    peso: int = 0

class TareaResponse(TareaCreate):
    id_tarea: int
    titulo: str
    descripcion: Optional[str] # <--- ESTE ES EL CAMPO CLAVE
    fecha_entrega: datetime
    tipo_evaluacion: str
    bimestre: int
    estado: str

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
# --- Esquemas de Chat ---
class EntregaCreate(BaseModel):
    id_tarea: int
    id_alumno: int
    archivo_url: Optional[str]
    comentario_alumno: Optional[str]

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