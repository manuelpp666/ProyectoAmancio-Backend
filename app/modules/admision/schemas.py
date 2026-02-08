# app/modules/admission/schemas.py
from pydantic import BaseModel
from app.modules.users.alumno.schemas import AlumnoCreate
from app.modules.users.familiar.schemas import FamiliarCreate

class AdmisionPostulante(BaseModel):
    alumno: AlumnoCreate
    familiar: FamiliarCreate
    tipo_parentesco: str
    es_apoderado: bool = True
    vive_con_alumno: bool = True