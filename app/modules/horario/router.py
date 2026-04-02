from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import time, datetime, date
from app.db.database import get_db
from app.modules.horario.models import HorarioEscolar, HoraLectiva
from app.modules.management.models import CargaAcademica
from app.modules.horario.schemas import HorarioCreate, HorarioResponse, HoraLectivaResponse, MateriaDisponibleResponse
from app.modules.academic.models import Seccion
from app.modules.enrollment.models import Matricula
from app.modules.users.alumno.models import Alumno
from app.modules.users.models import Usuario
from app.modules.users.docente.models import Docente
from app.core.util.security import get_current_user

router = APIRouter(prefix="/horarios", tags=["Horarios"])

# --- CONFIGURACIÓN DE HORAS ---
@router.get("/horas", response_model=List[HoraLectivaResponse])
def obtener_horas_lectivas(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Retorna los bloques de tiempo (filas del schedule)"""
    return db.query(HoraLectiva).order_by(HoraLectiva.hora_inicio).all()

# --- HORARIO POR SECCIÓN ---
@router.get("/seccion/{id_seccion}", response_model=List[HorarioResponse])
def obtener_horario_seccion(id_seccion: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    # Join explícito para evitar el error de Mapper
    horarios = db.query(HorarioEscolar).join(
        CargaAcademica, HorarioEscolar.id_carga_academica == CargaAcademica.id_carga_academica
    ).filter(CargaAcademica.id_seccion == id_seccion).all()
    
    resultado = []
    for h in horarios:
        # Importante: Manejar si dia_semana es un Enum o String
        dia = h.dia_semana.value if hasattr(h.dia_semana, 'value') else h.dia_semana
        
        resultado.append({
            "id_horario": h.id_horario,
            "dia_semana": dia,
            "id_carga_academica": h.id_carga_academica,
            "hora_inicio": h.hora_inicio.strftime("%H:%M"), # NUEVO: Horas dinámicas
            "hora_fin": h.hora_fin.strftime("%H:%M"),       # NUEVO: Horas dinámicas
            "curso_nombre": h.carga.curso.nombre,
            "docente_nombre": f"{h.carga.docente.nombres} {h.carga.docente.apellidos}",
            "seccion_nombre": h.carga.seccion.nombre
        })
    return resultado

# --- GUARDAR / ACTUALIZAR BLOQUE ---
@router.post("/", status_code=status.HTTP_201_CREATED)
def asignar_bloque_horario(horario_in: HorarioCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN" :
        raise HTTPException(status_code=403, detail="No puedes ver modificar esta información")
    # 1. Convertir strings del frontend a objetos time reales para operar en BD
    t_inicio = datetime.strptime(horario_in.hora_inicio, "%H:%M").time()
    t_fin = datetime.strptime(horario_in.hora_fin, "%H:%M").time()

    # 3. Obtener carga académica
    carga_actual = db.query(CargaAcademica).filter(
        CargaAcademica.id_carga_academica == horario_in.id_carga_academica
    ).first()
    
    if not carga_actual:
        raise HTTPException(status_code=404, detail="La carga académica no existe")

    # 4. VALIDACIÓN DE CONFLICTO DOCENTE (Join explícito - Adaptado a horas en vez de ID)
    conflicto = db.query(HorarioEscolar).join(
        CargaAcademica, HorarioEscolar.id_carga_academica == CargaAcademica.id_carga_academica
    ).filter(
        CargaAcademica.id_docente == carga_actual.id_docente,
        HorarioEscolar.dia_semana == horario_in.dia_semana,
        HorarioEscolar.hora_inicio < t_fin,   # Lógica de solapamiento de tiempo
        HorarioEscolar.hora_fin > t_inicio
    ).first()

    if conflicto:
        raise HTTPException(
            status_code=400,
            detail=f"Conflicto: El docente ya dicta clases en {conflicto.carga.seccion.nombre} en este horario."
        )

    # 5. Evitar aula ocupada (Faltaba el join explícito aquí - Adaptado a horas)
    aula_ocupada = db.query(HorarioEscolar).join(
        CargaAcademica, HorarioEscolar.id_carga_academica == CargaAcademica.id_carga_academica
    ).filter(
        CargaAcademica.id_seccion == carga_actual.id_seccion,
        HorarioEscolar.dia_semana == horario_in.dia_semana,
        HorarioEscolar.hora_inicio < t_fin,
        HorarioEscolar.hora_fin > t_inicio
    ).first()

    if aula_ocupada:
        raise HTTPException(status_code=400, detail="Esta sección ya tiene una materia asignada en este bloque")

    # 6. Guardar (Asegúrate de que los nombres de campos coincidan con tu Model)
    nuevo_horario = HorarioEscolar(
        id_carga_academica=horario_in.id_carga_academica,
        dia_semana=horario_in.dia_semana,
        hora_inicio=t_inicio,
        hora_fin=t_fin
    )
    db.add(nuevo_horario)
    db.commit()
    return {"message": "Horario asignado correctamente"}


@router.delete("/{id_horario}")
def eliminar_bloque_horario(id_horario: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes ver modificar esta información")
    db_horario = db.query(HorarioEscolar).filter(HorarioEscolar.id_horario == id_horario).first()
    if not db_horario:
        raise HTTPException(status_code=404, detail="No se encontró el bloque")
    db.delete(db_horario)
    db.commit()
    return {"message": "Bloque eliminado"}


@router.get("/materias-disponibles/{id_seccion}", response_model=List[MateriaDisponibleResponse])
def obtener_materias_disponibles(id_seccion: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    # Buscamos la carga académica de esa sección
    materias = db.query(CargaAcademica).filter(CargaAcademica.id_seccion == id_seccion).all()
    
    resultado = []
    for m in materias:
        # Calcular los minutos que ya se han asignado en el horario
        horarios = db.query(HorarioEscolar).filter(HorarioEscolar.id_carga_academica == m.id_carga_academica).all()
        min_asignados = 0
        for h in horarios:
            diff = datetime.combine(date.min, h.hora_fin) - datetime.combine(date.min, h.hora_inicio)
            min_asignados += diff.total_seconds() / 60

        resultado.append({
            "id_carga_academica": m.id_carga_academica,
            "curso_nombre": m.curso.nombre,
            "docente_nombre": f"{m.docente.nombres} {m.docente.apellidos}",
            "minutos_semanales": m.curso.minutos_semanales,
            "minutos_asignados": int(min_asignados)
        })
    return resultado

@router.get("/usuario/{id_usuario}", response_model=List[HorarioResponse])
def obtener_horario_por_usuario(
    id_usuario: int, 
    id_anio_escolar: str, 
    db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    if  current_user.get("id") != id_usuario:
        raise HTTPException(status_code=403, detail="No puedes ver esta información")
    """
    Obtiene el horario basado en el rol definido en la tabla Usuario.
    """
    # 1. Obtenemos el usuario para saber su rol
    usuario = db.query(Usuario).filter(Usuario.id_usuario == id_usuario).first()
    
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    horarios = []
    rol = usuario.rol.upper()  # Aseguramos consistencia

    # 2. Lógica según el rol del usuario
    if rol == "ALUMNO":
        alumno = db.query(Alumno).filter(Alumno.id_usuario == id_usuario).first()

        if not alumno:
            raise HTTPException(
                status_code=404, 
                detail="No se encontró un alumno asociado a este usuario"
            )

        # 2. Buscamos la matrícula usando el id_alumno encontrado
        matricula = db.query(Matricula).join(Seccion).filter(
            Matricula.id_alumno == alumno.id_alumno,
            Seccion.id_anio_escolar == id_anio_escolar
        ).first()

        if not matricula:
            raise HTTPException(
                status_code=404, 
                detail="El alumno no tiene una matrícula registrada para el año escolar seleccionado"
            )

        # 3. Lógica para obtener los horarios (se mantiene igual)
        id_seccion = matricula.id_seccion
        
        horarios = db.query(HorarioEscolar).join(
            CargaAcademica, HorarioEscolar.id_carga_academica == CargaAcademica.id_carga_academica
        ).filter(CargaAcademica.id_seccion == id_seccion).all()
    elif rol == "DOCENTE":
        docente = db.query(Docente).filter(Docente.id_usuario == id_usuario).first()
        if not docente:
            raise HTTPException(status_code=404, detail="Docente no vinculado a este usuario")

        # Filtramos horarios donde el docente tiene carga en el año escolar dado
        horarios = db.query(HorarioEscolar).join(CargaAcademica).join(Seccion).filter(
            CargaAcademica.id_docente == docente.id_docente,
            Seccion.id_anio_escolar == id_anio_escolar
        ).all()
    
    else:
        raise HTTPException(status_code=400, detail=f"Rol '{rol}' no soportado para consulta de horarios")

    # 3. Mapeo común a la respuesta
    resultado = []
    for h in horarios:
        dia = h.dia_semana.value if hasattr(h.dia_semana, 'value') else h.dia_semana
        resultado.append({
            "id_horario": h.id_horario,
            "dia_semana": dia,
            "id_carga_academica": h.id_carga_academica,
            "hora_inicio": h.hora_inicio.strftime("%H:%M"), # NUEVO: Se formatea la hora para el frontend
            "hora_fin": h.hora_fin.strftime("%H:%M"),       # NUEVO: Se formatea la hora para el frontend
            "curso_nombre": h.carga.curso.nombre,
            "docente_nombre": f"{h.carga.docente.nombres} {h.carga.docente.apellidos}",
            "seccion_nombre": h.carga.seccion.nombre
        })
    
    return resultado