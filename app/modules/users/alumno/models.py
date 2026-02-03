# app/modules/users/alumno/models.py
from sqlalchemy import Column, Integer, String, Boolean, Date, ForeignKey
from sqlalchemy.orm import relationship
from app.db.database import Base

class Alumno(Base):
    __tablename__ = "alumno"
    id_alumno = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuario.id_usuario"), unique=True)
    dni = Column(String(8), unique=True)
    nombres = Column(String(250), nullable=False)
    apellidos = Column(String(250), nullable=False)
    fecha_nacimiento = Column(Date)
    genero = Column(String(1))
    direccion = Column(String(300))
    enfermedad = Column(String(150))
    talla_polo = Column(String(5))
    colegio_procedencia = Column(String(100))
    relacion_fraternal = Column(Boolean, default=False)
    estado_ingreso = Column(String(20), default='POSTULANTE')

    # Relaciones
    usuario = relationship("Usuario")
    # matriculas = relationship("app.modules.enrollment.models.Matricula", back_populates="alumno") 
    # pagos = relationship("app.modules.finance.models.Pago", back_populates="alumno")