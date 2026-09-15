# -*- coding: utf-8 -*-
"""Imágenes, videos y documentos guardados en el propio servidor.

POR QUÉ EXISTE
    Hasta septiembre de 2026 todo esto se subía a Cloudinary. La cuenta donde
    estaban las imágenes de la página principal se desactivó y la web se quedó
    sin ellas de un día para otro, sin que nada del sistema pudiera evitarlo.
    Guardarlas aquí quita esa dependencia.

QUÉ SE COMPRUEBA, Y POR QUÉ NO BASTA LA EXTENSIÓN
    El tipo se decide mirando los primeros bytes del archivo, no el nombre:
    un `foto.jpg` que por dentro es HTML o un script se rechaza. Para el
    formulario de admisión, que es público, eso es lo que impide que alguien
    use el servidor del colegio para alojar otra cosa.

    Las imágenes, además, se vuelven a dibujar desde cero y se guardan como
    WEBP. Eso hace tres cosas a la vez:
      - Una imagen "políglota" (válida como imagen y como otra cosa) deja de
        serlo: lo que se guarda es solo el dibujo.
      - Se borran los metadatos. Una foto de celular lleva dentro la
        ubicación GPS de donde se tomó, y un DNI escaneado en casa la del
        domicilio del alumno.
      - Pesa mucho menos. Una foto de 6 MB del celular queda en unos cientos
        de KB, que es lo que se descarga cada visitante.

    Los videos y los PDF no se re-dibujan (haría falta ffmpeg o reescribir el
    PDF): se comprueba que lo sean de verdad y se guardan tal cual.
"""

import io
import os
import shutil
import threading
import time
import uuid
import warnings
from collections import deque

import filetype
from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.util import archivos, media

MB = archivos.MB

MAX_IMAGEN_BYTES = 10 * MB
MAX_DOCUMENTO_BYTES = 10 * MB
# Cabe por debajo del corte de 30 MB por petición de main.py. Un fondo en
# bucle de 15 a 30 segundos, en MP4 y sin audio, ocupa entre 3 y 10 MB.
MAX_VIDEO_BYTES = 25 * MB

# Una imagen de 30 MP descomprimida ocupa unos 120 MB de memoria. Por encima
# se rechaza: una imagen de pocos KB puede declarar 60.000 x 60.000 píxeles y
# tumbar el servidor al abrirla ("bomba de descompresión").
MAX_PIXELES = 30_000_000

LADO_MAXIMO_IMAGEN = 2560      # nítido a pantalla completa en un monitor grande
LADO_MAXIMO_DOCUMENTO = 2400   # un DNI o un certificado siguen leyéndose bien
CALIDAD_WEBP = 82

CARPETA_IMAGENES = "imagenes"
CARPETA_VIDEOS = "videos"
CARPETA_ADMISION = "admision"

TIPOS_IMAGEN = {"image/jpeg", "image/png", "image/webp"}
TIPOS_VIDEO = {"video/mp4": ".mp4", "video/webm": ".webm"}
TROZO = MB


def _error(codigo: int, mensaje: str) -> HTTPException:
    return HTTPException(status_code=codigo, detail=mensaje)


def _medir(archivo: UploadFile, maximo: int, que: str) -> int:
    tamano = archivos.medir(archivo)
    if tamano == 0:
        raise _error(status.HTTP_400_BAD_REQUEST, "El archivo está vacío.")
    if tamano > maximo:
        raise _error(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                     f"El archivo pesa {archivos.legible(tamano)} y el máximo "
                     f"para {que} son {archivos.legible(maximo)}.")
    return tamano


def tipo_real(cabecera: bytes) -> str | None:
    """Tipo MIME según el contenido del archivo, no según su nombre."""
    encontrado = filetype.guess(cabecera[:8192])
    return encontrado.mime if encontrado else None


def _exigir_imagen(mime: str | None, permitidos: str) -> None:
    if mime in TIPOS_IMAGEN:
        return
    if mime in ("image/heic", "image/heif"):
        raise _error(status.HTTP_400_BAD_REQUEST,
                     "Las fotos HEIC del iPhone no se pueden usar tal cual. "
                     "Envíala como JPG, o en el iPhone ve a Ajustes → Cámara → "
                     "Formatos y elige «Más compatible».")
    raise _error(status.HTTP_400_BAD_REQUEST,
                 f"El archivo no es válido. Solo se aceptan {permitidos}.")


def procesar_imagen(datos: bytes, lado_maximo: int) -> bytes:
    """Vuelve a dibujar la imagen como WEBP, sin metadatos y a tamaño razonable."""
    try:
        with warnings.catch_warnings():
            # Pillow solo AVISA a partir de ~89 MP y lanza el doble. Se
            # convierte el aviso en error y además se pone un tope propio.
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            imagen = Image.open(io.BytesIO(datos))
            ancho, alto = imagen.size
            if ancho * alto > MAX_PIXELES:
                raise _error(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                             f"La imagen mide {ancho}×{alto} píxeles y es "
                             f"demasiado grande. Redúcela a menos de 5000 "
                             f"píxeles de lado y vuelve a subirla.")
            # En JPEG se decodifica directamente a menor escala: una foto de
            # 12 MP no llega a ocupar su tamaño completo en memoria.
            imagen.draft("RGB", (lado_maximo, lado_maximo))
            # Gira la foto según la orientación con la que se tomó; como los
            # metadatos se van a descartar, sin esto saldría acostada.
            imagen = ImageOps.exif_transpose(imagen)

            con_transparencia = (imagen.mode in ("RGBA", "LA", "PA")
                                 or (imagen.mode == "P" and "transparency" in imagen.info))
            imagen = imagen.convert("RGBA" if con_transparencia else "RGB")
            imagen.thumbnail((lado_maximo, lado_maximo), Image.Resampling.LANCZOS)

            salida = io.BytesIO()
            imagen.save(salida, "WEBP", quality=CALIDAD_WEBP, method=4)
            return salida.getvalue()
    except HTTPException:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError,
            Image.DecompressionBombWarning):
        raise _error(status.HTTP_400_BAD_REQUEST,
                     "La imagen está dañada o es demasiado grande para abrirla.")
    except (OSError, ValueError, SyntaxError, MemoryError) as e:
        print(f"[MULTIMEDIA][WARN] Imagen no procesable: {type(e).__name__}: {e}")
        raise _error(status.HTTP_400_BAD_REQUEST,
                     "No se pudo leer la imagen. Prueba a guardarla de nuevo "
                     "como JPG o PNG y vuelve a subirla.")


def _destino(subcarpeta: str, extension: str) -> tuple[str, str]:
    """(ruta en disco, URL relativa) para un archivo nuevo con nombre aleatorio.

    El nombre es un uuid completo: nadie puede adivinar la dirección de un
    documento de admisión probando nombres.
    """
    carpeta = media.carpeta(subcarpeta)
    try:
        os.makedirs(carpeta, exist_ok=True)
    except OSError as e:
        print(f"[MULTIMEDIA][ERROR] No se pudo crear {carpeta}: {e}")
        raise _error(status.HTTP_500_INTERNAL_SERVER_ERROR,
                     "Error de permisos en el servidor.")
    nombre = f"{uuid.uuid4().hex}{extension}"
    return (os.path.join(carpeta, nombre),
            f"{media.URL_PREFIJO}/{subcarpeta}/{nombre}")


def _escribir(destino: str, escribir) -> None:
    """Escribe a un temporal y lo renombra al final.

    Así nunca queda publicado un archivo a medias: o está entero o no está.
    """
    temporal = destino + ".subiendo"
    try:
        with open(temporal, "wb") as fh:
            escribir(fh)
        os.replace(temporal, destino)
    except OSError as e:
        try:
            if os.path.exists(temporal):
                os.remove(temporal)
        except OSError:
            pass
        print(f"[MULTIMEDIA][ERROR] No se pudo escribir {destino}: {e}")
        raise _error(status.HTTP_500_INTERNAL_SERVER_ERROR,
                     "No se pudo guardar el archivo en el servidor.")


def guardar_imagen(archivo: UploadFile, subcarpeta: str = CARPETA_IMAGENES,
                   lado_maximo: int = LADO_MAXIMO_IMAGEN) -> dict:
    _medir(archivo, MAX_IMAGEN_BYTES, "una imagen")
    datos = archivo.file.read()
    _exigir_imagen(tipo_real(datos), "imágenes JPG, PNG o WEBP")
    webp = procesar_imagen(datos, lado_maximo)
    destino, ruta = _destino(subcarpeta, ".webp")
    _escribir(destino, lambda fh: fh.write(webp))
    return {"ruta": ruta, "tipo": "imagen", "bytes": len(webp)}


def guardar_video(archivo: UploadFile) -> dict:
    tamano = _medir(archivo, MAX_VIDEO_BYTES, "un video")
    cabecera = archivo.file.read(8192)
    archivo.file.seek(0)
    mime = tipo_real(cabecera)
    if mime not in TIPOS_VIDEO:
        if mime == "video/quicktime":
            raise _error(status.HTTP_400_BAD_REQUEST,
                         "Los videos .MOV del iPhone hay que convertirlos a MP4 "
                         "antes de subirlos.")
        raise _error(status.HTTP_400_BAD_REQUEST,
                     "El archivo no es válido. Solo se aceptan videos MP4 o WEBM.")
    destino, ruta = _destino(CARPETA_VIDEOS, TIPOS_VIDEO[mime])
    # Se copia a trozos: 25 MB leídos de golpe multiplicarían la memoria por
    # cada subida simultánea.
    _escribir(destino, lambda fh: shutil.copyfileobj(archivo.file, fh, TROZO))
    return {"ruta": ruta, "tipo": "video", "bytes": tamano}


def guardar_documento_admision(archivo: UploadFile) -> dict:
    _medir(archivo, MAX_DOCUMENTO_BYTES, "un documento")
    datos = archivo.file.read()
    mime = tipo_real(datos)
    if mime == "application/pdf":
        destino, ruta = _destino(CARPETA_ADMISION, ".pdf")
        _escribir(destino, lambda fh: fh.write(datos))
        return {"ruta": ruta, "tipo": "pdf", "bytes": len(datos)}

    _exigir_imagen(mime, "documentos PDF o imágenes JPG, PNG o WEBP")
    webp = procesar_imagen(datos, LADO_MAXIMO_DOCUMENTO)
    destino, ruta = _destino(CARPETA_ADMISION, ".webp")
    _escribir(destino, lambda fh: fh.write(webp))
    return {"ruta": ruta, "tipo": "imagen", "bytes": len(webp)}


class LimitadorPorIP:
    """Cuántas veces puede hacer algo una misma conexión en una ventana de tiempo.

    Vive en la memoria del proceso. Si el hosting arranca varios procesos de
    la aplicación, cada uno lleva su propia cuenta y el límite real es algo
    más alto; para frenar a quien sube archivos en bucle sigue bastando.
    """

    def __init__(self, maximo: int, ventana_segundos: int):
        self.maximo = maximo
        self.ventana = ventana_segundos
        self._golpes: dict[str, deque] = {}
        self._cerrojo = threading.Lock()

    def esperar(self, ip: str | None) -> int:
        """0 si puede pasar (y lo cuenta). Si no, segundos que le faltan."""
        ahora = time.monotonic()
        with self._cerrojo:
            cola = self._golpes.setdefault(ip or "desconocida", deque())
            while cola and ahora - cola[0] >= self.ventana:
                cola.popleft()
            if len(cola) >= self.maximo:
                return max(1, int(self.ventana - (ahora - cola[0])) + 1)
            cola.append(ahora)

            # Que el diccionario no crezca para siempre con IPs que ya se fueron.
            if len(self._golpes) > 5000:
                for clave in [k for k, c in self._golpes.items()
                              if not c or ahora - c[-1] >= self.ventana]:
                    del self._golpes[clave]
            return 0
