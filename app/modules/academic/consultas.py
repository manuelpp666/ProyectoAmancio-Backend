"""
Consultas académicas que se repiten en todo el backend.

Están aquí para no reescribirlas en cada módulo y, sobre todo, para poder
cachear el año escolar activo en un único sitio.
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.core.util import cache
from . import models

CLAVE_ANIO_ACTIVO = "anio_escolar_activo"
# El año activo cambia dos veces al año, así que se puede guardar bastante
# tiempo. Aun así se le pone caducidad para que un cambio hecho directamente en
# la base (sin pasar por la API) acabe reflejándose solo.
SEGUNDOS_CACHE = 300


def id_anio_activo(db: Session) -> Optional[str]:
    """
    Id del año escolar activo, cacheado.

    Se devuelve el id y no el objeto porque un objeto de SQLAlchemy pertenece a
    la sesión que lo creó: guardarlo en una caché compartida entre peticiones
    daría objetos «detached» en cuanto se cierre esa sesión.
    """
    def consultar():
        fila = db.query(models.AnioEscolar.id_anio_escolar).filter(
            models.AnioEscolar.activo.is_(True)
        ).first()
        return fila[0] if fila else None

    return cache.obtener(CLAVE_ANIO_ACTIVO, consultar, SEGUNDOS_CACHE)


def anio_activo(db: Session) -> Optional[models.AnioEscolar]:
    """El año escolar activo como objeto, para cuando hacen falta sus fechas."""
    id_anio = id_anio_activo(db)
    if not id_anio:
        return None
    return db.query(models.AnioEscolar).filter(
        models.AnioEscolar.id_anio_escolar == id_anio
    ).first()


def olvidar_anio_activo() -> None:
    """A llamar después de tocar el campo `activo` de cualquier año escolar."""
    cache.invalidar(CLAVE_ANIO_ACTIVO)
