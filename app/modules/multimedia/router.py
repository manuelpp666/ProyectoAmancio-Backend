# -*- coding: utf-8 -*-
"""Subida de imágenes, videos y documentos al propio servidor.

TRES PUERTAS, CON PERMISOS DISTINTOS

  POST /multimedia/imagen              ADMIN. Editor Web, noticias, docentes
                                       y foto de perfil.
  POST /multimedia/video               ADMIN. El fondo en bucle del inicio.
  POST /multimedia/documento-admision  PÚBLICA. El formulario de admisión lo
                                       rellenan familias que aún no tienen
                                       cuenta. Por eso va limitada por
                                       conexión y solo acepta PDF e imágenes.

Todas devuelven `{"ruta": "/media/...", "tipo": ..., "bytes": ...}`. El
frontend le pone delante la dirección del backend y guarda la URL completa,
igual que antes guardaba la de Cloudinary: así ninguna pantalla que las
muestra tuvo que cambiar.
"""

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from app.core.util.security import require_roles
from app.modules.seguridad.service import ip_de

from . import service

router = APIRouter(prefix="/multimedia", tags=["Multimedia"])

# Un postulante sube cuatro documentos, y alguno lo repetirá si se equivoca.
# Doce cada diez minutos da margen de sobra a una familia y corta a quien
# intenta usar el formulario para llenar el disco.
SUBIDAS_ADMISION_MAXIMAS = 12
VENTANA_ADMISION_SEGUNDOS = 10 * 60
limitador_admision = service.LimitadorPorIP(SUBIDAS_ADMISION_MAXIMAS,
                                            VENTANA_ADMISION_SEGUNDOS)


@router.post("/imagen")
def subir_imagen(archivo: UploadFile = File(...),
                 current_user: dict = Depends(require_roles("ADMIN"))):
    return service.guardar_imagen(archivo)


@router.post("/video")
def subir_video(archivo: UploadFile = File(...),
                current_user: dict = Depends(require_roles("ADMIN"))):
    return service.guardar_video(archivo)


@router.post("/documento-admision")
def subir_documento_admision(request: Request, archivo: UploadFile = File(...)):
    espera = limitador_admision.esperar(ip_de(request))
    if espera:
        minutos = max(1, round(espera / 60))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(f"Se han subido demasiados archivos seguidos desde tu "
                    f"conexión. Espera {minutos} minuto{'s' if minutos != 1 else ''} "
                    f"y vuelve a intentarlo."),
            headers={"Retry-After": str(espera)},
        )
    return service.guardar_documento_admision(archivo)
