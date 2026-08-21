# -*- coding: utf-8 -*-
"""Mantenimiento del espacio en disco.

DOS PUERTAS, A PROPÓSITO DISTINTAS

  GET  /mantenimiento/estado    ADMIN. Solo mira. Dice qué ocupa cada cosa y
                                cuántos archivos sueltos hay. Es la simulación
                                de la limpieza: enseña lo que se borraría sin
                                borrar nada.

  POST /mantenimiento/limpieza  Cron. Esta sí borra. No la protege un rol sino
                                la clave de servicio (`CRON_SECRET`), igual
                                que las tareas de pensiones y moras: la llama
                                una máquina, no una persona con sesión
                                iniciada.

POR QUÉ EL BORRADO NO ESTÁ EN EL PANEL
    Un botón "limpiar" en la pantalla del administrador acabaría pulsándose
    por curiosidad. El mantenimiento no necesita a nadie delante: corre solo
    una vez por semana, y quien quiera ver qué va a pasar tiene el estado.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import SessionLocal, get_db
from app.core.util.security import require_roles, require_service_key
from app.core.util import email as correo

from . import service as mantenimiento

router = APIRouter(prefix="/mantenimiento", tags=["Mantenimiento"])


def _avisar_del_disco(informe: dict) -> None:
    """Correo a los administradores cuando el disco va justo.

    Va en segundo plano y con su propia sesión, como el aviso de solicitudes
    de acceso: el SMTP del hosting tarda segundos y el cron no tiene por qué
    esperarlo.

    Solo se manda si se pasa el umbral. Un correo semanal diciendo que todo
    está bien se convierte en un correo que nadie abre, y el día que importe
    tampoco lo abrirán.
    """
    disco = informe.get("disco") or {}
    if not disco.get("en_alerta"):
        return
    if not correo.smtp_configurado():
        return

    sesion = None
    try:
        from app.modules.personal.models import Administrador

        sesion = SessionLocal()
        destinos = [a.email.strip() for a in sesion.query(Administrador).all()
                    if a.email and "@" in a.email]
        if not destinos:
            return

        liberado = informe.get("espacio_liberado", "0 B")
        huerfanos = informe.get("archivos_huerfanos", {})
        cuerpo = f"""
          <p>El disco del servidor está al
             <b>{disco.get('porcentaje_usado')}%</b>.</p>
          <table style="border-collapse:collapse;font-size:14px">
            <tr><td style="padding:4px 12px 4px 0;color:#777">Ocupado</td>
                <td><b>{disco.get('usado')}</b> de {disco.get('total')}</td></tr>
            <tr><td style="padding:4px 12px 4px 0;color:#777">Libre</td>
                <td><b>{disco.get('libre')}</b></td></tr>
            <tr><td style="padding:4px 12px 4px 0;color:#777">Liberado hoy</td>
                <td>{liberado} ({huerfanos.get('borrados', 0)} archivos
                    sueltos)</td></tr>
          </table>
          <p style="margin-top:16px">El mantenimiento automático ya pasó y
             esto es lo que queda. Cuando el aviso se repite semana tras
             semana, limpiar no basta: hay que mirar qué está creciendo, en
             <b>Panel &rarr; Mantenimiento</b>.</p>
          <p style="color:#999;font-size:12px">Lo que más suele ocupar no es
             la base de datos (pesa pocos MB) sino los archivos subidos al
             aula virtual, las copias de seguridad y los registros del
             servidor.</p>
        """
        html = correo.plantilla_institucional(
            "El disco del servidor se está llenando", cuerpo)
        for destino in destinos[:10]:
            correo.enviar_correo(
                destino,
                f"Disco al {disco.get('porcentaje_usado')}% — servidor del colegio",
                html)
    except Exception as e:
        # Que el aviso falle no puede tumbar el mantenimiento: la limpieza ya
        # se hizo y el informe ya se devolvió.
        print(f"[MANTENIMIENTO][WARN] No se pudo avisar del disco: "
              f"{type(e).__name__}: {str(e).splitlines()[0][:120]}")
    finally:
        if sesion is not None:
            try:
                sesion.close()
            except Exception:
                pass


@router.get("/estado")
def ver_estado(db: Session = Depends(get_db),
               current_user: dict = Depends(require_roles("ADMIN"))):
    """Qué ocupa el disco ahora mismo. No borra nada."""
    return mantenimiento.estado(db)


@router.post("/limpieza")
def ejecutar_limpieza(
    tareas: BackgroundTasks,
    simular: bool = Query(False,
                          description="Si es true, cuenta lo que borraría "
                                      "pero no borra nada."),
    db: Session = Depends(get_db),
    _svc: bool = Depends(require_service_key("CRON_SECRET")),
):
    """Mantenimiento semanal. Lo llama un cron; ver el README del módulo.

    Conviene estrenarlo con `?simular=true` unas cuantas semanas y mirar el
    informe antes de dejarlo borrando de verdad.
    """
    informe = mantenimiento.limpiar(db, simular=simular)
    if not simular:
        tareas.add_task(_avisar_del_disco, informe)
    return informe
