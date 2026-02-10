from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.core.util.password import get_password_hash, verify_password
# Imports corregidos: asegúrate de que las rutas sean las correctas en tu proyecto
from app.modules.users.models import Usuario
from app.modules.users.docente.models import Docente
from app.modules.users.alumno.models import Alumno
from .schemas import ChangePasswordSchema
# from app.modules.users.familiar.models import Familiar # Descomenta si lo usas

router = APIRouter(prefix="/perfil", tags=["Perfil"])

@router.get("/mi-perfil/{username}")
def obtener_perfil_por_nombre(username: str, db: Session = Depends(get_db)):
    # 1. Buscamos al usuario base (Quitamos 'models.' porque importaste la clase directa)
    user = db.query(Usuario).filter(Usuario.username == username).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # 2. Según el rol, buscamos en su tabla específica
    if user.rol == "ALUMNO":
        # Usamos la relación definida en tu modelo Usuario
        alumno = user.alumno 
        if not alumno:
            raise HTTPException(status_code=404, detail="Datos de alumno no encontrados")
        
        familiares_data = []
        # Verificamos si existe la relación de familiares en el modelo Alumno
        if hasattr(alumno, 'familiares_rel') and alumno.familiares_rel:
            for rel in alumno.familiares_rel:
                fam = rel.familiar
                familiares_data.append({
                    "nombre": f"{fam.nombres} {fam.apellidos}",
                    "parentesco": rel.tipo_parentesco,
                    "dni": fam.dni,
                    "telefono": fam.telefono
                })

        return {
            "rol": user.rol,
            "datos": alumno,
            "familiares": familiares_data
        }

    elif user.rol in ["DOCENTE", "ADMIN"]:
        # Buscamos en la tabla Docente (Quitamos 'models.')
        docente = db.query(Docente).filter(Docente.id_usuario == user.id_usuario).first()
        if not docente:
            raise HTTPException(status_code=404, detail="Datos de docente no encontrados")
            
        return {
            "rol": user.rol,
            "datos": docente
        }

    raise HTTPException(status_code=400, detail="Rol no soportado")


@router.post("/auth/change-password")
async def change_password(data: ChangePasswordSchema, db: Session = Depends(get_db)):
    # 1. Buscar al usuario
    user = db.query(Usuario).filter(Usuario.username == data.username).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # 2. Verificar si la contraseña actual es correcta
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="La contraseña actual es incorrecta")

    # 3. Encriptar la nueva y guardar
    user.password_hash = get_password_hash(data.new_password)
    db.commit()
    return {"message": "Contraseña actualizada con éxito"}