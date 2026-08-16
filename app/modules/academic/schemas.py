from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import date

# --- Año Escolar ---
class AnioEscolarCreate(BaseModel):
    id_anio_escolar: str
    fecha_inicio: date
    fecha_fin: date
    activo: bool = True
    tipo: str 
    
    # --- AGREGAR ESTOS CAMPOS NUEVOS ---
    inicio_inscripcion: Optional[date] = None
    fin_inscripcion: Optional[date] = None
    # -----------------------------------

class AnioEscolarResponse(AnioEscolarCreate):
    model_config = ConfigDict(from_attributes=True)


# Agrega este schema para la acción de copiar
class CopiarEstructuraRequest(BaseModel):
    anio_origen: str
    anio_destino: str

class InscripcionUpdate(BaseModel):
    inicio_inscripcion: date
    fin_inscripcion: date

# --- Bimestre ---
class BimestreItem(BaseModel):
    """Un bimestre suelto: su número (I a IV) y su rango de fechas."""
    numero: int = Field(..., ge=1, le=4)
    fecha_inicio: date
    fecha_fin: date

class BimestresUpdate(BaseModel):
    """Los cuatro bimestres a guardar de una vez (upsert por número)."""
    bimestres: List[BimestreItem]

class BimestresResponse(BaseModel):
    """Respuesta del calendario de bimestres de un año.

    `guardado` distingue si estas fechas ya las confirmó el colegio (True) o
    si son el reparto automático en cuatro tramos iguales que se calcula al
    vuelo porque todavía no hay nada guardado (False): el front debe avisar
    de que son aproximadas en ese caso.
    """
    id_anio_escolar: str
    guardado: bool
    bimestres: List[BimestreItem]

# --- Nivel ---
class NivelBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)

class NivelCreate(NivelBase):
    pass

class NivelSimpleResponse(NivelBase):
    id_nivel: int
    model_config = ConfigDict(from_attributes=True)

# --- Grado ---
class GradoBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    orden: int
    id_nivel: int

class GradoCreate(GradoBase):
    pass

class GradoResponse(GradoBase):
    id_grado: int
    nivel: Optional[NivelSimpleResponse] = None
    model_config = ConfigDict(from_attributes=True)

# --- Seccion ---
class SeccionBase(BaseModel):
    id_grado: int
    id_anio_escolar: str 
    nombre: str
    vacantes: int = Field(default=30, ge=0, le=50)
    
class SeccionCreate(SeccionBase): pass

class SeccionResponse(SeccionBase):
    id_seccion: int
    ocupadas: int = 0
    desglose_grados: Optional[List[dict]] = None
    grado: Optional[GradoResponse] = None
    model_config = ConfigDict(from_attributes=True)

class GradoConSecciones(GradoBase):
    id_grado: int
    secciones: List[SeccionResponse] = []
    model_config = ConfigDict(from_attributes=True)

# --- Curso ---
class CursoBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    id_area: int
    minutos_semanales: int = Field(default=0, ge=0)
    es_verano: bool = False
    tipo_verano: Optional[str] = None  # FIJO / TALLER
    grupo_verano: Optional[str] = None  # PRIM_1_2, ..., PRE_ACADEMIA

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

class GradoConCursos(GradoBase):
    id_grado: int
    planes_estudio: List[PlanEstudioResponse] = [] # Trae los cursos asignados a este grado
    model_config = ConfigDict(from_attributes=True)

class NivelResponse(NivelBase):
    id_nivel: int
    grados: List[GradoConSecciones] = []
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

#-- Para horario
class SeccionConDetalle(SeccionBase):
    id_seccion: int
    grado: Optional[GradoResponse] = None # Aquí incluimos el objeto grado
    
    model_config = ConfigDict(from_attributes=True)

class SeccionHorarioResponse(BaseModel):
    id_seccion: int
    nombre: str
    id_grado: int
    id_anio_escolar: str
    # Incluimos el grado completo para que el front tenga el nombre (1ero, 2do, etc.)
    grado: Optional[GradoResponse] = None 
    
    model_config = ConfigDict(from_attributes=True)