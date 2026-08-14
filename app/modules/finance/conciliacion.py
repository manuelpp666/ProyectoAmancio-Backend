# -*- coding: utf-8 -*-
"""
Conciliación de los cobros del BCP contra las cuotas del sistema.

Sustituye al circuito manual del .xlsm: se cargan los "Reporte de cobros" del
banco, se marcan las cuotas pagadas, se aplica la mora a las que vencieron sin
pagar y se genera el CREP que vuelve a subirse al BCP.

Reglas que no se pueden romper:

  · Los reportes se aplican SIEMPRE del más antiguo al más nuevo. La mora de un
    mes depende de quién ya había pagado, así que el orden cambia el resultado.
  · Un pago extornado (devuelto) NO cancela la deuda.
  · Un archivo ya procesado no se vuelve a aplicar: se reconoce por el hash de
    su contenido, no por el nombre.
  · La mora no se duplica: solo entra en cuotas que todavía no la tienen.
"""

from __future__ import annotations

import calendar
import datetime as dt
import hashlib
import json
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session, joinedload

from app.modules.finance import models as fin
from app.modules.finance.crep import (
    CabeceraCREP, CuotaCREP, ErrorFormatoBCP, PagoBCP,
    generar_crep, parsear_reporte_cobros,
)
from app.modules.users.alumno.models import Alumno

# Estados de `pago` que representan una deuda viva: son las que viajan al BCP.
PENDIENTES = ("PENDIENTE", "VENCIDO")
TOLERANCIA = Decimal("0.01")

# Tope de cobros que se devuelven al panel. Un reporte diario trae unas 50
# líneas, pero si alguien sube dos meses de golpe la respuesta se dispararía.
MAXIMO_COBROS_DEVUELTOS = 3000


def _doc(valor) -> str:
    """Normaliza un documento para comparar: sin espacios ni ceros delante."""
    return (str(valor or "").strip().lstrip("0")) if valor is not None else ""


def _huella(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


# ---------------------------------------------------------------------------
# El 30 y el 31: cuándo dos vencimientos son el mismo
# ---------------------------------------------------------------------------
#
# La plantilla de `tipo_pago` guarda el vencimiento como "MM-DD", o sea un día
# fijo, y las pensiones están puestas en 30. Al generar las cuotas se hace
# `min(30, último día del mes)`, así que en enero, marzo, mayo, julio, agosto,
# octubre y diciembre el sistema escribe 30 donde el BCP usa 31.
#
# Son la misma fecha dicha de dos maneras: "fin de mes". Sin esto, la mitad de
# los meses del año no cruzaría con el reporte del banco.
#
# La equivalencia es deliberadamente estrecha —solo el último día del mes y el
# anterior— para que el 10 de julio del módulo 2, que el colegio pone a
# propósito, siga siendo una fecha distinta y no se mezcle con nada.
#
# Diciembre no entra en esta regla y necesita otra. El colegio le cambia la
# fecha cada año —31 en 2022 y 2023, 30 en 2024 y 2025, 25 en 2026— así que
# fijar un día concreto se rompería el curso que viene. Para ese caso está el
# tercer intento de `IndiceDeudas.buscar`: mismo alumno, mismo mes y UNA SOLA
# cuota pendiente. Se apoya en un hecho de los datos, no en el calendario: en
# diciembre cada alumno debe una sola cuota, mientras que en abril y julio
# debe dos (la pensión y el módulo), y ahí la regla no llega a dispararse.

def _ultimo_dia(anio: int, mes: int) -> int:
    return calendar.monthrange(anio, mes)[1]


def es_fin_de_mes(fecha: Optional[dt.date]) -> bool:
    """¿Esta fecha quiere decir "el último día del mes"?

    Mes de 31 días -> 30 y 31.  Mes de 30 -> 29 y 30.  Febrero -> 28 (y 29 en
    año bisiesto). Cualquier día anterior es una fecha propia y no entra.
    """
    if not fecha:
        return False
    ultimo = _ultimo_dia(fecha.year, fecha.month)
    return fecha.day >= max(28, ultimo - 1)


def mismo_vencimiento(a: Optional[dt.date], b: Optional[dt.date]) -> bool:
    """Iguales, o los dos fin de mes del mismo mes."""
    if a is None or b is None:
        return a is None and b is None
    if a == b:
        return True
    return _mismo_mes(a, b) and es_fin_de_mes(a) and es_fin_de_mes(b)


def _mismo_mes(a: Optional[dt.date], b: Optional[dt.date]) -> bool:
    return bool(a and b and a.year == b.year and a.month == b.month)


def _marca(registro) -> Tuple[str, Optional[int]]:
    """Identifica una cuota sin importar si es `Pago` o `CuotaExterna`."""
    return (type(registro).__name__,
            getattr(registro, "id_pago", None)
            or getattr(registro, "id_cuota_externa", None))


# ---------------------------------------------------------------------------
# Índice de deudas
# ---------------------------------------------------------------------------

class IndiceDeudas:
    """Las cuotas vivas, indexadas por (documento, vencimiento).

    Se arma una sola vez por proceso y se va actualizando en memoria conforme
    se aplican los pagos, para no consultar la base por cada línea del reporte.
    """

    def __init__(self, db: Session):
        self.db = db
        self.por_clave: Dict[Tuple[str, dt.date], List] = {}
        # Segundo índice, solo con las cuotas que vencen a fin de mes, para
        # cruzar el 30 del sistema con el 31 del banco. Se consulta únicamente
        # cuando la fecha exacta no encuentra nada.
        self.por_fin_de_mes: Dict[Tuple[str, int, int], List] = {}
        # Todas las cuotas del alumno en cada mes, sin mirar el día. Es el
        # último recurso, y solo vale cuando en ese mes hay una sola: así se
        # resuelve diciembre, cuya fecha cambia de un año a otro.
        self.por_mes: Dict[Tuple[str, int, int], List] = {}
        # Dónde quedó cada cuota, para poder sacarla de todos los índices
        # cuando se aplica un pago.
        self._ubicaciones: Dict[Tuple[str, Optional[int]], List[Tuple[dict, tuple]]] = {}
        # Documento -> nombre, de TODOS los alumnos, no solo de los que deben.
        # Sirve para poder decir quién pagó aunque el cobro no cruce con
        # ninguna cuota: sin esto la tabla mostraría un DNI suelto.
        self.nombres: Dict[str, str] = {}
        self._cargar_nombres()
        self._cargar_pagos()
        self._cargar_externas()

    def _añadir(self, clave, registro):
        doc, venc = clave
        self.por_clave.setdefault(clave, []).append(registro)
        ubicaciones = self._ubicaciones.setdefault(_marca(registro), [])
        ubicaciones.append((self.por_clave, clave))
        if es_fin_de_mes(venc):
            fdm = (doc, venc.year, venc.month)
            self.por_fin_de_mes.setdefault(fdm, []).append(registro)
            ubicaciones.append((self.por_fin_de_mes, fdm))
        mes = (doc, venc.year, venc.month)
        self.por_mes.setdefault(mes, []).append(registro)
        ubicaciones.append((self.por_mes, mes))

    def quitar(self, registro) -> None:
        """Saca una cuota ya cobrada de todos los índices.

        Sin esto, dos líneas del mismo reporte podrían aplicarse a la misma
        cuota, o la segunda saldría como AMBIGUO sin serlo.
        """
        for indice, clave in self._ubicaciones.pop(_marca(registro), []):
            lista = indice.get(clave)
            if lista and registro in lista:
                lista.remove(registro)

    def _cargar_nombres(self):
        for dni, apellidos, nombres in self.db.query(
                Alumno.dni, Alumno.apellidos, Alumno.nombres).all():
            doc = _doc(dni)
            if doc:
                self.nombres[doc] = f"{apellidos or ''}, {nombres or ''}".strip(", ")
        for c in self.db.query(fin.CuotaExterna).all():
            for doc in {_doc(c.documento), _doc(c.codigo_depositante)}:
                if doc:
                    self.nombres.setdefault(doc, c.nombre)

    def nombre_de(self, pago: PagoBCP) -> Optional[str]:
        for doc in pago.documentos:
            hallado = self.nombres.get(_doc(doc))
            if hallado:
                return hallado
        return None

    def _cargar_pagos(self):
        filas = (self.db.query(fin.Pago)
                 .options(joinedload(fin.Pago.alumno))
                 .filter(fin.Pago.estado.in_(PENDIENTES))
                 .all())
        for p in filas:
            if not p.fecha_vencimiento or not p.alumno:
                continue
            doc = _doc(p.alumno.dni)
            if doc:
                self._añadir((doc, p.fecha_vencimiento), p)

    def _cargar_externas(self):
        filas = (self.db.query(fin.CuotaExterna)
                 .filter(fin.CuotaExterna.estado == "PENDIENTE").all())
        for c in filas:
            for doc in {_doc(c.documento), _doc(c.codigo_depositante)}:
                if doc:
                    self._añadir((doc, c.fecha_vencimiento), c)

    def buscar(self, pago: PagoBCP) -> Tuple[List, Optional[str]]:
        """Cuotas que encajan con ese cobro, sin repetir.

        Devuelve (cuotas, cómo se encontraron): None si la fecha era idéntica,
        "fin_de_mes" o "mismo_mes" si hubo que aflojar. Se intenta en ese
        orden y el primero que da resultado gana, así que la fecha exacta
        siempre manda y nada de lo que ya funcionaba cambia.
        """
        encontrados, vistos = [], set()

        def recoger(lista):
            for reg in lista or []:
                marca = _marca(reg)
                if marca not in vistos:
                    vistos.add(marca)
                    encontrados.append(reg)

        venc = pago.fecha_vencimiento
        if venc is None:
            return [], None

        # 1) La fecha exacta.
        for doc in pago.documentos:
            recoger(self.por_clave.get((_doc(doc), venc)))
        if encontrados:
            return encontrados, None

        # 2) El mismo fin de mes: el 30 del sistema y el 31 del banco.
        if es_fin_de_mes(venc):
            for doc in pago.documentos:
                recoger(self.por_fin_de_mes.get((_doc(doc), venc.year, venc.month)))
            if encontrados:
                return encontrados, "fin_de_mes"

        # 3) El mismo mes, pase lo que pase con el día. Solo se acepta si en
        #    ese mes hay UNA cuota: con dos no hay forma de saber cuál es y se
        #    devuelven las dos, que es lo que hace que salga como AMBIGUO y
        #    acabe en la bandeja para que alguien decida.
        for doc in pago.documentos:
            recoger(self.por_mes.get((_doc(doc), venc.year, venc.month)))
        return (encontrados, "mismo_mes") if encontrados else ([], None)


# ---------------------------------------------------------------------------
# Aplicación de un reporte
# ---------------------------------------------------------------------------

def _marcar_pagado(registro, pago: PagoBCP) -> None:
    registro.estado = "PAGADO"
    registro.fecha_pago = dt.datetime.combine(
        pago.fecha_pago or dt.date.today(), dt.time.min)
    registro.codigo_operacion_bcp = pago.operacion or None
    if isinstance(registro, fin.Pago):
        registro.json_respuesta_banco = json.dumps({
            "origen": "REPORTE_COBROS_BCP",
            "operacion": pago.operacion,
            "operacion_bd": pago.operacion_bd,
            "operacion_canal": pago.operacion_canal,
            "sucursal": pago.sucursal,
            "agencia": pago.agencia,
            "medio_atencion": pago.medio_atencion,
            "hora": pago.hora_atencion,
            "monto_pagado": str(pago.monto_pagado),
            "mora_pagada": str(pago.mora_pagada),
            "fecha_pago": pago.fecha_pago.isoformat() if pago.fecha_pago else None,
        }, ensure_ascii=False)


def _unica_por_importe(candidatos: List, pago: PagoBCP):
    """Cuando varias cuotas comparten vencimiento, la que cuadra en importe.

    Hace falta para los alumnos nuevos: las plantillas de Vacante y Matrícula
    vencen las dos el mismo día, así que todo el que ingrese tendrá dos cuotas
    con la misma clave. Se distinguen por el precio —100 la vacante, 200 la
    matrícula—, que es exactamente lo que el padre pagó en ventanilla.

    Devuelve None si cuadran varias o ninguna: ahí no hay nada que deducir y
    el cobro tiene que ir a revisión.
    """
    cuadran = [c for c in candidatos
               if abs(pago.monto_pagado - Decimal(str(c.monto))) <= TOLERANCIA]
    return cuadran[0] if len(cuadran) == 1 else None


def _conciliar_reporte(db: Session, indice: IndiceDeudas, reporte, lote,
                       nombre: str, simular: bool) -> Tuple[Dict[str, int], List[dict]]:
    """Devuelve (conteo por resultado, detalle de cada cobro).

    El detalle se arma siempre, también al simular: es lo que permite ver en
    pantalla quién pagó antes de escribir nada en la base.
    """
    conteo = {"APLICADO": 0, "EXTORNADO": 0, "SIN_COINCIDENCIA": 0,
              "REPETIDO": 0, "MONTO_DISTINTO": 0, "AMBIGUO": 0}
    detalle_cobros: List[dict] = []

    for pago in reporte.pagos:
        registro, resultado, detalle = None, None, None
        candidatos, como = [], None

        if pago.extornado:
            resultado = "EXTORNADO"
            detalle = "El banco devolvió el dinero: la deuda sigue viva"
        else:
            candidatos, como = indice.buscar(pago)
            # Cuando la fecha no era idéntica se deja constancia de por qué se
            # aceptó igual: el banco cobró con una fecha y la cuota tiene otra.
            # Con varias candidatas no se puede hablar de "la" cuota, así que
            # el aviso solo se redacta cuando hay una.
            aviso_fecha = ""
            if como and len(candidatos) == 1:
                suya = getattr(candidatos[0], "fecha_vencimiento", None)
                porque = ("es el mismo fin de mes" if como == "fin_de_mes" else
                          "es la única cuota que ese alumno debe de ese mes")
                aviso_fecha = (f" El banco lo cobró con vencimiento "
                               f"{pago.fecha_vencimiento:%d/%m/%Y} y en el sistema "
                               f"la cuota vence el {suya:%d/%m/%Y}; {porque}.")
            elif como and candidatos:
                aviso_fecha = (f" Ninguna cuota de ese alumno vence el "
                               f"{pago.fecha_vencimiento:%d/%m/%Y}; estas son las "
                               f"de ese mes.")
            if not candidatos:
                resultado = "SIN_COINCIDENCIA"
                detalle = (f"No hay cuota pendiente para el documento "
                           f"{pago.codigo_depositante} con vencimiento "
                           f"{pago.fecha_vencimiento}")
            elif len(candidatos) > 1 and _unica_por_importe(candidatos, pago) is None:
                resultado = "AMBIGUO"
                detalle = f"{len(candidatos)} cuotas encajan con ese cobro.{aviso_fecha}"
            else:
                desempatada = (_unica_por_importe(candidatos, pago)
                               if len(candidatos) > 1 else None)
                if desempatada is not None:
                    aviso_fecha += (
                        f" Ese alumno tenía {len(candidatos)} cuotas con ese "
                        f"vencimiento y se aplicó a «{desempatada.concepto}», "
                        f"la única cuyo importe coincide.")
                registro = desempatada or candidatos[0]
                esperado = Decimal(str(registro.monto))
                if abs(pago.monto_pagado - esperado) > TOLERANCIA:
                    resultado = "MONTO_DISTINTO"
                    detalle = (f"Pagó S/ {pago.monto_pagado} y la cuota es de "
                               f"S/ {esperado}. No se marcó como pagada.{aviso_fecha}")
                    registro = None
                else:
                    resultado = "APLICADO"
                    detalle = aviso_fecha.strip() or None
                    if not simular:
                        _marcar_pagado(registro, pago)
                        indice.quitar(registro)

        conteo[resultado] = conteo.get(resultado, 0) + 1

        detalle_cobros.append({
            "archivo": nombre,
            "linea": pago.linea,
            "documento": pago.codigo_depositante,
            "alumno": indice.nombre_de(pago),
            "concepto": getattr(registro, "concepto", None),
            "fecha_pago": pago.fecha_pago.isoformat() if pago.fecha_pago else None,
            "hora": (f"{pago.hora_atencion[:2]}:{pago.hora_atencion[2:4]}"
                     if len(pago.hora_atencion) >= 4 else ""),
            "fecha_vencimiento": (pago.fecha_vencimiento.isoformat()
                                  if pago.fecha_vencimiento else None),
            "monto_pagado": float(pago.monto_pagado),
            "mora_pagada": float(pago.mora_pagada),
            "monto_total": float(pago.monto_total),
            "operacion": pago.operacion,
            "medio": pago.medio_atencion,
            "resultado": resultado,
            "detalle": detalle,
            # Para que en la tabla se vea de un vistazo cuáles cruzaron con una
            # fecha distinta a la del banco, sin tener que leer el detalle.
            "cruce_por_fecha": (como if candidatos else None),
        })

        if not simular:
            db.add(fin.MovimientoCobranza(
                lote=lote,
                id_pago=getattr(registro, "id_pago", None)
                if isinstance(registro, fin.Pago) else None,
                id_cuota_externa=getattr(registro, "id_cuota_externa", None)
                if isinstance(registro, fin.CuotaExterna) else None,
                documento=pago.codigo_depositante or "",
                fecha_vencimiento=pago.fecha_vencimiento,
                fecha_pago=pago.fecha_pago,
                monto_pagado=pago.monto_pagado,
                mora_pagada=pago.mora_pagada,
                monto_total=pago.monto_total,
                operacion=pago.operacion,
                medio_atencion=pago.medio_atencion,
                resultado=resultado,
                detalle=(detalle or "")[:255] or None,
                # Los que se aplicaron solos no hay nada que revisarlos, y en
                # los extornados la decisión ya la tomó el banco. El resto
                # entra a la bandeja para que alguien los mire.
                estado=("RESUELTO" if resultado == "APLICADO"
                        else "DESCARTADO" if resultado == "EXTORNADO"
                        else "PENDIENTE_REVISION"),
                nota=("Aplicado automáticamente al conciliar"
                      if resultado == "APLICADO"
                      else "Extornado por el banco: el dinero se devolvió"
                      if resultado == "EXTORNADO" else None),
                fecha_resolucion=(dt.datetime.now()
                                  if resultado in ("APLICADO", "EXTORNADO") else None),
            ))
    return conteo, detalle_cobros


def procesar_reportes(db: Session, archivos: List[Tuple[str, bytes]],
                      id_usuario: Optional[int] = None,
                      simular: bool = False) -> dict:
    """Procesa uno o varios reportes de cobros, en orden cronológico.

    `archivos` es una lista de (nombre, contenido). Devuelve un resumen por
    archivo y uno global. Si `simular`, no escribe nada en la base.
    """
    if not archivos:
        raise ValueError("No se recibió ningún archivo")

    # 1) Leer todos antes de tocar nada: si uno está mal, no se aplica ninguno.
    leidos = []
    for nombre, datos in archivos:
        try:
            reporte = parsear_reporte_cobros(datos)
        except ErrorFormatoBCP as e:
            raise ErrorFormatoBCP(f"«{nombre}»: {e}")
        leidos.append((nombre, datos, reporte))

    # 2) Orden cronológico. Es obligatorio: aplicar agosto antes que julio
    #    dejaría mora a alumnos que ya habían pagado.
    leidos.sort(key=lambda x: (x[2].fecha_proceso or dt.date.min, x[0]))

    # 3) Descartar los que ya se aplicaron antes (por contenido, no por nombre).
    ya = {h for (h,) in db.query(fin.LoteCobranza.huella).all()}
    resumen, indice = [], IndiceDeudas(db)
    cobros: List[dict] = []
    total = {"APLICADO": 0, "EXTORNADO": 0, "SIN_COINCIDENCIA": 0,
             "REPETIDO": 0, "MONTO_DISTINTO": 0, "AMBIGUO": 0}

    for nombre, datos, reporte in leidos:
        huella = _huella(datos)
        if huella in ya:
            resumen.append({
                "archivo": nombre,
                "fecha_reporte": reporte.fecha_proceso.isoformat()
                if reporte.fecha_proceso else None,
                "omitido": True,
                "motivo": "Este archivo ya se había procesado antes",
                "cobros": len(reporte.pagos),
            })
            continue
        ya.add(huella)

        lote = fin.LoteCobranza(
            nombre_archivo=nombre[:255],
            fecha_reporte=reporte.fecha_proceso,
            registros_declarados=reporte.registros_declarados,
            monto_declarado=reporte.monto_declarado,
            huella=huella,
            estado="SIMULADO" if simular else "PROCESADO",
            id_usuario=id_usuario,
        )
        if not simular:
            db.add(lote)

        conteo, detalle_cobros = _conciliar_reporte(db, indice, reporte, lote,
                                                    nombre, simular)
        cobros.extend(detalle_cobros)
        for k, v in conteo.items():
            total[k] = total.get(k, 0) + v

        lote.aplicados = conteo["APLICADO"]
        lote.sin_coincidencia = conteo["SIN_COINCIDENCIA"]
        lote.extornados = conteo["EXTORNADO"]
        lote.repetidos = conteo["REPETIDO"]

        resumen.append({
            "archivo": nombre,
            "fecha_reporte": reporte.fecha_proceso.isoformat()
            if reporte.fecha_proceso else None,
            "omitido": False,
            "cobros": len(reporte.pagos),
            "monto": float(reporte.monto_real),
            "avisos": reporte.avisos(),
            **{k.lower(): v for k, v in conteo.items()},
        })

    if not simular:
        db.commit()

    # Orden cronológico del cobro: día, hora y número de operación. Es como se
    # leen en la ventanilla del banco y es lo que se enseña en pantalla.
    cobros.sort(key=lambda c: (c["fecha_pago"] or "", c["hora"] or "",
                               c["operacion"] or ""))

    return {
        "simulado": simular,
        "archivos": resumen,
        "totales": total,
        "cobros": cobros[:MAXIMO_COBROS_DEVUELTOS],
        "cobros_totales": len(cobros),
    }


# ---------------------------------------------------------------------------
# Mora
# ---------------------------------------------------------------------------

def _mora_del_tipo(tipo) -> Decimal:
    """Cuánta mora cobra ese concepto.

    Ojo con el cero: `Decimal('0.00')` es falso en Python, así que un
    `tipo.mora or 5` convertiría "no cobra mora" en "cobra 5 soles". Los
    módulos están justamente en cero, y con ese error se les cargaba una mora
    que el BCP no cobra.
    """
    if tipo is None or tipo.mora is None:
        return Decimal("5.00")
    return Decimal(str(tipo.mora))


def aplicar_mora(db: Session, fecha_vencimiento: dt.date,
                 importe: Optional[Decimal] = None,
                 simular: bool = False) -> dict:
    """Carga la mora a las cuotas de esa fecha que siguen sin pagarse.

    No la duplica: las cuotas que ya tienen mora se dejan como están. Es la
    misma regla del archivo del BCP, donde `Monto Mínimo = Monto + Mora`.
    """
    if es_fin_de_mes(fecha_vencimiento):
        # Si la fecha es fin de mes se cargan todas las de ese fin de mes, no
        # solo el día exacto: en la base conviven cuotas al 30 y al 31 del
        # mismo mes, y dejar unas con mora y otras sin ella descuadraría el
        # archivo que se le manda al banco.
        primero = fecha_vencimiento.replace(day=1)
        ultimo = fecha_vencimiento.replace(
            day=_ultimo_dia(fecha_vencimiento.year, fecha_vencimiento.month))
        cuotas = [c for c in db.query(fin.Pago)
                  .options(joinedload(fin.Pago.tipo_pago))
                  .filter(fin.Pago.estado.in_(PENDIENTES),
                          fin.Pago.fecha_vencimiento >= primero,
                          fin.Pago.fecha_vencimiento <= ultimo).all()
                  if es_fin_de_mes(c.fecha_vencimiento)]
    else:
        cuotas = (db.query(fin.Pago)
                  .options(joinedload(fin.Pago.tipo_pago))
                  .filter(fin.Pago.estado.in_(PENDIENTES),
                          fin.Pago.fecha_vencimiento == fecha_vencimiento)
                  .all())

    tocadas, ya_tenian, sin_regla = [], 0, 0
    for c in cuotas:
        tipo = c.tipo_pago
        if tipo is not None and tipo.accion_vencimiento != "APLICAR_MORA":
            sin_regla += 1
            continue
        if c.mora and Decimal(str(c.mora)) > 0:
            ya_tenian += 1
            continue
        valor = importe if importe is not None else _mora_del_tipo(tipo)
        if valor <= 0:
            # Mora en cero es una decisión, no un dato que falte: los módulos
            # están así a propósito porque el colegio no se la cobra.
            sin_regla += 1
            continue
        if not simular:
            c.mora = valor
            c.monto_total = Decimal(str(c.monto)) + valor
        tocadas.append({
            "id_pago": c.id_pago,
            "alumno": c.alumno_nombre,
            "dni": c.dni_alumno,
            "concepto": c.concepto,
            "monto": float(c.monto),
            "mora": float(valor),
            "nuevo_total": float(Decimal(str(c.monto)) + valor),
        })

    if not simular and tocadas:
        db.commit()

    return {
        "simulado": simular,
        "fecha_vencimiento": fecha_vencimiento.isoformat(),
        "cuotas_de_esa_fecha": len(cuotas),
        "con_mora_aplicada": len(tocadas),
        "ya_tenian_mora": ya_tenian,
        "sin_regla_de_mora": sin_regla,
        "importe_total": float(sum(Decimal(str(t["mora"])) for t in tocadas)) if tocadas else 0.0,
        "detalle": tocadas[:200],
    }


def vencimientos_sin_mora(db: Session, hasta: Optional[dt.date] = None) -> List[dict]:
    """Fechas ya vencidas con cuotas impagas que todavía no tienen mora."""
    hasta = hasta or dt.date.today()
    filas = (db.query(fin.Pago)
             .options(joinedload(fin.Pago.tipo_pago))
             .filter(fin.Pago.estado.in_(PENDIENTES),
                     fin.Pago.fecha_vencimiento <= hasta)
             .all())
    agrupado: Dict[tuple, dict] = {}
    for c in filas:
        tipo = c.tipo_pago
        if tipo is not None and tipo.accion_vencimiento != "APLICAR_MORA":
            continue
        cuanto = _mora_del_tipo(tipo)
        if cuanto <= 0:
            continue                      # concepto sin mora, como los módulos
        # El 30 y el 31 del mismo mes son una sola fila: son la misma fecha de
        # vencimiento escrita de dos formas.
        clave = (("FIN_DE_MES", c.fecha_vencimiento.year, c.fecha_vencimiento.month)
                 if es_fin_de_mes(c.fecha_vencimiento) else c.fecha_vencimiento)
        d = agrupado.setdefault(clave,
                                {"fecha": c.fecha_vencimiento, "impagas": 0,
                                 "sin_mora": 0, "importe": Decimal("0")})
        # Se muestra la fecha más tardía del grupo, que es la que usa el banco.
        d["fecha"] = max(d["fecha"], c.fecha_vencimiento)
        d["impagas"] += 1
        if not c.mora or Decimal(str(c.mora)) == 0:
            d["sin_mora"] += 1
            d["importe"] += cuanto
    return [{"fecha": v["fecha"].isoformat(), "impagas": v["impagas"],
             "sin_mora": v["sin_mora"], "importe": float(v["importe"])}
            for v in sorted(agrupado.values(), key=lambda x: x["fecha"])
            if v["sin_mora"]]


# ---------------------------------------------------------------------------
# Generación del CREP
# ---------------------------------------------------------------------------

def cuotas_para_crep(db: Session) -> List[CuotaCREP]:
    """Todo lo que sigue por cobrar: cuotas de alumnos + deuda histórica."""
    cuotas: List[CuotaCREP] = []

    filas = (db.query(fin.Pago).options(joinedload(fin.Pago.alumno))
             .filter(fin.Pago.estado.in_(PENDIENTES)).all())
    for p in filas:
        if not p.alumno or not p.fecha_vencimiento:
            continue
        doc = _doc(p.alumno.dni)
        if not doc:
            continue
        # El BCP no acepta emisión posterior al vencimiento. Si no hay dato,
        # se toma el primer día del mes del vencimiento, que es como venía
        # armado el archivo del colegio.
        emision = p.fecha_vencimiento.replace(day=1)
        cuotas.append(CuotaCREP(
            codigo_depositante=doc,
            nombre=f"{p.alumno.apellidos} {p.alumno.nombres}".strip(),
            documento=doc,
            fecha_emision=emision,
            fecha_vencimiento=p.fecha_vencimiento,
            monto=Decimal(str(p.monto)),
            mora=Decimal(str(p.mora or 0)),
        ))

    for c in (db.query(fin.CuotaExterna)
              .filter(fin.CuotaExterna.estado == "PENDIENTE").all()):
        cuotas.append(CuotaCREP(
            codigo_depositante=_doc(c.codigo_depositante),
            nombre=c.nombre,
            documento=_doc(c.documento),
            fecha_emision=c.fecha_emision,
            fecha_vencimiento=c.fecha_vencimiento,
            monto=Decimal(str(c.monto)),
            mora=Decimal(str(c.mora or 0)),
        ))

    # Mismo orden que traía el archivo del colegio: por alumno y vencimiento,
    # para que dos generaciones seguidas den archivos comparables.
    cuotas.sort(key=lambda c: (c.documento.zfill(12), c.fecha_vencimiento))
    return cuotas


def generar_archivo_crep(db: Session, fecha: Optional[dt.date] = None) -> Tuple[bytes, dict]:
    """Devuelve (contenido del archivo, resumen)."""
    cuotas = cuotas_para_crep(db)
    contenido = generar_crep(cuotas, fecha=fecha or dt.date.today())
    resumen = {
        "cuotas": len(cuotas),
        "alumnos": len({c.documento for c in cuotas}),
        "deuda": float(sum(c.monto for c in cuotas)),
        "mora": float(sum(c.mora for c in cuotas)),
        "total": float(sum(c.monto_minimo for c in cuotas)),
        "bytes": len(contenido),
    }
    return contenido, resumen


# ---------------------------------------------------------------------------
# Carga inicial: alinear la base con el CREP que el colegio usa hoy
# ---------------------------------------------------------------------------

def importar_crep_inicial(db: Session, datos: bytes, nombre: str = "CREP.txt",
                          simular: bool = True,
                          sincronizar_pagadas: bool = True) -> dict:
    """Toma el CREP vigente como foto de la deuda real y ajusta la base.

    Hace tres cosas, todas reversibles mientras `simular` esté activo:

      1. Da de alta como `cuota_externa` las cuotas de personas que no están
         en `alumno` (los arrastres de 2022-2025 de retirados y trasladados).
      2. Copia la mora que ya traiga el archivo a la cuota correspondiente.
      3. Si `sincronizar_pagadas`, marca como PAGADO lo que la base tiene
         pendiente pero el archivo ya no trae: son cuotas que se cobraron y
         se quitaron del Excel sin que nadie las tocara en el sistema.

    El paso 3 es el único que da por pagada una deuda sin ver el cobro, así
    que se informa cuota por cuota y conviene revisarlo antes de aplicarlo.
    """
    from app.modules.finance.crep import parsear_crep

    cabecera, cuotas = parsear_crep(datos)

    # Índice auxiliar por (documento, año, mes) para las fechas de fin de mes.
    # Aquí importa el doble: sin él una cuota que la base tiene al 30 y el
    # archivo trae al 31 se daría de alta OTRA VEZ como deuda histórica —se
    # cobraría dos veces— y la del sistema se marcaría como ya cobrada.
    def _fdm(doc: str, fecha: Optional[dt.date]):
        return (doc, fecha.year, fecha.month) if es_fin_de_mes(fecha) else None

    def _mes(doc: str, fecha: dt.date) -> Tuple[str, int, int]:
        return (doc, fecha.year, fecha.month)

    # --- lo que dice el archivo ---
    del_archivo: Dict[Tuple[str, dt.date], CuotaCREP] = {}
    archivo_fin_de_mes: Dict[Tuple[str, int, int], CuotaCREP] = {}
    archivo_por_mes: Dict[Tuple[str, int, int], List[CuotaCREP]] = {}
    for c in cuotas:
        del_archivo[(_doc(c.documento), c.fecha_vencimiento)] = c
        alias = _fdm(_doc(c.documento), c.fecha_vencimiento)
        if alias:
            archivo_fin_de_mes[alias] = c
        archivo_por_mes.setdefault(_mes(_doc(c.documento), c.fecha_vencimiento),
                                   []).append(c)

    # --- lo que dice la base ---
    pendientes = (db.query(fin.Pago).options(joinedload(fin.Pago.alumno))
                  .filter(fin.Pago.estado.in_(PENDIENTES)).all())
    de_la_base: Dict[Tuple[str, dt.date], object] = {}
    base_fin_de_mes: Dict[Tuple[str, int, int], object] = {}
    base_por_mes: Dict[Tuple[str, int, int], List] = {}
    for p in pendientes:
        if p.alumno and p.fecha_vencimiento and _doc(p.alumno.dni):
            doc = _doc(p.alumno.dni)
            de_la_base[(doc, p.fecha_vencimiento)] = p
            alias = _fdm(doc, p.fecha_vencimiento)
            if alias:
                base_fin_de_mes[alias] = p
            base_por_mes.setdefault(_mes(doc, p.fecha_vencimiento), []).append(p)

    def _unica_del_mes(clave_mes):
        """La cuota del mes, solo si hay exactamente una a cada lado.

        Con dos (abril y julio llevan pensión y módulo) no se puede saber cuál
        es cuál, y equivocarse aquí significa cobrar dos veces o dar por
        pagado lo que no está. En ese caso no se empareja nada.
        """
        del_mes = archivo_por_mes.get(clave_mes) or []
        en_base = base_por_mes.get(clave_mes) or []
        return en_base[0] if len(del_mes) == 1 and len(en_base) == 1 else None

    documentos_alumno = {_doc(d) for (d,) in db.query(Alumno.dni).all() if d}
    externas_ya = set()
    externas_fin_de_mes = set()
    externas_por_mes: Dict[Tuple[str, int, int], int] = {}
    for c in db.query(fin.CuotaExterna).all():
        externas_ya.add((_doc(c.documento), c.fecha_vencimiento))
        alias = _fdm(_doc(c.documento), c.fecha_vencimiento)
        if alias:
            externas_fin_de_mes.add(alias)
        k = _mes(_doc(c.documento), c.fecha_vencimiento)
        externas_por_mes[k] = externas_por_mes.get(k, 0) + 1

    nuevas_externas, mora_ajustada, sin_alumno_conocido = [], [], []
    monto_distinto = []
    emparejadas = set()          # marcas de las cuotas de la base ya cruzadas
    for clave, c in del_archivo.items():
        alias = _fdm(clave[0], clave[1])
        clave_mes = _mes(clave[0], clave[1])
        registro = de_la_base.get(clave)
        if registro is None and alias:
            registro = base_fin_de_mes.get(alias)
        if registro is None:
            registro = _unica_del_mes(clave_mes)
        if registro is not None:
            emparejadas.add(_marca(registro))
            # El importe NO se toca: es el precio de la cuota, no un dato del
            # banco. Si no coinciden hay que mirarlo a mano (una beca, un
            # convenio, media pensión), así que solo se informa.
            if abs(Decimal(str(c.monto)) - Decimal(str(registro.monto))) > TOLERANCIA:
                monto_distinto.append({
                    "dni": clave[0], "alumno": registro.alumno_nombre,
                    "concepto": registro.concepto,
                    "vencimiento": clave[1].isoformat(),
                    "en_el_sistema": float(registro.monto),
                    "en_el_archivo": float(c.monto)})
            # La mora se iguala a la del archivo en LOS DOS SENTIDOS. El archivo
            # es lo que el banco cobra de verdad: si la base tiene mora que el
            # BCP no está cobrando (pasa con los módulos, que no la llevan), hay
            # que quitarla, o el sistema mostraría al padre una deuda mayor que
            # la que le aparece en la ventanilla.
            del_archivo_mora = Decimal(str(c.mora))
            en_base = Decimal(str(registro.mora or 0))
            if del_archivo_mora != en_base:
                if not simular:
                    registro.mora = del_archivo_mora
                    registro.monto_total = Decimal(str(registro.monto)) + del_archivo_mora
                mora_ajustada.append({
                    "dni": clave[0], "alumno": registro.alumno_nombre,
                    "vencimiento": clave[1].isoformat(),
                    "antes": float(en_base), "ahora": float(del_archivo_mora)})
            continue

        # No hay cuota pendiente para esa deuda. Da igual que el alumno exista
        # o no: si no se guarda, deja de cobrarse en el BCP. Se registra como
        # deuda aparte y se avisa, para que alguien la revise.
        if clave[0] in documentos_alumno:
            sin_alumno_conocido.append({
                "dni": clave[0], "nombre": c.nombre,
                "vencimiento": clave[1].isoformat(), "monto": float(c.monto),
                "motivo": "El alumno está registrado pero no tiene esa cuota "
                          "pendiente; se guarda como deuda aparte para no perderla",
            })

        # Ya dada de alta: por la fecha exacta, por el mismo fin de mes, o
        # porque esa persona ya tiene una única deuda en ese mes y el archivo
        # trae también una sola. Duplicar aquí es cobrarle dos veces.
        ya_esta = (clave in externas_ya
                   or (alias and alias in externas_fin_de_mes)
                   or (len(archivo_por_mes.get(clave_mes) or []) == 1
                       and externas_por_mes.get(clave_mes, 0) == 1))
        if ya_esta:
            continue
        externas_ya.add(clave)
        if alias:
            externas_fin_de_mes.add(alias)
        externas_por_mes[clave_mes] = externas_por_mes.get(clave_mes, 0) + 1
        nuevas_externas.append(c)
        if not simular:
            db.add(fin.CuotaExterna(
                codigo_depositante=_doc(c.codigo_depositante),
                documento=_doc(c.documento),
                nombre=c.nombre[:120],
                concepto=f"Deuda anterior {c.fecha_vencimiento.strftime('%m/%Y')}",
                fecha_emision=c.fecha_emision,
                fecha_vencimiento=c.fecha_vencimiento,
                monto=Decimal(str(c.monto)),
                mora=Decimal(str(c.mora)),
                estado="PENDIENTE",
                origen=nombre[:120],
            ))

    # --- lo que la base cree pendiente y el archivo ya no trae ---
    ya_cobradas = []
    for clave, registro in de_la_base.items():
        if _marca(registro) in emparejadas:
            continue
        ya_cobradas.append({
            "id_pago": registro.id_pago,
            "dni": clave[0],
            "alumno": registro.alumno_nombre,
            "concepto": registro.concepto,
            "vencimiento": clave[1].isoformat(),
            "monto": float(registro.monto),
        })
        if sincronizar_pagadas and not simular:
            registro.estado = "PAGADO"
            registro.fecha_pago = dt.datetime.now()
            registro.json_respuesta_banco = json.dumps({
                "origen": "SINCRONIZACION_CREP",
                "archivo": nombre,
                "nota": "La cuota ya no figuraba en el archivo de cobranza del BCP",
            }, ensure_ascii=False)

    if not simular:
        db.commit()

    return {
        "simulado": simular,
        "archivo": nombre,
        "cuotas_en_el_archivo": len(del_archivo),
        "pendientes_en_la_base": len(de_la_base),
        "coinciden": len(emparejadas),
        "deuda_historica_creada": len(nuevas_externas),
        "deuda_historica_monto": float(sum(c.monto for c in nuevas_externas)),
        "mora_ajustada": len(mora_ajustada),
        "detalle_mora_ajustada": mora_ajustada[:200],
        "importes_que_no_cuadran": len(monto_distinto),
        "detalle_importes": monto_distinto[:200],
        "marcadas_como_pagadas": len(ya_cobradas) if sincronizar_pagadas else 0,
        "solo_en_el_archivo_con_alumno_conocido": sin_alumno_conocido[:200],
        "detalle_ya_cobradas": ya_cobradas[:200],
        "detalle_deuda_historica": [
            {"documento": _doc(c.documento), "nombre": c.nombre,
             "vencimiento": c.fecha_vencimiento.isoformat(),
             "monto": float(c.monto), "mora": float(c.mora)}
            for c in nuevas_externas[:200]],
    }


# ---------------------------------------------------------------------------
# Resolver a mano los cobros que no cuadraron
# ---------------------------------------------------------------------------
#
# Un cobro que no se pudo aplicar solo (SIN_COINCIDENCIA, AMBIGUO,
# MONTO_DISTINTO) necesita que alguien decida. Hay dos salidas:
#
#   · Aplicarlo a una cuota concreta -> esa cuota queda PAGADA y deja de salir
#     en el archivo de cobranza.
#   · Descartarlo -> el dinero no corresponde a ninguna deuda (un pago de más,
#     un depósito ajeno). No se toca ninguna cuota.
#
# En los dos casos el cobro sale de la bandeja de pendientes, con constancia
# de quién lo cerró y por qué.

def candidatos_para(db: Session, id_movimiento: int) -> dict:
    """Cuotas que podrían corresponder a un cobro sin aplicar.

    Busca por el documento del cobro en CUALQUIER vencimiento, no solo en el
    que traía el banco: el fallo más común es que el padre pague la cuota de
    un mes eligiendo en la ventanilla la de otro.
    """
    mov = (db.query(fin.MovimientoCobranza)
           .filter(fin.MovimientoCobranza.id_movimiento == id_movimiento).first())
    if not mov:
        raise ValueError("Ese cobro no existe")

    doc = _doc(mov.documento)
    pagado = Decimal(str(mov.monto_pagado or 0))

    propias = [p for p in db.query(fin.Pago)
               .options(joinedload(fin.Pago.alumno))
               .filter(fin.Pago.estado.in_(PENDIENTES)).all()
               if p.alumno and _doc(p.alumno.dni) == doc]

    externas = [c for c in db.query(fin.CuotaExterna)
                .filter(fin.CuotaExterna.estado == "PENDIENTE").all()
                if doc in {_doc(c.documento), _doc(c.codigo_depositante)}]

    lista = [{
        "tipo": "pago",
        "id": p.id_pago,
        "alumno": p.alumno_nombre,
        "concepto": p.concepto,
        "fecha_vencimiento": p.fecha_vencimiento.isoformat() if p.fecha_vencimiento else None,
        "monto": float(p.monto),
        "mora": float(p.mora or 0),
        "coincide_importe": abs(Decimal(str(p.monto)) - pagado) <= TOLERANCIA,
        "mismo_vencimiento": mismo_vencimiento(p.fecha_vencimiento,
                                               mov.fecha_vencimiento),
        "mismo_mes": _mismo_mes(p.fecha_vencimiento, mov.fecha_vencimiento),
    } for p in propias] + [{
        "tipo": "externa",
        "id": c.id_cuota_externa,
        "alumno": c.nombre,
        "concepto": c.concepto,
        "fecha_vencimiento": c.fecha_vencimiento.isoformat(),
        "monto": float(c.monto),
        "mora": float(c.mora or 0),
        "coincide_importe": abs(Decimal(str(c.monto)) - pagado) <= TOLERANCIA,
        "mismo_vencimiento": mismo_vencimiento(c.fecha_vencimiento,
                                               mov.fecha_vencimiento),
        "mismo_mes": _mismo_mes(c.fecha_vencimiento, mov.fecha_vencimiento),
    } for c in externas]

    # Primero las que cuadran en fecha, luego las del mismo mes (diciembre no
    # cae en la regla de fin de mes) y luego las que cuadran en importe.
    lista.sort(key=lambda x: (not x["mismo_vencimiento"], not x["mismo_mes"],
                              not x["coincide_importe"],
                              x["fecha_vencimiento"] or ""))
    return {
        "movimiento": {
            "id_movimiento": mov.id_movimiento,
            "documento": mov.documento,
            "fecha_pago": mov.fecha_pago.isoformat() if mov.fecha_pago else None,
            "fecha_vencimiento": mov.fecha_vencimiento.isoformat() if mov.fecha_vencimiento else None,
            "monto_pagado": float(mov.monto_pagado or 0),
            "monto_total": float(mov.monto_total or 0),
            "operacion": mov.operacion,
            "resultado": mov.resultado,
            "estado": mov.estado,
            "detalle": mov.detalle,
        },
        "candidatos": lista,
    }


def resolver_movimiento(db: Session, id_movimiento: int, accion: str,
                        id_pago: Optional[int] = None,
                        id_cuota_externa: Optional[int] = None,
                        nota: Optional[str] = None,
                        id_usuario: Optional[int] = None) -> dict:
    """Cierra a mano un cobro que no se pudo aplicar solo.

    `accion` = 'aplicar'   -> marca PAGADA la cuota indicada
               'descartar' -> no toca ninguna cuota, solo cierra el aviso

    Al aplicar se usan los datos reales del cobro (la fecha y el número de
    operación del banco), no la fecha de hoy: si el padre pagó el 10 y esto se
    revisa el 20, en el sistema tiene que quedar el 10.
    """
    mov = (db.query(fin.MovimientoCobranza)
           .filter(fin.MovimientoCobranza.id_movimiento == id_movimiento).first())
    if not mov:
        raise ValueError("Ese cobro no existe")
    if mov.estado != "PENDIENTE_REVISION":
        raise ValueError(f"Ese cobro ya figura como {mov.estado.lower()}: "
                         f"no se puede volver a resolver")

    accion = (accion or "").lower()
    if accion not in ("aplicar", "descartar"):
        raise ValueError("La acción debe ser 'aplicar' o 'descartar'")

    cuota = None
    if accion == "aplicar":
        if id_pago:
            cuota = db.query(fin.Pago).filter(fin.Pago.id_pago == id_pago).first()
        elif id_cuota_externa:
            cuota = (db.query(fin.CuotaExterna)
                     .filter(fin.CuotaExterna.id_cuota_externa == id_cuota_externa).first())
        if cuota is None:
            raise ValueError("Hay que indicar a qué cuota se aplica el cobro")
        if cuota.estado == "PAGADO":
            raise ValueError("Esa cuota ya figura como pagada")

        cuota.estado = "PAGADO"
        cuota.fecha_pago = dt.datetime.combine(
            mov.fecha_pago or dt.date.today(), dt.time.min)
        cuota.codigo_operacion_bcp = mov.operacion or "MANUAL-CONCILIACION"
        if isinstance(cuota, fin.Pago):
            cuota.json_respuesta_banco = json.dumps({
                "origen": "RESOLUCION_MANUAL",
                "id_movimiento": mov.id_movimiento,
                "resultado_automatico": mov.resultado,
                "operacion": mov.operacion,
                "monto_pagado": str(mov.monto_pagado),
                "fecha_pago": mov.fecha_pago.isoformat() if mov.fecha_pago else None,
                "nota": nota,
            }, ensure_ascii=False)
            mov.id_pago = cuota.id_pago
        else:
            mov.id_cuota_externa = cuota.id_cuota_externa

    mov.estado = "RESUELTO" if accion == "aplicar" else "DESCARTADO"
    mov.nota = (nota or ("Aplicado a mano desde la conciliación"
                         if accion == "aplicar" else "Descartado sin aplicar"))[:255]
    mov.id_usuario_resolucion = id_usuario
    mov.fecha_resolucion = dt.datetime.now()
    db.commit()

    return {
        "id_movimiento": mov.id_movimiento,
        "estado": mov.estado,
        "nota": mov.nota,
        "cuota_afectada": None if cuota is None else {
            "tipo": "pago" if isinstance(cuota, fin.Pago) else "externa",
            "id": getattr(cuota, "id_pago", None) or getattr(cuota, "id_cuota_externa", None),
            "concepto": getattr(cuota, "concepto", None),
            "monto": float(cuota.monto),
            "sale_del_crep": True,
        },
    }


def pendientes_de_revision(db: Session, limite: int = 200) -> List[dict]:
    """Cobros que el sistema no pudo aplicar y nadie ha atendido todavía."""
    filas = (db.query(fin.MovimientoCobranza, fin.LoteCobranza.nombre_archivo)
             .join(fin.LoteCobranza,
                   fin.LoteCobranza.id_lote == fin.MovimientoCobranza.id_lote)
             .filter(fin.MovimientoCobranza.estado == "PENDIENTE_REVISION")
             .order_by(fin.MovimientoCobranza.fecha_pago.asc(),
                       fin.MovimientoCobranza.id_movimiento.asc())
             .limit(limite).all())

    # Los nombres se resuelven en bloque: una consulta, no una por fila.
    documentos = {_doc(m.documento) for m, _ in filas}
    nombres: Dict[str, str] = {}
    if documentos:
        for dni, ap, no in db.query(Alumno.dni, Alumno.apellidos, Alumno.nombres).all():
            d = _doc(dni)
            if d in documentos:
                nombres[d] = f"{ap or ''}, {no or ''}".strip(", ")

    return [{
        "id_movimiento": m.id_movimiento,
        "archivo": archivo,
        "documento": m.documento,
        "alumno": nombres.get(_doc(m.documento)),
        "fecha_pago": m.fecha_pago.isoformat() if m.fecha_pago else None,
        "fecha_vencimiento": m.fecha_vencimiento.isoformat() if m.fecha_vencimiento else None,
        "monto_pagado": float(m.monto_pagado or 0),
        "monto_total": float(m.monto_total or 0),
        "operacion": m.operacion,
        "resultado": m.resultado,
        "detalle": m.detalle,
    } for m, archivo in filas]
