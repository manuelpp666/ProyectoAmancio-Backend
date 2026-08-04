from sqlalchemy import Column, Integer, String, Boolean, Date, ForeignKey, CHAR
from sqlalchemy.orm import relationship
from app.db.database import Base

# ... (AnioEscolar, Nivel, Grado se quedan igual) ...

class AnioEscolar(Base):
    __tablename__ = "anio_escolar"

    id_anio_escolar = Column(String(6), primary_key=True)
    fecha_inicio = Column(Date, nullable=False)
    fecha_fin = Column(Date, nullable=True)
    activo = Column(Boolean, default=False)
    tipo = Column(String(20), default="REGULAR")
    
    # --- AGREGAR ESTOS DOS CAMPOS ---
    inicio_inscripcion = Column(Date, nullable=True)
    fin_inscripcion = Column(Date, nullable=True)
    # -------------------------------

class Nivel(Base):
    __tablename__ = "nivel"
    id_nivel = Column(Integer, primary_key=True)
    nombre = Column(String(20), nullable=False)
    grados = relationship("Grado", back_populates="nivel", order_by="Grado.orden")


class Grado(Base):
    __tablename__ = "grado"
    id_grado = Column(Integer, primary_key=True)
    id_nivel = Column(Integer, ForeignKey("nivel.id_nivel"))
    nombre = Column(String(20), nullable=False)
    orden = Column(Integer, nullable=False)
    
    # Relación opcional para ver el nivel desde el grado
    nivel = relationship("Nivel", back_populates="grados")
    planes_estudio = relationship("PlanEstudio", back_populates="grado")

class Seccion(Base):
    __tablename__ = "seccion"
    id_seccion = Column(Integer, primary_key=True)
    id_grado = Column(Integer, ForeignKey("grado.id_grado"))
    # NUEVO CAMPO: Conexión con el año escolar
    id_anio_escolar = Column(CHAR(6), ForeignKey("anio_escolar.id_anio_escolar"), nullable=False)
    
    # 30 caracteres: primaria usa nombres de color ("Amarillo", "Azul") y no
    # solo la letra, así que no cabían en el VARCHAR(5) original.
    nombre = Column(String(30), nullable=False)  # Ej: "A", "B", "Amarillo", "Única"
    # BORRADO: aula = Column(String(20))
    vacantes = Column(Integer, default=30)

    # Relaciones útiles para consultas
    grado = relationship("Grado")
    anio_escolar = relationship("AnioEscolar")

# ... (Area, Curso, PlanEstudio se quedan igual) ...
class Area(Base):
    __tablename__ = "area"
    id_area = Column(Integer, primary_key=True)
    nombre = Column(String(100), nullable=False)

class Curso(Base):
    __tablename__ = "curso"
    id_curso = Column(Integer, primary_key=True)
    id_area = Column(Integer, ForeignKey("area.id_area"))
    nombre = Column(String(100), nullable=False)
    minutos_semanales = Column(Integer, default=0)
    # Marca para el año académico de verano
    es_verano = Column(Boolean, default=False)
    tipo_verano = Column(String(20), nullable=True)  # FIJO / TALLER (solo si es_verano)
    # Grupo/aula de verano al que pertenece un curso FIJO
    # (PRIM_1_2, PRIM_3_4, PRIM_5_6, SEC_1, SEC_2, SEC_3, PRE_ACADEMIA)
    grupo_verano = Column(String(20), nullable=True)

class PlanEstudio(Base):
    __tablename__ = "plan_estudio"
    id_plan_estudio = Column(Integer, primary_key=True)
    id_curso = Column(Integer, ForeignKey("curso.id_curso"))
    id_grado = Column(Integer, ForeignKey("grado.id_grado"))
    grado = relationship("Grado", back_populates="planes_estudio")
    curso = relationship("Curso")