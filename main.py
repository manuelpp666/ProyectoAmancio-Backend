import os
import sys
import time

# Zona horaria del colegio. TIENE QUE IR ANTES de que cualquier módulo calcule
# una fecha, porque `date.today()` se resuelve con la zona del proceso.
#
# El hosting compartido corre en UTC salvo que alguien lo cambie, y Perú está
# cinco horas por detrás. Con el servidor en UTC, a las 7 de la tarde hora de
# Lima el backend ya cree que es el día siguiente: el panel del administrador
# daba por no pasada la lista de TODAS las aulas a partir de esa hora, y los
# informes por fecha cortaban el día donde no tocaba.
#
# Fijándola aquí, el sistema tiene el mismo "hoy" que el colegio, sin depender
# de cómo esté configurado el servidor.
#
# Solo en Linux, y no por comodidad: Windows NO entiende los nombres de zona de
# la base de datos IANA ("America/Lima"). Su librería de C espera un formato
# propio y, al no reconocer el nombre, se pasa a UTC en silencio. Poniendo la
# variable sin más, el equipo de desarrollo pasaba a creerse que son las 01:00
# del día siguiente cuando en Lima son las 20:00 — justo el error que este
# bloque venía a evitar, pero al revés y sin avisar. El servidor es Linux, que
# sí la entiende, y el equipo local ya tiene la hora de Perú por su cuenta.
if hasattr(time, "tzset"):
    os.environ["TZ"] = "America/Lima"
    time.tzset()

# Límite de hilos de las librerías de cálculo. TIENE QUE IR ANTES de cualquier
# import que arrastre numpy (pytesseract lo hace), porque OpenBLAS lee estas
# variables una sola vez, al cargarse.
#
# Sin esto, el servidor no arrancaba en el hosting compartido: OpenBLAS intenta
# crear un hilo por núcleo de la máquina (32 en el servidor del colegio), el
# plan compartido no permite tantos procesos, y el arranque moría con
# "pthread_create failed: Resource temporarily unavailable". La API no llegaba
# a levantarse y el campus entero se quedaba sin backend.
#
# Aquí no se hace cálculo numérico pesado: un solo hilo es de sobra.
for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
             "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_var, "1")

# La consola de Windows usa cp1252 cuando la salida va a un archivo o a una
# tubería (por ejemplo al arrancar el servidor redirigiendo a un log). Con esa
# codificación, cualquier print con un emoji o una tilde aborta el arranque con
# UnicodeEncodeError antes de que el servidor llegue a escuchar. Se fuerza
# UTF-8 aquí, antes del primer print.
for _flujo in (sys.stdout, sys.stderr):
    if hasattr(_flujo, "reconfigure"):
        _flujo.reconfigure(encoding="utf-8", errors="replace")

from fastapi import FastAPI, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import text  # Para escribir SQL puro
from app.db.database import get_db # Ajusta la ruta según tu carpeta
from app.modules.users import router as usuario_router 
from app.modules.users.alumno import router as alumno_router
from app.modules.users.familiar import router as familiar_router
from app.modules.users.docente import router as docente_router
from app.modules.chatbot import router as chatbot_router
from app.modules.seguridad import router as seguridad_router
# Resto de módulos
from app.modules.perfil import router as perfil_router
from app.modules.academic import router as academic_router
from app.modules.academic import router_notas as academic_notas_router
from app.modules.academic import router_exoneracion as academic_exoneracion_router
from app.modules.academic import router_libreta as academic_libreta_router
from app.modules.enrollment import router as enrollment_router
from app.modules.finance import router as finance_router
from app.modules.finance import router_crep as finance_crep_router
from app.modules.management import router as management_router
from app.modules.virtual import router as virtual_router
from app.modules.behavior import router as behavior_router
from app.modules.web import router as web_router
from app.modules.admision import router as admision_router
from app.modules.horario import router as horario_router
from app.modules.pagina_principal import router as pagina_web_router
from app.modules.personal import router as personal_router
from app.modules.verano import router as verano_router
from app.modules.mantenimiento import router as mantenimiento_router
from app.core.socket_manager import socket_manager
from app.core import socket_manager as socket_manager_mod
from app.core import config
from dotenv import load_dotenv
load_dotenv()

# Si falta configuración esencial, es preferible no arrancar a fallar en la
# primera petición con un error que no explica nada.
config.verificar()
print(f"⚙️  {config.resumen()}")

import anyio
from contextlib import asynccontextmanager


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    """
    Ajusta el número de peticiones síncronas simultáneas antes de atender la
    primera.

    Los endpoints síncronos (la gran mayoría) corren en el pool de hilos de
    AnyIO, que por defecto admite 40. Ese número tiene que ir de la mano del de
    conexiones a la base: si entran más peticiones que conexiones hay, las que
    sobran esperan por una que no va a llegar y acaban fallando por tiempo
    agotado. El limitador solo existe dentro del bucle de eventos, así que se
    toca aquí y no al importar el módulo.
    """
    anyio.to_thread.current_default_thread_limiter().total_tokens = config.HILOS_PETICIONES
    socket_manager_mod.avisar_si_hay_varios_workers()
    yield

# En producción la documentación interactiva queda desactivada: publica el
# esquema completo de la API sin pedir credenciales.
app = FastAPI(docs_url=config.DOCS_URL, redoc_url=config.REDOC_URL,
              openapi_url=None if config.ES_PRODUCCION else "/openapi.json",
              lifespan=ciclo_de_vida)

# Solo activar cuando estés en el servidor de producción
# from fastapi.middleware.proxy_headers import ProxyHeadersMiddleware
# app.add_middleware(ProxyHeadersMiddleware, trusted_proxies="127.0.0.1")

raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
ALLOWED_ORIGINS = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]

# Agregamos un print para que veas en la terminal qué está cargando exactamente
print(f"📡 CORS Origins: {ALLOWED_ORIGINS}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Compresión GZip para respuestas JSON grandes (listas de matrículas, noticias, etc.)
app.add_middleware(GZipMiddleware, minimum_size=1024)


# Tope duro al tamaño de una petición.
#
# POR QUÉ AQUÍ Y NO EN EL ENDPOINT: Starlette vuelca el cuerpo entero a un
# archivo temporal ANTES de llamar al endpoint. Cuando el endpoint mide el
# archivo y lo rechaza, los 900 MB ya se escribieron en el disco del servidor
# (el temporal se borra después, pero se escribieron). Mirando la cabecera
# `Content-Length` se corta antes de leer nada.
#
# El número es holgado a propósito: los topes de verdad son los de cada
# endpoint (10 MB por archivo). Esto solo evita el disparate, y tiene que
# dejar pasar la subida de varios reportes del BCP a la vez, que es la
# petición más grande que hace el sistema.
#
# Esto NO sustituye al límite del servidor web (`LimitRequestBody` en Apache,
# `client_max_body_size` en nginx): quien envía puede mentir en la cabecera.
MAX_PETICION_MB = 30
MAX_PETICION_BYTES = MAX_PETICION_MB * 1024 * 1024


@app.middleware("http")
async def limitar_tamano_peticion(request: Request, call_next):
    declarado = request.headers.get("content-length")
    if declarado:
        try:
            if int(declarado) > MAX_PETICION_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={"detail": f"La petición supera los {MAX_PETICION_MB} MB. "
                                       f"Sube los archivos de uno en uno."},
                )
        except ValueError:
            # Cabecera con basura: que decida el servidor web.
            pass
    return await call_next(request)

# 1. Esto detecta la carpeta 'Backend' (donde está main.py)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 2. Apuntamos directamente a media dentro de Backend
MEDIA_PATH = os.path.join(BASE_DIR, "media")

# --- DEBUG ---
print(f"🚀 Servidor de archivos configurado en: {MEDIA_PATH}")

if not os.path.exists(MEDIA_PATH):
    os.makedirs(MEDIA_PATH, exist_ok=True)

# 3. Montamos la carpeta
app.mount("/media", StaticFiles(directory=MEDIA_PATH), name="media")

# Incluir Rutas
app.include_router(usuario_router.router)
app.include_router(horario_router.router)
app.include_router(alumno_router.router)
app.include_router(familiar_router.router)
app.include_router(docente_router.router)
app.include_router(perfil_router.router)
app.include_router(academic_router.router)
app.include_router(academic_notas_router.router)
app.include_router(academic_exoneracion_router.router)
app.include_router(academic_libreta_router.router)
app.include_router(enrollment_router.router)
app.include_router(finance_router.router)
app.include_router(finance_crep_router.router)
app.include_router(management_router.router)
app.include_router(virtual_router.router)
app.include_router(behavior_router.router)
app.include_router(web_router.router)
app.include_router(chatbot_router.router) 
app.include_router(admision_router.router)
app.include_router(pagina_web_router.router)
app.include_router(personal_router.router)
app.include_router(seguridad_router.router)
app.include_router(mantenimiento_router.router)
app.include_router(verano_router.router)

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    # 1. Conectar al usuario
    await socket_manager.connect(user_id, websocket)
    try:
        while True:
            # Mantener la conexión abierta escuchando mensajes (opcional)
            # data = await websocket.receive_text() 
            
            # Recibir JSON si necesitas señales como "está escribiendo" o "leído"
            data = await websocket.receive_json()
            
    except WebSocketDisconnect:
        # 2. Desconectar al usuario si cierra la pestaña o pierde internet
        socket_manager.disconnect(user_id)
    except Exception as e:
        print(f"Error en socket para usuario {user_id}: {e}")
        socket_manager.disconnect(user_id)

@app.get("/")
def check_db_connection(db: Session = Depends(get_db)):
    try:
        # Intentamos ejecutar una consulta simple
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "Conectada correctamente"}
    except Exception as e:
        # Si algo falla (user/pass mal, server apagado), lo veremos aquí
        raise HTTPException(
            status_code=500, 
            detail=f"Error conectando a la base de datos: {str(e)}"
        )