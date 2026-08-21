# -*- coding: utf-8 -*-
"""Mantenimiento del disco: qué ocupa espacio y qué se puede tirar.

POR QUÉ EXISTE
    Nada del sistema borraba nada. Lo que entraba se quedaba para siempre:
    archivos que se quedaron sin fila en la base, fotos del CREP de hace
    meses que ya no se comparan con nada, intentos de acceso de hace un año.
    El servidor del colegio tiene 150 GB y nadie mira cuánto queda hasta que
    deja de quedar.

    Esto lo llama un cron una vez por semana. También se puede mirar sin
    borrar nada, que es como conviene estrenarlo.

LA REGLA DE ORO
    Nunca se borra un archivo por no encontrarlo en la base de datos si la
    consulta a la base falló. Si `referencias()` no puede leer alguna tabla,
    aborta. Sin esa condición, una tabla caída convertiría "no encuentro
    ninguna referencia" en "borra media/ entera", que es exactamente la clase
    de accidente que un script de limpieza no puede permitirse.
"""

import os
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

# Raíz del backend: mantenimiento -> modules -> app -> Backend
_AQUI = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(_AQUI)))
MEDIA_DIR = os.path.join(BASE_DIR, "media")

MB = 1024 * 1024
GB = 1024 * MB

# --- Cuánto se guarda -------------------------------------------------------
#
# Estos números son la política de retención. Están juntos y aquí a propósito:
# son la clase de decisión que el colegio puede querer cambiar, y no debería
# haber que buscarla por el código.

# Un archivo sin fila en la base tuvo que quedar huérfano hace al menos un día
# para tocarlo. La ventana evita el caso malo: una subida que está a medias
# —el archivo ya escrito, la fila todavía sin confirmar— parecería huérfana.
GRACIA_HUERFANOS_HORAS = 24

# Fotos del padrón del CREP. La conciliación solo lee la MÁS RECIENTE
# (conciliacion.py ordena por id descendente y toma la primera), así que las
# viejas no se comparan con nada. Se conservan igual unas cuantas por si hay
# que dar marcha atrás, y solo se vacía el JSON: la fila con la fecha y los
# totales se queda, porque es el historial de qué se le mandó al banco.
CREP_SNAPSHOTS_A_CONSERVAR = 3
CREP_DIAS_A_CONSERVAR = 90

# Bitácoras de seguridad. El bloqueo por intentos fallidos solo mira los
# últimos minutos; lo demás es historial para consultar. Un año es más de lo
# que nadie ha necesitado nunca mirar hacia atrás.
RETENCION_INTENTOS_MESES = 12
RETENCION_SOLICITUDES_MESES = 12

# A partir de aquí se avisa por correo (opción F). Se puede cambiar sin tocar
# el código con DISCO_AVISO_PORCENTAJE en el .env.
try:
    UMBRAL_AVISO_DISCO = float(os.getenv("DISCO_AVISO_PORCENTAJE", "75")) / 100
except ValueError:
    UMBRAL_AVISO_DISCO = 0.75


def legible(bytes_: float) -> str:
    """Bytes en algo que se pueda leer de un vistazo."""
    valor = float(bytes_)
    for unidad in ("B", "KB", "MB"):
        if valor < 1024:
            return f"{valor:.0f} {unidad}"
        valor /= 1024
    return f"{valor:.2f} GB"


# ===========================================================================
# MEDIR
# ===========================================================================

def estado_disco() -> dict:
    """Cuánto ocupa y cuánto queda en el disco donde vive el backend.

    OJO CON ESTE NÚMERO EN HOSTING COMPARTIDO: `disk_usage` mira el volumen
    del sistema de ficheros, que en un cPanel es el disco de la máquina
    entera y no la cuota de la cuenta. Puede salir al 95% por lo que ocupan
    otros clientes, o al 20% teniendo la cuota del colegio a tope. El número
    que manda para la cuenta es el que enseña el panel del hosting.

    Por eso el informe trae también `del_sistema`, que sí es lo que ocupa
    este sistema y es sobre lo que se puede actuar.
    """
    try:
        import shutil
        uso = shutil.disk_usage(BASE_DIR)
        proporcion = uso.used / uso.total if uso.total else 0.0
        return {
            "total_bytes": uso.total,
            "usado_bytes": uso.used,
            "libre_bytes": uso.free,
            "total": legible(uso.total),
            "usado": legible(uso.used),
            "libre": legible(uso.free),
            "porcentaje_usado": round(proporcion * 100, 1),
            "en_alerta": proporcion >= UMBRAL_AVISO_DISCO,
            "advertencia": "En hosting compartido esto puede ser el disco de "
                           "la máquina y no la cuota del colegio. Contrástalo "
                           "con el panel del hosting.",
        }
    except OSError as e:
        return {"error": f"No se pudo leer el disco: {e}", "en_alerta": False}


def _tamano_de(ruta: str) -> tuple:
    """(bytes, número de archivos) de una carpeta."""
    total = 0
    cuantos = 0
    for raiz, _, ficheros in os.walk(ruta):
        for f in ficheros:
            try:
                total += os.path.getsize(os.path.join(raiz, f))
                cuantos += 1
            except OSError:
                continue
    return total, cuantos


def medir_media() -> dict:
    """Lo que ocupa cada carpeta de subidas, de mayor a menor."""
    if not os.path.isdir(MEDIA_DIR):
        return {"total_bytes": 0, "total": "0 B", "carpetas": []}

    carpetas = []
    total = 0
    for nombre in sorted(os.listdir(MEDIA_DIR)):
        ruta = os.path.join(MEDIA_DIR, nombre)
        if not os.path.isdir(ruta):
            continue
        bytes_, cuantos = _tamano_de(ruta)
        total += bytes_
        carpetas.append({"carpeta": nombre, "bytes": bytes_,
                         "tamano": legible(bytes_), "archivos": cuantos})

    carpetas.sort(key=lambda c: c["bytes"], reverse=True)
    return {"total_bytes": total, "total": legible(total), "carpetas": carpetas}


def medir_base_datos(db: Session) -> dict:
    """Peso de la base y de sus tablas más grandes.

    Puede fallar sin que sea un problema: en el hosting compartido el usuario
    de la base no siempre tiene permiso sobre `information_schema`, que es lo
    que ya se sabía por los scripts SQL. Si no se puede, se dice y se sigue.
    """
    try:
        filas = db.execute(text("""
            SELECT table_name,
                   table_rows,
                   data_length + index_length AS bytes
              FROM information_schema.tables
             WHERE table_schema = DATABASE()
             ORDER BY bytes DESC
             LIMIT 10
        """)).fetchall()
    except Exception as e:
        db.rollback()
        return {"disponible": False,
                "motivo": f"{type(e).__name__}: {str(e).splitlines()[0][:120]}"}

    tablas = [{"tabla": f[0], "filas": int(f[1] or 0), "bytes": int(f[2] or 0),
               "tamano": legible(int(f[2] or 0))} for f in filas]
    total = sum(t["bytes"] for t in tablas)
    return {"disponible": True, "total_bytes": total, "total": legible(total),
            "tablas": tablas}


# ===========================================================================
# ARCHIVOS HUÉRFANOS
# ===========================================================================

def _normalizar(ruta) -> str | None:
    """Ruta de la base convertida a ruta relativa al backend, con barras /.

    Hay dos formatos guardados: la mayoría de módulos guardan algo como
    `/media/recursos_tareas/carga_10/ref_ab12cd.pdf`, y el chatbot guarda la
    ruta absoluta del servidor. Los dos tienen que acabar comparándose igual.

    CUIDADO CON `os.path.isabs`: para Python, `/media/...` YA es una ruta
    absoluta, tanto en Linux como en Windows. Usarlo para distinguir los dos
    formatos convertía la ruta de cada archivo en uso en algo como
    `../../media/...`, que no coincidía con nada, y la limpieza daba por
    huérfano TODO lo que sí se usaba. Lo pilló la prueba; en el servidor
    habría borrado media/ entera en su primera pasada.

    El discriminador correcto es si la ruta empieza por `media/`, que es la
    carpeta de subidas del backend.
    """
    if not ruta:
        return None
    texto = str(ruta).strip().replace("\\", "/")
    if not texto:
        return None

    sin_barra = texto.lstrip("/")
    if sin_barra.startswith("media/"):
        return sin_barra

    # Ruta absoluta de verdad (el chatbot guarda así): se pasa a relativa.
    try:
        relativa = os.path.relpath(texto, BASE_DIR).replace("\\", "/")
    except ValueError:
        # Otra unidad de disco en Windows: no cuelga del backend.
        return None
    if relativa.startswith(".."):
        return None  # fuera del backend: no es un archivo de media/
    return relativa


def referencias(db: Session) -> set:
    """Todas las rutas de archivo que la base dice estar usando.

    Si CUALQUIERA de las consultas falla, lanza. Devolver un conjunto
    incompleto haría que la limpieza tomara por basura archivos que sí se
    usan. Es preferible no limpiar nada esta semana.
    """
    from app.modules.virtual import models as virtual
    from app.modules.finance import models as finance
    from app.modules.chatbot import models as chatbot

    usadas = set()
    consultas = (
        (virtual.Tarea, virtual.Tarea.archivo_adjunto_url),
        (virtual.MaterialClase, virtual.MaterialClase.archivo_url),
        (virtual.EntregaTarea, virtual.EntregaTarea.archivo_url),
        (finance.SolicitudTramite, finance.SolicitudTramite.archivo_adjunto),
        (chatbot.Chatbot, chatbot.Chatbot.file_path),
    )
    for _, columna in consultas:
        for (valor,) in db.query(columna).filter(columna.isnot(None)).all():
            norma = _normalizar(valor)
            if norma:
                usadas.add(norma)
    return usadas


def buscar_huerfanos(db: Session) -> list:
    """Archivos dentro de media/ que ninguna fila de la base referencia."""
    usadas = referencias(db)
    if not os.path.isdir(MEDIA_DIR):
        return []

    limite = datetime.now() - timedelta(hours=GRACIA_HUERFANOS_HORAS)
    sueltos = []
    for raiz, _, ficheros in os.walk(MEDIA_DIR):
        for f in ficheros:
            absoluta = os.path.join(raiz, f)
            relativa = os.path.relpath(absoluta, BASE_DIR).replace("\\", "/")
            if relativa in usadas:
                continue
            try:
                info = os.stat(absoluta)
            except OSError:
                continue
            if datetime.fromtimestamp(info.st_mtime) > limite:
                continue  # demasiado reciente: puede ser una subida en curso
            sueltos.append({"ruta": relativa, "bytes": info.st_size,
                            "tamano": legible(info.st_size),
                            "modificado": datetime.fromtimestamp(
                                info.st_mtime).strftime("%d/%m/%Y %H:%M")})

    sueltos.sort(key=lambda a: a["bytes"], reverse=True)
    return sueltos


def _borrar_carpetas_vacias() -> int:
    """Quita las carpetas que se quedaron sin nada dentro.

    No borra media/ ni sus carpetas de primer nivel: esas las crea el backend
    al arrancar y tenerlas vacías es lo normal.
    """
    borradas = 0
    protegidas = {os.path.normpath(MEDIA_DIR)}
    if os.path.isdir(MEDIA_DIR):
        for nombre in os.listdir(MEDIA_DIR):
            protegidas.add(os.path.normpath(os.path.join(MEDIA_DIR, nombre)))

    for raiz, carpetas, ficheros in os.walk(MEDIA_DIR, topdown=False):
        if os.path.normpath(raiz) in protegidas:
            continue
        if ficheros or carpetas:
            continue
        try:
            os.rmdir(raiz)
            borradas += 1
        except OSError:
            continue
    return borradas


# ===========================================================================
# LA LIMPIEZA
# ===========================================================================

def limpiar(db: Session, simular: bool = True) -> dict:
    """Pasa el mantenimiento. Con `simular` cuenta lo que haría sin tocar nada.

    Cada paso va por su cuenta: que uno falle no impide los demás, y lo que
    falló queda escrito en `errores` para que se vea en el panel.
    """
    informe = {
        "simulado": simular,
        "fecha": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "bytes_liberados": 0,
        "errores": [],
    }

    # --- 1. Archivos sin dueño ---------------------------------------------
    try:
        sueltos = buscar_huerfanos(db)
        liberado = 0
        borrados = 0
        if not simular:
            for archivo in sueltos:
                absoluta = os.path.join(BASE_DIR, archivo["ruta"])
                try:
                    os.remove(absoluta)
                    liberado += archivo["bytes"]
                    borrados += 1
                except OSError as e:
                    informe["errores"].append(
                        f"No se pudo borrar {archivo['ruta']}: {e}")
        else:
            liberado = sum(a["bytes"] for a in sueltos)

        informe["archivos_huerfanos"] = {
            "encontrados": len(sueltos),
            "borrados": borrados,
            "bytes": liberado,
            "espacio": legible(liberado),
            # Solo una muestra: si hay 4.000, la respuesta no puede traerlos
            # todos ni el correo puede listarlos.
            "ejemplos": sueltos[:10],
        }
        informe["bytes_liberados"] += liberado
    except Exception as e:
        db.rollback()
        informe["errores"].append(
            f"Archivos huérfanos: no se revisaron ({type(e).__name__}: "
            f"{str(e).splitlines()[0][:120]}). No se borró ningún archivo.")
        informe["archivos_huerfanos"] = {"encontrados": 0, "borrados": 0,
                                         "bytes": 0, "espacio": "0 B",
                                         "ejemplos": []}

    # --- 2. Carpetas vacías -------------------------------------------------
    try:
        informe["carpetas_vacias"] = {
            "borradas": 0 if simular else _borrar_carpetas_vacias()}
    except Exception as e:
        informe["errores"].append(f"Carpetas vacías: {type(e).__name__}")
        informe["carpetas_vacias"] = {"borradas": 0}

    # --- 3. Fotos viejas del CREP ------------------------------------------
    try:
        from app.modules.finance import models as finance

        recientes = [
            r[0] for r in db.query(finance.RegistroCREP.id_registro_crep)
            .order_by(finance.RegistroCREP.id_registro_crep.desc())
            .limit(CREP_SNAPSHOTS_A_CONSERVAR).all()
        ]
        corte = datetime.now() - timedelta(days=CREP_DIAS_A_CONSERVAR)

        candidatos = db.query(finance.RegistroCREP).filter(
            finance.RegistroCREP.cuotas_json.isnot(None),
            finance.RegistroCREP.fecha_generacion < corte,
        )
        if recientes:
            candidatos = candidatos.filter(
                finance.RegistroCREP.id_registro_crep.notin_(recientes))

        filas = candidatos.all()
        ganancia = sum(len(f.cuotas_json or "") for f in filas)
        if not simular and filas:
            for f in filas:
                f.cuotas_json = None
            db.commit()

        informe["snapshots_crep"] = {
            "vaciados": len(filas), "bytes": ganancia,
            "espacio": legible(ganancia),
            "conservados": len(recientes)}
        informe["bytes_liberados"] += ganancia
    except Exception as e:
        db.rollback()
        informe["errores"].append(f"Snapshots CREP: {type(e).__name__}: "
                                  f"{str(e).splitlines()[0][:120]}")
        informe["snapshots_crep"] = {"vaciados": 0, "bytes": 0,
                                     "espacio": "0 B", "conservados": 0}

    # --- 4. Bitácoras de seguridad -----------------------------------------
    informe["intentos_acceso"] = _purgar_bitacora(
        db, simular, "intento_acceso", RETENCION_INTENTOS_MESES, informe)
    informe["solicitudes_acceso"] = _purgar_bitacora(
        db, simular, "solicitud_acceso", RETENCION_SOLICITUDES_MESES, informe,
        # Una solicitud sin atender no se borra por vieja que sea: que lleve
        # un año ahí significa que se le debe una respuesta a alguien.
        extra="AND estado <> 'PENDIENTE'")

    # --- 5. Cómo queda el disco --------------------------------------------
    informe["espacio_liberado"] = legible(informe["bytes_liberados"])
    informe["disco"] = estado_disco()
    try:
        media = medir_media()
        informe["del_sistema"] = {
            "archivos_subidos": media.get("total", "0 B"),
            "carpetas": media.get("carpetas", []),
        }
    except Exception as e:
        informe["errores"].append(f"Medida de media/: {type(e).__name__}")
    return informe


def _purgar_bitacora(db: Session, simular: bool, tabla: str, meses: int,
                     informe: dict, extra: str = "") -> dict:
    """Borra filas viejas de una bitácora. SQL directo por dos razones.

    Una: son cientos de miles de filas y cargarlas al ORM para borrarlas es
    tirar memoria. Dos: la tabla puede no existir todavía si el script SQL
    correspondiente aún no se ejecutó en el servidor, y eso no debe tumbar el
    mantenimiento entero.

    `tabla` y `extra` NO vienen de fuera: son constantes de este archivo. Si
    algún día llegan de una petición, hay que dejar de interpolarlas.
    """
    corte = datetime.now() - timedelta(days=meses * 30)
    try:
        cuantas = db.execute(
            text(f"SELECT COUNT(*) FROM {tabla} WHERE fecha < :corte {extra}"),
            {"corte": corte},
        ).scalar() or 0

        if not simular and cuantas:
            db.execute(
                text(f"DELETE FROM {tabla} WHERE fecha < :corte {extra}"),
                {"corte": corte},
            )
            db.commit()

        return {"borradas": 0 if simular else int(cuantas),
                "encontradas": int(cuantas),
                "anteriores_a": corte.strftime("%d/%m/%Y")}
    except Exception as e:
        db.rollback()
        informe["errores"].append(
            f"{tabla}: {type(e).__name__}: {str(e).splitlines()[0][:120]}")
        return {"borradas": 0, "encontradas": 0, "anteriores_a": None}


def estado(db: Session) -> dict:
    """Foto de cómo está el espacio, sin tocar nada.

    Es lo que pinta el panel y lo que conviene mirar antes de dejar el cron
    borrando de verdad.
    """
    media = medir_media()
    base = medir_base_datos(db)
    foto = {
        "disco": estado_disco(),
        "media": media,
        "base_datos": base,
        # Lo que ocupa ESTE sistema, que es lo único sobre lo que se puede
        # actuar desde aquí. El porcentaje del disco puede estar hablando de
        # otra cosa (ver `estado_disco`); este número no.
        "del_sistema": {
            "bytes": media.get("total_bytes", 0) + base.get("total_bytes", 0),
            "total": legible(media.get("total_bytes", 0)
                             + base.get("total_bytes", 0)),
            "archivos_subidos": media.get("total", "0 B"),
            "base_datos": base.get("total", "no medible"),
        },
    }
    try:
        sueltos = buscar_huerfanos(db)
        foto["huerfanos"] = {
            "cuantos": len(sueltos),
            "bytes": sum(a["bytes"] for a in sueltos),
            "espacio": legible(sum(a["bytes"] for a in sueltos)),
            "ejemplos": sueltos[:10],
        }
    except Exception as e:
        foto["huerfanos"] = {
            "error": f"No se pudo revisar: {type(e).__name__}",
            "cuantos": 0, "bytes": 0, "espacio": "0 B", "ejemplos": []}
    return foto
