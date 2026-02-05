from sqlalchemy import Column, Integer, String, DateTime, Enum
from app.db.database import Base
from datetime import datetime

class Chatbot(Base):
    __tablename__ = "chatbot"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    unique_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_type = Column(String(50))
    pinecone_index = Column(String(100))
    total_chunks = Column(Integer, default=0)
    status = Column(String(50), default="procesando")
    fecha_creacion = Column(DateTime, default=datetime.now)