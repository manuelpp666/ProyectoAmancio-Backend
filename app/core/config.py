"""
Lo que cambia entre el portátil y el servidor.

El frontend y el backend viven en dominios distintos, así que la cookie de
sesión tiene que viajar entre sitios. El navegador solo lo permite si la cookie
lleva `SameSite=None`, y esa marca a su vez exige `Secure`, que solo funciona
sobre HTTPS. En local se trabaja por http, donde esa combinación impediría
iniciar sesión. Por eso el comportamiento no se adivina: lo decide ENTORNO.

En el .env del servidor:

    ENTORNO=produccion
    ALLOWED_ORIGINS=https://www.amanciovarona.edu.pe

En local basta con no poner ENTORNO (o ponerlo en 'desarrollo').
"""
import os

from dotenv import load_dotenv

load_dotenv()

ENTORNO = (os.getenv("ENTORNO") or "desarrollo").strip().lower()
ES_PRODUCCION = ENTORNO in ("produccion", "producción", "production", "prod")

# Cookie de sesión. Entre dominios distintos hace falta SameSite=None + Secure;
# en local, Secure sobre http haría que el navegador descartara la cookie y
# nadie podría entrar.
COOKIE_SECURE = ES_PRODUCCION
COOKIE_SAMESITE = "none" if ES_PRODUCCION else "lax"

# La documentación interactiva expone el esquema completo de la API. Útil
# mientras se desarrolla, innecesaria de puertas afuera.
DOCS_URL = None if ES_PRODUCCION else "/docs"
REDOC_URL = None if ES_PRODUCCION else "/redoc"

# --------------------------------------------------------------- CONCURRENCIA
#
# Casi todos los endpoints son síncronos (`def`, no `async def`), y FastAPI los
# ejecuta en un pool de hilos. Cada uno de esos hilos pide una conexión a la
# base mientras dura la petición, así que si caben más hilos que conexiones, los
# que sobran esperan a que se libere una y acaban fallando por tiempo agotado.
#
# Por eso los dos números se configuran juntos y por defecto coinciden: nunca
# hay más peticiones en curso que conexiones disponibles.
#
# El tope real lo pone el servidor de base de datos (`max_user_connections`).
# En un hosting compartido suele estar entre 25 y 50: si es tu caso, baja
# DB_POOL_SIZE y DB_MAX_OVERFLOW hasta que la suma quepa ahí.
def _entero(nombre: str, por_defecto: int) -> int:
    try:
        valor = int((os.getenv(nombre) or "").strip() or por_defecto)
        return valor if valor > 0 else por_defecto
    except ValueError:
        return por_defecto


DB_POOL_SIZE = _entero("DB_POOL_SIZE", 20)
DB_MAX_OVERFLOW = _entero("DB_MAX_OVERFLOW", 20)
DB_POOL_TIMEOUT = _entero("DB_POOL_TIMEOUT", 10)

# Peticiones síncronas simultáneas. Se ajusta al total de conexiones para que
# ningún hilo se quede esperando una que no existe.
HILOS_PETICIONES = _entero("HILOS_PETICIONES", DB_POOL_SIZE + DB_MAX_OVERFLOW)

# Sin estas variables la aplicación arranca pero falla en la primera petición
# real, con un error que no dice nada. Mejor no dejarla arrancar.
OBLIGATORIAS = ("DB_USER", "DB_HOST", "DB_NAME", "SECRET_KEY")
SOLO_EN_PRODUCCION = ("ALLOWED_ORIGINS",)


def verificar() -> None:
    """Aborta el arranque si falta configuración esencial."""
    faltan = [v for v in OBLIGATORIAS if not (os.getenv(v) or "").strip()]
    if ES_PRODUCCION:
        faltan += [v for v in SOLO_EN_PRODUCCION if not (os.getenv(v) or "").strip()]

    if faltan:
        raise RuntimeError(
            "Faltan variables de entorno obligatorias: " + ", ".join(faltan)
            + f". Defínelas en el archivo .env (entorno actual: {ENTORNO})."
        )

    if ES_PRODUCCION:
        origenes = os.getenv("ALLOWED_ORIGINS", "")
        if "localhost" in origenes or "127.0.0.1" in origenes:
            print("[AVISO] ALLOWED_ORIGINS todavía apunta a localhost en producción.")
        if not all(o.strip().startswith("https://") for o in origenes.split(",") if o.strip()):
            print("[AVISO] Hay orígenes sin https. La cookie de sesión es Secure y el "
                  "navegador no la enviará desde un origen http.")


def resumen() -> str:
    """Una línea para el log de arranque: deja claro en qué modo se levantó."""
    return (f"Entorno: {ENTORNO} · cookie SameSite={COOKIE_SAMESITE} "
            f"Secure={COOKIE_SECURE} · docs={'off' if ES_PRODUCCION else DOCS_URL} "
            f"· BD {DB_POOL_SIZE}+{DB_MAX_OVERFLOW} conexiones / "
            f"{HILOS_PETICIONES} peticiones simultáneas")
