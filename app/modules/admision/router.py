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
        # 1. Crear Alumno
        # Ya que reinsertaste 'direccion' en el modelo Alumno, esto funcionará directo
        nuevo_alumno = Alumno(**datos.alumno.model_dump())
        db.add(nuevo_alumno)
        db.flush() # Para obtener nuevo_alumno.id_alumno

        # 2. Crear Familiar 
        datos_fam = datos.familiar.model_dump()
        
        # Sincronización de seguridad:
        # Si el familiar no mandó dirección, le ponemos la del alumno
        if not datos_fam.get("direccion") or datos_fam["direccion"].strip() == "":
            datos_fam["direccion"] = datos.alumno.direccion
            
        datos_fam["tipo_parentesco"] = datos.tipo_parentesco
        nuevo_familiar = Familiar(**datos_fam)
        db.add(nuevo_familiar)
        db.flush() # Para obtener nuevo_familiar.id_familiar

        # 3. Relación y Parentesco
        # Si te sale NULL, asegúrate que 'datos.tipo_parentesco' sea lo que viene del Front
        # Imprimimos para depurar en tu consola de VS Code/Terminal
        print(f"DEBUG PARENTESCO RECIBIDO: {datos.tipo_parentesco}")

        # Normalizamos a Mayúsculas
        val_parentesco = (datos.tipo_parentesco or "OTRO").upper()
        
        nueva_relacion = RelacionFamiliar(
            id_alumno=nuevo_alumno.id_alumno,
            id_familiar=nuevo_familiar.id_familiar,
            tipo_parentesco=val_parentesco 
        )
        
        db.add(nueva_relacion)
        db.commit() # Aquí se guarda todo definitivamente

        return {
            "status": "success",
            "message": "Postulación registrada",
            "id_alumno": nuevo_alumno.id_alumno
        }

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


