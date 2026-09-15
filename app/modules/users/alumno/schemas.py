from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional
from urllib.parse import urlparse
from datetime import date
from app.core.util.utils import DniStr # Importante
from app.modules.users.familiar.schemas import FamiliarAlumnoCreate

class UsuarioEnAlumno(BaseModel):
    activo: bool
    username: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

def _validar_edad_escolar(v: Optional[date]) -> Optional[date]:
    if v:
        hoy = date.today()
        edad = hoy.year - v.year - ((hoy.month, hoy.day) < (v.month, v.day))
        if edad < 3:  # Edad mínima para inicial
            raise ValueError("El alumno debe tener al menos 3 años.")
        if edad > 20:  # Límite razonable para educación escolar
            raise ValueError("La edad del alumno excede el límite escolar permitido.")
    return v

# Hosts de donde pueden venir los documentos de admisión además del propio
# backend. Cloudinary queda mientras haya navegadores con la versión anterior
# del formulario en caché, que todavía sube allí.
_HOSTS_LEGADO_DOCUMENTOS = ("res.cloudinary.com",)


def _validar_url_documento(v: Optional[str]) -> Optional[str]:
    """Solo se aceptan documentos subidos por el propio formulario.

    El formulario de admisión es público. Sin esta comprobación cualquiera
    podía mandar en estos campos el enlace que quisiera, y quien revisa la
    postulación lo abriría creyendo que es el DNI del menor.

    Vacío se deja pasar tal cual: en verano los documentos no se piden.
    """
    if v is None or not v.strip():
        return v
    v = v.strip()
    if len(v) > 500:
        raise ValueError("La dirección del documento es demasiado larga.")
    partes = urlparse(v)
    if partes.scheme in ("http", "https") and partes.netloc:
        if partes.path.startswith("/media/admision/"):
            return v
        if (partes.hostname or "").lower() in _HOSTS_LEGADO_DOCUMENTOS:
            return v
    raise ValueError("El documento adjunto no es válido. Vuelve a subirlo.")


# 1. BASE: Tolerante para leer datos de la Base de Datos sin explotar
class AlumnoBase(BaseModel):
    nombres: str
    apellidos: str
    fecha_nacimiento: Optional[date] = None
    genero: Optional[str] = None
    direccion: Optional[str] = None
    enfermedad: Optional[str] = None
    talla_polo: Optional[str] = None
    colegio_procedencia: Optional[str] = None
    id_grado_ingreso: Optional[int] = None
    relacion_fraternal: Optional[bool] = False
    estado_ingreso: Optional[str] = 'POSTULANTE'
    # Documentos de admisión (año regular)
    doc_dni_menor: Optional[str] = None
    doc_dni_apoderado: Optional[str] = None
    doc_fum: Optional[str] = None
    doc_certificado_estudios: Optional[str] = None

# 2. CREATE: Estricto SOLO cuando se registra un alumno nuevo desde la web
class AlumnoCreate(AlumnoBase):
    dni: DniStr  # Validación automática aquí
    id_usuario: Optional[int] = None

    # Va aquí y no en AlumnoBase: la base también sirve para LEER alumnos, y
    # un documento antiguo con otro formato no puede tumbar un listado.
    @field_validator("doc_dni_menor", "doc_dni_apoderado", "doc_fum",
                     "doc_certificado_estudios")
    @classmethod
    def validar_documentos(cls, v):
        return _validar_url_documento(v)

    @field_validator('fecha_nacimiento')
    @classmethod
    def validar_edad(cls, v):
        return _validar_edad_escolar(v)

# 2b. UPDATE: edición desde el panel del administrador (datos del alumno + su usuario)
class AlumnoUpdate(AlumnoBase):
    dni: DniStr
    # Credenciales del usuario asociado. Ambas opcionales: solo se tocan si vienen.
    password: Optional[str] = Field(None, min_length=6, max_length=72)
    activo: Optional[bool] = None

    # El estado de admisión se decide en /decidir-admision, no se edita aquí.
    estado_ingreso: Optional[str] = Field(None, exclude=True)

    @field_validator('fecha_nacimiento')
    @classmethod
    def validar_edad(cls, v):
        return _validar_edad_escolar(v)

    @field_validator('nombres', 'apellidos')
    @classmethod
    def validar_no_vacio(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Debe tener al menos 2 caracteres.")
        return v

class GradoEnAlumno(BaseModel):
    id_grado: int
    nombre: str
    model_config = ConfigDict(from_attributes=True)

# 2c. Alta desde el panel del administrador: alumno y apoderado en una sola operación
class AlumnoConFamiliarCreate(BaseModel):
    alumno: AlumnoCreate
    familiar: FamiliarAlumnoCreate


class ReincorporarAlumnoRequest(BaseModel):
    id_grado: int
    id_seccion: Optional[int] = None
    generar_pagos: Optional[bool] = True


# 3. RESPONSE: Lo que se envía al Frontend
class AlumnoResponse(AlumnoBase):
    id_alumno: int
    id_usuario: Optional[int] = None
    dni: str 
    usuario: Optional[UsuarioEnAlumno] = None 
    motivo_rechazo: Optional[str] = None
    grado_ingreso: Optional[GradoEnAlumno] = None
    model_config = ConfigDict(from_attributes=True)