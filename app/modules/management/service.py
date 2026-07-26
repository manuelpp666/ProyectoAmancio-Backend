"""
Servicios del módulo de gestión.

Incluye la notificación por correo a los apoderados cuando se registra la
asistencia diaria de una sección.
"""
import logging
from datetime import date

from app.core.util.email import enviar_correos

logger = logging.getLogger("asistencia")

# Etiqueta y color de marca por cada estado de asistencia
ESTADOS_ASISTENCIA = {
    "P": {"label": "Presente", "color": "#059669"},
    "T": {"label": "Tardanza", "color": "#d97706"},
    "F": {"label": "Falta", "color": "#dc2626"},
    "J": {"label": "Justificado", "color": "#475569"},
}

GUINDA = "#701C32"


def _formatear_fecha(f: date) -> str:
    meses = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ]
    return f"{f.day} de {meses[f.month - 1]} de {f.year}"


def _construir_html(alumno_nombre: str, estado: str, fecha: date) -> str:
    info = ESTADOS_ASISTENCIA.get(estado, {"label": estado, "color": GUINDA})
    fecha_txt = _formatear_fecha(fecha)
    return f"""\
<!DOCTYPE html>
<html lang="es">
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;">
  <div style="max-width:520px;margin:0 auto;padding:24px;">
    <div style="background:{GUINDA};color:#ffffff;padding:24px;border-radius:16px 16px 0 0;text-align:center;">
      <h1 style="margin:0;font-size:20px;letter-spacing:1px;text-transform:uppercase;">Colegio Amancio Varona</h1>
      <p style="margin:6px 0 0;font-size:12px;opacity:.85;">Reporte de asistencia diaria</p>
    </div>
    <div style="background:#ffffff;padding:28px 24px;border-radius:0 0 16px 16px;border:1px solid #e2e8f0;border-top:none;">
      <p style="color:#334155;font-size:15px;margin:0 0 16px;">Estimado(a) apoderado(a):</p>
      <p style="color:#334155;font-size:15px;line-height:1.6;margin:0 0 20px;">
        Le informamos el registro de asistencia de su menor hijo(a)
        <strong>{alumno_nombre}</strong> correspondiente al <strong>{fecha_txt}</strong>:
      </p>
      <div style="text-align:center;margin:0 0 24px;">
        <span style="display:inline-block;background:{info['color']};color:#ffffff;font-weight:bold;font-size:16px;padding:12px 28px;border-radius:9999px;">
          {info['label']}
        </span>
      </div>
      <p style="color:#64748b;font-size:13px;line-height:1.6;margin:0;">
        Si considera que este registro es incorrecto, por favor comuníquese con la
        auxiliar de educación del colegio.
      </p>
    </div>
    <p style="text-align:center;color:#94a3b8;font-size:11px;margin:16px 0 0;">
      Este es un correo automático, por favor no responda a este mensaje.
    </p>
  </div>
</body>
</html>"""


def enviar_notificaciones_asistencia(notificaciones: list[dict]) -> None:
    """
    Envía un correo por cada apoderado. Se ejecuta en segundo plano.

    `notificaciones` es una lista de dicts con:
      { "email": str, "alumno_nombre": str, "estado": str, "fecha": date }
    """
    correos = []
    for n in notificaciones:
        estado = n.get("estado", "")
        label = ESTADOS_ASISTENCIA.get(estado, {}).get("label", estado)
        correos.append({
            "destinatario": n["email"],
            "asunto": f"Asistencia de {n['alumno_nombre']}: {label}",
            "html": _construir_html(n["alumno_nombre"], estado, n["fecha"]),
            "texto": (
                f"Estimado apoderado, le informamos que {n['alumno_nombre']} fue registrado(a) "
                f"con estado '{label}' el {_formatear_fecha(n['fecha'])}."
            ),
        })

    enviados = enviar_correos(correos)
    logger.info("Notificaciones de asistencia: %d de %d enviadas", enviados, len(correos))
