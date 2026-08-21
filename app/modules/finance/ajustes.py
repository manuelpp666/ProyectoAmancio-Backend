# -*- coding: utf-8 -*-
"""
Rastro de los cambios que se hacen a mano sobre las cuotas.

POR QUÉ EXISTE
  El archivo CREP se arma leyendo `pago` en vivo, así que cualquier cambio
  hecho desde el panel ya viaja al banco en la siguiente descarga. Lo que no
  había forma de saber es CUÁLES fueron esos cambios: quién rebajó un importe,
  a quién se le cobró en caja o qué cuota se borró. Al comparar el archivo de
  un mes con el del anterior aparecían diferencias que nadie sabía justificar.

  Aquí se anota cada uno de esos cambios y si el banco ya lo tiene.

REGLA QUE NO SE PUEDE ROMPER
  Anotar no puede impedir cobrar. Si esto fallara —la tabla todavía sin crear
  tras una subida a medias, la base saturada—, la operación de pago tiene que
  salir adelante igual. Por eso todo lo que escribe usa su PROPIA sesión y se
  traga sus errores: un apunte perdido es un problema; una caja que no puede
  cobrar, uno mucho mayor.

CÓMO SE USA
  El que hace el cambio toma una `instantanea` de la cuota ANTES de tocarla,
  otra después, y cuando su commit ya salió bien llama a `anotar`. En ese
  orden: si el pago no llegó a guardarse, no debe quedar el apunte diciendo
  que sí.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.modules.finance import models as fin

# Estados de una cuota que SÍ viajan al archivo del banco. Es la misma lista
# que usa conciliacion.PENDIENTES; se repite aquí para no cruzar los dos
# módulos por una constante y arriesgar un import circular.
VIVOS = ("PENDIENTE", "VENCIDO")

# Qué hizo la persona.
TIPOS = {
    "ALTA": "Cuota creada a mano",
    "MONTO": "Importe modificado",
    "MORA": "Mora modificada",
    "VENCIMIENTO": "Vencimiento cambiado",
    "ESTADO": "Estado cambiado a mano",
    "PAGO_MANUAL": "Cobrado en caja",
    "ELIMINACION": "Cuota eliminada",
    "PRECIO_MASIVO": "Cambio masivo de precio",
}

# Qué le hace ese cambio al archivo del BCP.
EFECTOS = {
    "ALTA": "Entra al archivo del banco",
    "BAJA": "Deja de cobrarse por el banco",
    "IMPORTE": "Cambia la cuota que cobra el banco",
    "NINGUNO": "No altera el archivo del banco",
}

# Tope de apuntes que se devuelven a la pantalla. Un cambio masivo de precios
# puede dejar cientos de una sola vez y la respuesta se dispararía.
MAXIMO_DEVUELTOS = 500


# ---------------------------------------------------------------------------
# Utilidades de conversión
# ---------------------------------------------------------------------------

def _motivo(e: Exception) -> str:
    """El error en una línea.

    Un fallo de SQLAlchemy arrastra la sentencia entera y todos sus parámetros,
    con el nombre y el DNI del alumno dentro. Al log solo va la primera línea,
    que es la que dice qué pasó ("Table ... doesn't exist").
    """
    return f"{type(e).__name__}: {str(e).splitlines()[0][:160]}"


def _texto(valor: Any, ancho: int) -> Optional[str]:
    if valor is None:
        return None
    limpio = str(valor).strip()
    return limpio[:ancho] or None


def _numero(valor: Any) -> Optional[Decimal]:
    if valor is None:
        return None
    try:
        return Decimal(str(valor)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, ArithmeticError):
        return None


def _iguales(a: Optional[Decimal], b: Optional[Decimal]) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(a - b) < Decimal("0.005")


def _fecha(valor: Any) -> Optional[dt.date]:
    if isinstance(valor, dt.datetime):
        return valor.date()
    return valor if isinstance(valor, dt.date) else None


# ---------------------------------------------------------------------------
# Instantánea de una cuota
# ---------------------------------------------------------------------------

def instantanea(cuota) -> Dict[str, Any]:
    """Los datos de una cuota como valores sueltos, desligados de la sesión.

    Se toma ANTES de tocar la cuota y otra vez después. Tienen que ser valores
    planos y no el objeto: cuando la cuota se borra, el objeto ya no se puede
    leer, y después de un commit SQLAlchemy vuelve a consultar cada atributo.

    Si algo falla leyendo, devuelve un diccionario vacío en lugar de romper:
    el apunte saldrá incompleto, que es preferible a tumbar la operación.
    """
    if cuota is None:
        return {}
    try:
        if isinstance(cuota, fin.Pago):
            alumno = getattr(cuota, "alumno", None)
            documento = getattr(alumno, "dni", None)
            nombre = cuota.alumno_nombre
            claves = {"id_pago": cuota.id_pago, "id_cuota_externa": None}
        else:
            documento = getattr(cuota, "documento", None)
            nombre = getattr(cuota, "nombre", None)
            claves = {"id_pago": None,
                      "id_cuota_externa": getattr(cuota, "id_cuota_externa", None)}

        datos = {
            "documento": _texto(documento, 20),
            "nombre": _texto(nombre, 120),
            "concepto": _texto(getattr(cuota, "concepto", None), 150),
            "fecha_vencimiento": _fecha(getattr(cuota, "fecha_vencimiento", None)),
            "monto": _numero(getattr(cuota, "monto", None)),
            "mora": _numero(getattr(cuota, "mora", None)),
            "estado": _texto(getattr(cuota, "estado", None), 20),
        }
        datos.update(claves)
        return datos
    except Exception as e:
        print(f"[AJUSTES][WARN] No se pudo leer la cuota para anotarla: {_motivo(e)}")
        return {}


def _viaja_al_banco(datos: Dict[str, Any]) -> bool:
    """Si esta cuota puede salir en el CREP.

    Las mismas condiciones que aplica `conciliacion.cuotas_para_crep`: sin
    documento o sin vencimiento la cuota nunca llega al archivo, así que
    cambiarla no le hace nada al banco.
    """
    return bool(datos.get("documento")) and datos.get("fecha_vencimiento") is not None


def _efecto(tipo: str, antes: Dict[str, Any], despues: Dict[str, Any]) -> str:
    """Qué le hace este cambio al archivo del banco."""
    estaba = antes.get("estado") in VIVOS and _viaja_al_banco(antes)
    esta = despues.get("estado") in VIVOS and _viaja_al_banco(despues)

    if tipo == "ELIMINACION":
        return "BAJA" if estaba else "NINGUNO"
    if tipo == "ALTA":
        return "ALTA" if esta else "NINGUNO"
    if estaba and not esta:
        return "BAJA"
    if esta and not estaba:
        return "ALTA"
    if not esta:
        # Ni antes ni ahora está en el archivo: se tocó una cuota ya cobrada o
        # anulada y el banco no se entera de nada.
        return "NINGUNO"
    # Sigue en el archivo, pero con otra cara. El vencimiento cuenta tanto como
    # el importe: es parte de la clave con la que el BCP identifica la cuota,
    # así que cambiarlo da de baja una línea y da de alta otra.
    if (not _iguales(antes.get("monto"), despues.get("monto"))
            or not _iguales(antes.get("mora"), despues.get("mora"))
            or antes.get("fecha_vencimiento") != despues.get("fecha_vencimiento")):
        return "IMPORTE"
    return "NINGUNO"


def tipo_del_cambio(antes: Dict[str, Any],
                    despues: Dict[str, Any]) -> Optional[str]:
    """Cómo llamar a una edición a mano. None si no cambió nada que importe.

    Una edición puede tocar varias cosas a la vez; se queda con la más
    relevante para la cobranza, que es el orden en que se pregunta. Los
    cambios que no afectan al cobro —retocar el texto del concepto— no se
    anotan: llenarían la tabla de ruido y taparían lo que sí hay que revisar.
    """
    try:
        if not _iguales(antes.get("monto"), despues.get("monto")):
            return "MONTO"
        if not _iguales(antes.get("mora"), despues.get("mora")):
            return "MORA"
        if antes.get("fecha_vencimiento") != despues.get("fecha_vencimiento"):
            return "VENCIMIENTO"
        if antes.get("estado") != despues.get("estado"):
            return "ESTADO"
        return None
    except Exception as e:
        print(f"[AJUSTES][WARN] No se pudo clasificar el cambio: {_motivo(e)}")
        return None


def _quien(usuario: Optional[dict]) -> Dict[str, Any]:
    if not isinstance(usuario, dict):
        return {"id_usuario": None, "usuario": None}
    return {"id_usuario": usuario.get("id"),
            "usuario": _texto(usuario.get("sub"), 60)}


def apunte(tipo: str, antes: Dict[str, Any],
           despues: Optional[Dict[str, Any]] = None, *,
           usuario: Optional[dict] = None,
           detalle: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Arma el apunte de un cambio. Devuelve None si no hay nada que anotar."""
    try:
        antes = antes or {}
        # En un alta no hay estado previo; en una baja no hay estado posterior.
        despues = despues or {}
        if not antes and not despues:
            return None

        referencia = despues or antes
        return {
            "id_pago": referencia.get("id_pago") or antes.get("id_pago"),
            "id_cuota_externa": (referencia.get("id_cuota_externa")
                                 or antes.get("id_cuota_externa")),
            "tipo": _texto(tipo, 20) or "ESTADO",
            "efecto_crep": _efecto(tipo, antes, despues),
            "documento": referencia.get("documento") or antes.get("documento"),
            "nombre": referencia.get("nombre") or antes.get("nombre"),
            "concepto": referencia.get("concepto") or antes.get("concepto"),
            "fecha_vencimiento": (referencia.get("fecha_vencimiento")
                                  or antes.get("fecha_vencimiento")),
            "monto_anterior": antes.get("monto"),
            "monto_nuevo": despues.get("monto"),
            "mora_anterior": antes.get("mora"),
            "mora_nueva": despues.get("mora"),
            "estado_anterior": antes.get("estado"),
            "estado_nuevo": despues.get("estado"),
            "detalle": _texto(detalle, 255),
            **_quien(usuario),
        }
    except Exception as e:
        print(f"[AJUSTES][WARN] No se pudo preparar el apunte: {_motivo(e)}")
        return None


# ---------------------------------------------------------------------------
# Escritura
# ---------------------------------------------------------------------------

def anotar(*apuntes) -> int:
    """Guarda los apuntes. NUNCA lanza: devuelve cuántos pudo guardar.

    Usa su propia sesión a propósito. Si compartiera la del que hace el pago,
    un fallo aquí (la tabla sin crear, por ejemplo) dejaría esa transacción
    envenenada y el cobro se perdería por culpa del registro.

    Se llama SIEMPRE después de que el commit del cambio real haya salido
    bien; así no queda constancia de algo que no llegó a pasar.
    """
    filas = [a for a in apuntes if a]
    if not filas:
        return 0
    sesion = None
    try:
        sesion = SessionLocal()
        sesion.add_all([fin.AjusteManualPago(**f) for f in filas])
        sesion.commit()
        return len(filas)
    except Exception as e:
        print(f"[AJUSTES][WARN] No se pudieron anotar {len(filas)} cambio(s) "
              f"manual(es): {_motivo(e)}")
        if sesion is not None:
            try:
                sesion.rollback()
            except Exception:
                pass
        return 0
    finally:
        if sesion is not None:
            try:
                sesion.close()
            except Exception:
                pass


def marcar_incorporados(id_registro_crep: int) -> int:
    """Sella los apuntes pendientes: el banco ya los tiene.

    Se llama justo después de crear un CREP oficial. También en su propia
    sesión: que el sello falle no puede deshacer la incorporación, que es lo
    importante.
    """
    sesion = None
    try:
        sesion = SessionLocal()
        n = (sesion.query(fin.AjusteManualPago)
             .filter(fin.AjusteManualPago.id_registro_crep.is_(None))
             # La hora la pone la base, no Python: la columna `fecha` de la
             # misma tabla se rellena con el CURRENT_TIMESTAMP de MySQL, y si
             # esta se pusiera con el reloj del proceso las dos podrían
             # discrepar cuando el servidor y la base no comparten zona.
             .update({"id_registro_crep": id_registro_crep,
                      "fecha_incorporacion": func.now()},
                     synchronize_session=False))
        sesion.commit()
        return int(n or 0)
    except Exception as e:
        print(f"[AJUSTES][WARN] No se pudieron marcar los cambios manuales "
              f"como incorporados: {_motivo(e)}")
        if sesion is not None:
            try:
                sesion.rollback()
            except Exception:
                pass
        return 0
    finally:
        if sesion is not None:
            try:
                sesion.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------

def _fila(a: fin.AjusteManualPago) -> dict:
    monto_ant = float(a.monto_anterior) if a.monto_anterior is not None else None
    monto_new = float(a.monto_nuevo) if a.monto_nuevo is not None else None
    mora_ant = float(a.mora_anterior) if a.mora_anterior is not None else None
    mora_new = float(a.mora_nueva) if a.mora_nueva is not None else None
    return {
        "id_ajuste": a.id_ajuste,
        "id_pago": a.id_pago,
        "id_cuota_externa": a.id_cuota_externa,
        "tipo": a.tipo,
        "tipo_texto": TIPOS.get(a.tipo, a.tipo),
        "efecto_crep": a.efecto_crep,
        "efecto_texto": EFECTOS.get(a.efecto_crep, a.efecto_crep),
        "documento": a.documento,
        "nombre": a.nombre,
        "concepto": a.concepto,
        "fecha_vencimiento": (a.fecha_vencimiento.isoformat()
                              if a.fecha_vencimiento else None),
        "monto_anterior": monto_ant,
        "monto_nuevo": monto_new,
        "mora_anterior": mora_ant,
        "mora_nueva": mora_new,
        "total_anterior": (None if monto_ant is None and mora_ant is None
                           else (monto_ant or 0) + (mora_ant or 0)),
        "total_nuevo": (None if monto_new is None and mora_new is None
                        else (monto_new or 0) + (mora_new or 0)),
        "estado_anterior": a.estado_anterior,
        "estado_nuevo": a.estado_nuevo,
        "detalle": a.detalle,
        "usuario": a.usuario,
        "fecha": a.fecha.isoformat() if a.fecha else None,
        "incorporado": a.id_registro_crep is not None,
        "id_registro_crep": a.id_registro_crep,
        "fecha_incorporacion": (a.fecha_incorporacion.isoformat()
                                if a.fecha_incorporacion else None),
    }


def listar(db: Session, *, estado: str = "pendientes",
           desde: Optional[dt.date] = None, hasta: Optional[dt.date] = None,
           tipo: Optional[str] = None,
           limite: int = MAXIMO_DEVUELTOS) -> dict:
    """Los cambios manuales para la pantalla.

    `estado` filtra por si el banco ya los tiene:
      pendientes   — todavía no se han incorporado a ningún CREP oficial
      incorporados — ya viajaron en un CREP
      todos        — sin filtrar
    """
    consulta = db.query(fin.AjusteManualPago)

    estado = (estado or "pendientes").lower()
    if estado == "pendientes":
        consulta = consulta.filter(fin.AjusteManualPago.id_registro_crep.is_(None))
    elif estado == "incorporados":
        consulta = consulta.filter(fin.AjusteManualPago.id_registro_crep.isnot(None))

    if tipo:
        consulta = consulta.filter(fin.AjusteManualPago.tipo == tipo.upper())
    if desde:
        consulta = consulta.filter(
            fin.AjusteManualPago.fecha >= dt.datetime.combine(desde, dt.time.min))
    if hasta:
        consulta = consulta.filter(
            fin.AjusteManualPago.fecha <= dt.datetime.combine(hasta, dt.time.max))

    total = consulta.count()
    limite = max(1, min(int(limite or MAXIMO_DEVUELTOS), MAXIMO_DEVUELTOS))
    filas = (consulta.order_by(fin.AjusteManualPago.fecha.desc(),
                               fin.AjusteManualPago.id_ajuste.desc())
             .limit(limite).all())

    # El desglose se cuenta sobre TODOS los pendientes, no sobre las filas
    # devueltas: si no, un cambio masivo recortado por el límite daría un
    # recuento que no cuadra con lo que hay de verdad.
    por_efecto = dict(
        db.query(fin.AjusteManualPago.efecto_crep,
                 func.count(fin.AjusteManualPago.id_ajuste))
        .filter(fin.AjusteManualPago.id_registro_crep.is_(None))
        .group_by(fin.AjusteManualPago.efecto_crep).all()
    )

    ajustes = [_fila(a) for a in filas]
    return {
        "ajustes": ajustes,
        "total": total,
        "mostrados": len(ajustes),
        "recortado": total > len(ajustes),
        "pendientes": contar_pendientes(db),
        "pendientes_por_efecto": {k: int(v) for k, v in por_efecto.items()},
    }


def contar_pendientes(db: Session) -> int:
    """Cambios manuales que el banco todavía no tiene. 0 si algo falla.

    Lo llama el resumen de la pantalla de conciliación, que pinta media
    pantalla: si esta cuenta reventara, se quedaría sin resumen entero.
    """
    try:
        return int(db.query(func.count(fin.AjusteManualPago.id_ajuste))
                   .filter(fin.AjusteManualPago.id_registro_crep.is_(None))
                   .scalar() or 0)
    except Exception as e:
        print(f"[AJUSTES][WARN] No se pudieron contar los cambios manuales: {_motivo(e)}")
        try:
            db.rollback()
        except Exception:
            pass
        return 0
