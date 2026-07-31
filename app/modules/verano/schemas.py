from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime

from app.modules.users.alumno.schemas import AlumnoCreate
from app.modules.users.familiar.schemas import FamiliarCreate


# --- Inscripción de EXTERNOS (formulario de admisión, modo verano) ---
class PostulanteVeranoExterno(BaseModel):
    alumno: AlumnoCreate
    familiar: FamiliarCreate
    tipo_parentesco: str
    id_anio_escolar: str            # año VERANO
    modalidad: str                  # CURSOS / TALLER / CURSOS_Y_TALLER
    cursos_ids: List[int] = []      # cursos fijos elegidos
    talleres_ids: List[int] = []    # talleres elegidos


# --- Inscripción de INTERNOS (panel del estudiante) ---
class InscripcionVeranoInterno(BaseModel):
    id_usuario: int
    id_anio_escolar: str
    modalidad: str                  # CURSOS / TALLER / CURSOS_Y_TALLER / NIVELACION
    cursos_ids: List[int] = []
    talleres_ids: List[int] = []


class CursoVeranoResponse(BaseModel):
    id_curso: int
    nombre: str
    tipo_verano: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class SolicitudVeranoResponse(BaseModel):
    id: int
    id_alumno: int
    alumno_nombre: Optional[str] = None
    alumno_dni: Optional[str] = None
    id_anio_escolar: Optional[str] = None
    grado_nombre: Optional[str] = None
    grupo_label: Optional[str] = None
    origen: Optional[str] = None
    modalidad: Optional[str] = None
    estado: Optional[str] = None
    estado_pago: Optional[str] = None
    monto: Optional[float] = None
    id_pago: Optional[int] = None
    cursos: List[str] = []
    fecha: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)
