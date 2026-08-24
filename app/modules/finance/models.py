from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, DateTime, Date, Text, Boolean, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base
import enum


class PeriodoAcademico(str, enum.Enum):
    REGULAR = "REGULAR"
    VERANO = "VERANO"
    AMBOS = "AMBOS"
# Opcional: Definir estados como Enums para evitar errores de escritura
class EstadoPago(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    PAGADO = "PAGADO"
    VENCIDO = "VENCIDO"
    ANULADO = "ANULADO"

class TipoTramite(Base):
    __tablename__ = "tipo_tramite"

    id_tipo_tramite = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    costo = Column(Numeric(10, 2), default=0.00)
    requisitos = Column(Text, nullable=True)
    activo = Column(Boolean, default=True)
    alcance = Column(String(20), default="TODOS") # E.g., 'PRIMARIA', 'SECUNDARIA'
    grados_permitidos = Column(String(255), nullable=True)
    periodo_academico = Column(
            Enum(PeriodoAcademico),
            default=PeriodoAcademico.REGULAR,
            nullable=False
        )
    # Días que tiene el alumno para pagar el trámite desde que lo solicita.
    dias_vencimiento = Column(Integer, nullable=False, server_default="15")
    # Si está marcado, el alumno con cuotas vencidas no puede solicitarlo: se
    # le avisa en pantalla y el endpoint rechaza la petición con un 409.
    requiere_pagos_al_dia = Column(Boolean, nullable=False, server_default="0")
    # Relación: Un tipo de trámite puede estar en muchas solicitudes
    solicitudes = relationship("SolicitudTramite", back_populates="tipo")

class SolicitudTramite(Base):
    __tablename__ = "solicitud_tramite"

    id_solicitud_tramite = Column(Integer, primary_key=True, index=True)
    id_alumno = Column(Integer, ForeignKey("alumno.id_alumno"))
    id_tipo_tramite = Column(Integer, ForeignKey("tipo_tramite.id_tipo_tramite"))
    fecha_solicitud = Column(DateTime, server_default=func.now())
    estado = Column(String(20), default="PENDIENTE_PAGO")
    archivo_adjunto = Column(String(255), nullable=True)
    comentario_usuario = Column(Text, nullable=True)
    respuesta_administrativa = Column(Text, nullable=True)

    # Relaciones
    alumno = relationship("Alumno") # Asumiendo que existe el modelo Alumno
    tipo = relationship("TipoTramite", back_populates="solicitudes")
    pago = relationship("Pago", back_populates="solicitud", uselist=False)

class Pago(Base):
    __tablename__ = "pago"

    id_pago = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuario.id_usuario"), nullable=True)
    id_alumno = Column(Integer, ForeignKey("alumno.id_alumno"), nullable=False)
    id_matricula = Column(Integer, ForeignKey("matricula.id_matricula"), nullable=True)
    id_solicitud_tramite = Column(Integer, ForeignKey("solicitud_tramite.id_solicitud_tramite"), nullable=True)
    id_tipo_pago = Column(Integer, ForeignKey("tipo_pago.id_tipo_pago"))
    
    concepto = Column(String(150), nullable=False) # E.g., 'Pensión Marzo', 'Certificado'
    monto = Column(Numeric(10, 2), nullable=False)
    mora = Column(Numeric(10, 2), default=0.00)
    monto_total = Column(Numeric(10, 2), nullable=False)
    
    # Campos específicos para la integración BCP
    codigo_operacion_bcp = Column(String(50), nullable=True)
    estado = Column(String(20), default="PENDIENTE")
    fecha_vencimiento = Column(Date, nullable=True)
    fecha_pago = Column(DateTime, nullable=True)
    json_respuesta_banco = Column(Text, nullable=True) # Para guardar el log del Webhook

    # Relaciones para facilitar consultas
    alumno = relationship("Alumno")
    solicitud = relationship("SolicitudTramite", back_populates="pago")
    matricula = relationship("Matricula")
    tipo_pago = relationship("TipoPago")

    # Datos del alumno aplanados para las tablas de caja y recaudación, donde
    # hay que ver de quién es cada pago sin abrir la ficha.
    # Los endpoints que devuelvan muchos pagos deben usar joinedload(Pago.alumno)
    # para no disparar una consulta por fila.
    @property
    def alumno_nombre(self):
        if not self.alumno:
            return None
        return f"{self.alumno.apellidos}, {self.alumno.nombres}".strip(", ")

    @property
    def dni_alumno(self):
        return self.alumno.dni if self.alumno else None

class TipoPago(Base):
    __tablename__ = "tipo_pago"
    
    id_tipo_pago = Column(Integer, primary_key=True, index=True)
    categoria = Column(Enum('VACANTE', 'MATRICULA', 'PENSION', 'MODULO', 'OTRO'), default='OTRO')
    nombre = Column(String(150), nullable=False)
    costo = Column(Numeric(10, 2), nullable=False)
    fecha_inicio = Column(String(5), nullable=False) # Formato "MM-DD"
    fecha_vencimiento = Column(String(5), nullable=False) # Formato "MM-DD"
    mora = Column(Numeric(10, 2), default=0.00)
    accion_vencimiento = Column(Enum('DESHABILITAR', 'APLICAR_MORA'), default='APLICAR_MORA')
    activo = Column(Boolean, default=True)
    periodo_academico = Column(
        Enum(PeriodoAcademico),
        default=PeriodoAcademico.REGULAR,
        nullable=False
    )

# ===========================================================================
# CONCILIACIÓN CON EL BCP (servicio CREP)
#
# El BCP entrega cada día un "Reporte de cobros" con lo que se pagó, y espera
# de vuelta un archivo CREP con lo que queda por cobrar. Antes ese circuito se
# hacía a mano con un .xlsm de macros; estas tablas lo dejan dentro del sistema.
#
# Las cuotas pendientes NO viven aquí: viven en `pago`, que es la que manda.
# Aquí solo se guarda el rastro de qué archivo trajo qué pago, para poder
# auditar después y para no aplicar dos veces el mismo cobro.
# ===========================================================================

class LoteCobranza(Base):
    """Un archivo 'Reporte de cobros' procesado."""
    __tablename__ = "lote_cobranza"

    id_lote = Column(Integer, primary_key=True, index=True)
    nombre_archivo = Column(String(255), nullable=False)
    # Fecha que declara la cabecera del archivo. Es la que ordena el proceso:
    # los reportes SIEMPRE se aplican del más antiguo al más nuevo, porque la
    # mora de un mes depende de quién ya había pagado.
    fecha_reporte = Column(Date, nullable=True, index=True)
    registros_declarados = Column(Integer, default=0)
    monto_declarado = Column(Numeric(12, 2), default=0)
    # Huella del contenido: impide cargar dos veces el mismo archivo aunque le
    # cambien el nombre.
    huella = Column(String(64), nullable=False, unique=True)
    aplicados = Column(Integer, default=0)
    sin_coincidencia = Column(Integer, default=0)
    extornados = Column(Integer, default=0)
    repetidos = Column(Integer, default=0)
    estado = Column(String(20), default="PROCESADO")   # PROCESADO | SIMULADO
    fecha_carga = Column(DateTime, server_default=func.now())
    id_usuario = Column(Integer, ForeignKey("usuario.id_usuario"), nullable=True)

    movimientos = relationship("MovimientoCobranza", back_populates="lote",
                               cascade="all, delete-orphan")


class MovimientoCobranza(Base):
    """Una línea del reporte y qué se hizo con ella."""
    __tablename__ = "movimiento_cobranza"

    id_movimiento = Column(Integer, primary_key=True, index=True)
    id_lote = Column(Integer, ForeignKey("lote_cobranza.id_lote"), nullable=False)
    id_pago = Column(Integer, ForeignKey("pago.id_pago"), nullable=True)
    id_cuota_externa = Column(Integer, ForeignKey("cuota_externa.id_cuota_externa"),
                              nullable=True)

    documento = Column(String(20), nullable=False, index=True)
    fecha_vencimiento = Column(Date, nullable=True, index=True)
    fecha_pago = Column(Date, nullable=True)
    monto_pagado = Column(Numeric(10, 2), default=0)
    mora_pagada = Column(Numeric(10, 2), default=0)
    monto_total = Column(Numeric(10, 2), default=0)
    operacion = Column(String(30), nullable=True)
    medio_atencion = Column(String(10), nullable=True)

    # APLICADO · EXTORNADO · SIN_COINCIDENCIA · REPETIDO · MONTO_DISTINTO · AMBIGUO
    resultado = Column(String(20), nullable=False, index=True)
    detalle = Column(String(255), nullable=True)

    # Qué pasó DESPUÉS con este cobro. `resultado` dice qué pudo hacer el
    # sistema solo; `estado` dice si una persona ya lo atendió. Sin esto, los
    # cobros que no cuadran se acumulan sin que nadie sepa cuáles quedan.
    # PENDIENTE_REVISION · RESUELTO · DESCARTADO
    estado = Column(String(20), nullable=False, default="PENDIENTE_REVISION",
                    server_default="PENDIENTE_REVISION", index=True)
    nota = Column(String(255), nullable=True)
    id_usuario_resolucion = Column(Integer, nullable=True)
    fecha_resolucion = Column(DateTime, nullable=True)

    lote = relationship("LoteCobranza", back_populates="movimientos")
    pago = relationship("Pago")


class CuotaExterna(Base):
    """Deuda de alguien que ya no está matriculado.

    En el CREP que venía usando el colegio hay 193 cuotas de 2022 a 2025 de
    alumnos retirados o trasladados que no existen en `alumno`. Si el archivo
    se generara solo con la tabla `pago`, esas deudas dejarían de cobrarse en
    el BCP. Se guardan aquí para que sigan viajando en el archivo sin ensuciar
    el padrón de alumnos ni las matrículas.
    """
    __tablename__ = "cuota_externa"

    id_cuota_externa = Column(Integer, primary_key=True, index=True)
    codigo_depositante = Column(String(20), nullable=False, index=True)
    documento = Column(String(20), nullable=False, index=True)
    nombre = Column(String(120), nullable=False)
    concepto = Column(String(150), nullable=True)
    fecha_emision = Column(Date, nullable=False)
    fecha_vencimiento = Column(Date, nullable=False, index=True)
    monto = Column(Numeric(10, 2), nullable=False)
    mora = Column(Numeric(10, 2), default=0)
    estado = Column(String(20), default="PENDIENTE", index=True)
    fecha_pago = Column(DateTime, nullable=True)
    codigo_operacion_bcp = Column(String(50), nullable=True)
    origen = Column(String(120), nullable=True)   # de qué archivo salió


class RegistroCREP(Base):
    """Historial de archivos CREP generados / incorporados oficialmente.

    Permite saber la fecha y hora de la última generación y comparar el estado de la
    base de datos para detectar bajas por retiros de alumnos, altas y modificaciones
    pendientes de sincronizar con el BCP.
    """
    __tablename__ = "registro_crep"

    id_registro_crep = Column(Integer, primary_key=True, index=True)
    nombre_archivo = Column(String(255), nullable=False)
    fecha_generacion = Column(DateTime, server_default=func.now(), index=True)
    id_usuario = Column(Integer, ForeignKey("usuario.id_usuario"), nullable=True)
    total_cuotas = Column(Integer, default=0)
    total_alumnos = Column(Integer, default=0)
    monto_total = Column(Numeric(12, 2), default=0)
    mora_total = Column(Numeric(12, 2), default=0)
    estado = Column(String(20), default="INCORPORADO", index=True)  # INCORPORADO | DESCARGADO
    # Lista de cuotas serializadas en JSON para la comparación delta exacta
    cuotas_json = Column(Text().with_variant(Text(4294967295), "mysql"), nullable=True)


class AjusteManualPago(Base):
    """Cada cambio que una persona hace a mano sobre una cuota.

    POR QUÉ EXISTE
      El archivo CREP se genera leyendo `pago` en vivo, así que un cambio hecho
      a mano ya viaja al banco en la siguiente descarga. Lo que no había forma
      de saber es CUÁLES fueron esos cambios: quién bajó un importe, a quién se
      le cobró en caja o qué cuota se borró. Al comparar el archivo con el del
      mes anterior aparecían diferencias que nadie sabía justificar.

      Esta tabla es el rastro. No decide nada del cobro —la que manda sigue
      siendo `pago`—, solo anota lo que pasó y si el banco ya lo tiene.

    LO QUE NO ES
      No es la conciliación. Los cobros que llegan del BCP se anotan en
      `movimiento_cobranza`; aquí solo entra lo que hizo una persona desde el
      panel.
    """
    __tablename__ = "ajuste_manual_pago"

    id_ajuste = Column(Integer, primary_key=True, index=True)

    # La cuota afectada. Queda a NULL cuando se borró: por eso los datos que
    # hacen falta para reconocerla en el CREP (documento, vencimiento, importe)
    # se copian aquí y no se leen por relación.
    # Enteros sueltos, sin clave foránea a propósito: con una FK, borrar un
    # pago fallaría mientras quede su apunte, y el registro de lo ocurrido no
    # puede ser motivo de que una operación normal deje de funcionar.
    id_pago = Column(Integer, nullable=True, index=True)
    id_cuota_externa = Column(Integer, nullable=True, index=True)

    # ALTA · MONTO · MORA · ESTADO · PAGO_MANUAL · ELIMINACION · PRECIO_MASIVO
    tipo = Column(String(20), nullable=False, index=True)

    # Qué le hace este cambio al archivo del banco, ya resuelto al anotarlo:
    # ALTA (entra una cuota) · BAJA (deja de cobrarse) · IMPORTE (cambia lo que
    # se cobra) · NINGUNO (no altera el archivo).
    efecto_crep = Column(String(10), nullable=False, default="NINGUNO",
                         server_default="NINGUNO", index=True)

    documento = Column(String(20), nullable=True, index=True)
    nombre = Column(String(120), nullable=True)
    concepto = Column(String(150), nullable=True)
    fecha_vencimiento = Column(Date, nullable=True, index=True)

    monto_anterior = Column(Numeric(10, 2), nullable=True)
    monto_nuevo = Column(Numeric(10, 2), nullable=True)
    mora_anterior = Column(Numeric(10, 2), nullable=True)
    mora_nueva = Column(Numeric(10, 2), nullable=True)
    estado_anterior = Column(String(20), nullable=True)
    estado_nuevo = Column(String(20), nullable=True)

    detalle = Column(String(255), nullable=True)

    id_usuario = Column(Integer, nullable=True, index=True)
    usuario = Column(String(60), nullable=True)
    fecha = Column(DateTime, server_default=func.now(), nullable=False, index=True)

    # Con qué CREP oficial se envió al banco. NULL = todavía no incorporado,
    # que es lo que la pantalla enseña como pendiente.
    id_registro_crep = Column(Integer, nullable=True, index=True)
    fecha_incorporacion = Column(DateTime, nullable=True)
