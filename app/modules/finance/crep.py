# -*- coding: utf-8 -*-
"""
Lectura y escritura de los archivos de texto del BCP (servicio CREP).

Aquí solo vive el FORMATO. No se toca la base de datos ni Excel, para que la
misma lógica se pueda probar sola y para que un cambio en el negocio no obligue
a tocar el que sabe de posiciones de caracteres.

Dos archivos, los dos de ancho fijo (250 caracteres), latin-1 y saltos CRLF:

  · REPORTE DE COBROS  — lo entrega el BCP cada día con lo que se cobró.
  · CREP               — lo genera el colegio con lo que queda por cobrar.

Las posiciones se dedujeron comparando los archivos reales contra las hojas
"Visualizar Archivo de Resultado" y "Generar Archivo de Cobranza" del .xlsm del
BCP, y están comprobadas: `generar_crep` reconstruye el CREP.txt original byte
a byte. Si alguna vez el BCP cambia el formato, esa prueba es la que avisa.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

ANCHO = 250
CODIFICACION = "latin-1"
SALTO = "\r\n"

# El código de operación ocupa seis caracteres y viene relleno con ceros por
# delante: 048937, no 48937. Ver `normalizar_operacion`.
LARGO_OPERACION = 6


class ErrorFormatoBCP(ValueError):
    """El archivo no tiene la pinta de un archivo del BCP."""


# ---------------------------------------------------------------------------
# Conversiones de campo
# ---------------------------------------------------------------------------

def _a_decimal(texto: str) -> Decimal:
    """'000000000025000' -> Decimal('250.00'). Los montos van en céntimos."""
    limpio = texto.strip() or "0"
    if not limpio.isdigit():
        raise ErrorFormatoBCP(f"Se esperaba un importe numérico y vino {texto!r}")
    return (Decimal(limpio) / 100).quantize(Decimal("0.01"))


def _de_decimal(valor, ancho: int) -> str:
    centimos = (Decimal(str(valor)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    texto = str(int(centimos))
    if len(texto) > ancho:
        raise ErrorFormatoBCP(
            f"El importe {valor} no cabe en {ancho} dígitos del archivo del BCP")
    return texto.zfill(ancho)


def _a_fecha(texto: str) -> Optional[dt.date]:
    """'20260731' -> date(2026, 7, 31). Devuelve None si el campo viene vacío."""
    limpio = texto.strip()
    if not limpio or limpio == "0" * len(limpio):
        return None
    try:
        return dt.datetime.strptime(limpio, "%Y%m%d").date()
    except ValueError:
        raise ErrorFormatoBCP(f"Se esperaba una fecha AAAAMMDD y vino {texto!r}")


def _de_fecha(valor: dt.date) -> str:
    return valor.strftime("%Y%m%d")


def _documento(texto: str) -> str:
    """Quita los ceros de relleno: '00000062884107' -> '62884107'."""
    return texto.strip().lstrip("0")


def normalizar_operacion(valor) -> Optional[str]:
    """El código de operación en la forma en que lo manda el banco: '48937' -> '048937'.

    Al revés que en el documento, aquí el cero de relleno SÍ es parte del
    código, y se pierde con una facilidad enorme: si el código pasa por una
    hoja de cálculo, Excel lo guarda como el número 48937; si alguien lo teclea
    a mano, rara vez escribe el cero. Al conciliar se comparan en crudo, así
    que '048937' y '48937' pasan por cobros distintos, y una cuota que ya
    estaba pagada acaba en la bandeja de revisión como posible pago doble.

    Se rellena en lugar de recortar por delante para que lo guardado coincida
    con lo que llega del banco, que es contra lo que se contrasta.

    Lo que no son puros dígitos se devuelve tal cual: MANUAL-CAJA y
    MANUAL-CONCILIACION son marcas del sistema, no códigos del BCP. Un código
    más largo de la cuenta tampoco se toca —zfill no recorta— porque acortarlo
    sería inventarse un dato.
    """
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    # isdigit() acepta dígitos de otros alfabetos, que zfill no sabría alinear.
    if texto.isascii() and texto.isdigit():
        return texto.zfill(LARGO_OPERACION)
    return texto


# ---------------------------------------------------------------------------
# REPORTE DE COBROS — lo que el BCP cobró en un día
# ---------------------------------------------------------------------------

@dataclass
class PagoBCP:
    """Una línea de cobro. Es lo que el padre pagó en ventanilla o por app."""
    linea: int
    codigo_depositante: str      # con el que el BCP enrutó el pago
    dato_adicional: str          # documento alterno, si el padre puso otro
    fecha_pago: Optional[dt.date]
    fecha_vencimiento: Optional[dt.date]
    monto_pagado: Decimal
    mora_pagada: Decimal
    monto_total: Decimal
    sucursal: str
    agencia: str
    operacion: str
    referencia: str
    medio_atencion: str
    hora_atencion: str
    extornado: bool              # el dinero se devolvió: NO cancela la deuda
    operacion_bd: str
    operacion_canal: str

    @property
    def documentos(self) -> List[str]:
        """Documentos con los que se puede buscar al alumno, sin repetir."""
        vistos = []
        for d in (self.codigo_depositante, self.dato_adicional):
            if d and d not in vistos:
                vistos.append(d)
        return vistos


@dataclass
class ReporteCobros:
    fecha_proceso: Optional[dt.date]
    registros_declarados: int
    monto_declarado: Decimal
    cuenta: str
    pagos: List[PagoBCP] = field(default_factory=list)

    @property
    def monto_real(self) -> Decimal:
        return sum((p.monto_total for p in self.pagos), Decimal("0.00"))

    def avisos(self) -> List[str]:
        """Descuadres entre la cabecera y el detalle. No impiden procesar."""
        problemas = []
        if self.registros_declarados != len(self.pagos):
            problemas.append(
                f"La cabecera declara {self.registros_declarados} cobros pero el "
                f"archivo trae {len(self.pagos)}")
        if abs(self.monto_real - self.monto_declarado) > Decimal("0.01"):
            problemas.append(
                f"La cabecera declara S/ {self.monto_declarado} pero las líneas "
                f"suman S/ {self.monto_real}")
        return problemas


def _lineas(datos: bytes) -> List[str]:
    if not datos:
        raise ErrorFormatoBCP("El archivo está vacío")
    try:
        texto = datos.decode(CODIFICACION)
    except UnicodeDecodeError as e:
        raise ErrorFormatoBCP(f"El archivo no se puede leer como texto: {e}")
    crudas = texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return [l for l in crudas if l.strip()]


def _validar(lineas: List[str], nombre: str) -> None:
    if not lineas:
        raise ErrorFormatoBCP(f"El archivo no tiene ninguna línea con contenido")
    if not lineas[0].startswith("CC"):
        raise ErrorFormatoBCP(
            f"Esto no parece un {nombre} del BCP: la primera línea debería "
            f"empezar por 'CC' y empieza por {lineas[0][:2]!r}")
    cortas = [i + 1 for i, l in enumerate(lineas) if len(l) < 100]
    if cortas:
        raise ErrorFormatoBCP(
            f"El archivo está recortado: las líneas {cortas[:5]} son demasiado "
            f"cortas para un registro del BCP")
    raras = {l[:2] for l in lineas[1:]} - {"DD"}
    if raras:
        raise ErrorFormatoBCP(
            f"Hay líneas de un tipo que no se conoce: {sorted(raras)}. "
            f"Solo se esperan 'CC' (cabecera) y 'DD' (detalle)")


def parsear_reporte_cobros(datos: bytes) -> ReporteCobros:
    """Lee un 'Reporte de cobros' del BCP. Lanza ErrorFormatoBCP si no lo es."""
    lineas = _lineas(datos)
    _validar(lineas, "reporte de cobros")
    cab = lineas[0]

    reporte = ReporteCobros(
        cuenta=cab[2:13],
        fecha_proceso=_a_fecha(cab[14:22]),
        registros_declarados=int(cab[22:31] or 0),
        monto_declarado=_a_decimal(cab[31:46]),
    )
    for i, l in enumerate(lineas[1:], start=2):
        reporte.pagos.append(PagoBCP(
            linea=i,
            codigo_depositante=_documento(l[13:27]),
            dato_adicional=_documento(l[27:57]),
            fecha_pago=_a_fecha(l[57:65]),
            fecha_vencimiento=_a_fecha(l[65:73]),
            monto_pagado=_a_decimal(l[73:88]),
            mora_pagada=_a_decimal(l[88:103]),
            monto_total=_a_decimal(l[103:118]),
            sucursal=l[118:121].strip(),
            agencia=l[121:124].strip(),
            # `or ""` para no cambiar el tipo cuando el campo viene en blanco:
            # antes era cadena vacía y hay sitios que la esperan así.
            operacion=normalizar_operacion(l[124:130]) or "",
            referencia=l[130:152].strip(),
            medio_atencion=l[156:158].strip(),
            hora_atencion=l[168:174].strip(),
            # El campo viene en blanco o a '0' cuando NO hubo extorno; cualquier
            # otra cosa significa que el dinero se devolvió.
            extornado=l[196:197].strip() not in ("", "0"),
            operacion_bd=l[217:225].strip(),
            operacion_canal=l[225:233].strip(),
        ))
    return reporte


# ---------------------------------------------------------------------------
# CREP — lo que queda por cobrar
# ---------------------------------------------------------------------------

@dataclass
class CuotaCREP:
    """Una cuota pendiente, tal como viaja en el archivo de cobranza."""
    codigo_depositante: str
    nombre: str
    documento: str
    fecha_emision: dt.date
    fecha_vencimiento: dt.date
    monto: Decimal
    mora: Decimal

    @property
    def monto_minimo(self) -> Decimal:
        """Regla del archivo, sin excepción en las 3 649 filas reales."""
        return (Decimal(self.monto) + Decimal(self.mora)).quantize(Decimal("0.01"))


@dataclass
class CabeceraCREP:
    """Los datos fijos del afiliado. Salen del .xlsm y no cambian."""
    cuenta: str = "30509864504"
    tipo_cuenta: str = "C"
    empresa: str = "CORPORACION EDUCATIVA MONTEHERMOZO SAC"
    tipo_archivo: str = "R"          # R = Archivo de Reemplazo
    codigo_servicio: str = "000000"


def parsear_crep(datos: bytes) -> tuple:
    """Lee un CREP ya existente. Devuelve (CabeceraCREP, [CuotaCREP])."""
    lineas = _lineas(datos)
    _validar(lineas, "archivo de cobranza (CREP)")
    c = lineas[0]
    cabecera = CabeceraCREP(
        cuenta=c[2:13], tipo_cuenta=c[13:14], empresa=c[14:54].strip(),
        tipo_archivo=c[86:87], codigo_servicio=c[87:93],
    )
    cuotas = []
    for l in lineas[1:]:
        emision = _a_fecha(l[97:105])
        vencimiento = _a_fecha(l[105:113])
        if emision is None or vencimiento is None:
            raise ErrorFormatoBCP(
                f"Una cuota de {l[27:67].strip()!r} viene sin fecha de emisión "
                f"o de vencimiento")
        cuotas.append(CuotaCREP(
            codigo_depositante=_documento(l[13:27]),
            nombre=l[27:67].strip(),
            documento=_documento(l[173:189]),
            fecha_emision=emision,
            fecha_vencimiento=vencimiento,
            monto=_a_decimal(l[113:128]),
            mora=_a_decimal(l[128:143]),
        ))
    return cabecera, cuotas


def generar_crep(cuotas: List[CuotaCREP],
                 fecha: Optional[dt.date] = None,
                 cabecera: Optional[CabeceraCREP] = None) -> bytes:
    """Arma el archivo que se sube al BCP.

    Comprobado contra el CREP.txt real: con las mismas cuotas devuelve
    exactamente los mismos bytes, cabecera incluida.
    """
    cabecera = cabecera or CabeceraCREP()
    fecha = fecha or dt.date.today()
    if not cuotas:
        raise ErrorFormatoBCP(
            "No hay ninguna cuota pendiente: el archivo de cobranza quedaría "
            "vacío y el BCP lo rechazaría")

    # El "Monto Total" de la cabecera es la suma de Monto a Pagar, SIN la mora.
    # Con la mora incluida el BCP devuelve el archivo por descuadre.
    total = sum((Decimal(c.monto) for c in cuotas), Decimal("0.00"))

    lineas = [
        ("CC" + cabecera.cuenta + cabecera.tipo_cuenta
         + cabecera.empresa.ljust(40)[:40] + _de_fecha(fecha)
         + str(len(cuotas)).zfill(9) + _de_decimal(total, 15)
         + cabecera.tipo_archivo + cabecera.codigo_servicio).ljust(ANCHO)
    ]
    for c in cuotas:
        lineas.append((
            "DD"
            + cabecera.cuenta
            + c.codigo_depositante.zfill(14)[-14:]
            + _quitar_acentos(c.nombre).upper().ljust(40)[:40]
            + c.codigo_depositante.ljust(30)[:30]      # Información de Retorno
            + _de_fecha(c.fecha_emision)
            + _de_fecha(c.fecha_vencimiento)
            + _de_decimal(c.monto, 15)
            + _de_decimal(c.mora, 15)
            + _de_decimal(c.monto_minimo, 9)
            + " " * 15
            + "RECIBO"
            + c.documento.zfill(16)[-16:]
        ).ljust(ANCHO))

    return (SALTO.join(lineas) + SALTO).encode(CODIFICACION)


def _quitar_acentos(texto: str) -> str:
    """El archivo va en latin-1, pero el BCP espera nombres sin tildes ni ñ.

    Ninguno de los 3 649 nombres del archivo real lleva acentos; si se colara
    uno, `encode('latin-1')` no fallaría pero el BCP mostraría basura.
    """
    import unicodedata
    plano = unicodedata.normalize("NFKD", texto)
    plano = "".join(ch for ch in plano if not unicodedata.combining(ch))
    return "".join(ch if 32 <= ord(ch) < 127 else " " for ch in plano)
