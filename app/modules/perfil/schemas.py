from pydantic import BaseModel, Field

class ChangePasswordSchema(BaseModel):
    username: str
    current_password: str
    new_password: str = Field(..., min_length=8)