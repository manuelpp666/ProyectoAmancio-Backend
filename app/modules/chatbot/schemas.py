from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

class ChatbotResponse(BaseModel):
    id: int
    filename: str
    file_type: str
    status: str
    total_chunks: int
    fecha_creacion: datetime

    model_config = ConfigDict(from_attributes=True)