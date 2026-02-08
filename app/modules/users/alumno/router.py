from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.db.database import get_db
from app.modules.users.models import Usuario 
from app.modules.users.relacion_familiar.models import RelacionFamiliar
from app.core.util.password import get_password_hash
from . import models, schemas # Asegúrate de importar los modelos correctos

router = APIRouter(prefix="/alumnos", tags=["Alumnos"])

@router.post("/", response_model=schemas.AlumnoResponse)
def crear_alumno(alumno: schemas.AlumnoCreate, db: Session = Depends(get_db)):
    db_alumno = models.Alumno(**alumno.model_dump())
    db.add(db_alumno)
    db.commit()
    db.refresh(db_alumno)
    return db_alumno

@router.get("/", response_model=List[schemas.AlumnoResponse])
def listar_alumnos(db: Session = Depends(get_db)):
    # Por defecto listamos activos y postulantes, ocultamos rechazados
    return db.query(models.Alumno).filter(models.Alumno.estado_ingreso != "rechazado").all()

@router.get("/solicitudes-pendientes", response_model=List[schemas.AlumnoResponse])
def listar_postulantes(db: Session = Depends(get_db)):
    return db.query(models.Alumno).filter(models.Alumno.estado_ingreso == "postulante").all()

@router.post("/decidir-admision/{id_alumno}")
def decidir_admision(
    id_alumno: int, 
    aprobado: bool, 
    motivo: str = None, 
    db: Session = Depends(get_db)
):
    try:
        # 1. Buscar al alumno por su ID
        alumno = db.query(models.Alumno).filter(models.Alumno.id_alumno == id_alumno).first()
        if not alumno:
            raise HTTPException(status_code=404, detail="No se encontró el postulante")

        if aprobado:
            # --- LÓGICA DE APROBACIÓN ---
            alumno.estado_ingreso = "ADMITIDO"
            alumno.motivo_rechazo = None

            # A. Crear Usuario para el ALUMNO (si no tiene uno asignado)
            if not alumno.id_usuario:
                nuevo_user_alumno = Usuario(
                    username=alumno.dni,
                    password_hash=get_password_hash(alumno.dni), # El DNI es su clave inicial
                    rol="ALUMNO", # Coincide con tu Enum
                    activo=True
                )
                db.add(nuevo_user_alumno)
                db.flush() # Para obtener el id_usuario inmediatamente
                alumno.id_usuario = nuevo_user_alumno.id_usuario

            # B. Buscar al apoderado principal para crearle su cuenta
            relacion = db.query(RelacionFamiliar).filter(
                RelacionFamiliar.id_alumno == id_alumno,
                RelacionFamiliar.es_apoderado_principal == True
            ).first()

            # Si hay una relación y el familiar no tiene cuenta aún
            if relacion and relacion.familiar and not relacion.familiar.id_usuario:
                nuevo_user_familiar = Usuario(
                    username=relacion.familiar.dni,
                    password_hash=get_password_hash(relacion.familiar.dni),
                    rol="FAMILIAR",
                    activo=True
                )
                db.add(nuevo_user_familiar)
                db.flush()
                relacion.familiar.id_usuario = nuevo_user_familiar.id_usuario

        else:
            # --- LÓGICA DE RECHAZO ---
            alumno.estado_ingreso = "RECHAZADO"
            alumno.motivo_rechazo = motivo

        # Guardar todos los cambios de forma atómica
        db.commit()
        return {
            "status": "success", 
            "message": f"El alumno ha sido {'admitido' if aprobado else 'rechazado'} correctamente."
        }

    except Exception as e:
        db.rollback() # Si algo falla (ej: DNI de usuario duplicado), deshace todo
        print(f"Error en decidir_admision: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error al procesar la admisión"
        )
    
@router.get("/detalle-completo/{id_alumno}")
def obtener_detalle_postulante(id_alumno: int, db: Session = Depends(get_db)):
    alumno = db.query(models.Alumno).filter(models.Alumno.id_alumno == id_alumno).first()
    if not alumno:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")
    
    familiares_data = []
    # Usamos la relación definida en tu modelo Alumno
    for rel in alumno.familiares_rel:
        fam = rel.familiar
        familiares_data.append({
            "id_familiar": fam.id_familiar,
            "nombre": f"{fam.nombres} {fam.apellidos}",
            "dni": fam.dni,
            "parentesco": rel.tipo_parentesco,  # <--- CORREGIDO: Ahora coincide con tu modelo
            "es_apoderado": rel.es_apoderado_principal,
            "vive_con": rel.vive_con_alumno,     # Agregamos este dato que es útil
            "telefono": fam.telefono,
            "email": fam.email,
            "direccion": fam.direccion
        })

    return {
        "alumno": {
            "id_alumno": alumno.id_alumno,
            "nombres": alumno.nombres,
            "apellidos": alumno.apellidos,
            "dni": alumno.dni,
            "estado_ingreso": alumno.estado_ingreso,
            "colegio_procedencia": alumno.colegio_procedencia,
            "enfermedad": alumno.enfermedad,
            "direccion": alumno.direccion,
            "fecha_nacimiento": alumno.fecha_nacimiento.isoformat() if alumno.fecha_nacimiento else None,
            "genero": alumno.genero,
            "talla_polo": alumno.talla_polo
        },
        "familiares": familiares_data
    }