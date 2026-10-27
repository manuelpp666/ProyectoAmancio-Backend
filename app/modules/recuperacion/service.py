# -*- coding: utf-8 -*-
"""
La lógica de la recuperación de contraseña. Los endpoints están en router.py.

EN QUÉ SE APOYA LA SEGURIDAD
  El DNI no prueba nada: lo sabe mucha gente. Lo que demuestra que eres el
  dueño de la cuenta es recibir el código en el correo registrado. Por eso:

  * El código son 6 cifras al azar (`secrets`), vale 10 minutos, admite 5
    intentos y se guarda como huella, nunca tal cual.
  * Acertarlo no cambia nada todavía: entrega un permiso de un solo uso, de
    10 minutos, que es lo único que acepta el paso de la contraseña nueva.
    Saltarse el código llamando directamente a ese paso no sirve.
  * Los límites por DNI y por conexión impiden revisar DNIs en masa o llenar
    de códigos el correo de otra persona.

LO QUE SE DICE ANTES DEL CÓDIGO
  Que el DNI existe, el rol de cada cuenta, el correo a medias y si la cuenta
  sigue con la contraseña inicial. Se aceptó así a sabiendas: el login ya deja
  comprobar si una cuenta abre con su contraseña inicial, así que el
  formulario no revela nada nuevo, y los límites frenan los barridos. Lo que
  NO se dice nunca es cuál es esa contraseña inicial ni el nombre de nadie.
"""

from __future__ import annotations

import hashlib
import hmac
import html
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core.util import email as correo_util
from app.core.util.correo_usuario import PERFIL_POR_ROL, obtener_correo
from app.core.util.password import verify_password
from app.core.util.usuarios import generar_username
from app.modules.users.alumno.models import Alumno
from app.modules.users.models import Usuario

from .models import RecuperacionCodigo, RecuperacionConsulta
from .schemas import ROLES

# --- Límites -----------------------------------------------------------------
CONSULTAS_POR_IP_HORA = 10    # DNIs distintos que se pueden mirar desde un sitio
CODIGOS_POR_DNI_HORA = 3      # correos con código a un mismo DNI
CODIGOS_POR_IP_HORA = 10      # correos con código desde un mismo sitio
ESPERA_REENVIO_SEG = 60       # entre un código y el siguiente de la misma cuenta
CODIGO_MINUTOS = 10
MAX_INTENTOS = 5
PERMISO_MINUTOS = 10
RETENCION_DIAS = 30

# --- Lo que puede pasarle a una cuenta ----------------------------------------
CON_CORREO = "CON_CORREO"                    # caso normal: se le manda el código
SIN_CORREO = "SIN_CORREO"                    # cambió su contraseña pero no dejó correo
INICIAL_SIN_CORREO = "INICIAL_SIN_CORREO"    # nunca entró: ni contraseña propia ni correo
INICIAL_CON_CORREO = "INICIAL_CON_CORREO"    # nunca entró, pero hay correo (admisión web)
DESACTIVADA = "DESACTIVADA"

ESTADOS_CON_CODIGO = (CON_CORREO, INICIAL_CON_CORREO)

NOMBRE_ROL = {
    "ADMIN": "Administrador",
    "DOCENTE": "Docente",
    "ALUMNO": "Alumno",
    "AUXILIAR": "Auxiliar",
    "PSICOLOGO": "Psicólogo",
}


class Freno(Exception):
    """Se superó un límite. `segundos` es lo que falta para poder seguir."""

    def __init__(self, mensaje: str, segundos: int):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.segundos = segundos


# --- Tablas --------------------------------------------------------------------
_tablas_listas = False


def asegurar_tablas(db: Session) -> None:
    """Crea las dos tablas si el script 31 todavía no se ejecutó.

    Es una red, no la forma prevista: lo que hay que correr es el SQL. Se
    comprueba una vez por proceso, así que no cuesta nada en cada petición.
    """
    global _tablas_listas
    if _tablas_listas:
        return
    for modelo in (RecuperacionConsulta, RecuperacionCodigo):
        modelo.__table__.create(bind=db.get_bind(), checkfirst=True)
    _tablas_listas = True


# --- Cuentas ---------------------------------------------------------------------
def _usuarios_del_dni(db: Session, dni: str) -> dict:
    """rol -> Usuario de cada cuenta con ese DNI.

    El username lleva el prefijo del rol (ALU-, DOC-…). Se acepta también el
    username antiguo sin prefijo, por si queda alguno; si conviven, manda el
    que lleva prefijo.
    """
    nombres = [generar_username(dni, rol) for rol in ROLES] + [dni]
    cuentas: dict = {}
    for u in db.query(Usuario).filter(Usuario.username.in_(nombres)).all():
        rol = str(getattr(u.rol, "value", u.rol))
        if rol not in cuentas or u.username != dni:
            cuentas[rol] = u
    return cuentas


def _correo_valido(db: Session, usuario: Usuario) -> Optional[str]:
    c = (obtener_correo(db, usuario) or "").strip()
    return c if "@" in c and "." in c.split("@")[-1] else None


def estado_de(db: Session, usuario: Usuario, dni: str) -> tuple:
    """(estado, correo) de una cuenta. El correo solo si se le puede escribir.

    "Contraseña inicial" se comprueba de verdad (¿abre con su DNI?) y no con la
    marca `debe_cambiar_password`: esa marca también la enciende el
    administrador para obligar a cambiar una contraseña que ya no es el DNI, y
    entonces el aviso de "entra con tu contraseña inicial" sería falso.
    """
    if not usuario.activo:
        return DESACTIVADA, None
    correo = _correo_valido(db, usuario)
    inicial = verify_password(dni, usuario.password_hash or "")
    if inicial:
        return (INICIAL_CON_CORREO, correo) if correo else (INICIAL_SIN_CORREO, None)
    return (CON_CORREO, correo) if correo else (SIN_CORREO, None)


def cuentas_del_dni(db: Session, dni: str) -> list:
    """Lo que el formulario enseña de cada cuenta, en el orden de ROLES."""
    usuarios = _usuarios_del_dni(db, dni)
    resultado = []
    for rol in ROLES:
        u = usuarios.get(rol)
        if not u:
            continue
        estado, correo = estado_de(db, u, dni)
        resultado.append({
            "rol": rol,
            "rol_nombre": NOMBRE_ROL[rol],
            # Para dejarlo escrito en el login. No revela nada: es el prefijo
            # del rol más el DNI que la persona acaba de teclear.
            "usuario": u.username,
            "estado": estado,
            "correo_oculto": ocultar_correo(correo) if correo else None,
        })
    return resultado


def cuenta(db: Session, dni: str, rol: str) -> Optional[Usuario]:
    return _usuarios_del_dni(db, dni).get(rol)


def nombre_de(db: Session, usuario: Usuario) -> str:
    """Nombre de la persona, solo para el correo (nunca para la pantalla)."""
    try:
        rol = str(getattr(usuario.rol, "value", usuario.rol))
        modelo = Alumno if rol == "ALUMNO" else PERFIL_POR_ROL.get(rol)
        perfil = (db.query(modelo).filter(modelo.id_usuario == usuario.id_usuario).first()
                  if modelo else None)
        if perfil:
            return f"{perfil.nombres or ''} {perfil.apellidos or ''}".strip()
    except Exception:
        db.rollback()
    return ""


def ocultar_correo(correo: str) -> str:
    """jesusleonardoh1@gmail.com -> je************1@gmail.com

    Lo justo para que la persona reconozca su correo y nadie más pueda
    copiarlo. El dominio se deja entero: sin él no sabría si mirar el Gmail o
    el Hotmail.
    """
    local, _, dominio = (correo or "").partition("@")
    if not local or not dominio:
        return "***"
    if len(local) <= 2:
        visible = local[0] + "*" * 3
    else:
        visible = local[:2] + "*" * max(3, len(local) - 3) + local[-1]
    return f"{visible}@{dominio}"


# --- Límites -----------------------------------------------------------------------
def _hace(minutos: int = 60) -> datetime:
    return datetime.now() - timedelta(minutes=minutos)


def _restante(mas_antigua: datetime, minutos: int = 60) -> int:
    fin = mas_antigua + timedelta(minutes=minutos)
    return max(1, int((fin - datetime.now()).total_seconds()))


def _en_minutos(segundos: int) -> str:
    m = max(1, round(segundos / 60))
    return f"{m} minuto" + ("" if m == 1 else "s")


def frenar_consultas(db: Session, ip: Optional[str]) -> None:
    """Freno a revisar DNIs en masa desde un mismo sitio."""
    if not ip:
        return
    q = (db.query(RecuperacionConsulta.fecha)
         .filter(RecuperacionConsulta.ip == ip, RecuperacionConsulta.fecha >= _hace()))
    if q.count() >= CONSULTAS_POR_IP_HORA:
        espera = _restante(q.order_by(RecuperacionConsulta.fecha).first()[0])
        raise Freno("Se han hecho demasiadas consultas desde este equipo. "
                    f"Vuelve a intentarlo en {_en_minutos(espera)}.", espera)


def anotar_consulta(db: Session, dni: str, encontrado: bool, ip: Optional[str]) -> None:
    db.add(RecuperacionConsulta(dni=dni, encontrado=encontrado, ip=ip, fecha=datetime.now()))
    db.commit()


def frenar_envio(db: Session, usuario: Usuario, dni: str, ip: Optional[str]) -> None:
    """Los tres frenos de mandar un código: reenvío, DNI y conexión."""
    ultimo = (db.query(RecuperacionCodigo.fecha)
              .filter(RecuperacionCodigo.id_usuario == usuario.id_usuario,
                      RecuperacionCodigo.enviado.is_(True))
              .order_by(RecuperacionCodigo.fecha.desc()).first())
    if ultimo:
        pasado = (datetime.now() - ultimo[0]).total_seconds()
        if pasado < ESPERA_REENVIO_SEG:
            espera = max(1, int(ESPERA_REENVIO_SEG - pasado))
            raise Freno(f"Acabamos de enviarte un código. Espera {espera} segundos "
                        "para pedir otro.", espera)

    del_dni = (db.query(RecuperacionCodigo.fecha)
               .filter(RecuperacionCodigo.dni == dni,
                       RecuperacionCodigo.enviado.is_(True),
                       RecuperacionCodigo.fecha >= _hace()))
    if del_dni.count() >= CODIGOS_POR_DNI_HORA:
        espera = _restante(del_dni.order_by(RecuperacionCodigo.fecha).first()[0])
        raise Freno(f"Ya te enviamos {CODIGOS_POR_DNI_HORA} códigos en la última hora. "
                    f"Revisa tu correo (también la carpeta de no deseados) o vuelve a "
                    f"intentarlo en {_en_minutos(espera)}.", espera)

    if ip:
        de_la_ip = (db.query(RecuperacionCodigo.fecha)
                    .filter(RecuperacionCodigo.ip == ip,
                            RecuperacionCodigo.fecha >= _hace()))
        if de_la_ip.count() >= CODIGOS_POR_IP_HORA:
            espera = _restante(de_la_ip.order_by(RecuperacionCodigo.fecha).first()[0])
            raise Freno("Se han pedido demasiados códigos desde este equipo. "
                        f"Vuelve a intentarlo en {_en_minutos(espera)}.", espera)


# --- Códigos y permisos ----------------------------------------------------------------
def _huella(texto: str) -> str:
    clave = (os.getenv("SECRET_KEY") or "").encode("utf-8")
    return hmac.new(clave, texto.encode("utf-8"), hashlib.sha256).hexdigest()


def huella_codigo(id_usuario: int, codigo: str) -> str:
    return _huella(f"codigo:{id_usuario}:{codigo}")


def huella_permiso(permiso: str) -> str:
    return _huella(f"permiso:{permiso}")


def _anular_pendientes(db: Session, id_usuario: int) -> None:
    (db.query(RecuperacionCodigo)
     .filter(RecuperacionCodigo.id_usuario == id_usuario,
             RecuperacionCodigo.anulado.is_(False),
             RecuperacionCodigo.usado_en.is_(None))
     .update({RecuperacionCodigo.anulado: True}, synchronize_session=False))


def crear_codigo(db: Session, usuario: Usuario, dni: str, ip: Optional[str],
                 user_agent: Optional[str]) -> tuple:
    """(fila, código). Anula los anteriores: solo vale el último que llegó."""
    ahora = datetime.now()
    # Limpieza de paso: lo de hace más de un mes ya no sirve ni para revisar.
    limite = ahora - timedelta(days=RETENCION_DIAS)
    db.query(RecuperacionCodigo).filter(RecuperacionCodigo.fecha < limite).delete(synchronize_session=False)
    db.query(RecuperacionConsulta).filter(RecuperacionConsulta.fecha < limite).delete(synchronize_session=False)

    _anular_pendientes(db, usuario.id_usuario)
    codigo = f"{secrets.randbelow(10 ** 6):06d}"
    fila = RecuperacionCodigo(
        id_usuario=usuario.id_usuario, dni=dni,
        codigo_hash=huella_codigo(usuario.id_usuario, codigo),
        intentos=0, expira=ahora + timedelta(minutes=CODIGO_MINUTOS),
        enviado=False, anulado=False, ip=ip, user_agent=user_agent, fecha=ahora,
    )
    db.add(fila)
    db.commit()
    return fila, codigo


def codigo_vigente(db: Session, id_usuario: int) -> Optional[RecuperacionCodigo]:
    """El último código enviado y sin usar, bloqueado para esta petición.

    El bloqueo (FOR UPDATE) evita que dos peticiones a la vez cuenten el mismo
    intento o canjeen dos veces el mismo código.
    """
    return (db.query(RecuperacionCodigo)
            .filter(RecuperacionCodigo.id_usuario == id_usuario,
                    RecuperacionCodigo.enviado.is_(True),
                    RecuperacionCodigo.anulado.is_(False),
                    RecuperacionCodigo.verificado_en.is_(None),
                    RecuperacionCodigo.usado_en.is_(None))
            .order_by(RecuperacionCodigo.fecha.desc())
            .with_for_update().first())


def permiso_vigente(db: Session, id_usuario: int, permiso: str) -> Optional[RecuperacionCodigo]:
    fila = (db.query(RecuperacionCodigo)
            .filter(RecuperacionCodigo.token_hash == huella_permiso(permiso),
                    RecuperacionCodigo.id_usuario == id_usuario,
                    RecuperacionCodigo.anulado.is_(False),
                    RecuperacionCodigo.usado_en.is_(None))
            .with_for_update().first())
    if fila is None or not fila.token_expira or fila.token_expira <= datetime.now():
        return None
    return fila


def cerrar_recuperacion(db: Session, fila: RecuperacionCodigo) -> None:
    """Marca el permiso como usado y anula cualquier otro código de la cuenta."""
    fila.usado_en = datetime.now()
    _anular_pendientes(db, fila.id_usuario)


# --- Correos -----------------------------------------------------------------------------
def _cuenta_en_texto(db: Session, usuario: Usuario) -> str:
    rol = NOMBRE_ROL.get(str(getattr(usuario.rol, "value", usuario.rol)), "")
    nombre = nombre_de(db, usuario)
    return f"de {rol.lower()} de <b>{html.escape(nombre)}</b>" if nombre else f"de {rol.lower()}"


def enviar_codigo(db: Session, usuario: Usuario, correo: str, codigo: str) -> bool:
    cuerpo = f"""
      <p>Recibimos un pedido para restablecer la contraseña de la cuenta
         {_cuenta_en_texto(db, usuario)} en el Campus Virtual.</p>
      <p>Tu código de verificación es:</p>
      <div style="font-size:32px;letter-spacing:10px;font-weight:bold;color:#093E7A;
                  background:#f3f6fb;border:1px solid #dbe3f0;border-radius:10px;
                  padding:16px;text-align:center;margin:8px 0 16px">{codigo}</div>
      <p>Vence en <b>{CODIGO_MINUTOS} minutos</b> y solo sirve una vez. No se lo
         compartas a nadie: el colegio nunca te lo va a pedir.</p>
      <p style="color:#777">Si no pediste este código, no hagas nada: tu
         contraseña sigue siendo la misma.</p>
    """
    texto = (f"Tu código para restablecer la contraseña del Campus Virtual es {codigo}. "
             f"Vence en {CODIGO_MINUTOS} minutos. Si no lo pediste, ignora este correo.")
    return correo_util.enviar_correo(
        correo, "Código para restablecer tu contraseña",
        correo_util.plantilla_institucional("Restablecer tu contraseña", cuerpo), texto)


def avisar_cambio(correo: str, cuenta_en_texto: str, cuando: datetime) -> None:
    """El aviso de que la contraseña cambió. Va después de responder: si no
    sale, la contraseña ya está cambiada igual y no hay nada que deshacer."""
    try:
        cuerpo = f"""
          <p>La contraseña de la cuenta {cuenta_en_texto} en el Campus Virtual se
             cambió el <b>{cuando.strftime('%d/%m/%Y')}</b> a las
             <b>{cuando.strftime('%H:%M')}</b>, con un código enviado a este correo.</p>
          <p>Si fuiste tú, no tienes que hacer nada más.</p>
          <p style="color:#701C32"><b>Si no fuiste tú</b>, comunícate con el colegio
             de inmediato para proteger la cuenta.</p>
        """
        correo_util.enviar_correo(
            correo, "Tu contraseña se cambió",
            correo_util.plantilla_institucional("Tu contraseña se cambió", cuerpo),
            "La contraseña de tu cuenta del Campus Virtual se acaba de cambiar. "
            "Si no fuiste tú, comunícate con el colegio de inmediato.")
    except Exception as e:  # noqa: BLE001
        print(f"[RECUPERACION][WARN] No se pudo enviar el aviso de cambio: {e}")
