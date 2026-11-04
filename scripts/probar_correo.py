# -*- coding: utf-8 -*-
"""
Diagnóstico del envío de correos, para correr EN EL SERVIDOR.

Prueba, con el mismo código que usa el backend, cada forma de llegar al
servidor de correo:

  * la que está en el .env (SMTP_HOST / SMTP_PORT);
  * localhost en los puertos 465, 587 y 25. En el hosting compartido la
    aplicación no puede conectarse al nombre público (da "Connection
    refused"), pero suele poder hacerlo al servidor de correo de la misma
    máquina.

Con cada una intenta conectar e iniciar sesión, y al final dice qué poner en
el .env. No enseña la contraseña, no cambia el .env ni la base de datos.

Cómo se usa (Terminal de cPanel, dentro del entorno de la app Python):

    cd ~/ruta/del/backend
    python scripts/probar_correo.py                    # solo prueba conexiones
    python scripts/probar_correo.py tu@correo.com      # y manda un correo de prueba
                                                       # con la primera que funcione
"""
import os
import smtplib
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
for flujo in (sys.stdout, sys.stderr):
    if hasattr(flujo, "reconfigure"):
        flujo.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(BASE, ".env"))

from app.core.util import email as correo  # noqa: E402

DESTINO = sys.argv[1] if len(sys.argv) > 1 else None

print("\n1) Configuración del .env")
faltan = [n for n in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD")
          if not (os.getenv(n) or "").strip()]
if faltan:
    print(f"  [FALLA] Faltan en el .env: {', '.join(faltan)}")
    print("          Cópialas del .env de tu equipo y reinicia la app Python.")
    sys.exit(1)
clave = os.getenv("SMTP_PASSWORD") or ""
print(f"  [OK]    SMTP_HOST={correo.SMTP_HOST}  SMTP_PORT={correo.SMTP_PORT}  "
      f"SMTP_USER={correo.SMTP_USER}  SMTP_PASSWORD=({len(clave)} caracteres)")
if clave != clave.strip():
    print("  [AVISO] La contraseña empieza o termina con espacios: revisa que no "
          "se hayan colado al copiarla.")


def probar(host: str, puerto: int):
    """Conecta e inicia sesión como lo hace el backend. Devuelve la conexión o el error."""
    local = host.lower() in ("localhost", "127.0.0.1", "::1")
    try:
        return correo._abrir(host, puerto, local), None
    except smtplib.SMTPAuthenticationError as e:
        return None, f"usuario o contraseña rechazados ({e.smtp_code})"
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


print("\n2) Formas de llegar al servidor de correo")
candidatas = [(correo.SMTP_HOST, correo.SMTP_PORT)]
for p in (465, 587, 25):
    if ("localhost", p) not in candidatas:
        candidatas.append(("localhost", p))

funciona = None
for host, puerto in candidatas:
    servidor, error = probar(host, puerto)
    if servidor:
        print(f"  [OK]    {host}:{puerto}  -> conecta e inicia sesión")
        if funciona is None:
            funciona = (host, puerto, servidor)
        else:
            servidor.quit()
    else:
        print(f"  [--]    {host}:{puerto}  -> {error}")

if funciona is None:
    print("\n  [FALLA] Ninguna funciona desde este servidor.")
    print("          Pide al soporte del hosting que permita a tu usuario de cPanel enviar")
    print("          correo por SMTP desde la aplicación Python («SMTP Restrictions»),")
    print("          y envíales las líneas de arriba.")
    sys.exit(1)

host, puerto, servidor = funciona
print(f"\n3) Qué poner en el .env del servidor")
if (host, puerto) == (os.getenv("SMTP_HOST", "").strip(), int(os.getenv("SMTP_PORT", "0") or 0)):
    print(f"  [OK]    Lo que ya tienes funciona (SMTP_HOST={host}, SMTP_PORT={puerto}).")
else:
    print(f"  Cambia estas dos líneas y reinicia la app Python:")
    print(f"      SMTP_HOST={host}")
    print(f"      SMTP_PORT={puerto}")
    print(f"  SMTP_USER y SMTP_PASSWORD se quedan como están.")

if not DESTINO:
    servidor.quit()
    print("\nPara probar también un envío real:")
    print("    python scripts/probar_correo.py tu@correo.com\n")
    sys.exit(0)

print(f"\n4) Envío real a {DESTINO} por {host}:{puerto}")
try:
    rechazados = servidor.send_message(correo._crear_mensaje(
        DESTINO, "Prueba de correo del Campus Virtual",
        correo.plantilla_institucional(
            "Prueba de correo",
            "<p>Si lees esto, el servidor del campus puede enviar correos.</p>"),
        "Si lees esto, el servidor del campus puede enviar correos."))
    servidor.quit()
except smtplib.SMTPDataError as e:
    print(f"  [FALLA] El servidor rechazó el mensaje: {e.smtp_code} {e.smtp_error!r}")
    print("          Si dice rSPAM, es el filtro de salida del hosting (MailBaby).")
    sys.exit(1)
except Exception as e:  # noqa: BLE001
    print(f"  [FALLA] {type(e).__name__}: {e}")
    sys.exit(1)
if rechazados:
    print(f"  [FALLA] Rechazados: {rechazados}")
    sys.exit(1)
print("  [OK]    El servidor de correo aceptó el mensaje. Revisa la bandeja (y spam).\n")
