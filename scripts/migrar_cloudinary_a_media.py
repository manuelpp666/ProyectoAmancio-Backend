# -*- coding: utf-8 -*-
"""
Trae al servidor las imágenes que siguen en Cloudinary y reescribe sus URLs.

POR QUÉ
    Desde septiembre de 2026 lo nuevo se sube al propio backend (/media), pero
    en la base quedan URLs de Cloudinary de antes. Mientras sigan ahí, la web
    depende de una cuenta externa que se puede desactivar como pasó con la
    anterior. Este script las descarga, las guarda en MEDIA_DIR con las mismas
    reglas que una subida normal (las imágenes, en WEBP y sin metadatos) y
    cambia la URL en la base.

LO QUE NO PUEDE HACER
    Las que están en una cuenta DESACTIVADA ya no se pueden descargar: el
    script las lista para que se vuelvan a subir a mano desde el panel.

DÓNDE BUSCA
    configuración de la web (también dentro de los JSON de Inicio), portada y
    galería de noticias, foto de docentes y administradores, y los cuatro
    documentos de admisión.

CÓMO SE USA (en el servidor, con el backend nuevo ya subido)

    1. Respaldo de la base. Siempre.
    2. Simulación: dice qué encontraría y cuáles se pueden descargar.
         python scripts/migrar_cloudinary_a_media.py --base-url https://api.tudominio.pe
    3. De verdad:
         python scripts/migrar_cloudinary_a_media.py --base-url https://api.tudominio.pe --aplicar
    4. Si algo no cuadra, deshacer con el respaldo que dejó el paso 3:
         python scripts/migrar_cloudinary_a_media.py --revertir scripts/respaldos/cloudinary_a_media_ANTES_....json

    --base-url es la dirección PÚBLICA del backend, la misma que
    NEXT_PUBLIC_API_URL en el frontend. Se escribe delante de /media/... en
    cada URL nueva.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import requests

import main  # noqa: F401  (registra todos los modelos)
from app.db.database import SessionLocal
from app.core.util import media
from app.modules.multimedia import service as mm
from app.modules.pagina_principal.models import PaginaConfiguracion
from app.modules.web.models import Noticia
from app.modules.users.docente.models import Docente
from app.modules.personal.models import Administrador
from app.modules.users.alumno.models import Alumno

URL_CLOUDINARY = re.compile(r"https?://res\.cloudinary\.com/[^\s\"'<>()\[\]{}\\,]+")
MAX_DESCARGA = 30 * 1024 * 1024
RESPALDOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "respaldos")

# (modelo, columna de clave primaria, columna, ¿es documento de admisión?)
COLUMNAS = [
    (PaginaConfiguracion, "id", "valor", False),
    (Noticia, "id_noticia", "imagen_portada_url", False),
    (Noticia, "id_noticia", "imagenes", False),
    (Docente, "id_docente", "url_perfil", False),
    (Administrador, "id_admin", "url_perfil", False),
    (Alumno, "id_alumno", "doc_dni_menor", True),
    (Alumno, "id_alumno", "doc_dni_apoderado", True),
    (Alumno, "id_alumno", "doc_fum", True),
    (Alumno, "id_alumno", "doc_certificado_estudios", True),
]


def urls_en(valor):
    if valor is None:
        return []
    if isinstance(valor, (list, tuple)):
        return [u for v in valor for u in urls_en(v)]
    return URL_CLOUDINARY.findall(str(valor))


def reemplazar(valor, cambios):
    if isinstance(valor, list):
        return [reemplazar(v, cambios) for v in valor]
    if not isinstance(valor, str):
        return valor
    for viejo, nuevo in cambios.items():
        valor = valor.replace(viejo, nuevo)
    return valor


def descargar(url):
    """(bytes, None) o (None, motivo)."""
    try:
        with requests.get(url, stream=True, timeout=30) as r:
            if r.status_code != 200:
                cuerpo = r.text[:80].strip() if r.status_code in (401, 403) else ""
                return None, f"HTTP {r.status_code} {cuerpo}".strip()
            partes, total = [], 0
            for trozo in r.iter_content(1024 * 256):
                total += len(trozo)
                if total > MAX_DESCARGA:
                    return None, "pesa más de 30 MB"
                partes.append(trozo)
            return b"".join(partes), None
    except requests.RequestException as e:
        return None, f"sin conexión ({type(e).__name__})"


def guardar(datos, es_documento):
    """Guarda con las mismas reglas que una subida. Devuelve la ruta /media/..."""
    mime = mm.tipo_real(datos)
    if mime in mm.TIPOS_IMAGEN:
        lado = mm.LADO_MAXIMO_DOCUMENTO if es_documento else mm.LADO_MAXIMO_IMAGEN
        salida = mm.procesar_imagen(datos, lado)
        destino, ruta = mm._destino(mm.CARPETA_ADMISION if es_documento else mm.CARPETA_IMAGENES, ".webp")
    elif mime in mm.TIPOS_VIDEO and not es_documento:
        salida = datos
        destino, ruta = mm._destino(mm.CARPETA_VIDEOS, mm.TIPOS_VIDEO[mime])
    elif mime == "application/pdf" and es_documento:
        salida = datos
        destino, ruta = mm._destino(mm.CARPETA_ADMISION, ".pdf")
    else:
        raise ValueError(f"tipo no admitido aquí: {mime}")
    mm._escribir(destino, lambda fh: fh.write(salida))
    return ruta, destino


def buscar(db):
    """Filas afectadas: lista de (modelo, pk, columna, valor, es_doc, urls)."""
    filas = []
    for modelo, pk, col, es_doc in COLUMNAS:
        for fila in db.query(modelo).filter(getattr(modelo, col).isnot(None)).all():
            valor = getattr(fila, col)
            urls = urls_en(valor)
            if urls:
                filas.append((modelo, getattr(fila, pk), pk, col, valor, es_doc, urls))
    return filas


def revertir(ruta_respaldo):
    with open(ruta_respaldo, encoding="utf-8") as fh:
        respaldo = json.load(fh)
    modelos = {m.__name__: m for m, *_ in COLUMNAS}
    db = SessionLocal()
    try:
        for f in respaldo["filas"]:
            modelo = modelos[f["modelo"]]
            fila = db.query(modelo).filter(getattr(modelo, f["pk"]) == f["id"]).first()
            if fila is None:
                print(f"  [AVISO] {f['modelo']} {f['id']} ya no existe, se salta")
                continue
            setattr(fila, f["columna"], f["valor"])
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    borrados = 0
    for ruta in respaldo.get("archivos_creados", []):
        fisico = media.ruta_fisica(ruta)
        if fisico and os.path.isfile(fisico):
            os.remove(fisico)
            borrados += 1
    print(f"Revertidas {len(respaldo['filas'])} celdas y borrados {borrados} archivos descargados.")


def principal():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-url", help="dirección pública del backend, p. ej. https://api.tudominio.pe")
    p.add_argument("--aplicar", action="store_true", help="descargar y reescribir de verdad")
    p.add_argument("--revertir", metavar="RESPALDO.json", help="deshacer una ejecución anterior")
    a = p.parse_args()

    if a.revertir:
        return revertir(a.revertir)

    base = (a.base_url or "").rstrip("/")
    if not re.match(r"^https?://[^/\s]+$", base):
        p.error("--base-url es obligatorio: la dirección pública del backend, sin barra final "
                "(la misma que NEXT_PUBLIC_API_URL del frontend)")
    if a.aplicar and base.startswith("http://") and "localhost" not in base and "127.0.0.1" not in base:
        p.error("en el servidor --base-url tiene que empezar por https://")

    db = SessionLocal()
    try:
        filas = buscar(db)
        unicas = sorted({u for *_, urls in filas for u in urls})
        es_doc = {u for *_, ed, urls in filas if ed for u in urls}
        print(f"MEDIA_DIR: {media.MEDIA_DIR}")
        print(f"URLs de Cloudinary encontradas: {len(unicas)} en {len(filas)} celdas\n")

        cambios, perdidas, creados = {}, {}, []
        for url in unicas:
            datos, motivo = descargar(url)
            if datos is None:
                perdidas[url] = motivo
                print(f"  PERDIDA  {motivo:<40} {url}")
                continue
            if not a.aplicar:
                print(f"  OK       {len(datos)//1024:>6} KB se descargaría     {url}")
                continue
            try:
                ruta, _ = guardar(datos, url in es_doc)
            except Exception as e:  # noqa: BLE001
                perdidas[url] = f"no se pudo guardar: {e}"
                print(f"  ERROR    {e}  {url}")
                continue
            creados.append(ruta)
            cambios[url] = base + ruta
            print(f"  MIGRADA  -> {base + ruta}")

        if perdidas:
            print("\nNo se pueden traer (hay que volver a subirlas desde el panel):")
            for modelo, pk_valor, pk, col, valor, _, urls in filas:
                for u in urls:
                    if u in perdidas:
                        donde = f"{modelo.__tablename__}.{col} #{pk_valor}"
                        if modelo is PaginaConfiguracion:
                            donde = f"Editor Web, campo «{db.get(modelo, pk_valor).clave}»"
                        print(f"  - {donde}: {perdidas[u]}")

        if not a.aplicar:
            print("\nSIMULACIÓN: no se ha descargado ni cambiado nada. Añade --aplicar para hacerlo.")
            return
        if not cambios:
            print("\nNada que migrar.")
            return

        os.makedirs(RESPALDOS, exist_ok=True)
        ruta_respaldo = os.path.join(
            RESPALDOS, f"cloudinary_a_media_ANTES_{datetime.now():%Y%m%d_%H%M%S}.json")
        afectadas = [f for f in filas if any(u in cambios for u in f[-1])]
        with open(ruta_respaldo, "w", encoding="utf-8") as fh:
            json.dump({"fecha": datetime.now().isoformat(), "base_url": base,
                       "archivos_creados": creados,
                       "filas": [{"modelo": m.__name__, "pk": pk, "id": pkv, "columna": col, "valor": val}
                                 for m, pkv, pk, col, val, _, _ in afectadas]},
                      fh, ensure_ascii=False, indent=1, default=str)

        try:
            for modelo, pk_valor, pk, col, valor, _, _ in afectadas:
                fila = db.query(modelo).filter(getattr(modelo, pk) == pk_valor).first()
                setattr(fila, col, reemplazar(getattr(fila, col), cambios))
            db.commit()
        except Exception:
            db.rollback()
            for ruta in creados:
                fisico = media.ruta_fisica(ruta)
                if fisico and os.path.isfile(fisico):
                    os.remove(fisico)
            print("\nFALLÓ al escribir en la base: no se cambió nada y se borraron los archivos descargados.")
            raise

        print(f"\nHecho: {len(cambios)} URLs migradas en {len(afectadas)} celdas.")
        print(f"Respaldo para deshacer: {ruta_respaldo}")
    finally:
        db.close()


if __name__ == "__main__":
    principal()
