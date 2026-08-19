# -*- coding: utf-8 -*-
"""
Consulta del registro de accesos. Solo ADMIN.

Responde a las tres preguntas que uno se hace cuando sospecha que le han
entrado a la cuenta: quién ha entrado, desde dónde, y si alguien estuvo
probando contraseñas antes.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.core.util.security import require_roles

from .models import IntentoAcceso

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
