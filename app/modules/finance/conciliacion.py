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

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.modules.finance import models as fin
from app.modules.finance.crep import (
    CabeceraCREP, CuotaCREP, ErrorFormatoBCP, PagoBCP,
    generar_crep, parsear_reporte_cobros,
)
from app.modules.users.alumno.models import Alumno
from app.modules.users.relacion_familiar.models import RelacionFamiliar

# Estados de `pago` que representan una deuda viva: son las que viajan al BCP.
PENDIENTES = ("PENDIENTE", "VENCIDO")
TOLERANCIA = Decimal("0.01")

# La puesta en marcha se anota como un lote con este estado. No es un reporte
# de cobros y no debe salir en el historial de reportes ni contar como uno.
ESTADO_LOTE_INICIAL = "INICIAL"

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

class CuotaPagada:
    """Copia ligera de una cuota YA COBRADA, solo para poder reconocerla.

    No es una fila de la base que se vaya a modificar: sirve para contestar
    "esto ya estaba pagado" cuando un cobro del banco no cruza con ninguna
    deuda viva. Se guarda una copia mínima en vez del objeto entero porque son
    casi diez mil y solo hacen falta cinco campos.
    """

    __slots__ = ("id_pago", "id_cuota_externa", "concepto", "monto",
                 "fecha_vencimiento", "fecha_pago", "operacion", "del_crep")

    def __init__(self, *, id_pago=None, id_cuota_externa=None, concepto=None,
                 monto=None, fecha_vencimiento=None, fecha_pago=None,
                 operacion=None, del_crep=False):
        self.id_pago = id_pago
        self.id_cuota_externa = id_cuota_externa
        self.concepto = concepto
        self.monto = monto
        self.fecha_vencimiento = fecha_vencimiento
        self.fecha_pago = fecha_pago
        self.operacion = operacion
        # True si se dio por pagada en la importación inicial, sin ver el cobro:
        # cuando llega el reporte del banco, ese cobro la CONFIRMA. Si en cambio
        # ya se había aplicado un cobro real y ahora llega otro distinto, eso sí
        # hay que mirarlo.
        self.del_crep = del_crep


class _Cajones:
    """Los tres niveles con los que se busca una cuota, de estricto a laxo."""

    def __init__(self):
        # 1) La fecha exacta.
        self.por_clave: Dict[Tuple[str, dt.date], List] = {}
        # 2) Solo las que vencen a fin de mes, para cruzar el 30 del sistema
        #    con el 31 del banco. Se consulta si la fecha exacta no da nada.
        self.por_fin_de_mes: Dict[Tuple[str, int, int], List] = {}
        # 3) Todas las del alumno en ese mes, sin mirar el día. Último recurso,
        #    y solo vale cuando hay una sola: así se resuelve diciembre, cuya
        #    fecha cambia de un año a otro.
        self.por_mes: Dict[Tuple[str, int, int], List] = {}


class IndiceDeudas:
    """Las cuotas indexadas por (documento, vencimiento).

    Se arma una sola vez por proceso y se va actualizando en memoria conforme
    se aplican los pagos, para no consultar la base por cada línea del reporte.

    Hay DOS juegos de índices: las cuotas vivas, que son a las que se puede
    aplicar un cobro, y las ya pagadas, que solo se consultan cuando no hay
    ninguna viva. Sin las segundas, un cobro de algo que el sistema ya daba por
    cobrado salía como "sin coincidencia", que es lo mismo que dice un depósito
    de un desconocido, y no hay forma de distinguirlos.
    """

    def __init__(self, db: Session):
        self.db = db
        self.vivas = _Cajones()
        self.pagadas = _Cajones()
        # Dónde quedó cada cuota viva, para poder sacarla de todos los índices
        # cuando se aplica un pago.
        self._ubicaciones: Dict[Tuple[str, Optional[int]], List[Tuple[dict, tuple]]] = {}
        # Documento -> nombre, de TODOS los alumnos, no solo de los que deben.
        # Sirve para poder decir quién pagó aunque el cobro no cruce con
        # ninguna cuota: sin esto la tabla mostraría un DNI suelto.
        self.nombres: Dict[str, str] = {}
        self._cargar_nombres()
        self._cargar_pagos()
        self._cargar_externas()
        self._cargar_pagadas()

    def _añadir(self, clave, registro, cajones: Optional[_Cajones] = None,
                rastrear: bool = True):
        cajones = cajones or self.vivas
        doc, venc = clave
        if venc is None:
            return
        cajones.por_clave.setdefault(clave, []).append(registro)
        ubicaciones = self._ubicaciones.setdefault(_marca(registro), []) if rastrear else None
        if ubicaciones is not None:
            ubicaciones.append((cajones.por_clave, clave))
        if es_fin_de_mes(venc):
            fdm = (doc, venc.year, venc.month)
            cajones.por_fin_de_mes.setdefault(fdm, []).append(registro)
            if ubicaciones is not None:
                ubicaciones.append((cajones.por_fin_de_mes, fdm))
        mes = (doc, venc.year, venc.month)
        cajones.por_mes.setdefault(mes, []).append(registro)
        if ubicaciones is not None:
            ubicaciones.append((cajones.por_mes, mes))

    def quitar(self, registro) -> None:
        """Saca una cuota ya cobrada de todos los índices.

        Sin esto, dos líneas del mismo reporte podrían aplicarse a la misma
        cuota, o la segunda saldría como AMBIGUO sin serlo.
        """
        for indice, clave in self._ubicaciones.pop(_marca(registro), []):
            lista = indice.get(clave)
            if lista and registro in lista:
                lista.remove(registro)

    def dar_por_cobrada(self, registro, pago: PagoBCP) -> None:
        """Mueve una cuota de las vivas a las pagadas, dentro de esta pasada.

        Hay que hacer las dos cosas. Quitarla de las vivas evita aplicarle un
        segundo cobro; meterla en las pagadas es lo que permite reconocer ese
        segundo cobro como repetido en vez de darlo por huérfano. Sin lo
        segundo, subir el reporte de media mañana y el del cierre en la MISMA
        carga sacaba los cobros comunes como «sin coincidencia».

        Se llama también al simular: no toca la base —solo estas listas en
        memoria— y es lo que hace que la simulación cuente lo mismo que va a
        pasar de verdad.
        """
        self.quitar(registro)
        doc = ""
        if isinstance(registro, fin.Pago):
            doc = _doc(registro.alumno.dni) if registro.alumno else ""
        else:
            doc = _doc(getattr(registro, "documento", None))
        if not doc or not registro.fecha_vencimiento:
            return
        self._añadir(
            (doc, registro.fecha_vencimiento),
            CuotaPagada(
                id_pago=getattr(registro, "id_pago", None),
                id_cuota_externa=getattr(registro, "id_cuota_externa", None),
                concepto=getattr(registro, "concepto", None),
                monto=registro.monto,
                fecha_vencimiento=registro.fecha_vencimiento,
                fecha_pago=pago.fecha_pago,
                operacion=pago.operacion,
                del_crep=False),
            cajones=self.pagadas, rastrear=False)

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

    def _cargar_pagadas(self):
        """Las cuotas ya cobradas, para reconocer un cobro repetido.

        Se traen solo las columnas que hacen falta —son casi diez mil filas— y
        no se rastrean sus ubicaciones: de aquí no se quita nada nunca, porque
        no se les puede aplicar ningún cobro.
        """
        from app.modules.users.alumno.models import Alumno as _Al

        for f in (self.db.query(fin.Pago.id_pago, fin.Pago.concepto, fin.Pago.monto,
                                fin.Pago.fecha_vencimiento, fin.Pago.fecha_pago,
                                fin.Pago.codigo_operacion_bcp,
                                fin.Pago.json_respuesta_banco, _Al.dni)
                  .join(_Al, _Al.id_alumno == fin.Pago.id_alumno)
                  .filter(fin.Pago.estado == "PAGADO").all()):
            doc = _doc(f.dni)
            if not doc or not f.fecha_vencimiento:
                continue
            self._añadir(
                (doc, f.fecha_vencimiento),
                CuotaPagada(id_pago=f.id_pago, concepto=f.concepto, monto=f.monto,
                            fecha_vencimiento=f.fecha_vencimiento,
                            fecha_pago=f.fecha_pago,
                            operacion=f.codigo_operacion_bcp,
                            del_crep="SINCRONIZACION_CREP" in (f.json_respuesta_banco or "")),
                cajones=self.pagadas, rastrear=False)

        for c in (self.db.query(fin.CuotaExterna)
                  .filter(fin.CuotaExterna.estado == "PAGADO").all()):
            for doc in {_doc(c.documento), _doc(c.codigo_depositante)}:
                if doc:
                    self._añadir(
                        (doc, c.fecha_vencimiento),
                        CuotaPagada(id_cuota_externa=c.id_cuota_externa,
                                    concepto=c.concepto, monto=c.monto,
                                    fecha_vencimiento=c.fecha_vencimiento,
                                    fecha_pago=c.fecha_pago,
                                    operacion=c.codigo_operacion_bcp),
                        cajones=self.pagadas, rastrear=False)

    def _buscar_en(self, cajones: _Cajones, pago: PagoBCP) -> Tuple[List, Optional[str]]:
        """Cuotas de esos cajones que encajan con el cobro, sin repetir.

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
            recoger(cajones.por_clave.get((_doc(doc), venc)))
        if encontrados:
            return encontrados, None

        # 2) El mismo fin de mes: el 30 del sistema y el 31 del banco.
        if es_fin_de_mes(venc):
            for doc in pago.documentos:
                recoger(cajones.por_fin_de_mes.get((_doc(doc), venc.year, venc.month)))
            if encontrados:
                return encontrados, "fin_de_mes"

        # 3) El mismo mes, pase lo que pase con el día. Solo se acepta si en
        #    ese mes hay UNA cuota: con dos no hay forma de saber cuál es y se
        #    devuelven las dos, que es lo que hace que salga como AMBIGUO y
        #    acabe en la bandeja para que alguien decida.
        for doc in pago.documentos:
            recoger(cajones.por_mes.get((_doc(doc), venc.year, venc.month)))
        return (encontrados, "mismo_mes") if encontrados else ([], None)

    def buscar(self, pago: PagoBCP) -> Tuple[List, Optional[str]]:
        """Cuotas VIVAS que encajan con ese cobro."""
        return self._buscar_en(self.vivas, pago)

    def buscar_pagada(self, pago: PagoBCP) -> List[CuotaPagada]:
        """Cuotas YA COBRADAS que encajan. Solo para explicar, no para aplicar."""
        encontradas, _ = self._buscar_en(self.pagadas, pago)
        return encontradas


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


def _explicar_ya_cobrada(ya: "CuotaPagada", pago: PagoBCP) -> Tuple[str, str, Optional[str]]:
    """Por qué un cobro no encontró deuda: la cuota ya estaba cobrada.

    Devuelve (resultado, detalle, cierre). `cierre` a None significa que el
    caso va a la bandeja para que alguien lo mire. Hay tres situaciones y solo
    una necesita a una persona:

      · Es literalmente el mismo cobro (misma operación) -> REPETIDO. Pasa al
        subir el reporte de media mañana y el del cierre, que trae otra vez los
        de la mañana. No hay nada que hacer.
      · La cuota se dio por pagada en la puesta en marcha, sin ver el cobro, y
        ahora llega el cobro de verdad -> lo confirma. Tampoco hay nada que hacer.
      · Ya se había aplicado OTRO cobro distinto a esa cuota -> puede ser un
        pago doble, y eso sí hay que mirarlo.
    """
    cuando = f" el {ya.fecha_pago:%d/%m/%Y}" if ya.fecha_pago else ""

    if ya.operacion and pago.operacion and str(ya.operacion) == str(pago.operacion):
        return ("REPETIDO",
                f"Este mismo cobro (operación {pago.operacion}) ya se había "
                f"aplicado{cuando} a «{ya.concepto}». No se hace nada.",
                "El mismo cobro ya estaba aplicado")

    if ya.del_crep:
        return ("YA_PAGADO",
                f"«{ya.concepto}» ya figuraba pagada por la puesta en marcha, sin "
                f"ver el cobro. Este reporte lo confirma: no hay nada que corregir.",
                "El banco confirma un pago que ya estaba registrado")

    return ("YA_PAGADO",
            f"«{ya.concepto}» ya figuraba pagada{cuando}"
            f"{f' con la operación {ya.operacion}' if ya.operacion else ''}. "
            f"Este cobro es otro distinto: revisa si se pagó dos veces.",
            None)


def _misma_por_importe(candidatos: List, pago: PagoBCP):
    """La cuota cuyo importe cuadra clavado con lo que se pagó.

    Se usa sobre cuotas YA COBRADAS, para reconocer de cuál era un cobro que no
    encajó con ninguna deuda viva. Con varias que cuadren no se elige ninguna:
    decir "es esta" sin estar seguro sería peor que no decir nada.
    """
    cuadran = [c for c in candidatos
               if abs(pago.monto_pagado - Decimal(str(c.monto or 0))) <= TOLERANCIA]
    return cuadran[0] if len(cuadran) == 1 else None


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
              "REPETIDO": 0, "YA_PAGADO": 0, "MONTO_DISTINTO": 0, "AMBIGUO": 0}
    detalle_cobros: List[dict] = []

    for pago in reporte.pagos:
        registro, resultado, detalle = None, None, None
        candidatos, como = [], None
        # Nota automática con la que se cierra el cobro sin que nadie lo mire.
        # Si queda en None, el cobro va a la bandeja de revisión.
        cierre: Optional[str] = None

        if pago.extornado:
            resultado = "EXTORNADO"
            detalle = "El banco devolvió el dinero: la deuda sigue viva"
            cierre = "Extornado por el banco: el dinero se devolvió"
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
                # Antes de darlo por huérfano se mira si esa cuota ya estaba
                # cobrada. Es lo más común después de la puesta en marcha: la
                # importación inicial dio por pagadas las cuotas que el CREP ya
                # no traía, y días después llega el reporte del banco con esos
                # mismos cobros. Sin esto salían como "sin coincidencia", igual
                # que un depósito de un desconocido, y no había cómo separarlos.
                pagadas = indice.buscar_pagada(pago)
                if pagadas:
                    resultado, detalle, cierre = _explicar_ya_cobrada(pagadas[0], pago)
                else:
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
                    # Antes de cantar "monto distinto": si el importe cuadra
                    # clavado con una cuota YA COBRADA de esa misma fecha, lo
                    # que pasa es que el cobro es de esa. Ocurre siempre que el
                    # alumno debe dos cosas el mismo día —la pensión y el
                    # módulo— y una ya estaba pagada: queda la otra de
                    # candidata y sus importes no tienen por qué coincidir.
                    gemela = _misma_por_importe(indice.buscar_pagada(pago), pago)
                    if gemela is not None:
                        resultado, detalle, cierre = _explicar_ya_cobrada(gemela, pago)
                    else:
                        resultado = "MONTO_DISTINTO"
                        detalle = (f"Pagó S/ {pago.monto_pagado} y la cuota es de "
                                   f"S/ {esperado}. No se marcó como pagada.{aviso_fecha}")
                    registro = None
                else:
                    resultado = "APLICADO"
                    detalle = aviso_fecha.strip() or None
                    cierre = "Aplicado automáticamente al conciliar"
                    if not simular:
                        _marcar_pagado(registro, pago)
                    # El índice se actualiza SIEMPRE, también al simular: es
                    # solo memoria, y sin ello la simulación contaría dos veces
                    # un cobro que aparece en dos archivos de la misma carga.
                    indice.dar_por_cobrada(registro, pago)

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
                # `cierre` lo pone arriba cada caso que no necesita que nadie
                # lo mire: el aplicado, el extornado (lo decidió el banco), el
                # repetido y el que solo confirma un pago ya registrado. Lo que
                # se queda sin `cierre` va a la bandeja de revisión.
                estado=("RESUELTO" if resultado == "APLICADO"
                        else "DESCARTADO" if cierre
                        else "PENDIENTE_REVISION"),
                nota=cierre,
                fecha_resolucion=dt.datetime.now() if cierre else None,
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
    #    La puesta en marcha no entra: es otro tipo de archivo y no debe hacer
    #    que un reporte de cobros parezca ya procesado.
    ya = {h for (h,) in db.query(fin.LoteCobranza.huella)
          .filter(fin.LoteCobranza.estado != ESTADO_LOTE_INICIAL).all()}
    resumen, indice = [], IndiceDeudas(db)
    cobros: List[dict] = []
    total = {"APLICADO": 0, "EXTORNADO": 0, "SIN_COINCIDENCIA": 0,
             "REPETIDO": 0, "YA_PAGADO": 0, "MONTO_DISTINTO": 0, "AMBIGUO": 0}

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

def estado_puesta_en_marcha(db: Session) -> Optional[dict]:
    """Si la importación inicial ya se hizo: cuándo, con qué y cómo se sabe.

    Lo normal es que esté anotada como un lote INICIAL. Pero las que se hicieron
    antes de que existiera esa anotación no dejaron el apunte, así que si no hay
    lote se busca el RASTRO que deja en los datos:

      · cuotas marcadas como pagadas por la sincronización del CREP, y
      · deuda histórica dada de alta desde un archivo.

    Ninguna de las dos cosas aparece por otro camino, así que si están, la
    puesta en marcha se hizo. Se devuelve `registrada=False` para poder decir
    que se dedujo en vez de afirmar una fecha exacta que no se guardó.
    """
    lote = (db.query(fin.LoteCobranza)
            .filter(fin.LoteCobranza.estado == ESTADO_LOTE_INICIAL)
            .order_by(fin.LoteCobranza.id_lote.desc()).first())
    if lote is not None:
        return {
            "archivo": lote.nombre_archivo,
            "fecha": lote.fecha_carga.isoformat() if lote.fecha_carga else None,
            "cuotas": lote.registros_declarados,
            "cuadraron": lote.aplicados,
            "deuda_historica": lote.sin_coincidencia,
            "registrada": True,
        }

    sincronizadas, desde = (
        db.query(func.count(fin.Pago.id_pago), func.min(fin.Pago.fecha_pago))
        .filter(fin.Pago.estado == "PAGADO",
                fin.Pago.json_respuesta_banco.like("%SINCRONIZACION_CREP%")).one())
    externas = (db.query(func.count(fin.CuotaExterna.id_cuota_externa))
                .filter(fin.CuotaExterna.origen.isnot(None)).scalar() or 0)

    if not sincronizadas and not externas:
        return None

    origen = (db.query(fin.CuotaExterna.origen)
              .filter(fin.CuotaExterna.origen.isnot(None)).first())
    return {
        "archivo": origen[0] if origen else None,
        "fecha": desde.isoformat() if desde else None,
        "cuotas": None,
        "cuadraron": None,
        "deuda_historica": externas,
        # Se dedujo del rastro, no de un apunte: la pantalla lo dice así.
        "registrada": False,
        "sincronizadas": int(sincronizadas or 0),
    }


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

    # ¿Ya se hizo antes? La puesta en marcha es de una sola vez, así que queda
    # anotada como un lote propio (estado INICIAL). Sin esa anotación no había
    # forma de saber si estaba hecha: la pantalla se veía igual antes y después.
    previa = estado_puesta_en_marcha(db)
    huella = _huella(datos)
    mismo_archivo = bool(
        previa and previa["registrada"]
        and db.query(fin.LoteCobranza)
        .filter(fin.LoteCobranza.estado == ESTADO_LOTE_INICIAL,
                fin.LoteCobranza.huella == huella).first())

    if not simular and mismo_archivo:
        raise ValueError(
            "Este mismo archivo ya se importó como puesta en marcha"
            + (f" el {dt.datetime.fromisoformat(previa['fecha']):%d/%m/%Y}"
               if previa.get("fecha") else "")
            + ". Volver a aplicarlo no cambiaría nada.")

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
                    # El identificador viaja para poder decidir desde la propia
                    # pantalla, sin ir a buscar la cuota a mano en Pagos.
                    "tipo": "pago" if isinstance(registro, fin.Pago) else "externa",
                    "id": (getattr(registro, "id_pago", None)
                           or getattr(registro, "id_cuota_externa", None)),
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
        # Queda constancia de que la puesta en marcha se hizo, con qué archivo
        # y cuándo. Es lo que permite que la pantalla lo diga en vez de invitar
        # a repetirla.
        db.add(fin.LoteCobranza(
            nombre_archivo=nombre[:255],
            # El CREP no lleva fecha de proceso en la cabecera (solo la llevan
            # los reportes de cobros); queda la fecha_carga, que es cuándo se
            # aplicó, que es justo lo que hay que poder enseñar.
            fecha_reporte=None,
            registros_declarados=len(cuotas),
            monto_declarado=sum((Decimal(str(c.monto)) for c in cuotas), Decimal("0")),
            huella=huella,
            estado=ESTADO_LOTE_INICIAL,
            aplicados=len(emparejadas),
            sin_coincidencia=len(nuevas_externas),
        ))
        db.commit()

    return {
        "simulado": simular,
        "archivo": nombre,
        "ya_se_habia_hecho": None if previa is None else {
            **previa, "mismo_archivo": mismo_archivo,
        },
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


def ajustar_importe(db: Session, tipo: str, id_cuota: int,
                    monto: Decimal) -> dict:
    """Pone en una cuota pendiente el importe que trae el archivo del BCP.

    Es la ÚNICA vía por la que la conciliación cambia un precio, y solo ocurre
    pulsando el botón de esa fila. El proceso automático nunca lo toca: el
    importe es una decisión del colegio —una beca, media pensión, un convenio—
    y no un dato del banco, así que nadie puede adivinar cuál de los dos manda.

    A diferencia del resto de la importación inicial, esto NO tiene simulación:
    se llama cuando alguien ya miró la fila y decidió. Escribe y devuelve cómo
    quedó, para poder enseñarlo.
    """
    tipo = (tipo or "").lower()
    if tipo not in ("pago", "externa"):
        raise ValueError("El tipo de cuota debe ser 'pago' o 'externa'")

    monto = Decimal(str(monto))
    if monto <= 0:
        raise ValueError("El importe tiene que ser mayor que cero")

    if tipo == "pago":
        cuota = (db.query(fin.Pago).options(joinedload(fin.Pago.alumno))
                 .filter(fin.Pago.id_pago == id_cuota).first())
        estados_vivos = PENDIENTES
    else:
        cuota = (db.query(fin.CuotaExterna)
                 .filter(fin.CuotaExterna.id_cuota_externa == id_cuota).first())
        estados_vivos = ("PENDIENTE",)

    if cuota is None:
        raise ValueError("Esa cuota no existe")
    if cuota.estado not in estados_vivos:
        # Cambiar el precio de algo ya cobrado descuadraría lo recaudado.
        raise ValueError(f"Esa cuota figura como {cuota.estado.lower()}: "
                         f"su importe ya no se puede cambiar desde aquí")

    antes = Decimal(str(cuota.monto))
    mora = Decimal(str(cuota.mora or 0))
    cuota.monto = monto
    cuota.monto_total = monto + mora
    db.commit()

    return {
        "tipo": tipo,
        "id": id_cuota,
        "alumno": (cuota.alumno_nombre if isinstance(cuota, fin.Pago)
                   else cuota.nombre),
        "concepto": cuota.concepto,
        "antes": float(antes),
        "ahora": float(monto),
        "mora": float(mora),
        "nuevo_total": float(monto + mora),
    }


# ---------------------------------------------------------------------------
# Reporte de deudores
# ---------------------------------------------------------------------------
#
# Es lo que el colegio sacaba a mano del .xlsm: quién debe, cuánto y desde
# cuándo, con el desglose por sección para poder repartirlo entre los tutores.
#
# Se arma con TRES consultas, no una por alumno: las cuotas vivas, las
# matrículas del año (que son las que dicen en qué sección está cada uno) y la
# deuda anterior. Con ~500 alumnos y varias cuotas cada uno, ir alumno por
# alumno serían miles de viajes a la base.

def _seccion_de_cada_alumno(db: Session, anio: Optional[str]) -> Tuple[Dict[int, dict], Optional[str]]:
    """id_alumno -> dónde está matriculado este año. También devuelve el año.

    La sección sale de la MATRÍCULA, no del pago: una pensión de marzo se
    cobra igual aunque al alumno lo hayan cambiado de sección en mayo, y el
    tutor que tiene que reclamarla es el de ahora.
    """
    from app.modules.academic.models import AnioEscolar, Grado, Nivel, Seccion
    from app.modules.enrollment.models import Matricula

    if not anio:
        activo = (db.query(AnioEscolar).filter(AnioEscolar.activo.is_(True))
                  .order_by(AnioEscolar.id_anio_escolar.desc()).first())
        anio = activo.id_anio_escolar if activo else None
    if not anio:
        return {}, None

    filas = (db.query(Matricula.id_alumno, Seccion.nombre.label("seccion"),
                      Grado.nombre.label("grado"), Grado.orden.label("orden_grado"),
                      Nivel.nombre.label("nivel"))
             .join(Seccion, Seccion.id_seccion == Matricula.id_seccion)
             .join(Grado, Grado.id_grado == Seccion.id_grado)
             .join(Nivel, Nivel.id_nivel == Grado.id_nivel)
             .filter(Matricula.id_anio_escolar == anio).all())

    return ({f.id_alumno: {"nivel": f.nivel, "grado": f.grado,
                           "seccion": f.seccion, "orden_grado": f.orden_grado or 0}
             for f in filas}, anio)


def reporte_deudores(db: Session, anio: Optional[str] = None,
                     hasta: Optional[dt.date] = None) -> dict:
    """Todo el que debe algo, con su desglose y agrupado por sección.

    Solo incluye a los alumnos que efectivamente tienen deuda vencida o exigible
    hasta la fecha de corte (por defecto hoy). Excluye a quienes tienen sus
    pagos al día y no deben ninguna cuota vencida.
    """
    hoy = dt.date.today()
    limite = hasta or hoy

    ubicacion, anio = _seccion_de_cada_alumno(db, anio)

    # --- información de apoderados y teléfonos ---
    relaciones = (
        db.query(RelacionFamiliar)
        .options(joinedload(RelacionFamiliar.familiar))
        .all()
    )
    info_apoderados: Dict[int, dict] = {}
    for rel in relaciones:
        f = rel.familiar
        if not f:
            continue
        id_al = rel.id_alumno
        tel = (f.telefono or "").strip()
        nom = (str(f.apellidos or "") + ", " + str(f.nombres or "")).strip(", ")
        parentesco = (rel.tipo_parentesco or "").strip()
        if id_al in info_apoderados:
            if not info_apoderados[id_al]["telefono"] and tel:
                info_apoderados[id_al]["telefono"] = tel
                info_apoderados[id_al]["apoderado"] = nom
                info_apoderados[id_al]["parentesco"] = parentesco
            elif tel and tel not in info_apoderados[id_al]["telefono"]:
                info_apoderados[id_al]["telefono"] += f" / {tel}"
        else:
            info_apoderados[id_al] = {
                "telefono": tel,
                "apoderado": nom,
                "parentesco": parentesco,
            }

    # --- cuotas vivas de alumnos exigibles a la fecha de corte ---
    q = (db.query(fin.Pago).options(joinedload(fin.Pago.alumno))
         .filter(fin.Pago.estado.in_(PENDIENTES))
         .filter(fin.Pago.fecha_vencimiento <= limite))

    SIN_SECCION = {"nivel": "—", "grado": "—", "seccion": "SIN SECCIÓN", "orden_grado": 999}
    deudores: Dict[int, dict] = {}

    for p in q.all():
        if not p.alumno:
            continue                        # cuota huérfana: no hay a quién cobrarle
        monto = Decimal(str(p.monto or 0))
        mora = Decimal(str(p.mora or 0))
        total = monto + mora
        if total <= Decimal("0"):
            continue                        # registro sin saldo deudor

        donde = ubicacion.get(p.alumno.id_alumno, SIN_SECCION)
        fam = info_apoderados.get(p.alumno.id_alumno, {"telefono": "", "apoderado": "", "parentesco": ""})

        d = deudores.setdefault(p.alumno.id_alumno, {
            "dni": p.alumno.dni or "",
            "alumno": (str(p.alumno.apellidos or "") + ", " + str(p.alumno.nombres or "")).strip(", "),
            "apoderado": fam["apoderado"],
            "telefono": fam["telefono"],
            "parentesco": fam["parentesco"],
            **donde,
            "cuotas": [],
        })
        vencida = bool(p.fecha_vencimiento and p.fecha_vencimiento < hoy)
        d["cuotas"].append({
            "concepto": p.concepto or "",
            "vencimiento": p.fecha_vencimiento,
            "monto": monto,
            "mora": mora,
            "total": total,
            "vencida": vencida,
            "dias_atraso": (hoy - p.fecha_vencimiento).days if vencida else 0,
        })

    # --- totales de cada alumno (solo alumnos con deuda real > 0) ---
    deudores_activos: Dict[int, dict] = {}
    for id_al, d in deudores.items():
        if not d["cuotas"]:
            continue
        # Lo más antiguo primero: es el orden en que se reclama.
        d["cuotas"].sort(key=lambda c: (c["vencimiento"] or dt.date.max, c["concepto"]))
        vencidas = [c for c in d["cuotas"] if c["vencida"]]
        d["num_cuotas"] = len(d["cuotas"])
        d["num_vencidas"] = len(vencidas)
        d["deuda"] = sum((c["monto"] for c in d["cuotas"]), Decimal("0"))
        d["mora"] = sum((c["mora"] for c in d["cuotas"]), Decimal("0"))
        d["total"] = d["deuda"] + d["mora"]
        if d["total"] <= Decimal("0"):
            continue                        # sin deuda real
        d["vencido"] = sum((c["total"] for c in vencidas), Decimal("0"))
        d["dias_atraso"] = max((c["dias_atraso"] for c in vencidas), default=0)
        d["desde"] = vencidas[0]["vencimiento"] if vencidas else None
        deudores_activos[id_al] = d

    lista = sorted(deudores_activos.values(),
                   key=lambda d: (d["nivel"] or "", d["orden_grado"],
                                  d["seccion"] or "", d["alumno"]))

    # --- por sección, para repartir entre tutores ---
    secciones: Dict[tuple, dict] = {}
    for d in lista:
        clave = (d["nivel"], d["orden_grado"], d["grado"], d["seccion"])
        s = secciones.setdefault(clave, {
            "nivel": d["nivel"], "grado": d["grado"], "seccion": d["seccion"],
            "orden_grado": d["orden_grado"], "alumnos": [],
        })
        s["alumnos"].append(d)
    for s in secciones.values():
        s["num_alumnos"] = len(s["alumnos"])
        s["num_cuotas"] = sum(a["num_cuotas"] for a in s["alumnos"])
        s["deuda"] = sum((a["deuda"] for a in s["alumnos"]), Decimal("0"))
        s["mora"] = sum((a["mora"] for a in s["alumnos"]), Decimal("0"))
        s["total"] = sum((a["total"] for a in s["alumnos"]), Decimal("0"))
        s["vencido"] = sum((a["vencido"] for a in s["alumnos"]), Decimal("0"))

    # --- deuda anterior: gente que ya no está matriculada ---
    q_ext = db.query(fin.CuotaExterna).filter(fin.CuotaExterna.estado == "PENDIENTE")
    q_ext = q_ext.filter(fin.CuotaExterna.fecha_vencimiento <= limite)
    externas = []
    for c in q_ext.all():
        monto = Decimal(str(c.monto or 0))
        mora = Decimal(str(c.mora or 0))
        vencida = bool(c.fecha_vencimiento and c.fecha_vencimiento < hoy)
        externas.append({
            "documento": _doc(c.documento), "nombre": c.nombre or "",
            "concepto": c.concepto or "", "vencimiento": c.fecha_vencimiento,
            "monto": monto, "mora": mora, "total": monto + mora,
            "dias_atraso": (hoy - c.fecha_vencimiento).days if vencida else 0,
            "origen": c.origen or "",
        })
    externas.sort(key=lambda e: (e["vencimiento"] or dt.date.max, e["nombre"]))

    return {
        "anio": anio,
        "fecha": hoy,
        "deudores": lista,
        "secciones": sorted(secciones.values(),
                            key=lambda s: (s["nivel"] or "", s["orden_grado"],
                                           s["seccion"] or "")),
        "externas": externas,
        "totales": {
            "alumnos": len(lista),
            "cuotas": sum(d["num_cuotas"] for d in lista),
            "deuda": sum((d["deuda"] for d in lista), Decimal("0")),
            "mora": sum((d["mora"] for d in lista), Decimal("0")),
            "total": sum((d["total"] for d in lista), Decimal("0")),
            "vencido": sum((d["vencido"] for d in lista), Decimal("0")),
            "externas": len(externas),
            "total_externas": sum((e["total"] for e in externas), Decimal("0")),
        },
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
