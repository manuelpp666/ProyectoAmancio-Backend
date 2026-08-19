# -*- coding: utf-8 -*-
"""
Registro de intentos de acceso.

Nació de un incidente real: alguien entró a una cuenta de administrador y
mandó un mensaje desde ella. No hubo forma de saber cuándo, desde dónde, ni
si había habido tanteos previos, porque el sistema no guardaba nada. Un login
que no deja rastro es un login que no se puede investigar.

Se anotan los aciertos y los fallos. Los aciertos responden a "¿quién entró a
mi cuenta?"; los fallos, a "¿alguien estuvo probando contraseñas?".
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Index
from sqlalchemy.sql import func

from app.db.database import Base


class IntentoAcceso(Base):
    __tablename__ = "intento_acceso"

    id_intento = Column(Integer, primary_key=True, autoincrement=True)

    # Lo que se escribió en el formulario, exista o no esa cuenta: si alguien
    # prueba usuarios al azar, interesa ver qué nombres tanteó.
    username = Column(String(50), nullable=False, index=True)

    # Se rellena solo cuando la cuenta existe.
    id_usuario = Column(Integer, nullable=True, index=True)
    rol = Column(String(20), nullable=True)

    exito = Column(Boolean, nullable=False, default=False)

    # Por qué falló: 'USUARIO_NO_EXISTE', 'PASSWORD_INCORRECTA',
    # 'CUENTA_DESACTIVADA', 'BLOQUEADO'. Vacío si entró.
    motivo = Column(String(30), nullable=True)

    # IPv6 cabe en 45 caracteres.
    ip = Column(String(45), nullable=True, index=True)
    user_agent = Column(String(255), nullable=True)

    fecha = Column(DateTime, nullable=False, server_default=func.now(), index=True)

    # La consulta que más se repite es "fallos de este usuario en los últimos
    # minutos", que es justo lo que decide si hay que bloquear.
    __table_args__ = (
        Index("ix_intento_usuario_fecha", "username", "fecha"),
        Index("ix_intento_ip_fecha", "ip", "fecha"),
    )
