from pydantic import BaseModel
from decimal import Decimal
from datetime import date, datetime
from typing import Optional

# --- Schemas Carga Académica ---
class CargaCreate(BaseModel):
    id_anio_escolar: str
    id_seccion: int
    id_curso: int
    id_docente: int

class CargaResponse(CargaCreate):
    id_carga_academica: int
    class Config: from_attributes = True

# --- Schemas Notas ---
class NotaCreate(BaseModel):
    id_matricula: int
    id_curso: int
    bimestre: int
    valor: Decimal
    tipo_nota: str = 'PROMEDIO'

class NotaResponse(NotaCreate):
    id_nota: int
    fecha_registro: datetime
    class Config: from_attributes = True

# --- Schemas Asistencia ---
class AsistenciaCreate(BaseModel):
    id_matricula: int
    fecha: date
    estado: str
    observacion: Optional[str] = None

class AsistenciaResponse(AsistenciaCreate):
    id_asistencia: int
    class Config: from_attributes = True


class CursoEstudianteResponse(BaseModel):
    id_curso: int
    curso_nombre: str
    docente_nombres: Optional[str] = "No definido"
    docente_apellidos: Optional[str] = ""
    url_perfil_docente: Optional[str] = None
