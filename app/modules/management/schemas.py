from pydantic import BaseModel, ConfigDict,Field, field_validator
from decimal import Decimal
from datetime import date, datetime
from typing import Optional,Literal

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
    bimestre: int = Field(..., ge=1, le=4)
    valor: Decimal = Field(..., ge=0, le=20, decimal_places=2)
    tipo_nota: str = 'PROMEDIO'

class NotaResponse(NotaCreate):
    id_nota: int
    fecha_registro: datetime
    model_config = ConfigDict(from_attributes=True)

# --- Schemas Asistencia ---
class AsistenciaCreate(BaseModel):
    id_matricula: int
    fecha: date
    estado: str
    observacion: Optional[str] = Field(None, max_length=255)

class AsistenciaResponse(AsistenciaCreate):
    id_asistencia: int
    model_config = ConfigDict(from_attributes=True)

# --- Registro de asistencia por lotes (toda una sección de una vez) ---
class AsistenciaLoteItem(BaseModel):
    id_matricula: int
    estado: Literal["P", "T", "F", "J"]
    observacion: Optional[str] = Field(None, max_length=255)

class AsistenciaLoteCreate(BaseModel):
    fecha: date
    registros: list[AsistenciaLoteItem]

class AsistenciaLoteResponse(BaseModel):
    guardados: int
    correos_encolados: int
    notificar: bool = True


class CursoEstudianteResponse(BaseModel):
    id_curso: int
    curso_nombre: str
    docente_nombres: Optional[str] = "No definido"
    docente_apellidos: Optional[str] = ""
    url_perfil_docente: Optional[str] = None

#-- Para la asignacion de docente a un curso
class DocenteBasicoResponse(BaseModel):
    id_docente: int
    nombres: str
    apellidos: str
    url_perfil: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class VinculoAcademicoResponse(BaseModel):
    id_seccion: int
    seccion_nombre: str
    grado_nombre: str
    id_curso: int
    curso_nombre: str
    id_carga_academica: Optional[int]
    docente: Optional[DocenteBasicoResponse]

    model_config = ConfigDict(from_attributes=True)

class CargaUpdate(BaseModel):
    id_docente: Optional[int] = Field(None, gt=0)


class CursoDocenteResponse(BaseModel):
    id_carga: int
    curso_nombre: str
    grado_nombre: Optional[str] = ""
    seccion_nombre: Optional[str] = ""
    alumnos: int = 0
    img: Optional[str] = ""

    model_config = ConfigDict(from_attributes=True)

# --- NUEVO: SCHEMAS DE TUTORÍA ---
class TutorSeccionCreate(BaseModel):
    id_anio_escolar: str
    id_seccion: int
    id_docente: int

class TutorResponse(BaseModel):
    id_tutor_seccion: int
    id_seccion: int
    seccion_nombre: str
    grado_nombre: str
    docente: Optional[DocenteBasicoResponse]

    model_config = ConfigDict(from_attributes=True)