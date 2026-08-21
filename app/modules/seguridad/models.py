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

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Index
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


class SolicitudAcceso(Base):
    """Un aviso de "no puedo entrar" mandado desde la pantalla de login.

    POR QUÉ EXISTE
      Quien no consigue entrar no tiene forma de avisar: no puede escribir un
      mensaje interno porque el mensaje interno está DETRÁS del login. Hasta
      ahora la pantalla se limitaba a decirle que fuera a hablar con la
      administración, y los avisos llegaban por WhatsApp al que le pillara.

    LO QUE NO HACE
      No abre ninguna puerta. No reinicia contraseñas, no desbloquea cuentas y
      no responde nada al que escribe. Es una nota que llega al panel para que
      un administrador la atienda a mano. Cualquier otra cosa sería un agujero:
      el que la manda no ha demostrado ser quien dice ser.
    """

    __tablename__ = "solicitud_acceso"

    id_solicitud = Column(Integer, primary_key=True, autoincrement=True)

    # Los tres datos que pide el formulario.
    dni = Column(String(8), nullable=False, index=True)
    telefono = Column(String(9), nullable=False)
    descripcion = Column(Text, nullable=False)

    # Quién resulta ser ese DNI, resuelto al recibir la solicitud. Se guarda
    # copiado y no por relación a propósito: la solicitud tiene que seguir
    # entendiéndose dentro de un año, aunque el alumno se haya retirado.
    #
    # Al que escribe NUNCA se le dice si el DNI existe o no —eso convertiría
    # el formulario en una forma de averiguar quién estudia aquí—, pero el
    # administrador sí necesita verlo: un DNI que no figura casi siempre es un
    # número mal escrito, y es lo primero que hay que descartar.
    nombre = Column(String(120), nullable=True)
    rol = Column(String(20), nullable=True)
    dni_encontrado = Column(Boolean, nullable=False, default=False)

    # PENDIENTE | ATENDIDA | DESCARTADA
    estado = Column(String(20), nullable=False, default="PENDIENTE", index=True)
    nota = Column(String(300), nullable=True)          # qué se hizo
    atendida_por = Column(String(50), nullable=True)
    fecha_atencion = Column(DateTime, nullable=True)

    ip = Column(String(45), nullable=True, index=True)
    user_agent = Column(String(255), nullable=True)

    fecha = Column(DateTime, nullable=False, server_default=func.now(), index=True)

    # Las dos consultas del freno: cuántas van hoy de este DNI y de esta IP.
    __table_args__ = (
        Index("ix_solicitud_dni_fecha", "dni", "fecha"),
        Index("ix_solicitud_ip_fecha", "ip", "fecha"),
    )
