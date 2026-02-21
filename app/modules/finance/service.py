from sqlalchemy.orm import Session
from sqlalchemy import or_, case
from datetime import datetime, date
import calendar
from . import models
from app.modules.academic import models as academic_models
from app.modules.enrollment import models as enrollment_models
from app.modules.users.alumno import models as user_models 

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
    def aplicar_moras_pagos_vencidos(db: Session):
        """
        Busca pagos PENDIENTES que ya pasaron su fecha de vencimiento
        y les aplica una mora única de 5 soles.
        """
        hoy = date.today()
        
        # Filtramos:
        # 1. Solo pagos PENDIENTES
        # 2. Donde la fecha de vencimiento sea menor a hoy
        # 3. Donde la mora sea 0 (para asegurar que es la primera vez que se aplica)
        pagos_vencidos = db.query(models.Pago).filter(
            models.Pago.estado == "PENDIENTE",
            models.Pago.fecha_vencimiento < hoy,
            models.Pago.mora == 0
        ).all()

        for pago in pagos_vencidos:
            pago.mora = 5.00
            # El monto_total ahora refleja la deuda + la multa
            pago.monto_total = pago.monto + 5.00
        
        db.commit()
        return len(pagos_vencidos)