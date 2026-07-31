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
"""
import os
import ssl
import smtplib
import logging
from email.message import EmailMessage
from email.utils import formataddr

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("email")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Colegio Amancio Varona")


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


def _crear_mensaje(destinatario: str, asunto: str, html: str, texto_plano: str | None) -> EmailMessage:
    mensaje = EmailMessage()
    mensaje["Subject"] = asunto
    mensaje["From"] = formataddr((SMTP_FROM_NAME, SMTP_USER))
    mensaje["To"] = destinatario
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
    Envía muchos correos reutilizando UNA sola conexión SMTP (mucho más rápido
    que reconectar por cada destinatario). Devuelve cuántos se enviaron.

    Cada item: { "destinatario": str, "asunto": str, "html": str, "texto": str? }
    """
    if not smtp_configurado():
        logger.warning("SMTP no configurado: se omiten %d correos", len(correos))
        return 0
    if not correos:
        return 0

    enviados = 0
    try:
        with _conectar() as servidor:
            for c in correos:
                destinatario = c.get("destinatario", "")
                if not destinatario or "@" not in destinatario:
                    logger.warning("Destinatario inválido, se omite: %r", destinatario)
                    continue
                try:
                    servidor.send_message(
                        _crear_mensaje(destinatario, c["asunto"], c["html"], c.get("texto"))
                    )
                    enviados += 1
                except Exception as e:  # noqa: BLE001 - un fallo no debe detener el lote
                    logger.error("Error enviando correo a %s: %s", destinatario, e)
    except Exception as e:  # noqa: BLE001 - fallo al conectar/autenticar
        logger.error("Error de conexión SMTP para el lote: %s", e)

    return enviados
