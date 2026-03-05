from sqlalchemy import Column, Integer, String, Text, DateTime,Enum
from sqlalchemy.sql import func
from app.db.database import Base

class PaginaConfiguracion(Base):
    __tablename__ = "pagina_configuracion"

    id = Column(Integer, primary_key=True, index=True)
    seccion = Column(String(50), nullable=False, index=True)
    clave = Column(String(100), nullable=False, unique=True)
    valor = Column(Text, nullable=False)
    tipo = Column(Enum('text', 'rich_text', 'image', 'json', name='tipo_contenido'), default='text')
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())