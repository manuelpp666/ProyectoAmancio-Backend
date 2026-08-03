"""
Utilitario de envío de correos por SMTP.

Diseñado para ser tolerante a fallos: si el SMTP no está configurado o el envío
falla, se registra el error y se continúa (nunca rompe el flujo que lo invoca).

Variables de entorno requeridas (.env):
  SMTP_HOST       ej. smtp.gmail.com
  SMTP_PORT       ej. 465 (SSL) o 587 (STARTTLS)
  SMTP_USER       correo remitente (usuario de la cuenta)
  SMTP_PASSWORD   contraseña de aplicación (App Password en Gmail)
  SMTP_FROM_NAME  nombre visible del remitente (opcional, ej. "Colegio Amancio Varona")

Variables opcionales para controlar el ritmo de los envíos masivos:
  SMTP_MAX_POR_CONEXION  mensajes por conexión antes de reciclarla (por defecto 50)
  SMTP_PAUSA_SEGUNDOS    pausa entre mensajes (por defecto 0.5)
"""
import os
import ssl
import time
import smtplib
import logging
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("email")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Colegio Amancio Varona")
# Buzón al que responden los apoderados si contestan el correo (opcional)
SMTP_REPLY_TO = os.getenv("SMTP_REPLY_TO")

# Ningún proveedor acepta cientos de mensajes seguidos por una misma conexión:
# la cortan por límite de mensajes por sesión o por exceso de velocidad. Estos
# dos valores mantienen el envío dentro de lo que toleran (ajustables por .env).
SMTP_MAX_POR_CONEXION = int(os.getenv("SMTP_MAX_POR_CONEXION", "50"))
SMTP_PAUSA_SEGUNDOS = float(os.getenv("SMTP_PAUSA_SEGUNDOS", "0.5"))

# Si el servidor no acepta la conexión tras estos intentos, el lote se aborta en
# vez de reintentar una por una en los cientos de correos restantes.
_MAX_INTENTOS_CONEXION = 3


def smtp_configurado() -> bool:
    """Indica si hay credenciales SMTP disponibles."""
    return bool(SMTP_USER and SMTP_PASSWORD)


def plantilla_institucional(titulo: str, cuerpo_html: str) -> str:
    """Envuelve un cuerpo HTML en la plantilla institucional (cabecera guinda)."""
    return f"""
    <div style="font-family:Arial,sans-serif;color:#333;max-width:600px;margin:auto;border:1px solid #eee;border-radius:12px;overflow:hidden">
      <div style="background:#701C32;color:#fff;padding:20px 24px">
        <h2 style="margin:0;font-size:18px">Colegio Amancio Varona</h2>
      </div>
      <div style="padding:24px">
        <h3 style="color:#701C32;margin-top:0">{titulo}</h3>
        {cuerpo_html}
        <p style="margin-top:24px;color:#999;font-size:12px">Este es un mensaje automático, por favor no responda a este correo.</p>
      </div>
    </div>
    """


def _dominio_remitente() -> str:
    """Dominio del remitente, para generar Message-ID coherentes con el From."""
    return (SMTP_USER or "").split("@")[-1] or "localhost"


def _crear_mensaje(destinatario: str, asunto: str, html: str, texto_plano: str | None) -> EmailMessage:
    mensaje = EmailMessage()
    mensaje["Subject"] = asunto
    mensaje["From"] = formataddr((SMTP_FROM_NAME, SMTP_USER))
    mensaje["To"] = destinatario

    # Date y Message-ID son obligatorios según la RFC 5322 y los filtros de spam
    # los revisan. Si no los ponemos, el mensaje depende de que el servidor los
    # agregue por su cuenta; generarlos aquí evita esa incertidumbre.
    mensaje["Date"] = formatdate(localtime=True)
    mensaje["Message-ID"] = make_msgid(domain=_dominio_remitente())

    # Marca el correo como generado automáticamente: evita que las respuestas
    # automáticas de los apoderados ("estoy de vacaciones") reboten de vuelta.
    mensaje["Auto-Submitted"] = "auto-generated"

    # Buzón real al que puede responder un apoderado, si se configura
    if SMTP_REPLY_TO:
        mensaje["Reply-To"] = SMTP_REPLY_TO

    mensaje.set_content(texto_plano or "Este correo requiere un cliente compatible con HTML.")
    mensaje.add_alternative(html, subtype="html")
    return mensaje


def _conectar():
    """Abre una conexión SMTP autenticada (SSL o STARTTLS según el puerto)."""
    if SMTP_PORT == 465:
        servidor = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ssl.create_default_context(), timeout=20)
    else:
        servidor = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20)
        servidor.starttls(context=ssl.create_default_context())
    servidor.login(SMTP_USER, SMTP_PASSWORD)
    return servidor


def _conectar_con_reintentos():
    """Intenta conectar varias veces con espera creciente. Devuelve None si no lo logra."""
    for intento in range(1, _MAX_INTENTOS_CONEXION + 1):
        try:
            return _conectar()
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "Fallo de conexión SMTP (intento %d/%d): %s", intento, _MAX_INTENTOS_CONEXION, e
            )
            if intento < _MAX_INTENTOS_CONEXION:
                time.sleep(2 * intento)
    return None


def _cerrar(servidor) -> None:
    """Cierra la conexión ignorando errores (la sesión puede estar ya muerta)."""
    if servidor is None:
        return
    try:
        servidor.quit()
    except Exception:  # noqa: BLE001
        pass


def enviar_correo(destinatario: str, asunto: str, html: str, texto_plano: str | None = None) -> bool:
    """
    Envía un correo HTML a un destinatario. Devuelve True si se envió, False si no.
    No lanza excepciones: registra el error y devuelve False.
    """
    if not smtp_configurado():
        logger.warning("SMTP no configurado: se omite el envío de correo a %s", destinatario)
        return False
    if not destinatario or "@" not in destinatario:
        logger.warning("Destinatario de correo inválido: %r", destinatario)
        return False

    try:
        with _conectar() as servidor:
            servidor.send_message(_crear_mensaje(destinatario, asunto, html, texto_plano))
        return True
    except Exception as e:  # noqa: BLE001
        logger.error("Error enviando correo a %s: %s", destinatario, e)
        return False


def enviar_correos(correos: list[dict]) -> int:
    """
    Envía un lote de correos reutilizando la conexión SMTP, pero reciclándola
    cada SMTP_MAX_POR_CONEXION mensajes y pausando entre envíos para no chocar
    con los límites de velocidad del proveedor. Devuelve cuántos se enviaron.

    Si la conexión se cae a mitad del lote, se reconecta y reintenta ese correo
    una vez; si no se puede conectar del todo, se aborta y se registra el error.

    Cada item: { "destinatario": str, "asunto": str, "html": str, "texto": str? }
    """
    if not smtp_configurado():
        logger.warning("SMTP no configurado: se omiten %d correos", len(correos))
        return 0
    if not correos:
        return 0

    # Descartamos destinatarios inválidos antes de abrir la conexión
    validos = [c for c in correos if c.get("destinatario") and "@" in c["destinatario"]]
    descartados = len(correos) - len(validos)
    if descartados:
        logger.warning("Se descartaron %d correos con destinatario inválido", descartados)
    if not validos:
        return 0

    total = len(validos)
    enviados = 0
    servidor = None
    en_conexion = 0  # mensajes enviados por la conexión actual
    indice = 0
    reintentado = False

    while indice < total:
        item = validos[indice]
        destinatario = item["destinatario"]

        # Conexión nueva al inicio y cada SMTP_MAX_POR_CONEXION mensajes
        if servidor is None or en_conexion >= SMTP_MAX_POR_CONEXION:
            _cerrar(servidor)
            servidor = _conectar_con_reintentos()
            if servidor is None:
                logger.error(
                    "Lote abortado por fallo de conexión SMTP: %d de %d enviados", enviados, total
                )
                break
            en_conexion = 0

        try:
            servidor.send_message(
                _crear_mensaje(destinatario, item["asunto"], item["html"], item.get("texto"))
            )
            enviados += 1
            en_conexion += 1
            indice += 1
            reintentado = False
            if SMTP_PAUSA_SEGUNDOS > 0 and indice < total:
                time.sleep(SMTP_PAUSA_SEGUNDOS)

        except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, OSError) as e:
            # La sesión murió: reciclamos y reintentamos ESTE correo una vez
            _cerrar(servidor)
            servidor = None
            en_conexion = 0
            if not reintentado:
                reintentado = True
                logger.warning("Conexión perdida al enviar a %s (%s). Se reintenta.", destinatario, e)
                continue
            logger.error("Se omite %s tras reintento fallido: %s", destinatario, e)
            reintentado = False
            indice += 1

        except Exception as e:  # noqa: BLE001 - un rechazo puntual no detiene el lote
            logger.error("Error enviando correo a %s: %s", destinatario, e)
            indice += 1
            reintentado = False

    _cerrar(servidor)
    logger.info("Lote SMTP finalizado: %d de %d enviados", enviados, total)
    return enviados
