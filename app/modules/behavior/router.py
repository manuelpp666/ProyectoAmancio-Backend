from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import extract,func
from app.db.database import get_db
from app.modules.users.alumno import models as alumno_models
from app.modules.users.familiar.models import Familiar
from app.modules.users.relacion_familiar.models import RelacionFamiliar
from app.core.util.security import get_current_user
from . import models, schemas
from typing import Optional
from datetime import datetime

router = APIRouter(prefix="/conducta", tags=["Conducta y Psicología"])

@router.post("/reportes/")
def crear_reporte_auxiliar(reporte: schemas.ReporteCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "AUXILIAR":
        raise HTTPException(status_code=403, detail="No puedes ver esta información")
    nuevo_reporte = models.ReporteConducta(**reporte.model_dump())
    db.add(nuevo_reporte)
    db.commit()
    db.refresh(nuevo_reporte)
    
    # Opcional: Podrías devolver un mensaje si el alumno bajó de cierto puntaje
    return {"mensaje": "Reporte registrado con éxito", "data": nuevo_reporte}


@router.get("/usuario/{id_usuario}/estado-conducta")
def obtener_estado_por_usuario(
    id_usuario: int, 
    anio: Optional[int] = Query(None), 
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("id") != id_usuario:
        raise HTTPException(status_code=403, detail="No puedes ver esta información")
    # 1. Buscar al alumno asociado
    alumno = db.query(alumno_models.Alumno).filter(
        alumno_models.Alumno.id_usuario == id_usuario
    ).first()

    if not alumno:
        raise HTTPException(status_code=404, detail="El usuario no tiene un perfil de alumno asociado")

    # 2. Definir el año a consultar (si no viene, usar el actual)
    if anio is None:
        anio = datetime.now().year

    # 3. Base de la consulta filtrada POR ALUMNO Y AÑO (Siempre)
    reportes = db.query(models.ReporteConducta).filter(
        models.ReporteConducta.id_alumno == alumno.id_alumno,
        extract('year', models.ReporteConducta.fecha_reporte) == anio
    ).order_by(models.ReporteConducta.fecha_reporte.desc()).all()

    # 4. Cálculo de puntos
    # Usamos r.nivel.puntos porque en tus inserts pusiste valores positivos (3, 2, 8, etc.)
    total_penalizacion = sum(r.nivel.puntos for r in reportes if r.nivel)
    puntaje_actual = max(0, 100 - total_penalizacion)

    # 5. Lógica de colores (Semáforo)
    estado_visual = "Verde"
    if puntaje_actual < 40: estado_visual = "Rojo"
    elif puntaje_actual < 75: estado_visual = "Amarillo"

    return {
        "id_usuario": id_usuario,
        "id_alumno": alumno.id_alumno,
        "nombre_alumno": f"{alumno.nombres} {alumno.apellidos}",
        "anio_consultado": anio, # Es bueno devolver qué año se calculó
        "puntaje_actual": puntaje_actual,
        "porcentaje_progreso": f"{puntaje_actual}%",
        "estado_color": estado_visual,
        "total_reportes": len(reportes),
        "historial": [
            {
                "id_reporte": r.id_reporte,
                "fecha": r.fecha_reporte.strftime("%d/%m/%Y"),
                "motivo": r.nivel.nombre if r.nivel else "Falta registrada",
                "puntos_restados": r.nivel.puntos if r.nivel else 0,
                "nota_reglamento": r.descripcion_suceso or (r.nivel.descripcion if r.nivel else "")
            } for r in reportes
        ]
    }


@router.get("/usuario/{id_usuario}/anios-reportes")
def obtener_anios_con_reportes(id_usuario: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if  current_user.get("id") != id_usuario:
        raise HTTPException(status_code=403, detail="No puedes ver esta información")
    # 1. Buscar al alumno
    alumno = db.query(alumno_models.Alumno).filter(
        alumno_models.Alumno.id_usuario == id_usuario
    ).first()

    if not alumno:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    # 2. Obtener años únicos de sus reportes
    # Usamos extract('year') y distinct para no repetir años
    anios = db.query(
        extract('year', models.ReporteConducta.fecha_reporte).label('anio')
    ).filter(
        models.ReporteConducta.id_alumno == alumno.id_alumno
    ).distinct().order_by(extract('year', models.ReporteConducta.fecha_reporte).desc()).all()

    # Retornamos una lista simple de enteros: [2026, 2025]
    return [int(a.anio) for a in anios]

@router.get("/niveles-conducta")
def listar_niveles_disponibles(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    # Esto servirá para llenar el select/dropdown en la interfaz del auxiliar
    return db.query(models.NivelConducta).all()

# --- ENDPOINTS DE CITAS PSICOLÓGICAS ---

@router.post("/citas/")
def programar_cita(cita: schemas.CitaCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Permite al psicólogo o auxiliar agendar una nueva cita."""
    if current_user.get("rol") != "AUXILIAR" and current_user.get("rol") != "PSICOLOGO":
        raise HTTPException(status_code=403, detail="No puedes mddificar esta información")
    
    # Validación 1: Fecha en el futuro
    if cita.fecha_cita <= datetime.now():
        raise HTTPException(status_code=400, detail="La fecha y hora de la cita debe ser posterior al momento actual.")

    # Validación 2: Prevención de colisión de horarios
    cita_existente = db.query(models.CitaPsicologia).filter(
        models.CitaPsicologia.fecha_cita == cita.fecha_cita,
        models.CitaPsicologia.estado.in_(["PROGRAMADA", "REPROGRAMADA"])
    ).first()

    if cita_existente:
        raise HTTPException(status_code=400, detail="El horario seleccionado ya se encuentra ocupado por otra cita.")
    
    nueva_cita = models.CitaPsicologia(**cita.model_dump())
    db.add(nueva_cita)
    db.commit()
    db.refresh(nueva_cita)
    return {"mensaje": "Cita programada exitosamente", "data": nueva_cita}

@router.get("/usuario/{id_usuario}/citas")
def obtener_citas_estudiante(id_usuario: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """
    Lista todas las citas programadas para el estudiante logueado.
    """
    if current_user.get("id") != id_usuario:
        raise HTTPException(status_code=403, detail="No puedes ver esta información")
    # 1. Buscar al alumno asociado al usuario
    alumno = db.query(alumno_models.Alumno).filter(
        alumno_models.Alumno.id_usuario == id_usuario
    ).first()

    if not alumno:
        raise HTTPException(status_code=404, detail="Perfil de alumno no encontrado")

    # 2. Obtener sus citas ordenadas por fecha (las más próximas primero)
    citas = db.query(models.CitaPsicologia).filter(
        models.CitaPsicologia.id_alumno == alumno.id_alumno
    ).order_by(models.CitaPsicologia.fecha_cita.asc()).all()

    return [
        {
            "id_cita": c.id_cita,
            "motivo": c.motivo,
            "fecha": c.fecha_cita.strftime("%d/%m/%Y"),
            "hora": c.fecha_cita.strftime("%H:%M %p"),
            "estado": c.estado,
            "resultado": c.resultado_reunion,
            "es_hoy": c.fecha_cita.date() == datetime.now().date()
        } for c in citas
    ]

@router.patch("/citas/{id_cita}/completar")
def finalizar_cita(id_cita: int, resultado: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """El psicólogo registra lo ocurrido en la reunión y cierra la cita."""
    if current_user.get("rol") != "AUXILIAR" and current_user.get("rol") != "PSICOLOGO":
        raise HTTPException(status_code=403, detail="No puedes mddificar esta información")
    
    cita = db.query(models.CitaPsicologia).filter(models.CitaPsicologia.id_cita == id_cita).first()
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    
    cita.estado = "COMPLETADA"
    cita.resultado_reunion = resultado
    db.commit()
    return {"mensaje": "Cita finalizada y registrada"}




# 1. Endpoint para el Resumen (Solo envía LA PRÓXIMA CITA activa)
@router.get("/usuario/{id_usuario}/proxima-cita")
def obtener_proxima_cita(id_usuario: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("id") != id_usuario:
        raise HTTPException(status_code=403, detail="No puedes ver esta información")
    alumno = db.query(alumno_models.Alumno).filter(alumno_models.Alumno.id_usuario == id_usuario).first()
    if not alumno:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    # Filtramos en la base de datos: solo citas activas (programadas o reprogramadas) y fecha futura
    cita = db.query(models.CitaPsicologia).filter(
        models.CitaPsicologia.id_alumno == alumno.id_alumno,
        models.CitaPsicologia.estado.in_(["PROGRAMADA", "REPROGRAMADA"]),
        models.CitaPsicologia.fecha_cita >= datetime.now()
    ).order_by(models.CitaPsicologia.fecha_cita.asc()).first() # .first() solo trae UNA

    if not cita:
        return None # El front recibirá un null, muy fácil de manejar

    return {
        "id_cita": cita.id_cita,
        "motivo": cita.motivo,
        "fecha": cita.fecha_cita.strftime("%d/%m/%Y"),
        "hora": cita.fecha_cita.strftime("%H:%M %p"),
        "es_hoy": cita.fecha_cita.date() == datetime.now().date()
    }

# 2. Endpoint para el Historial (Filtrado por año en DB)
@router.get("/usuario/{id_usuario}/historial-citas")
def obtener_historial_citas(
    id_usuario: int, 
    anio: Optional[int] = Query(None), 
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("id") != id_usuario:
        raise HTTPException(status_code=403, detail="No puedes ver esta información")
    
    alumno = db.query(alumno_models.Alumno).filter(alumno_models.Alumno.id_usuario == id_usuario).first()
    if not alumno:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    if not anio:
        anio = datetime.now().year

    # El filtro se hace en el motor de la base de datos
    citas = db.query(models.CitaPsicologia).filter(
        models.CitaPsicologia.id_alumno == alumno.id_alumno,
        extract('year', models.CitaPsicologia.fecha_cita) == anio
    ).order_by(models.CitaPsicologia.fecha_cita.desc()).all()

    return [
        {
            "id_cita": c.id_cita,
            "motivo": c.motivo,
            "fecha": c.fecha_cita.strftime("%d/%m/%Y"),
            "hora": c.fecha_cita.strftime("%H:%M"),
            "estado": c.estado,
            "resultado": c.resultado_reunion # Solo el historial ve el resultado
        } for c in citas
    ]


@router.get("/usuario/{id_usuario}/anios-citas")
def obtener_anios_con_citas(id_usuario: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Años en los que el alumno tiene citas registradas (para el selector del historial)."""
    if current_user.get("id") != id_usuario:
        raise HTTPException(status_code=403, detail="No puedes ver esta información")

    alumno = db.query(alumno_models.Alumno).filter(alumno_models.Alumno.id_usuario == id_usuario).first()
    if not alumno:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    anios = db.query(
        extract('year', models.CitaPsicologia.fecha_cita).label('anio')
    ).filter(
        models.CitaPsicologia.id_alumno == alumno.id_alumno
    ).distinct().order_by(extract('year', models.CitaPsicologia.fecha_cita).desc()).all()

    return [int(a.anio) for a in anios]


@router.patch("/citas/{id_cita}/reprogramar")
def reprogramar_cita(
    id_cita: int, 
    nueva_fecha: datetime, 
    db: Session = Depends(get_db), 
    current_user: dict = Depends(get_current_user)
):
    """Permite cambiar la fecha y hora de una cita pendiente."""
    if current_user.get("rol") not in ["AUXILIAR", "PSICOLOGO"]:
        raise HTTPException(status_code=403, detail="No tienes permisos")
    
    cita = db.query(models.CitaPsicologia).filter(models.CitaPsicologia.id_cita == id_cita).first()
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    
    if cita.estado != "PROGRAMADA":
        raise HTTPException(status_code=400, detail="Solo se pueden reprogramar citas pendientes")

    # Validación 1: Fecha en el futuro
    if nueva_fecha <= datetime.now():
        raise HTTPException(status_code=400, detail="La nueva fecha y hora debe ser posterior al momento actual.")

    # Validación 2: Prevención de colisión de horarios (excluyendo la cita actual)
    cita_existente = db.query(models.CitaPsicologia).filter(
        models.CitaPsicologia.fecha_cita == nueva_fecha,
        models.CitaPsicologia.estado.in_(["PROGRAMADA", "REPROGRAMADA"]),
        models.CitaPsicologia.id_cita != id_cita
    ).first()

    if cita_existente:
        raise HTTPException(status_code=400, detail="El nuevo horario seleccionado ya se encuentra ocupado por otra cita.")
    
    cita.fecha_cita = nueva_fecha
    cita.estado = "REPROGRAMADA" # Opcional, o mantener como PROGRAMADA
    db.commit()
    return {"mensaje": "Cita reprogramada con éxito", "nueva_fecha": nueva_fecha.strftime("%d/%m/%Y %H:%M")}

@router.patch("/citas/{id_cita}/cancelar")
def cancelar_cita(id_cita: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") not in ["AUXILIAR", "PSICOLOGO"]:
        raise HTTPException(status_code=403, detail="No tienes permisos")
    
    cita = db.query(models.CitaPsicologia).filter(models.CitaPsicologia.id_cita == id_cita).first()
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    
    cita.estado = "CANCELADA"
    db.commit()
    return {"mensaje": "Cita cancelada"}

@router.get("/citas/agenda-diaria")
def obtener_agenda_dia(fecha: Optional[datetime] = None, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") not in ["AUXILIAR", "PSICOLOGO"]:
        raise HTTPException(status_code=403, detail="Acceso denegado")
    
    if not fecha: fecha = datetime.now()

    # Hacemos join con la tabla alumno para traer el nombre
    citas = db.query(
        models.CitaPsicologia.id_cita,
        models.CitaPsicologia.id_alumno,
        models.CitaPsicologia.motivo,
        models.CitaPsicologia.fecha_cita,
        models.CitaPsicologia.estado,
        (alumno_models.Alumno.nombres + " " + alumno_models.Alumno.apellidos).label("alumno_nombre")
    ).join(alumno_models.Alumno, models.CitaPsicologia.id_alumno == alumno_models.Alumno.id_alumno)\
     .filter(func.date(models.CitaPsicologia.fecha_cita) == fecha.date())\
     .all()

    return [
        {
            "id_cita": c.id_cita,
            "id_alumno": c.id_alumno,
            "motivo": c.motivo,
            "fecha_cita": c.fecha_cita,
            "estado": c.estado,
            "alumno_nombre": c.alumno_nombre
        } for c in citas
    ]

@router.get("/seguimiento/{id_alumno}")
def obtener_seguimiento_detallado(id_alumno: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Vista integral para el psicólogo: Reportes de conducta + Citas pasadas."""
    if current_user.get("rol") not in ["AUXILIAR", "PSICOLOGO"]:
        raise HTTPException(status_code=403, detail="Acceso denegado")

    reportes = db.query(models.ReporteConducta).filter(models.ReporteConducta.id_alumno == id_alumno).all()
    citas = db.query(models.CitaPsicologia).filter(models.CitaPsicologia.id_alumno == id_alumno).all()

    return {
        "id_alumno": id_alumno,
        "total_incidentes": len(reportes),
        "total_citas": len(citas),
        "historial_conducta": reportes,
        "historial_psicologico": citas
    }

@router.get("/resumen-psicologo")
def obtener_resumen_dashboard(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") not in ["PSICOLOGO", "AUXILIAR"]:
        raise HTTPException(status_code=403, detail="No autorizado")
    
    anio_actual = datetime.now().year

    # Lógica para contar alumnos en riesgo (< 75 puntos)
    # 1. Obtener puntos perdidos por cada alumno en el año actual
    subquery = db.query(
        models.ReporteConducta.id_alumno,
        func.sum(models.NivelConducta.puntos).label("total_perdido")
    ).join(models.NivelConducta).filter(
        extract('year', models.ReporteConducta.fecha_reporte) == anio_actual
    ).group_by(models.ReporteConducta.id_alumno).subquery()

    # 2. Contar cuántos tienen un puntaje (100 - perdido) menor a 75
    conteo_riesgo = db.query(subquery).filter(
        (100 - subquery.c.total_perdido) < 75
    ).count()
    atenciones_mes = db.query(models.CitaPsicologia).filter(
        extract('month', models.CitaPsicologia.fecha_cita) == datetime.now().month,
        models.CitaPsicologia.estado == "COMPLETADA"
    ).count()

    return {
        "citas_pendientes": db.query(models.CitaPsicologia).filter(models.CitaPsicologia.estado == "PROGRAMADA").count(),
        "alumnos_riesgo": conteo_riesgo,
        "atenciones_mes": atenciones_mes
    }

#Búsqueda de alumnos
@router.get("/buscar-alumnos")
def buscar_alumnos(
    q: str = Query(..., min_length=3), 
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Busca alumnos matriculados por nombre o DNI (Escalable)."""
    # Filtramos solo alumnos con matrícula activa (asumiendo que existe la tabla matricula)
    alumnos = db.query(alumno_models.Alumno).filter(
        (alumno_models.Alumno.nombres.ilike(f"%{q}%")) | 
        (alumno_models.Alumno.apellidos.ilike(f"%{q}%")) |
        (alumno_models.Alumno.dni.ilike(f"%{q}%"))
    ).limit(10).all() # Limitamos para que sea rápido
    
    return alumnos

@router.get("/alumno/{id_alumno}/familiares")
def obtener_familiares_alumno(id_alumno: int, db: Session = Depends(get_db)):
    """Devuelve los familiares vinculados a un alumno específico."""
    # Nota: Asegúrate de tener importado RelacionFamiliar y Familiar
    relaciones = db.query(RelacionFamiliar).filter(
        RelacionFamiliar.id_alumno == id_alumno
    ).all()
    
    return [
        {
            "id_familiar": r.familiar.id_familiar,
            "nombre": f"{r.familiar.nombres} {r.familiar.apellidos}",
            "parentesco": r.tipo_parentesco
        } for r in relaciones
    ]

@router.get("/alumnos-en-riesgo")
def obtener_alumnos_riesgo(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Devuelve la lista de alumnos que requieren atención psicológica por baja conducta (< 75 pts)."""
    if current_user.get("rol") not in ["PSICOLOGO", "AUXILIAR"]:
        raise HTTPException(status_code=403, detail="No autorizado")

    anio_actual = datetime.now().year
    
    # 1. Obtener todos los reportes del año actual con su respectivo alumno y nivel
    reportes = db.query(
        models.ReporteConducta
    ).join(
        alumno_models.Alumno, models.ReporteConducta.id_alumno == alumno_models.Alumno.id_alumno
    ).filter(
        extract('year', models.ReporteConducta.fecha_reporte) == anio_actual
    ).all()

    # 2. Agrupar puntos por alumno
    puntajes_alumnos = {}
    for r in reportes:
        if r.alumno not in puntajes_alumnos:
            puntajes_alumnos[r.alumno] = 0
        if r.nivel:
            puntajes_alumnos[r.alumno] += r.nivel.puntos

    # 3. Filtrar los que están en riesgo
    alumnos_riesgo = []
    for alumno, puntos_perdidos in puntajes_alumnos.items():
        puntaje_actual = max(0, 100 - puntos_perdidos)
        if puntaje_actual < 75:
            alumnos_riesgo.append({
                "id_alumno": alumno.id_alumno,
                "nombre_completo": f"{alumno.nombres} {alumno.apellidos}",
                "dni": alumno.dni,
                "puntaje": puntaje_actual,
                "estado": "Rojo" if puntaje_actual < 40 else "Amarillo"
            })

    # Ordenar priorizando los casos más críticos (menor puntaje)
    alumnos_riesgo.sort(key=lambda x: x["puntaje"])
    
    return alumnos_riesgo