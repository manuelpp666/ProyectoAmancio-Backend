# -*- coding: utf-8 -*-
"""
Registro de accesos y buzón de "no puedo entrar".

Dos cosas que se miran juntas cuando algo va mal con una cuenta:

  · El REGISTRO DE ACCESOS (solo ADMIN) responde a las tres preguntas que uno
    se hace cuando sospecha que le han entrado a la cuenta: quién ha entrado,
    desde dónde, y si alguien estuvo probando contraseñas antes.

  · Las SOLICITUDES DE ACCESO son el camino de vuelta. El envío es público
    por necesidad —lo usa quien no consigue entrar, así que no puede haber
    sesión de por medio— y lo único que hace es dejar una nota en el panel.
    No reinicia contraseñas ni desbloquea nada: quien escribe no ha demostrado
    ser quien dice ser, y el que decide es una persona.
"""

from __future__ import annotations

import html
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy import func, desc
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.db.database import SessionLocal, get_db
from app.core.util.security import require_roles
from app.core.util import email as correo

from . import service as seguridad
from .models import IntentoAcceso, SolicitudAcceso
from .schemas import SolicitudAccesoAtender, SolicitudAccesoCreate

router = APIRouter(prefix="/seguridad", tags=["Seguridad"])


def _fila(i: IntentoAcceso) -> dict:
    return {
        "id_intento": i.id_intento,
        "username": i.username,
        "rol": i.rol,
        "exito": bool(i.exito),
        "motivo": i.motivo,
        "ip": i.ip,
        "user_agent": i.user_agent,
        "fecha": i.fecha.strftime("%d/%m/%Y %H:%M:%S") if i.fecha else None,
    }


@router.get("/accesos")
def listar_accesos(dias: int = Query(7, ge=1, le=90),
                   username: Optional[str] = None,
                   solo_fallos: bool = False,
                   solo_aciertos: bool = False,
                   limite: int = Query(200, ge=1, le=1000),
                   db: Session = Depends(get_db),
                   current_user: dict = Depends(require_roles("ADMIN"))):
    desde = datetime.now() - timedelta(days=dias)
    q = db.query(IntentoAcceso).filter(IntentoAcceso.fecha >= desde)

    if username:
        q = q.filter(IntentoAcceso.username.ilike(f"%{username}%"))
    if solo_fallos:
        q = q.filter(IntentoAcceso.exito.is_(False))
    elif solo_aciertos:
        q = q.filter(IntentoAcceso.exito.is_(True))

    filas = q.order_by(desc(IntentoAcceso.fecha)).limit(limite).all()
    return {"dias": dias, "total": len(filas),
            "accesos": [_fila(f) for f in filas]}


@router.get("/resumen")
def resumen(dias: int = Query(7, ge=1, le=90),
            db: Session = Depends(get_db),
            current_user: dict = Depends(require_roles("ADMIN"))):
    """Lo que conviene mirar de un vistazo."""
    desde = datetime.now() - timedelta(days=dias)
    base = db.query(IntentoAcceso).filter(IntentoAcceso.fecha >= desde)

    aciertos = base.filter(IntentoAcceso.exito.is_(True)).count()
    fallos = base.filter(IntentoAcceso.exito.is_(False)).count()

    # Cuentas con más fallos: si una destaca, alguien la está tanteando.
    tanteadas = (db.query(IntentoAcceso.username, func.count().label("n"))
                 .filter(IntentoAcceso.fecha >= desde,
                         IntentoAcceso.exito.is_(False))
                 .group_by(IntentoAcceso.username)
                 .order_by(desc("n")).limit(10).all())

    # Desde cuántos sitios distintos ha entrado cada cuenta de administrador.
    # Dos IPs muy distintas para el mismo administrador es la señal que delata
    # un acceso ajeno.
    ips_admin = (db.query(IntentoAcceso.username,
                          func.count(func.distinct(IntentoAcceso.ip)).label("n_ips"),
                          func.count().label("entradas"))
                 .filter(IntentoAcceso.fecha >= desde,
                         IntentoAcceso.exito.is_(True),
                         IntentoAcceso.rol == "ADMIN")
                 .group_by(IntentoAcceso.username)
                 .order_by(desc("n_ips")).all())

    return {
        "dias": dias,
        "aciertos": aciertos,
        "fallos": fallos,
        "cuentas_mas_tanteadas": [{"username": u, "fallos": n} for u, n in tanteadas],
        "admins_por_ip": [{"username": u, "ips_distintas": n, "entradas": e}
                          for u, n, e in ips_admin],
    }


@router.get("/mis-accesos")
def mis_accesos(dias: int = Query(30, ge=1, le=90),
                db: Session = Depends(get_db),
                current_user: dict = Depends(require_roles("ADMIN"))):
    """Las entradas a MI propia cuenta. Es la vista que resuelve la sospecha."""
    desde = datetime.now() - timedelta(days=dias)
    filas = (db.query(IntentoAcceso)
             .filter(IntentoAcceso.fecha >= desde,
                     IntentoAcceso.username == current_user.get("sub"))
             .order_by(desc(IntentoAcceso.fecha)).limit(300).all())
    return {"username": current_user.get("sub"), "dias": dias,
            "accesos": [_fila(f) for f in filas]}


# ---------------------------------------------------------------------------
# Solicitudes de acceso — "no puedo entrar"
# ---------------------------------------------------------------------------

ESTADOS = ("PENDIENTE", "ATENDIDA", "DESCARTADA")


def _fila_solicitud(s: SolicitudAcceso) -> dict:
    return {
        "id_solicitud": s.id_solicitud,
        "dni": s.dni,
        "telefono": s.telefono,
        "descripcion": s.descripcion,
        "nombre": s.nombre,
        "rol": s.rol,
        "dni_encontrado": bool(s.dni_encontrado),
        "estado": s.estado,
        "nota": s.nota,
        "atendida_por": s.atendida_por,
        "fecha_atencion": (s.fecha_atencion.strftime("%d/%m/%Y %H:%M")
                           if s.fecha_atencion else None),
        "ip": s.ip,
        "fecha": s.fecha.strftime("%d/%m/%Y %H:%M") if s.fecha else None,
    }


def _asegurar_tabla(db: Session) -> None:
    """Crea `solicitud_acceso` si el script SQL todavía no se ha ejecutado.

    Es una red de seguridad, no la forma prevista de crearla: el script
    27_solicitudes_acceso.sql sigue siendo lo que hay que correr. Pero este
    endpoint lo usa gente que ya está teniendo un problema, y perder su aviso
    porque falta una tabla sería el peor momento posible para fallar.
    """
    SolicitudAcceso.__table__.create(bind=db.get_bind(), checkfirst=True)


def _avisar_a_los_administradores(id_solicitud: int) -> None:
    """Manda el aviso por correo. Se ejecuta DESPUÉS de responder.

    Va en segundo plano y con su propia sesión a propósito: el SMTP del
    hosting tarda segundos en algunas conexiones, y este endpoint es público.
    Si el aviso se hiciera dentro de la petición, bastaría con llamarlo en
    bucle para dejar la web colgada.

    Que el correo falle no importa: la solicitud ya está guardada y sale en el
    panel igualmente. El correo solo sirve para que alguien la vea antes.
    """
    if not correo.smtp_configurado():
        return
    sesion = None
    try:
        from app.modules.personal.models import Administrador

        sesion = SessionLocal()
        s = sesion.get(SolicitudAcceso, id_solicitud)
        if s is None:
            return

        destinos = [a.email.strip() for a in sesion.query(Administrador).all()
                    if a.email and "@" in a.email]
        if not destinos:
            return

        # Todo lo que escribió el visitante se escapa antes de meterlo en el
        # HTML: es texto de fuera y podría traer etiquetas.
        quien = (f"{html.escape(s.nombre)} ({s.rol})" if s.nombre
                 else "<b>ese DNI no figura en el sistema</b>")
        cuando = s.fecha.strftime("%d/%m/%Y %H:%M") if s.fecha else "—"
        cuerpo = f"""
          <p>Alguien no consigue entrar al campus y ha dejado este aviso desde
             la pantalla de inicio de sesión:</p>
          <table style="border-collapse:collapse;font-size:14px">
            <tr><td style="padding:4px 12px 4px 0;color:#777">DNI</td>
                <td><b>{html.escape(s.dni)}</b> — {quien}</td></tr>
            <tr><td style="padding:4px 12px 4px 0;color:#777">Teléfono</td>
                <td><b>{html.escape(s.telefono)}</b></td></tr>
            <tr><td style="padding:4px 12px 4px 0;color:#777">Fecha</td>
                <td>{cuando}</td></tr>
          </table>
          <p style="margin-top:16px;color:#777">Lo que cuenta:</p>
          <blockquote style="margin:0;padding:12px 16px;background:#f6f6f6;
                             border-left:4px solid #701C32">
            {html.escape(s.descripcion)}
          </blockquote>
          <p style="margin-top:20px">Se atiende en el panel, en
             <b>Seguridad &rarr; Solicitudes de acceso</b>.</p>
          <p style="color:#999;font-size:12px">Comprueba la identidad de la
             persona antes de tocarle la cuenta: cualquiera pudo escribir ese
             DNI.</p>
        """
        html_final = correo.plantilla_institucional(
            "Alguien no puede entrar al campus", cuerpo)
        for destino in destinos[:10]:
            correo.enviar_correo(
                destino, f"Solicitud de acceso — DNI {s.dni}", html_final)
    except Exception as e:
        print(f"[SEGURIDAD][WARN] No se pudo avisar de la solicitud "
              f"{id_solicitud}: {type(e).__name__}: {str(e).splitlines()[0][:120]}")
    finally:
        if sesion is not None:
            try:
                sesion.close()
            except Exception:
                pass


@router.post("/solicitudes-acceso", status_code=201)
def crear_solicitud(datos: SolicitudAccesoCreate,
                    request: Request,
                    tareas: BackgroundTasks,
                    db: Session = Depends(get_db)):
    """Recibe un aviso de "no puedo entrar". PÚBLICO, sin sesión.

    Tiene que ser público: el que lo usa es precisamente el que no consigue
    iniciar sesión. A cambio, lo único que puede hacer es dejar la nota.
    """
    ip = seguridad.ip_de(request)

    freno = seguridad.solicitudes_recientes(db, datos.dni, ip)
    if freno:
        # 429 y no 400: no es que el dato esté mal, es que ya llegó.
        raise HTTPException(status_code=429, detail=freno)

    nombre, rol = seguridad.titular_del_dni(db, datos.dni)

    solicitud = SolicitudAcceso(
        dni=datos.dni,
        telefono=datos.telefono,
        descripcion=datos.descripcion,
        nombre=nombre,
        rol=rol,
        dni_encontrado=bool(nombre),
        estado="PENDIENTE",
        ip=ip,
        user_agent=(request.headers.get("user-agent") or "")[:255] or None,
    )
    try:
        db.add(solicitud)
        db.commit()
    except (ProgrammingError, OperationalError):
        db.rollback()
        try:
            _asegurar_tabla(db)
            db.add(solicitud)
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"[SEGURIDAD][ERROR] No se pudo guardar la solicitud: {e}")
            raise HTTPException(
                status_code=503,
                detail=("Ahora mismo no podemos recibir tu solicitud. "
                        "Inténtalo más tarde o llama al colegio."))
    db.refresh(solicitud)

    tareas.add_task(_avisar_a_los_administradores, solicitud.id_solicitud)

    # La respuesta es la misma exista o no el DNI. Decir "ese DNI no figura"
    # ayudaría a quien se equivocó al teclear, pero también convertiría el
    # formulario en una forma de comprobar quién estudia aquí, y eso no
    # compensa. El administrador sí lo ve en el panel.
    return {
        "ok": True,
        "mensaje": ("Hemos recibido tu solicitud. El colegio revisará tu caso "
                    "y se pondrá en contacto contigo por el teléfono que "
                    "dejaste."),
    }


@router.get("/solicitudes-acceso")
def listar_solicitudes(estado: Optional[str] = Query(None),
                       dias: int = Query(90, ge=1, le=365),
                       limite: int = Query(200, ge=1, le=500),
                       db: Session = Depends(get_db),
                       current_user: dict = Depends(require_roles("ADMIN"))):
    """La bandeja del panel. Las más recientes primero."""
    desde = datetime.now() - timedelta(days=dias)
    try:
        q = db.query(SolicitudAcceso).filter(SolicitudAcceso.fecha >= desde)
        if estado in ESTADOS:
            q = q.filter(SolicitudAcceso.estado == estado)
        filas = q.order_by(desc(SolicitudAcceso.fecha)).limit(limite).all()
        pendientes = (db.query(func.count(SolicitudAcceso.id_solicitud))
                      .filter(SolicitudAcceso.estado == "PENDIENTE")
                      .scalar() or 0)
    except (ProgrammingError, OperationalError):
        # La tabla aún no existe: la pantalla se dibuja vacía en vez de romper
        # el resto de los ajustes de seguridad, que sí funcionan.
        db.rollback()
        return {"total": 0, "pendientes": 0, "solicitudes": [],
                "aviso": ("Falta ejecutar el script "
                          "27_solicitudes_acceso.sql en la base de datos.")}

    return {"total": len(filas), "pendientes": int(pendientes),
            "solicitudes": [_fila_solicitud(f) for f in filas]}


@router.patch("/solicitudes-acceso/{id_solicitud}")
def atender_solicitud(id_solicitud: int,
                      datos: SolicitudAccesoAtender,
                      db: Session = Depends(get_db),
                      current_user: dict = Depends(require_roles("ADMIN"))):
    """Marca una solicitud como atendida o descartada, con una nota de qué se hizo."""
    solicitud = db.get(SolicitudAcceso, id_solicitud)
    if solicitud is None:
        raise HTTPException(status_code=404, detail="Esa solicitud no existe")

    solicitud.estado = datos.estado
    solicitud.nota = (datos.nota or "").strip()[:300] or None
    if datos.estado == "PENDIENTE":
        # Se devuelve a la bandeja: se limpia quién y cuándo la cerró, para que
        # no quede diciendo que la atendió alguien que ya no la ha atendido.
        solicitud.atendida_por = None
        solicitud.fecha_atencion = None
    else:
        solicitud.atendida_por = (current_user.get("sub") or "")[:50] or None
        # La hora la pone la base, no Python: la columna `fecha` de esta misma
        # tabla se rellena con el CURRENT_TIMESTAMP de MySQL, y si esta se
        # pusiera con el reloj del proceso las dos discreparían cuando el
        # servidor y la base no comparten zona horaria. Se ve enseguida: una
        # solicitud atendida cinco horas ANTES de recibirse.
        solicitud.fecha_atencion = func.now()
    db.commit()
    db.refresh(solicitud)
    return _fila_solicitud(solicitud)
