from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.database import get_db
from .schemas import DocenteCreate, DocenteResponse,DocenteUpdate
from .models import Docente
from app.modules.users.models import Usuario
from typing import List
from app.core.util.password import get_password_hash
from sqlalchemy.orm import joinedload
from sqlalchemy import or_

# Creamos el router. 'prefix' evita repetir "/docentes" en cada ruta.
router = APIRouter(
    prefix="/docentes",
    tags=["Docentes"] # Esto los agrupa en la documentación /docs
)

@router.post("/", response_model=DocenteResponse, status_code=status.HTTP_201_CREATED)
def crear_docente(docente_in: DocenteCreate, db: Session = Depends(get_db)):
    # 1. Verificar si el DNI (username) ya existe
    docente_existente = db.query(Docente).filter(Docente.dni == docente_in.dni).first()
    if docente_existente:
        raise HTTPException(status_code=400, detail="El DNI ya está registrado")

    try:
        # 2. Crear el Usuario primero
        nuevo_usuario = Usuario(
            username=docente_in.dni,
            # La contraseña inicial podría ser el mismo DNI o una enviada
            password_hash=get_password_hash(docente_in.dni), 
            rol="DOCENTE", # Forzamos el rol desde el backend por seguridad
            activo=True
        )
        db.add(nuevo_usuario)
        db.flush() # Flush envía los cambios a la DB y obtiene el ID sin cerrar la transacción

        # 3. Crear el Docente vinculado al usuario creado
        docente_data = docente_in.model_dump()
        docente_data["id_usuario"] = nuevo_usuario.id_usuario # Asignamos el ID recién generado
        
        db_docente = Docente(**docente_data)
        db.add(db_docente)
        
        db.commit() # Si todo sale bien, guardamos ambos
        db.refresh(db_docente)
        return db_docente

    except Exception as e:
        db.rollback() # Si falla algo, deshacemos todo (no se crea ni el usuario ni el docente)
        raise HTTPException(status_code=500, detail=f"Error al registrar: {str(e)}")

@router.get("/", response_model=List[DocenteResponse])
def listar_docentes(search: str = None, db: Session = Depends(get_db)):
    """
    Lista docentes con opción de búsqueda por nombre, apellido o especialidad.
    """
    query = db.query(Docente).options(joinedload(Docente.usuario))

    if search:
        # ilike es para búsquedas que ignoran mayúsculas/minúsculas
        search_filter = f"%{search}%"
        query = query.filter(
            or_(
                Docente.nombres.ilike(search_filter),
                Docente.apellidos.ilike(search_filter),
                Docente.especialidad.ilike(search_filter)
            )
        )

    return query.all()


@router.get("/{id}", response_model=DocenteResponse)
def obtener_docente(id: int, db: Session = Depends(get_db)):
    docente = db.query(Docente).filter(Docente.id_docente == id).first()
    if not docente:
        raise HTTPException(status_code=404, detail="Docente no encontrado")
    return docente

@router.put("/{id}", response_model=DocenteResponse)
def actualizar_docente(id: int, docente_update: DocenteUpdate, db: Session = Depends(get_db)):
    db_docente = db.query(Docente).filter(Docente.id_docente == id).first()
    
    if not db_docente:
        raise HTTPException(status_code=404, detail="Docente no encontrado")
    
    datos_a_actualizar = docente_update.model_dump(exclude_unset=True)
    # Actualizamos los campos dinámicamente
    for key, value in datos_a_actualizar.items():
        setattr(db_docente, key, value)
    
    db.commit()
    db.refresh(db_docente)
    return db_docente

@router.put("/{id}/modificarestado", response_model=DocenteResponse)
def desactivar_docente(id: int, db: Session = Depends(get_db)):
    # 1. Buscar al docente por ID
    docente = db.query(Docente).filter(Docente.id_docente == id).first()
    
    if not docente:
        raise HTTPException(status_code=404, detail="Docente no encontrado")
    
    # 2. Buscar al usuario vinculado
    usuario = db.query(Usuario).filter(Usuario.id_usuario == docente.id_usuario).first()
    
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario vinculado no encontrado")

    # 3. Cambiar el estado 
    usuario.activo = not usuario.activo
    
    db.commit()
    db.refresh(docente) # Refrescamos el docente para que devuelva el nuevo estado del usuario
    return docente