from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import date

# --- Año Escolar ---
class AnioEscolarCreate(BaseModel):
    id_anio_escolar: str
    fecha_inicio: date
    fecha_fin: date
    activo: bool

class AnioEscolarResponse(AnioEscolarCreate):
    model_config = ConfigDict(from_attributes=True)

# --- Seccion ---
class SeccionBase(BaseModel):
    nombre: str
    aula: str
    vacantes: int
    id_grado: int

class SeccionCreate(SeccionBase): pass

class SeccionResponse(SeccionBase):
    id_seccion: int
    model_config = ConfigDict(from_attributes=True)

# --- Curso ---
class CursoBase(BaseModel):
    nombre: str
    id_area: int

class CursoCreate(CursoBase):
    pass

class CursoResponse(CursoBase):
    id_curso: int
    model_config = ConfigDict(from_attributes=True)

# --- 4. PLAN ESTUDIO (La relación intermedia) ---
class PlanEstudioCreate(BaseModel):
    id_curso: int
    id_grado: int

class PlanEstudioResponse(BaseModel):
    id_plan_estudio: int
    id_curso: int
    id_grado: int
    curso: CursoResponse # Para que al consultar el plan, veamos el nombre del curso
    model_config = ConfigDict(from_attributes=True)

# --- Grado ---

class GradoBase(BaseModel):
    nombre: str
    orden: int
    id_nivel: int

class GradoConSecciones(GradoBase):
    id_grado: int
    secciones: List[SeccionResponse] = []

class GradoCreate(GradoBase):
    pass

class GradoResponse(GradoBase):
    id_grado: int
    model_config = ConfigDict(from_attributes=True)

class GradoConCursos(GradoBase):
    id_grado: int
    planes_estudio: List[PlanEstudioResponse] = [] # Trae los cursos asignados a este grado
    model_config = ConfigDict(from_attributes=True)


# --- Nivel ---
class NivelBase(BaseModel):
    nombre: str

class NivelCreate(NivelBase):
    pass

class NivelResponse(NivelBase):
    id_nivel: int
    grados: List["GradoConSecciones"] = []
    model_config = ConfigDict(from_attributes=True)

class NivelConCursosResponse(NivelBase):
    id_nivel: int
    grados: List[GradoConCursos] = [] # Aquí está la clave
    model_config = ConfigDict(from_attributes=True)
# --- Area ---
class AreaBase(BaseModel):
    nombre: str

class AreaCreate(AreaBase):
    pass

class AreaResponse(AreaBase):
    id_area: int
    model_config = ConfigDict(from_attributes=True)

