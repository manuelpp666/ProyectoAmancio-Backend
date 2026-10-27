# -*- coding: utf-8 -*-
"""
Recuperación de contraseña con un código al correo de la cuenta.

Dos tablas, las dos pequeñas y de vida corta (se limpian solas a los 30 días):

  recuperacion_consulta  cada DNI que se escribió en el formulario. Es el freno
                         a quien quiera usarlo para averiguar, DNI a DNI, quién
                         estudia o trabaja en el colegio.

  recuperacion_codigo    cada código enviado. El código NO se guarda: se guarda
                         su huella (HMAC con la SECRET_KEY), así que ni quien
                         vea la base puede usarlo. Lo mismo con el permiso de
                         un solo uso que se entrega al acertar el código y que
                         es lo único que autoriza a cambiar la contraseña.

Las fechas las pone siempre Python y no la base: el resto de comparaciones
usan `datetime.now()` del backend, y si el MySQL del hosting estuviera en otra
zona horaria un código caducaría horas antes o después de lo debido.
"""

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String

from app.db.database import Base


class RecuperacionConsulta(Base):
    __tablename__ = "recuperacion_consulta"

    id_consulta = Column(Integer, primary_key=True, autoincrement=True)
    dni = Column(String(8), nullable=False)
    encontrado = Column(Boolean, nullable=False, default=False)
    ip = Column(String(45), nullable=True)
    fecha = Column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_rec_consulta_ip_fecha", "ip", "fecha"),
        Index("ix_rec_consulta_fecha", "fecha"),
    )


class RecuperacionCodigo(Base):
    __tablename__ = "recuperacion_codigo"

    id_codigo = Column(Integer, primary_key=True, autoincrement=True)
    id_usuario = Column(Integer, nullable=False)
    dni = Column(String(8), nullable=False)
    codigo_hash = Column(String(64), nullable=False)
    intentos = Column(Integer, nullable=False, default=0)
    expira = Column(DateTime, nullable=False)
    # Si el correo no llegó a salir, el código no cuenta para el límite del
    # DNI: con el correo caído, la persona no debe quedarse sin intentos.
    enviado = Column(Boolean, nullable=False, default=False)
    # Pedir otro código, agotar los intentos o cambiar la contraseña lo anula.
    anulado = Column(Boolean, nullable=False, default=False)
    verificado_en = Column(DateTime, nullable=True)
    token_hash = Column(String(64), nullable=True)
    token_expira = Column(DateTime, nullable=True)
    usado_en = Column(DateTime, nullable=True)
    ip = Column(String(45), nullable=True)
    user_agent = Column(String(255), nullable=True)
    fecha = Column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_rec_codigo_usuario_fecha", "id_usuario", "fecha"),
        Index("ix_rec_codigo_dni_fecha", "dni", "fecha"),
        Index("ix_rec_codigo_ip_fecha", "ip", "fecha"),
        Index("ix_rec_codigo_token", "token_hash"),
        Index("ix_rec_codigo_fecha", "fecha"),
    )
