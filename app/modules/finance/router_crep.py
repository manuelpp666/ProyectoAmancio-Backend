# -*- coding: utf-8 -*-
"""
Endpoints de la conciliación con el BCP.

Van aparte del router de finanzas porque son un circuito propio: subir los
reportes del banco, revisar qué se aplicó y descargar el archivo de cobranza.
Todo lo que escribe en la base tiene modo simulación, porque una conciliación
mal aplicada da por pagadas cuotas que nadie pagó.
"""

from __future__ import annotations

import datetime as dt
import io
from decimal import Decimal, InvalidOperation
from typing import List, Optional

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Query,
                     UploadFile, status)
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.exc import ProgrammingError, OperationalError
from sqlalchemy.orm import Session, joinedload

from app.core.util.security import get_current_user
from app.db.database import get_db
from app.modules.finance import conciliacion as con
from app.modules.finance import models as fin
from app.modules.finance.crep import ErrorFormatoBCP

router = APIRouter(prefix="/finance/crep", tags=["Finanzas - BCP"])

TAMANO_MAXIMO = 8 * 1024 * 1024      # 8 MB: el CREP real pesa 0.9 MB
MAXIMO_ARCHIVOS = 40


def _solo_admin(current_user: dict):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403,
                            detail="No puedes acceder a la conciliación de pagos")


def _sin_tablas(e: Exception) -> HTTPException:
    """Las tablas se crean con 12_conciliacion_bcp.sql."""
    return HTTPException(
        status_code=503,
        detail="Falta preparar la base de datos: ejecuta el script "
               "12_conciliacion_bcp.sql para crear las tablas de conciliación.")


async def _leer(archivos: List[UploadFile]) -> List[tuple]:
    if not archivos:
        raise HTTPException(400, "No se recibió ningún archivo")
    if len(archivos) > MAXIMO_ARCHIVOS:
        raise HTTPException(
            400, f"Demasiados archivos de una vez ({len(archivos)}). "
                 f"El máximo es {MAXIMO_ARCHIVOS}")
    salida = []
    for a in archivos:
        datos = await a.read()
        if not datos:
            raise HTTPException(400, f"«{a.filename}» llegó vacío")
        if len(datos) > TAMANO_MAXIMO:
            raise HTTPException(
                400, f"«{a.filename}» pesa {len(datos)/1024/1024:.1f} MB y el "
                     f"máximo es {TAMANO_MAXIMO//1024//1024} MB")
        salida.append((a.filename or "sin_nombre.txt", datos))
    return salida


# ---------------------------------------------------------------------------
# Estado general
# ---------------------------------------------------------------------------

@router.get("/resumen")
def resumen(db: Session = Depends(get_db),
            current_user: dict = Depends(get_current_user)):
    """Lo que hace falta para pintar la pantalla de un vistazo."""
    _solo_admin(current_user)
    try:
        pendientes = (db.query(func.count(fin.Pago.id_pago),
                               func.coalesce(func.sum(fin.Pago.monto), 0),
                               func.coalesce(func.sum(fin.Pago.mora), 0))
                      .filter(fin.Pago.estado.in_(con.PENDIENTES)).one())
        externas = (db.query(func.count(fin.CuotaExterna.id_cuota_externa),
                             func.coalesce(func.sum(fin.CuotaExterna.monto), 0),
                             func.coalesce(func.sum(fin.CuotaExterna.mora), 0))
                    .filter(fin.CuotaExterna.estado == "PENDIENTE").one())
        ultimo = (db.query(fin.LoteCobranza)
                  .order_by(fin.LoteCobranza.id_lote.desc()).first())
    except (ProgrammingError, OperationalError):
        db.rollback()
        raise _sin_tablas(Exception())

    return {
        "cuotas_pendientes": int(pendientes[0]) + int(externas[0]),
        "de_alumnos": int(pendientes[0]),
        "deuda_historica": int(externas[0]),
        "deuda": float(pendientes[1]) + float(externas[1]),
        "mora": float(pendientes[2]) + float(externas[2]),
        "vencimientos_sin_mora": con.vencimientos_sin_mora(db),
        "cobros_por_revisar": db.query(func.count(fin.MovimientoCobranza.id_movimiento))
            .filter(fin.MovimientoCobranza.estado == "PENDIENTE_REVISION").scalar() or 0,
        "ultimo_lote": None if not ultimo else {
            "id_lote": ultimo.id_lote,
            "archivo": ultimo.nombre_archivo,
            "fecha_reporte": ultimo.fecha_reporte.isoformat() if ultimo.fecha_reporte else None,
            "fecha_carga": ultimo.fecha_carga.isoformat() if ultimo.fecha_carga else None,
            "aplicados": ultimo.aplicados,
            "sin_coincidencia": ultimo.sin_coincidencia,
        },
    }


@router.get("/lotes")
def listar_lotes(limite: int = Query(30, ge=1, le=200),
                 db: Session = Depends(get_db),
                 current_user: dict = Depends(get_current_user)):
    """Historial de reportes procesados, del más reciente al más antiguo."""
    _solo_admin(current_user)
    try:
        filas = (db.query(fin.LoteCobranza)
                 .order_by(fin.LoteCobranza.id_lote.desc()).limit(limite).all())
    except (ProgrammingError, OperationalError):
        db.rollback()
        raise _sin_tablas(Exception())
    return [{
        "id_lote": l.id_lote,
        "archivo": l.nombre_archivo,
        "fecha_reporte": l.fecha_reporte.isoformat() if l.fecha_reporte else None,
        "fecha_carga": l.fecha_carga.isoformat() if l.fecha_carga else None,
        "registros": l.registros_declarados,
        "monto": float(l.monto_declarado or 0),
        "aplicados": l.aplicados,
        "sin_coincidencia": l.sin_coincidencia,
        "extornados": l.extornados,
    } for l in filas]


@router.get("/lotes/{id_lote}/movimientos")
def movimientos_del_lote(id_lote: int,
                         resultado: Optional[str] = None,
                         db: Session = Depends(get_db),
                         current_user: dict = Depends(get_current_user)):
    """Las líneas de un reporte y qué se hizo con cada una."""
    _solo_admin(current_user)
    lote = db.query(fin.LoteCobranza).filter(
        fin.LoteCobranza.id_lote == id_lote).first()
    if not lote:
        raise HTTPException(404, "Ese lote no existe")

    consulta = (db.query(fin.MovimientoCobranza)
                .options(joinedload(fin.MovimientoCobranza.pago)
                         .joinedload(fin.Pago.alumno))
                .filter(fin.MovimientoCobranza.id_lote == id_lote))
    if resultado:
        consulta = consulta.filter(fin.MovimientoCobranza.resultado == resultado.upper())

    return [{
        "id_movimiento": m.id_movimiento,
        "documento": m.documento,
        "alumno": m.pago.alumno_nombre if m.pago else None,
        "fecha_vencimiento": m.fecha_vencimiento.isoformat() if m.fecha_vencimiento else None,
        "fecha_pago": m.fecha_pago.isoformat() if m.fecha_pago else None,
        "monto_pagado": float(m.monto_pagado or 0),
        "mora_pagada": float(m.mora_pagada or 0),
        "monto_total": float(m.monto_total or 0),
        "operacion": m.operacion,
        "medio": m.medio_atencion,
        "resultado": m.resultado,
        "detalle": m.detalle,
    } for m in consulta.all()]


# ---------------------------------------------------------------------------
# Procesar reportes de cobros
# ---------------------------------------------------------------------------

@router.post("/reportes")
async def cargar_reportes(archivos: List[UploadFile] = File(...),
                          simular: bool = Form(True),
                          db: Session = Depends(get_db),
                          current_user: dict = Depends(get_current_user)):
    """Sube uno o varios 'Reporte de cobros' del BCP.

    Se ordenan solos por la fecha que trae cada archivo, no por el orden en
    que se suban: aplicar agosto antes que julio dejaría mora a alumnos que ya
    habían pagado.

    Con `simular` en true no se escribe nada; sirve para ver qué pasaría.
    """
    _solo_admin(current_user)
    lista = await _leer(archivos)
    try:
        return con.procesar_reportes(db, lista,
                                     id_usuario=current_user.get("id"),
                                     simular=simular)
    except ErrorFormatoBCP as e:
        db.rollback()
        raise HTTPException(400, str(e))
    except (ProgrammingError, OperationalError):
        db.rollback()
        raise _sin_tablas(Exception())
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"No se pudo procesar la carga: {e}")


@router.post("/importacion-inicial")
async def importacion_inicial(archivo: UploadFile = File(...),
                              simular: bool = Form(True),
                              sincronizar_pagadas: bool = Form(True),
                              db: Session = Depends(get_db),
                              current_user: dict = Depends(get_current_user)):
    """Toma el CREP que el colegio usa hoy y alinea la base con él.

    Se hace UNA vez, al arrancar el módulo. Da de alta la deuda de quien ya no
    está matriculado, iguala la mora a la del archivo y, si se pide, marca como
    pagadas las cuotas que el archivo ya no trae.
    """
    _solo_admin(current_user)
    (nombre, datos), = await _leer([archivo])
    try:
        return con.importar_crep_inicial(db, datos, nombre, simular=simular,
                                         sincronizar_pagadas=sincronizar_pagadas)
    except ErrorFormatoBCP as e:
        db.rollback()
        raise HTTPException(400, str(e))
    except (ProgrammingError, OperationalError):
        db.rollback()
        raise _sin_tablas(Exception())
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"No se pudo importar el archivo: {e}")


# ---------------------------------------------------------------------------
# Cobros que hay que revisar a mano
# ---------------------------------------------------------------------------

@router.get("/pendientes")
def cobros_pendientes(limite: int = Query(200, ge=1, le=1000),
                      db: Session = Depends(get_db),
                      current_user: dict = Depends(get_current_user)):
    """Cobros del banco que el sistema no pudo aplicar y nadie ha atendido."""
    _solo_admin(current_user)
    try:
        return con.pendientes_de_revision(db, limite=limite)
    except (ProgrammingError, OperationalError):
        db.rollback()
        raise _sin_tablas(Exception())


@router.get("/pendientes/{id_movimiento}/candidatos")
def candidatos(id_movimiento: int, db: Session = Depends(get_db),
               current_user: dict = Depends(get_current_user)):
    """Cuotas que podrían corresponder a ese cobro, la más probable primero."""
    _solo_admin(current_user)
    try:
        return con.candidatos_para(db, id_movimiento)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/pendientes/{id_movimiento}/resolver")
def resolver(id_movimiento: int,
             accion: str = Form(...),
             id_pago: Optional[int] = Form(None),
             id_cuota_externa: Optional[int] = Form(None),
             nota: Optional[str] = Form(None),
             db: Session = Depends(get_db),
             current_user: dict = Depends(get_current_user)):
    """Cierra a mano un cobro.

    Con `accion=aplicar` la cuota indicada queda pagada y desaparece del
    siguiente archivo de cobranza. Con `accion=descartar` no se toca ninguna
    cuota: solo deja de salir en la bandeja de pendientes.
    """
    _solo_admin(current_user)
    try:
        return con.resolver_movimiento(
            db, id_movimiento, accion=accion, id_pago=id_pago,
            id_cuota_externa=id_cuota_externa, nota=nota,
            id_usuario=current_user.get("id"))
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"No se pudo resolver el cobro: {e}")


# ---------------------------------------------------------------------------
# Mora
# ---------------------------------------------------------------------------

@router.post("/mora")
def cargar_mora(fecha_vencimiento: str = Form(...),
                importe: Optional[str] = Form(None),
                simular: bool = Form(True),
                db: Session = Depends(get_db),
                current_user: dict = Depends(get_current_user)):
    """Carga la mora a las cuotas de esa fecha que siguen sin pagarse.

    Nunca la duplica: si ya la tienen, se dejan como están.
    """
    _solo_admin(current_user)
    try:
        fecha = dt.date.fromisoformat(fecha_vencimiento)
    except ValueError:
        raise HTTPException(400, "La fecha debe venir como AAAA-MM-DD")

    valor = None
    if importe not in (None, ""):
        try:
            valor = Decimal(str(importe))
        except (InvalidOperation, ValueError):
            raise HTTPException(400, f"El importe {importe!r} no es un número")
        if valor < 0:
            raise HTTPException(400, "El importe de la mora no puede ser negativo")

    try:
        return con.aplicar_mora(db, fecha, importe=valor, simular=simular)
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"No se pudo aplicar la mora: {e}")


# ---------------------------------------------------------------------------
# Generación del archivo de cobranza
# ---------------------------------------------------------------------------

@router.get("/vista-previa")
def vista_previa(db: Session = Depends(get_db),
                 current_user: dict = Depends(get_current_user)):
    """Qué llevaría el archivo si se generara ahora, sin descargarlo."""
    _solo_admin(current_user)
    try:
        _, res = con.generar_archivo_crep(db)
    except ErrorFormatoBCP as e:
        raise HTTPException(400, str(e))
    except (ProgrammingError, OperationalError):
        db.rollback()
        raise _sin_tablas(Exception())
    return res


@router.get("/descargar")
def descargar(db: Session = Depends(get_db),
              current_user: dict = Depends(get_current_user)):
    """El archivo CREP, listo para subir al BCP."""
    _solo_admin(current_user)
    try:
        contenido, _ = con.generar_archivo_crep(db)
    except ErrorFormatoBCP as e:
        raise HTTPException(400, str(e))
    except (ProgrammingError, OperationalError):
        db.rollback()
        raise _sin_tablas(Exception())

    nombre = f"CREP-{dt.date.today().strftime('%d-%m-%Y')}.txt"
    return StreamingResponse(
        io.BytesIO(contenido),
        media_type="text/plain; charset=iso-8859-1",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"',
                 "Content-Length": str(len(contenido))},
    )


@router.get("/descargar-excel")
def descargar_excel(db: Session = Depends(get_db),
                    current_user: dict = Depends(get_current_user)):
    """La misma cobranza en .xlsx, para revisarla o guardarla de respaldo.

    No lleva las macros del BCP: ya no hacen falta, porque el .txt lo genera
    el propio sistema.
    """
    _solo_admin(current_user)
    try:
        from openpyxl import Workbook
    except ImportError:
        raise HTTPException(
            503, "Falta la librería openpyxl en el servidor para exportar a Excel")

    cuotas = con.cuotas_para_crep(db)
    if not cuotas:
        raise HTTPException(400, "No hay ninguna cuota pendiente que exportar")

    wb = Workbook()
    h = wb.active
    h.title = "Generar Archivo de Cobranza"
    h.append(["Código del Depositante", "Nombre del Depositante",
              "Información de Retorno", "Fecha de Emisión", "Fecha de Vencimiento",
              "Monto a Pagar", "Mora / Cargo Fijo", "Monto Mínimo",
              "Tipo de Registro", "Nro. Documento de Pago",
              "Nro. Documento de Identidad"])
    for c in cuotas:
        h.append([c.codigo_depositante, c.nombre, c.codigo_depositante,
                  c.fecha_emision.strftime("%d/%m/%Y"),
                  c.fecha_vencimiento.strftime("%d/%m/%Y"),
                  float(c.monto), float(c.mora), float(c.monto_minimo),
                  "No Aplica", "RECIBO", c.documento])
    for col, ancho in zip("ABCDEFGHIJK", (22, 42, 22, 16, 18, 14, 16, 14, 15, 20, 24)):
        h.column_dimensions[col].width = ancho
    h.freeze_panes = "A2"

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    nombre = f"Cobranza-{dt.date.today().strftime('%d-%m-%Y')}.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
