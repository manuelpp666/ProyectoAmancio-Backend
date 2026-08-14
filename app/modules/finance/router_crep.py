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
                  .filter(fin.LoteCobranza.estado != con.ESTADO_LOTE_INICIAL)
                  .order_by(fin.LoteCobranza.id_lote.desc()).first())
        # La puesta en marcha: se hace una sola vez y la pantalla tiene que
        # poder decir si ya está hecha.
        inicial = con.estado_puesta_en_marcha(db)
    except (ProgrammingError, OperationalError):
        db.rollback()
        raise _sin_tablas(Exception())

    return {
        "importacion_inicial": inicial,
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
        # Sin la puesta en marcha: no es un reporte de cobros y sus cifras
        # significan otra cosa, así que en esta lista solo confundiría.
        filas = (db.query(fin.LoteCobranza)
                 .filter(fin.LoteCobranza.estado != con.ESTADO_LOTE_INICIAL)
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
    except ValueError as e:
        # Reaplicar el mismo archivo de puesta en marcha.
        db.rollback()
        raise HTTPException(409, str(e))
    except (ProgrammingError, OperationalError):
        db.rollback()
        raise _sin_tablas(Exception())
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"No se pudo importar el archivo: {e}")


@router.post("/ajustar-importe")
def ajustar_importe(tipo: str = Form(...),
                    id_cuota: int = Form(...),
                    monto: str = Form(...),
                    db: Session = Depends(get_db),
                    current_user: dict = Depends(get_current_user)):
    """Deja en una cuota el importe que trae el archivo del BCP.

    Se llama desde la fila del aviso «importe distinto», una a una. OJO: esto
    sí escribe, no hay simulación. Es a propósito: llega aquí quien ya comparó
    los dos importes y decidió cuál es el bueno.
    """
    _solo_admin(current_user)
    try:
        valor = Decimal(monto)
    except (InvalidOperation, ValueError):
        raise HTTPException(400, f"«{monto}» no es un importe válido")
    try:
        return con.ajustar_importe(db, tipo, id_cuota, valor)
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    except (ProgrammingError, OperationalError):
        db.rollback()
        raise _sin_tablas(Exception())
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"No se pudo cambiar el importe: {e}")


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


# ---------------------------------------------------------------------------
# Reporte de deudores
# ---------------------------------------------------------------------------

# Excel no admite estos caracteres en el nombre de una hoja, y corta a 31.
_PROHIBIDOS_HOJA = set(r"[]:*?/\'")


def _nombre_hoja(texto: str, usados: set) -> str:
    """Un nombre de hoja válido y único, lo más parecido posible al original."""
    limpio = "".join(" " if c in _PROHIBIDOS_HOJA else c for c in (texto or "")).strip()
    limpio = " ".join(limpio.split()) or "Hoja"
    base = limpio[:31]
    nombre, n = base, 2
    while nombre.lower() in usados:
        # Al recortar, dos secciones distintas pueden chocar. Se numeran.
        sufijo = f" ({n})"
        nombre = base[:31 - len(sufijo)] + sufijo
        n += 1
    usados.add(nombre.lower())
    return nombre


@router.get("/deudores.xlsx")
def deudores_excel(anio: Optional[str] = Query(None, description="Año escolar; por defecto el activo"),
                   db: Session = Depends(get_db),
                   current_user: dict = Depends(get_current_user)):
    """La lista de deudores en Excel: resumen, detalle y una hoja por sección.

    Es el reporte que el colegio sacaba a mano del .xlsm. Lleva:

      · Resumen      — cuánto debe cada sección, para ver dónde está el grueso
      · Deudores     — un alumno por fila, con su total y su atraso
      · Detalle      — una cuota por fila, para cuadrar importe a importe
      · Una hoja por sección, que es lo que se le pasa a cada tutor
      · Deuda anterior — retirados y trasladados, que no tienen sección
    """
    _solo_admin(current_user)
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
    except ImportError:
        raise HTTPException(
            503, "Falta la librería openpyxl en el servidor para exportar a Excel")

    try:
        datos = con.reporte_deudores(db, anio)
    except (ProgrammingError, OperationalError):
        db.rollback()
        raise _sin_tablas(Exception())
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"No se pudo armar el reporte: {e}")

    if not datos["deudores"] and not datos["externas"]:
        raise HTTPException(
            400, "No hay ninguna deuda pendiente: no hay nada que exportar")

    GRANATE = PatternFill("solid", fgColor="701C32")
    GRIS = PatternFill("solid", fgColor="F1F1F1")
    BLANCO_NEGRITA = Font(bold=True, color="FFFFFF")
    NEGRITA = Font(bold=True)
    ROJO = Font(bold=True, color="B21E1E")
    SOLES = '"S/ "#,##0.00'
    FECHA = "DD/MM/YYYY"

    def cabecera(hoja, titulos, anchos):
        hoja.append(titulos)
        for celda in hoja[1]:
            celda.fill = GRANATE
            celda.font = BLANCO_NEGRITA
            celda.alignment = Alignment(horizontal="center", vertical="center",
                                        wrap_text=True)
        for i, ancho in enumerate(anchos, start=1):
            hoja.column_dimensions[hoja.cell(row=1, column=i).column_letter].width = ancho
        hoja.freeze_panes = "A2"

    def formatear(hoja, columnas_soles=(), columnas_fecha=()):
        for fila in hoja.iter_rows(min_row=2):
            for celda in fila:
                if celda.column_letter in columnas_soles:
                    celda.number_format = SOLES
                elif celda.column_letter in columnas_fecha:
                    celda.number_format = FECHA

    wb = Workbook()
    usados: set = set()

    # ------------------------------------------------------------- resumen
    h = wb.active
    h.title = _nombre_hoja("Resumen", usados)
    t = datos["totales"]
    h.append([f"Deudores del colegio · año {datos['anio'] or '—'}"])
    h["A1"].font = Font(bold=True, size=14, color="701C32")
    h.append([f"Generado el {datos['fecha'].strftime('%d/%m/%Y')}"])
    h.append([])
    for etiqueta, valor, es_dinero in (
            ("Alumnos que deben", t["alumnos"], False),
            ("Cuotas pendientes", t["cuotas"], False),
            ("Deuda (sin mora)", float(t["deuda"]), True),
            ("Mora acumulada", float(t["mora"]), True),
            ("TOTAL a cobrar", float(t["total"]), True),
            ("De eso, ya vencido", float(t["vencido"]), True),
            ("Cuotas de deuda anterior", t["externas"], False),
            ("Total de deuda anterior", float(t["total_externas"]), True)):
        h.append([etiqueta, valor])
        h.cell(row=h.max_row, column=1).font = NEGRITA
        if es_dinero:
            h.cell(row=h.max_row, column=2).number_format = SOLES
    h.append([])

    inicio = h.max_row + 1
    h.append(["Nivel", "Grado", "Sección", "Alumnos", "Cuotas",
              "Deuda", "Mora", "Total", "Vencido"])
    for celda in h[inicio]:
        celda.fill = GRANATE
        celda.font = BLANCO_NEGRITA
        celda.alignment = Alignment(horizontal="center", wrap_text=True)
    for s in datos["secciones"]:
        h.append([s["nivel"], s["grado"], s["seccion"], s["num_alumnos"],
                  s["num_cuotas"], float(s["deuda"]), float(s["mora"]),
                  float(s["total"]), float(s["vencido"])])
        for col in ("F", "G", "H", "I"):
            h[f"{col}{h.max_row}"].number_format = SOLES
    for col, ancho in zip("ABCDEFGHI", (16, 14, 12, 10, 9, 14, 12, 14, 14)):
        h.column_dimensions[col].width = ancho

    # ------------------------------------------------------- todos los deudores
    h = wb.create_sheet(_nombre_hoja("Deudores", usados))
    cabecera(h, ["DNI", "Alumno", "Nivel", "Grado", "Sección", "Cuotas",
                 "Vencidas", "Deuda", "Mora", "Total", "Debe desde",
                 "Días de atraso"],
             (12, 38, 14, 14, 10, 8, 9, 13, 11, 13, 14, 12))
    for d in datos["deudores"]:
        h.append([d["dni"], d["alumno"], d["nivel"], d["grado"], d["seccion"],
                  d["num_cuotas"], d["num_vencidas"], float(d["deuda"]),
                  float(d["mora"]), float(d["total"]), d["desde"], d["dias_atraso"]])
        if d["num_vencidas"]:
            h.cell(row=h.max_row, column=12).font = ROJO
    formatear(h, columnas_soles=("H", "I", "J"), columnas_fecha=("K",))
    h.auto_filter.ref = h.dimensions

    # --------------------------------------------------------------- detalle
    h = wb.create_sheet(_nombre_hoja("Detalle por cuota", usados))
    cabecera(h, ["DNI", "Alumno", "Nivel", "Grado", "Sección", "Concepto",
                 "Vence", "Monto", "Mora", "Total", "Estado", "Días de atraso"],
             (12, 34, 14, 14, 10, 26, 12, 12, 11, 12, 12, 12))
    for d in datos["deudores"]:
        for c in d["cuotas"]:
            h.append([d["dni"], d["alumno"], d["nivel"], d["grado"], d["seccion"],
                      c["concepto"], c["vencimiento"], float(c["monto"]),
                      float(c["mora"]), float(c["total"]),
                      "VENCIDA" if c["vencida"] else "Por vencer",
                      c["dias_atraso"]])
            if c["vencida"]:
                h.cell(row=h.max_row, column=11).font = ROJO
    formatear(h, columnas_soles=("H", "I", "J"), columnas_fecha=("G",))
    h.auto_filter.ref = h.dimensions

    # ------------------------------------------------------ una hoja por sección
    for s in datos["secciones"]:
        titulo = f"{s['grado']} {s['seccion']}".strip() or s["seccion"]
        h = wb.create_sheet(_nombre_hoja(titulo, usados))
        h.append([f"{s['nivel']} · {s['grado']} · {s['seccion']}"])
        h["A1"].font = Font(bold=True, size=12, color="701C32")
        h.append([f"{s['num_alumnos']} alumnos deben {s['num_cuotas']} cuotas"])
        h.append([])
        inicio = h.max_row + 1
        h.append(["DNI", "Alumno", "Concepto", "Vence", "Monto", "Mora",
                  "Total", "Días de atraso"])
        for celda in h[inicio]:
            celda.fill = GRANATE
            celda.font = BLANCO_NEGRITA
            celda.alignment = Alignment(horizontal="center", wrap_text=True)
        for d in s["alumnos"]:
            for c in d["cuotas"]:
                h.append([d["dni"], d["alumno"], c["concepto"], c["vencimiento"],
                          float(c["monto"]), float(c["mora"]), float(c["total"]),
                          c["dias_atraso"]])
                h[f"D{h.max_row}"].number_format = FECHA
                for col in ("E", "F", "G"):
                    h[f"{col}{h.max_row}"].number_format = SOLES
                if c["vencida"]:
                    h[f"H{h.max_row}"].font = ROJO
        h.append([])
        h.append(["", "TOTAL DE LA SECCIÓN", "", "", float(s["deuda"]),
                  float(s["mora"]), float(s["total"]), ""])
        for col in ("B", "E", "F", "G"):
            h[f"{col}{h.max_row}"].font = NEGRITA
            h[f"{col}{h.max_row}"].fill = GRIS
        for col in ("E", "F", "G"):
            h[f"{col}{h.max_row}"].number_format = SOLES
        for col, ancho in zip("ABCDEFGH", (12, 36, 26, 12, 12, 11, 12, 13)):
            h.column_dimensions[col].width = ancho
        h.freeze_panes = f"A{inicio + 1}"

    # -------------------------------------------------------- deuda anterior
    if datos["externas"]:
        h = wb.create_sheet(_nombre_hoja("Deuda anterior", usados))
        cabecera(h, ["Documento", "Nombre", "Concepto", "Vence", "Monto",
                     "Mora", "Total", "Días de atraso", "Origen"],
                 (14, 38, 26, 12, 12, 11, 12, 13, 26))
        for e in datos["externas"]:
            h.append([e["documento"], e["nombre"], e["concepto"], e["vencimiento"],
                      float(e["monto"]), float(e["mora"]), float(e["total"]),
                      e["dias_atraso"], e["origen"]])
        formatear(h, columnas_soles=("E", "F", "G"), columnas_fecha=("D",))
        h.auto_filter.ref = h.dimensions

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    nombre = (f"Deudores-{datos['anio'] or 'sin-anio'}-"
              f"{datos['fecha'].strftime('%d-%m-%Y')}.xlsx")
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
