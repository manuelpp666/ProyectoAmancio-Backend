from pydantic import BaseModel, ConfigDict
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
    model_config = ConfigDict(from_attributes=True)

# --- Schemas Asistencia ---
class AsistenciaCreate(BaseModel):
    id_matricula: int
    fecha: date
    estado: str
    observacion: Optional[str] = None

class AsistenciaResponse(AsistenciaCreate):
    id_asistencia: int
    model_config = ConfigDict(from_attributes=True)


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
    url_perfil: Optional[str]

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
    id_docente: Optional[int] = None


class CursoDocenteResponse(BaseModel):
    id_carga: int
    curso_nombre: str
    grado_nombre: str
    seccion_nombre: str
    alumnos: int
    img: str

    model_config = ConfigDict(from_attributes=True)