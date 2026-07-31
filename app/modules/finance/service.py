from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, case
from datetime import datetime, date, timedelta
import calendar
from . import models
from app.modules.academic import models as academic_models
from app.modules.enrollment import models as enrollment_models
from app.modules.users.alumno import models as user_models
from app.modules.finance import models as finance_models 

class FinanceService:
    @staticmethod
    def obtener_tipo_tramite_por_periodo(db: Session, nombre_clave: str, tipo_periodo: str):
        """
        Busca un trámite por nombre (ej: 'PENSION') que coincida con el 
        periodo (REGULAR/VERANO) o sea 'AMBOS'.
        """
        return db.query(models.TipoTramite).filter(
            models.TipoTramite.nombre.ilike(f"%{nombre_clave}%"),
            models.TipoTramite.activo == True,
            models.TipoTramite.periodo_academico.in_([tipo_periodo, "AMBOS"])
        ).order_by(
            # Prioridad 1: Match exacto (REGULAR == REGULAR)
            # Prioridad 2: Match con 'AMBOS'
            case((models.TipoTramite.periodo_academico == tipo_periodo, 1), else_=2)
        ).first()

   
    @staticmethod
    def generar_pension_mensual(db: Session, id_alumno: int, id_matricula: int, tipo_periodo: str, mes: int, anio: int):
        

        matricula = db.query(enrollment_models.Matricula).filter(enrollment_models.Matricula.id_matricula == id_matricula).first()
        if not matricula: return

        anio_escolar = db.query(academic_models.AnioEscolar).filter(academic_models.AnioEscolar.id_anio_escolar == matricula.id_anio_escolar).first()
        if not anio_escolar: return

        # 2. Validación de rango de clases
        fecha_a_cobrar = date(anio, mes, 1)
        inicio_clases = anio_escolar.fecha_inicio.replace(day=1)
        fin_clases = anio_escolar.fecha_fin.replace(day=1)

        if fecha_a_cobrar < inicio_clases or fecha_a_cobrar > fin_clases:
            print(f"INFO: Omitiendo mes {mes}/{anio}. Fuera de clases.")
            return

        # 3. Buscar costo
        tramite = FinanceService.obtener_tipo_tramite_por_periodo(db, "PENSION", tipo_periodo)
        if not tramite:
            print(f"ERROR: No hay costo configurado para PENSION - {tipo_periodo}")
            return

        # 4. Preparar datos del pago
        nombre_mes = ["", "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", 
                    "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"][mes]
        concepto = f"PENSION {nombre_mes} {anio}"

        # Verificamos si ya existe para no duplicar deudas
        existe = db.query(models.Pago).filter(
            models.Pago.id_alumno == id_alumno,
            models.Pago.concepto == concepto
        ).first()

        if not existe:
            # Obtenemos el id_usuario del alumno para vincular el pago
            alumno = db.query(user_models.Alumno).filter(user_models.Alumno.id_alumno == id_alumno).first()
            
            ultimo_dia = calendar.monthrange(anio, mes)[1]
            nuevo_pago = models.Pago(
                id_usuario=alumno.id_usuario if alumno else None, # ¡Importante!
                id_alumno=id_alumno,
                id_matricula=id_matricula,
                concepto=concepto,
                monto=tramite.costo,
                monto_total=tramite.costo,
                estado="PENDIENTE",
                fecha_vencimiento=date(anio, mes, ultimo_dia),
                mora=0
            )
            db.add(nuevo_pago)
            # Usamos flush() si viene de un router que ya hace commit, o commit() si es independiente
            db.commit() 
            print(f"SUCCESS: Generada {concepto} para Alumno {id_alumno}")
    
    

    @staticmethod
    def limpiar_pensiones_fuera_de_rango(db: Session, ids_alumnos=None):
        """
        Elimina las pensiones PENDIENTES cuyo mes cae fuera del rango
        [mes de inicio, mes de fin] de TODOS los años en los que el alumno está
        matriculado. Respeta verano (usa la unión de rangos de sus matrículas) y
        NO toca pensiones ya pagadas. Devuelve la cantidad eliminada.
        """
        # Rango de meses (1er día de mes) por año escolar
        rango_anio = {}
        for a in db.query(academic_models.AnioEscolar).all():
            if a.fecha_inicio and a.fecha_fin:
                rango_anio[a.id_anio_escolar] = (a.fecha_inicio.replace(day=1), a.fecha_fin.replace(day=1))

        # Rango(s) válidos por alumno = unión de sus años matriculados
        mq = db.query(enrollment_models.Matricula)
        if ids_alumnos:
            mq = mq.filter(enrollment_models.Matricula.id_alumno.in_(ids_alumnos))
        rangos_alumno = {}
        for m in mq.all():
            rng = rango_anio.get(m.id_anio_escolar)
            if rng:
                rangos_alumno.setdefault(m.id_alumno, []).append(rng)

        pq = db.query(models.Pago).filter(
            models.Pago.estado == "PENDIENTE",
            models.Pago.concepto.like("PENSION %")
        )
        if ids_alumnos:
            pq = pq.filter(models.Pago.id_alumno.in_(ids_alumnos))

        eliminadas = 0
        for p in pq.all():
            if not p.fecha_vencimiento:
                continue
            primero = p.fecha_vencimiento.replace(day=1)
            rangos = rangos_alumno.get(p.id_alumno, [])
            if not any(ini <= primero <= fin for (ini, fin) in rangos):
                db.delete(p)
                eliminadas += 1
        if eliminadas:
            db.commit()
        return eliminadas

    @staticmethod
    def aplicar_moras_pagos_vencidos(db):
        hoy = date.today()
        # Calculamos la fecha límite (10 días después del vencimiento)
        limite_gracia = hoy - timedelta(days=10)
        
        # Buscamos deudas que superen el límite de gracia y que no tengan la mora cobrada aún
        pagos_vencidos = db.query(finance_models.Pago).options(
            joinedload(finance_models.Pago.tipo_pago)
        ).filter(
            finance_models.Pago.estado == "PENDIENTE",
            finance_models.Pago.fecha_vencimiento < limite_gracia,
            finance_models.Pago.mora == 0 
        ).all()

        cantidad = 0
        for pago in pagos_vencidos:
            if pago.tipo_pago and pago.tipo_pago.categoria in ('PENSION', 'MODULO'):
                mora_configurada = pago.tipo_pago.mora
                if mora_configurada > 0:
                    pago.mora = mora_configurada
                    pago.monto_total = pago.monto + mora_configurada
                    cantidad += 1
        
        db.commit()
        return cantidad