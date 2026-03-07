from pydantic import BaseModel, ConfigDict
from datetime import datetime

#-- Esquema para la pagina principal
class ConfigBase(BaseModel):
    seccion: str
    clave: str
    valor: str
    tipo: str

class ConfigCreate(ConfigBase):
    pass

class ConfigUpdate(BaseModel):
    valor: str

class ConfigRead(ConfigBase):
    id: int
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)