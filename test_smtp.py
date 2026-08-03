"""
Diagnóstico del envío SMTP del cPanel de amanciovarona.com.

Prueba los dos puertos habituales y explica el error si algo falla.
La contraseña se pide por teclado: no queda guardada en el archivo.

Uso:  python test_smtp.py
"""
import ssl
import smtplib
import socket
from getpass import getpass
from email.message import EmailMessage
from email.utils import formataddr

# --- Datos que muestra cPanel en "Conectar dispositivos" ---
HOST = "mail.amanciovarona.com"
USER = "notificaciones@amanciovarona.com"
FROM_NAME = "Colegio Amancio Varona"

# Puertos a probar: (puerto, tipo de cifrado)
PUERTOS = [(465, "SSL"), (587, "STARTTLS")]


def construir_mensaje(destino: str, puerto: int) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = f"Prueba SMTP desde cPanel (puerto {puerto})"
    msg["From"] = formataddr((FROM_NAME, USER))
    msg["To"] = destino
    msg.set_content(
        "Prueba de envio del Colegio Amancio Varona.\n"
        f"Enviado por {HOST} en el puerto {puerto}."
    )
    msg.add_alternative(
        '<div style="font-family:Arial,sans-serif">'
        '<div style="background:#701C32;color:#fff;padding:16px">'
        "<strong>Colegio Amancio Varona</strong></div>"
        f'<div style="padding:16px"><p>Prueba de envio correcta.</p>'
        f"<p>Servidor: {HOST}<br>Puerto: {puerto}</p></div></div>",
        subtype="html",
    )
    return msg


def diagnosticar(e: Exception, puerto: int) -> str:
    if isinstance(e, smtplib.SMTPAuthenticationError):
        return ("AUTENTICACION RECHAZADA. El usuario debe ser el correo COMPLETO "
                "y la contrasena la del buzon. Si son correctos, revisa si cPHulk "
                "bloqueo tu IP tras varios intentos fallidos.")
    if isinstance(e, ssl.SSLCertVerificationError):
        return (f"CERTIFICADO SSL NO VALIDO para {HOST}. El certificado esta emitido "
                "a otro nombre. Usa el hostname real del servidor (cPanel > "
                "Informacion del servidor) en lugar de mail.amanciovarona.com.")
    if isinstance(e, (socket.timeout, TimeoutError)):
        return (f"TIMEOUT en el puerto {puerto}. O tu proveedor de internet bloquea "
                "este puerto saliente, o el hosting no permite acceso SMTP remoto.")
    if isinstance(e, smtplib.SMTPConnectError):
        return f"El servidor rechazo la conexion en el puerto {puerto}."
    if isinstance(e, (ConnectionRefusedError, OSError)):
        return (f"No se pudo abrir el puerto {puerto}. Puede estar cerrado en el "
                "servidor o bloqueado por tu red.")
    if isinstance(e, smtplib.SMTPRecipientsRefused):
        return "El servidor acepto el login pero rechazo al destinatario."
    return "Error no clasificado (ver el detalle de arriba)."


def probar(puerto: int, cifrado: str, password: str, destino: str) -> bool:
    print(f"\n{'=' * 58}")
    print(f"Probando {HOST}:{puerto}  ({cifrado})")
    print("=" * 58)
    servidor = None
    try:
        contexto = ssl.create_default_context()
        if cifrado == "SSL":
            servidor = smtplib.SMTP_SSL(HOST, puerto, context=contexto, timeout=20)
        else:
            servidor = smtplib.SMTP(HOST, puerto, timeout=20)
            servidor.starttls(context=contexto)
        print("  [1/3] Conexion establecida y cifrada")

        servidor.login(USER, password)
        print("  [2/3] Autenticacion correcta")

        servidor.send_message(construir_mensaje(destino, puerto))
        print(f"  [3/3] Correo enviado a {destino}")
        print(f"\n  >>> EXITO en el puerto {puerto} <<<")
        return True

    except Exception as e:
        print(f"  FALLO: {type(e).__name__}: {e}")
        print(f"\n  >>> {diagnosticar(e, puerto)}")
        return False
    finally:
        if servidor is not None:
            try:
                servidor.quit()
            except Exception:
                pass


def main():
    print(f"\nDiagnostico SMTP para {USER}\n")
    destino = input("Correo donde quieres recibir la prueba (usa un Gmail): ").strip()
    if "@" not in destino:
        print("Correo invalido.")
        return
    password = getpass(f"Contrasena de {USER} (no se muestra): ")
    if not password:
        print("Sin contrasena no se puede probar.")
        return

    exitosos = [p for p, c in PUERTOS if probar(p, c, password, destino)]

    print(f"\n{'=' * 58}")
    print("RESUMEN")
    print("=" * 58)
    if exitosos:
        recomendado = 465 if 465 in exitosos else exitosos[0]
        print(f"Puertos que funcionan: {exitosos}")
        print("\nPon esto en tu archivo .env:\n")
        print(f"  SMTP_HOST={HOST}")
        print(f"  SMTP_PORT={recomendado}")
        print(f"  SMTP_USER={USER}")
        print("  SMTP_PASSWORD=<la contrasena del buzon>")
        print(f"  SMTP_FROM_NAME={FROM_NAME}")
        print("\nAHORA REVISA EL CORREO QUE RECIBISTE:")
        print("  - Si llego a BANDEJA DE ENTRADA: vas bien.")
        print("  - Si llego a SPAM: falta configurar SPF y DKIM")
        print("    (cPanel > Correo electronico > Email Deliverability).")
        print("  - Si no llego nada: revisa cPanel > Monitorizar el envio.")
    else:
        print("Ningun puerto funciono. Revisa el diagnostico de cada uno arriba.")
        print("Si ambos dieron TIMEOUT, prueba desde otra red (datos del celular)")
        print("para descartar que sea tu proveedor de internet quien bloquea.")


if __name__ == "__main__":
    main()
