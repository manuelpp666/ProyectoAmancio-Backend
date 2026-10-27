# -*- coding: utf-8 -*-
"""
«Olvidé mi contraseña»: DNI -> código al correo -> contraseña nueva.

Los cuatro endpoints son públicos por necesidad (los usa quien no puede
entrar). Cada uno vuelve a comprobar todo por su cuenta: la pantalla guía,
pero no se fía nadie de ella. La lógica y el porqué de cada regla están en
service.py.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.util.password import get_password_hash
from app.db.database import get_db
from app.modules.seguridad import service as seguridad

from . import service
from .schemas import CambiarPassword, ConsultaDni, CuentaElegida, VerificarCodigo

router = APIRouter(prefix="/recuperar-password", tags=["Recuperar contraseña"])

_NO_DISPONIBLE = ("Ahora mismo no podemos atender tu pedido. Inténtalo en unos "
                  "minutos o usa «No puedo entrar».")
_VUELVE_A_EMPEZAR = ("El tiempo para cambiar la contraseña terminó o el enlace ya "
                     "se usó. Vuelve a pedir un código.")


def _frenado(e: service.Freno) -> HTTPException:
    return HTTPException(status_code=429, detail=e.mensaje,
                         headers={"Retry-After": str(e.segundos)})


def _preparar(db: Session, request: Request) -> str | None:
    """Tablas listas y freno de consultas por conexión. Devuelve la IP."""
    try:
        service.asegurar_tablas(db)
    except Exception as e:  # noqa: BLE001
        db.rollback()
        print(f"[RECUPERACION][ERROR] No se pudieron crear las tablas: {e}")
        raise HTTPException(status_code=503, detail=_NO_DISPONIBLE)
    ip = seguridad.ip_de(request)
    try:
        service.frenar_consultas(db, ip)
    except service.Freno as e:
        raise _frenado(e)
    return ip


def _cuenta_o_404(db: Session, dni: str, rol: str, ip: str | None):
    """La cuenta elegida. Si no existe, cuenta como consulta fallida: si no,
    estos endpoints servirían para revisar DNIs saltándose el freno."""
    usuario = service.cuenta(db, dni, rol)
    if usuario is None:
        service.anotar_consulta(db, dni, False, ip)
        raise HTTPException(status_code=404,
                            detail="No encontramos esa cuenta. Vuelve a escribir tu DNI.")
    return usuario


def _fallo_de_base(e: Exception, paso: str) -> HTTPException:
    print(f"[RECUPERACION][ERROR] {paso}: {type(e).__name__}: {str(e).splitlines()[0][:200]}")
    return HTTPException(status_code=503, detail=_NO_DISPONIBLE)


@router.post("/consultar")
def consultar(datos: ConsultaDni, request: Request, db: Session = Depends(get_db)):
    """Paso 1: qué cuentas tiene el DNI y qué se puede hacer con cada una."""
    ip = _preparar(db, request)
    try:
        cuentas = service.cuentas_del_dni(db, datos.dni)
        service.anotar_consulta(db, datos.dni, bool(cuentas), ip)
    except SQLAlchemyError as e:
        db.rollback()
        raise _fallo_de_base(e, "consultar")
    if not cuentas:
        raise HTTPException(
            status_code=404,
            detail=f"No encontramos ninguna cuenta con el DNI {datos.dni}. "
                   "Revisa que esté bien escrito.")
    return {"dni": datos.dni, "cuentas": cuentas}


@router.post("/enviar-codigo")
def enviar_codigo(datos: CuentaElegida, request: Request, db: Session = Depends(get_db)):
    """Paso 2: manda el código al correo de la cuenta elegida."""
    ip = _preparar(db, request)
    try:
        usuario = _cuenta_o_404(db, datos.dni, datos.rol, ip)
        estado, correo = service.estado_de(db, usuario, datos.dni)
        if estado == service.DESACTIVADA:
            raise HTTPException(status_code=403,
                                detail="Esta cuenta está desactivada. Comunícate con el colegio.")
        if not correo:
            raise HTTPException(
                status_code=409,
                detail="Esta cuenta no tiene un correo registrado, así que no podemos "
                       "enviarte un código. Usa «No puedo entrar».")
        try:
            service.frenar_envio(db, usuario, datos.dni, ip)
        except service.Freno as e:
            raise _frenado(e)

        ua = (request.headers.get("user-agent") or "")[:255] or None
        fila, codigo = service.crear_codigo(db, usuario, datos.dni, ip, ua)
    except SQLAlchemyError as e:
        db.rollback()
        raise _fallo_de_base(e, "crear código")

    # El correo va dentro de la petición, no en segundo plano: si no sale, la
    # persona tiene que saberlo ahora y no quedarse esperando uno que no llega.
    enviado = service.enviar_codigo(db, usuario, correo, codigo)
    try:
        fila.enviado = enviado
        fila.anulado = not enviado
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        raise _fallo_de_base(e, "marcar código enviado")

    if not enviado:
        raise HTTPException(
            status_code=503,
            detail="No pudimos enviar el correo ahora mismo. Inténtalo en unos minutos; "
                   "si sigue fallando, usa «No puedo entrar».")
    return {
        "correo_oculto": service.ocultar_correo(correo),
        "vence_en": service.CODIGO_MINUTOS * 60,
        "reenviar_en": service.ESPERA_REENVIO_SEG,
        "intentos": service.MAX_INTENTOS,
    }


@router.post("/verificar-codigo")
def verificar_codigo(datos: VerificarCodigo, request: Request, db: Session = Depends(get_db)):
    """Paso 3: comprueba el código y entrega el permiso para cambiar la contraseña."""
    ip = _preparar(db, request)
    try:
        usuario = _cuenta_o_404(db, datos.dni, datos.rol, ip)
        fila = service.codigo_vigente(db, usuario.id_usuario)
        ahora = datetime.now()
        # 410: no hay nada que reintentar con este código, hace falta otro.
        if fila is None or fila.expira <= ahora:
            db.rollback()
            raise HTTPException(status_code=410,
                                detail="Tu código venció o ya no es válido. Pide uno nuevo.")

        if not secrets.compare_digest(fila.codigo_hash,
                                      service.huella_codigo(usuario.id_usuario, datos.codigo)):
            fila.intentos = (fila.intentos or 0) + 1
            quedan = service.MAX_INTENTOS - fila.intentos
            if quedan <= 0:
                fila.anulado = True
            db.commit()
            if quedan <= 0:
                raise HTTPException(status_code=410,
                                    detail="Código incorrecto. Ya no te quedan intentos: pide un código nuevo.")
            raise HTTPException(
                status_code=400,
                detail=f"Código incorrecto. Te queda{'' if quedan == 1 else 'n'} "
                       f"{quedan} intento{'' if quedan == 1 else 's'}.")

        permiso = secrets.token_urlsafe(32)
        fila.verificado_en = ahora
        fila.token_hash = service.huella_permiso(permiso)
        fila.token_expira = ahora + timedelta(minutes=service.PERMISO_MINUTOS)
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        raise _fallo_de_base(e, "verificar código")
    return {"token": permiso, "vence_en": service.PERMISO_MINUTOS * 60}


@router.post("/cambiar")
def cambiar(datos: CambiarPassword, request: Request, tareas: BackgroundTasks,
            db: Session = Depends(get_db)):
    """Paso 4: guarda la contraseña nueva. Solo con un permiso vigente."""
    ip = _preparar(db, request)
    try:
        usuario = _cuenta_o_404(db, datos.dni, datos.rol, ip)
        fila = service.permiso_vigente(db, usuario.id_usuario, datos.token)
        if fila is None:
            db.rollback()
            raise HTTPException(status_code=410, detail=_VUELVE_A_EMPEZAR)
        if not usuario.activo:
            db.rollback()
            raise HTTPException(status_code=403,
                                detail="Esta cuenta está desactivada. Comunícate con el colegio.")

        usuario.password_hash = get_password_hash(datos.nueva)
        usuario.debe_cambiar_password = False
        service.cerrar_recuperacion(db, fila)
        # El correo y el texto del aviso se sacan ahora: la tarea en segundo
        # plano corre cuando esta sesión ya está cerrada.
        correo = service._correo_valido(db, usuario)
        cuenta_en_texto = service._cuenta_en_texto(db, usuario)
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        raise _fallo_de_base(e, "cambiar contraseña")

    # Queda en Panel -> Seguridad -> Registro de accesos. Cuenta como acierto
    # a propósito: demostró ser el dueño, y así los fallos anteriores de esa
    # cuenta dejan de contar para el bloqueo del login.
    seguridad.anotar(db, request, usuario.username, True, "PASSWORD_RECUPERADA",
                     usuario.id_usuario, str(getattr(usuario.rol, "value", usuario.rol)))
    if correo:
        tareas.add_task(service.avisar_cambio, correo, cuenta_en_texto, datetime.now())
    return {
        "mensaje": "Cambiaste tu contraseña exitosamente. Inicia sesión con tu nueva contraseña.",
        "username": usuario.username,
    }
