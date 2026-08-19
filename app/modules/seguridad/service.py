# -*- coding: utf-8 -*-
"""
Freno a la prueba de contraseñas y anotación de cada intento.

Sin esto, un atacante puede lanzar miles de combinaciones por minuto contra el
login. Con el colegio usando el DNI como contraseña inicial, eso no es teoría:
el espacio de DNIs que merece la pena probar es pequeño.

La cuenta de fallos vive en la base y no en memoria a propósito. En el
servidor la aplicación corre bajo Passenger, que arranca y reinicia procesos
por su cuenta; un contador en memoria se borraría solo y el bloqueo sería un
adorno.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import Request
from sqlalchemy import desc
from sqlalchemy.orm import Session

from .models import IntentoAcceso

# Cuánto se mira hacia atrás.
VENTANA_MINUTOS = 15

# Fallos permitidos antes de cerrar la puerta.
MAX_FALLOS_USUARIO = 5     # tanteo contra una cuenta concreta
MAX_FALLOS_IP = 20         # barrido desde un mismo sitio contra muchas cuentas


def ip_de(request: Request) -> Optional[str]:
    """La IP real del visitante.

    En producción la aplicación está detrás de Apache, así que `request.client`
    es siempre 127.0.0.1: la IP verdadera viaja en X-Forwarded-For, y el primer
    valor de la lista es el cliente original.
    """
    reenviada = request.headers.get("x-forwarded-for")
    if reenviada:
        primera = reenviada.split(",")[0].strip()
        if primera:
            return primera[:45]
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()[:45]
    return getattr(getattr(request, "client", None), "host", None)


def _desde(minutos: int = VENTANA_MINUTOS) -> datetime:
    return datetime.now() - timedelta(minutes=minutos)


def segundos_de_bloqueo(db: Session, username: str, ip: Optional[str]) -> int:
    """Segundos que faltan para poder volver a intentar. 0 = puede pasar.

    Los fallos se cuentan desde el último acierto: quien entra bien deja el
    contador a cero y no arrastra tanteos viejos.

    Si algo falla aquí (la tabla todavía no creada tras una subida a medias, la
    base saturada), se deja pasar. Un colegio entero sin poder entrar es mucho
    peor que quedarse un rato sin freno a la fuerza bruta, y el fallo sería
    invisible: el login devolvería un error 500 y la pantalla no diría nada.
    """
    try:
        return _calcular_bloqueo(db, username, ip)
    except Exception as e:
        print(f"[SEGURIDAD][WARN] No se pudo comprobar el bloqueo, se deja pasar: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return 0


def _calcular_bloqueo(db: Session, username: str, ip: Optional[str]) -> int:
    desde = _desde()

    ultimo_ok = (db.query(IntentoAcceso.fecha)
                 .filter(IntentoAcceso.username == username,
                         IntentoAcceso.exito.is_(True),
                         IntentoAcceso.fecha >= desde)
                 .order_by(desc(IntentoAcceso.fecha)).first())
    corte = max(desde, ultimo_ok[0]) if ultimo_ok else desde

    def _mas_antiguo_de(consulta):
        fila = consulta.order_by(IntentoAcceso.fecha).first()
        return fila[0] if fila else None

    # Se excluyen los rechazos del propio bloqueo: si contaran, cada reintento
    # de alguien ya bloqueado renovaría su castigo y el dueño legítimo de la
    # cuenta podría quedarse fuera mucho más de los 15 minutos previstos.
    fallos_usuario = (db.query(IntentoAcceso.fecha)
                      .filter(IntentoAcceso.username == username,
                              IntentoAcceso.exito.is_(False),
                              IntentoAcceso.motivo != "BLOQUEADO",
                              IntentoAcceso.fecha >= corte))
    n_usuario = fallos_usuario.count()

    if n_usuario >= MAX_FALLOS_USUARIO:
        primero = _mas_antiguo_de(fallos_usuario)
        return _restante(primero)

    if ip:
        fallos_ip = (db.query(IntentoAcceso.fecha)
                     .filter(IntentoAcceso.ip == ip,
                             IntentoAcceso.exito.is_(False),
                             IntentoAcceso.motivo != "BLOQUEADO",
                             IntentoAcceso.fecha >= desde))
        if fallos_ip.count() >= MAX_FALLOS_IP:
            return _restante(_mas_antiguo_de(fallos_ip))

    return 0


def _restante(primer_fallo: Optional[datetime]) -> int:
    """Cuánto queda para que el fallo más viejo salga de la ventana."""
    if not primer_fallo:
        return VENTANA_MINUTOS * 60
    fin = primer_fallo + timedelta(minutes=VENTANA_MINUTOS)
    return max(1, int((fin - datetime.now()).total_seconds()))


def anotar(db: Session, request: Request, username: str, exito: bool,
           motivo: Optional[str] = None, id_usuario: Optional[int] = None,
           rol: Optional[str] = None) -> None:
    """Deja constancia del intento.

    Nunca interrumpe el login: si esto fallara (tabla ausente tras una subida a
    medias, por ejemplo), el colegio se quedaría sin poder entrar, y eso sería
    peor que quedarse sin registro.
    """
    try:
        ua = (request.headers.get("user-agent") or "")[:255]
        db.add(IntentoAcceso(
            username=(username or "")[:50],
            id_usuario=id_usuario,
            rol=rol,
            exito=exito,
            motivo=motivo,
            ip=ip_de(request),
            user_agent=ua or None,
        ))
        db.commit()
    except Exception:
        db.rollback()
