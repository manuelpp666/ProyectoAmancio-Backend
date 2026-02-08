from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import date

# --- Año Escolar ---
class AnioEscolarCreate(BaseModel):
    id_anio_escolar: str
    fecha_inicio: date
    fecha_fin: date
    activo: bool = True
    tipo: str # "REGULAR" o "VERANO"

class AnioEscolarResponse(AnioEscolarCreate):
    class Config: from_attributes = True

# Agrega este schema para la acción de copiar
class CopiarEstructuraRequest(BaseModel):
    anio_origen: str
    anio_destino: str

# --- Seccion ---
class SeccionBase(BaseModel):
    id_grado: int
    id_anio_escolar: str # <--- NUEVO: Obligatorio
    nombre: str
    vacantes: int = 30
    # BORRADO: aula

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

