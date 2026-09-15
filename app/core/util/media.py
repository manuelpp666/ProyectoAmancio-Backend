# -*- coding: utf-8 -*-
"""Dónde viven los archivos subidos, y cómo se pasa de una URL a su archivo.

POR QUÉ EXISTE
    Cada router calculaba su carpeta por su cuenta como
    `<carpeta del backend>/media/...`. Eso ataba los archivos a la carpeta del
    código: al actualizar el backend en el hosting borrando la carpeta y
    subiendo la nueva, se iban con ella las tareas, los materiales, los
    adjuntos de trámites y las imágenes de la web. Ahora se decide aquí, en un
    solo sitio, y se puede sacar fuera.

        # .env del servidor — una carpeta que NO esté dentro del backend
        MEDIA_DIR=/home/usuario/amancio_media

    Sin MEDIA_DIR se usa `<backend>/media`, que es donde ha estado siempre.
    En local no cambia nada.

LAS URLS NO CAMBIAN AL MOVER LA CARPETA
    La base guarda `/media/<subcarpeta>/<archivo>`, o esa misma ruta con el
    dominio del backend delante. `/media` es la dirección pública, no la
    carpeta: main.py la monta sobre MEDIA_DIR esté donde esté. Mover los
    archivos de sitio no obliga a tocar ni una fila.
"""

import mimetypes
import os
import re
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

# util -> core -> app -> backend
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

_configurada = (os.getenv("MEDIA_DIR") or "").strip()
MEDIA_DIR = (os.path.abspath(os.path.expanduser(_configurada)) if _configurada
             else os.path.join(BASE_DIR, "media"))

# Prefijo público con el que se sirven, montado en main.py.
URL_PREFIJO = "/media"

# Python no trae .webp en su tabla de tipos (sí .mp4 y .webm, pero depende del
# sistema). Sin esto, el servidor entregaría las imágenes como
# application/octet-stream y con la cabecera nosniff el navegador no las
# pintaría.
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("video/mp4", ".mp4")
mimetypes.add_type("video/webm", ".webm")

# Una URL de media metida dentro de un texto: el JSON de «Niveles» del inicio,
# la lista de imágenes de una noticia... Se corta en lo que no puede ser parte
# del nombre de un archivo subido.
_EN_TEXTO = re.compile(r"/media/([^\s\"'<>()\[\]{}\\,?#]+)")

# Ruta absoluta de disco que pasa por una carpeta llamada media: así se
# reconocen las filas del chatbot, que guardan la ruta del servidor, aunque
# la carpeta se haya movido después de guardarlas.
_ABSOLUTA_CON_MEDIA = re.compile(r"(?:^|/)media/(.+)$")
_UNIDAD_WINDOWS = re.compile(r"^[A-Za-z]:/")


def carpeta(*partes: str) -> str:
    """Ruta absoluta de una subcarpeta de MEDIA_DIR."""
    return os.path.join(MEDIA_DIR, *partes)


def carpeta_de(relativa: str) -> str:
    """`media/recursos_tareas/carga_3` -> `<MEDIA_DIR>/recursos_tareas/carga_3`.

    Los routers ya tenían sus rutas escritas con el prefijo `media/` (es el
    mismo texto que va a la URL). Esto las lleva a la carpeta de verdad sin
    tener que reescribirlas.
    """
    clave_rel = (relativa or "").replace("\\", "/").strip("/")
    if clave_rel == "media":
        return MEDIA_DIR
    if clave_rel.startswith("media/"):
        clave_rel = clave_rel[len("media/"):]
    return os.path.join(MEDIA_DIR, *[p for p in clave_rel.split("/") if p])


def _segura(relativa: str) -> str | None:
    """Descarta lo que intentaría salir de MEDIA_DIR (`..`) o está vacío."""
    partes = [p for p in relativa.replace("\\", "/").split("/") if p not in ("", ".")]
    if not partes or any(p == ".." for p in partes):
        return None
    return "/".join(partes)


def clave(valor) -> str | None:
    """Ruta de un archivo relativa a MEDIA_DIR, o None si no es de media.

    Es la forma única con la que se comparan los archivos entre sí, venga la
    referencia como venga guardada:

        /media/imagenes/ab12.webp                         (lo normal)
        https://api.colegio.pe/media/imagenes/ab12.webp   (web, perfiles)
        /home/u/amancio_media/chatbot_files/x.pdf         (chatbot)
        C:/.../ProyectoAmancio-Backend/media/chatbot_files/x.pdf

    Todas dan `imagenes/ab12.webp` o `chatbot_files/x.pdf`.
    """
    if valor is None:
        return None
    texto = str(valor).strip().replace("\\", "/")
    if not texto:
        return None

    # 1. URL completa: solo cuenta si su ruta es /media/...
    if texto.lower().startswith(("http://", "https://")):
        ruta = urlparse(texto).path
        if ruta.startswith(URL_PREFIJO + "/"):
            return _segura(ruta[len(URL_PREFIJO) + 1:])
        return None

    # 2. Ruta de la URL sin dominio: /media/... o media/...
    sin_barra = texto.lstrip("/")
    if sin_barra.startswith("media/") and not _UNIDAD_WINDOWS.match(texto):
        return _segura(sin_barra[len("media/"):])

    # 3. Ruta absoluta de disco dentro de MEDIA_DIR.
    if os.path.isabs(texto) or _UNIDAD_WINDOWS.match(texto):
        try:
            relativa = os.path.relpath(texto, MEDIA_DIR).replace("\\", "/")
            if not relativa.startswith(".."):
                return _segura(relativa)
        except ValueError:
            pass  # otra unidad de disco en Windows

        # 4. Ruta absoluta de donde estuvo antes la carpeta media.
        encontrada = _ABSOLUTA_CON_MEDIA.search(texto)
        if encontrada:
            return _segura(encontrada.group(1))

    return None


def claves_en(valor) -> set:
    """Todas las claves que aparecen en un valor guardado.

    Sirve igual para una ruta suelta, una URL, una lista de URLs o un texto
    JSON con varias URLs dentro. Ante la duda devuelve de más, nunca de menos:
    quien la usa es la limpieza de huérfanos, y una clave de sobra solo hace
    que conserve un archivo, mientras que una de menos haría que lo borrara.
    """
    if valor is None:
        return set()
    if isinstance(valor, (list, tuple, set)):
        salida = set()
        for v in valor:
            salida.update(claves_en(v))
        return salida

    texto = str(valor).replace("\\/", "/")
    salida = set()
    entera = clave(texto)
    if entera:
        salida.add(entera)
    for encontrada in _EN_TEXTO.finditer(texto.replace("\\", "/")):
        segura = _segura(encontrada.group(1))
        if segura:
            salida.add(segura)
    return salida


def ruta_fisica(valor) -> str | None:
    """Archivo en disco al que apunta una URL o ruta guardada.

    Devuelve None si no es de media o si, resuelta, caería fuera de
    MEDIA_DIR: una fila manipulada con `../../main.py` no puede terminar en un
    `os.remove` del código.
    """
    relativa = clave(valor)
    if not relativa:
        return None
    raiz = os.path.realpath(MEDIA_DIR)
    destino = os.path.realpath(os.path.join(raiz, *relativa.split("/")))
    try:
        if os.path.commonpath([destino, raiz]) != raiz:
            return None
    except ValueError:
        return None
    return destino
