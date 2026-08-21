# -*- coding: utf-8 -*-
"""Guardado de archivos subidos, con los frenos puestos.

POR QUÉ EXISTE
    Cada endpoint que aceptaba archivos los guardaba a su manera. Tres de
    ellos —el material de clase, el recurso adjunto de una tarea y el adjunto
    de un trámite— no miraban el tamaño: `shutil.copyfileobj` escribe lo que
    le echen. Un vídeo de 900 MB subido por equivocación entraba sin
    protestar. El servidor del colegio tiene 150 GB y nada del sistema borra
    nada por su cuenta, así que lo que entra se queda para siempre.

    Aquí está la única copia de las reglas: extensión permitida, tamaño
    máximo y cuota de la carpeta. Los endpoints solo llaman a
    `guardar_subida`.

POR QUÉ NO SE DEDUPLICA POR CONTENIDO
    La idea era: si el archivo ya existe (mismo hash), no escribir otra copia
    y apuntar las dos filas al mismo fichero. Se descartó a propósito. El
    código actual borra el fichero físico cuando se borra o se reemplaza la
    fila que lo referencia. Con ficheros compartidos, el primero en borrar
    dejaría a los demás apuntando a un archivo que ya no existe: dos alumnos
    que entregan el mismo PDF y uno lo reemplaza, el otro se queda sin
    entrega. Deduplicar exige antes llevar la cuenta de cuántas filas usan
    cada fichero, y eso es otro trabajo.

EL LÍMITE DE VERDAD NO ESTÁ AQUÍ
    Starlette vuelca el cuerpo entero de la petición a un temporal ANTES de
    llamar al endpoint, así que cuando esta función mide el archivo, los
    900 MB ya se escribieron en disco (el temporal se borra al terminar, pero
    se escriben). Para que ni siquiera lleguen está el corte por
    `Content-Length` en main.py, y por encima de todo el límite del servidor
    web (`LimitRequestBody` en Apache, `client_max_body_size` en nginx).
"""

import os
import shutil

from fastapi import HTTPException, UploadFile, status

MB = 1024 * 1024

# Tope por archivo. Es el que ya aplicaba la entrega del alumno; ahora vale
# para todos.
MAX_SUBIDA_MB = 10
MAX_SUBIDA_BYTES = MAX_SUBIDA_MB * MB

# Cuota por carpeta. Las carpetas del docente son por curso (`carga_X`), así
# que esto es "cuánto puede ocupar un curso" y no un límite global: un docente
# que se pase no le come el disco al resto.
#
# No se aplica a las carpetas donde el tamaño ya está acotado solo (las
# entregas, que son una por alumno) ni donde bloquear haría daño (los
# trámites). Quien llama decide, pasando `cuota_bytes=None`.
CUOTA_CARPETA_MB = 300
CUOTA_CARPETA_BYTES = CUOTA_CARPETA_MB * MB

# Se copia a trozos en vez de leer el archivo entero en memoria: con varios
# docentes subiendo a la vez, `file.read()` multiplicaría el consumo de RAM
# del servidor por el número de subidas simultáneas.
TROZO = MB


def medir(archivo: UploadFile) -> int:
    """Tamaño en bytes del archivo subido, dejando el puntero al principio.

    Se usa `archivo.file` (el SpooledTemporaryFile de Python) y no el
    UploadFile, porque el `seek` de este último no acepta el segundo
    argumento.
    """
    archivo.file.seek(0, os.SEEK_END)
    tamano = archivo.file.tell()
    archivo.file.seek(0)
    return tamano


def tamano_carpeta(ruta: str) -> int:
    """Bytes que ocupa una carpeta. Devuelve 0 si no existe."""
    total = 0
    for raiz, _, ficheros in os.walk(ruta):
        for f in ficheros:
            try:
                total += os.path.getsize(os.path.join(raiz, f))
            except OSError:
                # Un fichero que desaparece mientras se recorre no es un
                # error: solo deja de contar.
                continue
    return total


def legible(bytes_: float) -> str:
    """Bytes en algo que se pueda leer de un vistazo."""
    valor = float(bytes_)
    for unidad in ("B", "KB", "MB"):
        if valor < 1024:
            return f"{valor:.0f} {unidad}"
        valor /= 1024
    return f"{valor:.2f} GB"


def guardar_subida(
    archivo: UploadFile,
    carpeta_abs: str,
    nombre_destino: str,
    *,
    extensiones: set,
    max_bytes: int = MAX_SUBIDA_BYTES,
    cuota_bytes: int | None = CUOTA_CARPETA_BYTES,
) -> int:
    """Comprueba y guarda un archivo subido. Devuelve su tamaño en bytes.

    `nombre_destino` es el nombre final ya decidido por quien llama (con su
    prefijo y su uuid): esta función no lo inventa, para no cambiar los
    formatos que ya están guardados en la base.

    Lanza HTTPException con el mensaje que ve el usuario:
      400 extensión no permitida       413 archivo demasiado grande
      413 la carpeta del curso llena   500 no se pudo escribir
    """
    ext = os.path.splitext(archivo.filename or "")[1].lower()
    if ext not in extensiones:
        permitidas = ", ".join(sorted(e.lstrip(".") for e in extensiones))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Formato {ext or 'desconocido'} no permitido. "
                   f"Se aceptan: {permitidas}.",
        )

    tamano = medir(archivo)
    if tamano == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo está vacío.",
        )
    if tamano > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"El archivo pesa {legible(tamano)} y el máximo son "
                   f"{legible(max_bytes)}. Comprímelo, o súbelo a Drive y "
                   f"pega el enlace.",
        )

    try:
        os.makedirs(carpeta_abs, exist_ok=True)
    except OSError as e:
        print(f"[ARCHIVOS][ERROR] No se pudo crear {carpeta_abs}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error de permisos en el servidor.",
        )

    # La cuota se mira DESPUÉS de conocer el tamaño y ANTES de escribir: si no
    # cabe, no se toca el disco.
    if cuota_bytes is not None:
        ocupado = tamano_carpeta(carpeta_abs)
        if ocupado + tamano > cuota_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Esta carpeta ya ocupa {legible(ocupado)} de los "
                       f"{legible(cuota_bytes)} disponibles y el archivo no "
                       f"cabe. Borra material antiguo que ya no uses, o sube "
                       f"los archivos pesados a Drive y pega el enlace.",
            )

    destino = os.path.join(carpeta_abs, nombre_destino)
    try:
        with open(destino, "wb") as buffer:
            shutil.copyfileobj(archivo.file, buffer, TROZO)
    except OSError as e:
        # Un fallo a mitad de escritura deja un archivo cortado que nadie
        # volvería a mirar y que ocuparía sitio para siempre.
        try:
            if os.path.exists(destino):
                os.remove(destino)
        except OSError:
            pass
        print(f"[ARCHIVOS][ERROR] No se pudo escribir {destino}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo guardar el archivo en el servidor.",
        )

    return tamano
