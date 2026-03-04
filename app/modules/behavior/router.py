from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import extract,func
from app.db.database import get_db
from app.modules.users.alumno import models as alumno_models
from . import models, schemas
from typing import Optional
from datetime import datetime

router = APIRouter(prefix="/conducta", tags=["Conducta y Psicología"])

@router.post("/reportes/")
def crear_reporte_auxiliar(reporte: schemas.ReporteCreate, db: Session = Depends(get_db)):
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
    db: Session = Depends(get_db)
):
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
                "motivo": r.nivel.nombre,
                "puntos_restados": r.nivel.puntos,
                "nota_reglamento": r.nivel.descripcion
            } for r in reportes
        ]
    }


@router.get("/usuario/{id_usuario}/anios-reportes")
def obtener_anios_con_reportes(id_usuario: int, db: Session = Depends(get_db)):
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
def listar_niveles_disponibles(db: Session = Depends(get_db)):
    # Esto servirá para llenar el select/dropdown en la interfaz del auxiliar
    return db.query(models.NivelConducta).all()

# --- ENDPOINTS DE CITAS PSICOLÓGICAS ---

@router.post("/citas/")
def programar_cita(cita: schemas.CitaCreate, db: Session = Depends(get_db)):
    """Permite al psicólogo o auxiliar agendar una nueva cita."""
    nueva_cita = models.CitaPsicologia(**cita.model_dump())
    db.add(nueva_cita)
    db.commit()
    db.refresh(nueva_cita)
    return {"mensaje": "Cita programada exitosamente", "data": nueva_cita}

@router.get("/usuario/{id_usuario}/citas")
def obtener_citas_estudiante(id_usuario: int, db: Session = Depends(get_db)):
    """
    Lista todas las citas programadas para el estudiante logueado.
    """
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
def finalizar_cita(id_cita: int, resultado: str, db: Session = Depends(get_db)):
    """El psicólogo registra lo ocurrido en la reunión y cierra la cita."""
    cita = db.query(models.CitaPsicologia).filter(models.CitaPsicologia.id_cita == id_cita).first()
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    
    cita.estado = "COMPLETADA"
    cita.resultado_reunion = resultado
    db.commit()
    return {"mensaje": "Cita finalizada y registrada"}




# 1. Endpoint para el Resumen (Solo envía LA PRÓXIMA CITA activa)
@router.get("/usuario/{id_usuario}/proxima-cita")
def obtener_proxima_cita(id_usuario: int, db: Session = Depends(get_db)):
    alumno = db.query(alumno_models.Alumno).filter(alumno_models.Alumno.id_usuario == id_usuario).first()
    if not alumno:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    # Filtramos en la base de datos: solo PROGRAMADAS y fecha futura
    cita = db.query(models.CitaPsicologia).filter(
        models.CitaPsicologia.id_alumno == alumno.id_alumno,
        models.CitaPsicologia.estado == "PROGRAMADA",
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
    db: Session = Depends(get_db)
):
    alumno = db.query(alumno_models.Alumno).filter(alumno_models.Alumno.id_usuario == id_usuario).first()
    
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
            "estado": c.estado,
            "resultado": c.resultado_reunion # Solo el historial ve el resultado
        } for c in citas
    ]