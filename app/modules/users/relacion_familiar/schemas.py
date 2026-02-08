from pydantic import BaseModel, ConfigDict, Field
from typing import Optional


class RelacionFamiliarBase(BaseModel):
    id_alumno: int
    id_familiar: int
    tipo_parentesco: str

class RelacionFamiliarCreate(RelacionFamiliarBase):
    pass

class RelacionFamiliarResponse(RelacionFamiliarBase):
    id_relacion_familiar: int
    model_config = ConfigDict(from_attributes=True)