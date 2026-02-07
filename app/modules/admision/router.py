from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.modules.users.alumno.models import Alumno
from app.modules.users.familiar.models import Familiar
from app.modules.users.relacion_familiar.models import RelacionFamiliar # El que creamos antes
from . import schemas

router = APIRouter(prefix="/admision", tags=["Admisión"])

@router.post("/postular", status_code=status.HTTP_201_CREATED)
def postular_alumno(datos: schemas.AdmisionPostulante, db: Session = Depends(get_db)):
    try:
        # 1. Crear el Alumno (sin id_usuario por ahora)
        nuevo_alumno = Alumno(**datos.alumno.model_dump())
        db.add(nuevo_alumno)
        db.flush() # flush() obtiene el ID sin cerrar la transacción

        # 2. Crear el Familiar (sin id_usuario por ahora)
        nuevo_familiar = Familiar(**datos.familiar.model_dump())
        db.add(nuevo_familiar)
        db.flush() 

        # 3. Crear la Relación Familiar
        nueva_relacion = RelacionFamiliar(
            id_alumno=nuevo_alumno.id_alumno,
            id_familiar=nuevo_familiar.id_familiar,
            es_apoderado_principal=datos.es_apoderado,
            vive_con_alumno=datos.vive_con_alumno,
            tipo_parentesco=datos.tipo_parentesco
        )
        db.add(nueva_relacion)

        # 4. Confirmar todo en la base de datos
        db.commit()
        
        return {"message": "Postulación registrada exitosamente", "id_alumno": nuevo_alumno.id_alumno}

    except Exception as e:
        db.rollback()
        # Loguea el error real en consola para ti
        print(f"DEBUG ERROR: {e}") 
        
        # Mensaje amigable para el usuario
        mensaje = "Error interno del servidor"
        if "Duplicate entry" in str(e):
            mensaje = "El DNI ingresado ya se encuentra registrado."
        elif "foreign key constraint" in str(e):
            mensaje = "Error de integridad en los datos proporcionados."
            
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=mensaje
        )


