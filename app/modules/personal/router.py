from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from typing import List
from app.db.database import get_db
from . import models, schemas
from app.modules.users.models import Usuario
from app.modules.users.docente.models import Docente
from app.core.util.password import get_password_hash
from app.core.util.security import get_current_user

router = APIRouter(prefix="/personal", tags=["Gestión de Personal"])

# Función auxiliar para unificar la respuesta
def to_response(registro, tipo):
    id_val = getattr(registro, f"id_{tipo}")
    return {
        "id": id_val,
        "id_usuario": registro.id_usuario,
        "dni": registro.dni,
        "nombres": registro.nombres,
        "apellidos": registro.apellidos,
        "telefono": registro.telefono,
        "email": registro.email,
        "sueldo": registro.sueldo,
        "usuario": registro.usuario,
        # Importante: Solo el administrador tiene permisos
        "permisos": getattr(registro, "permisos", None) 
    }

@router.get("/{tipo}", response_model=List[schemas.PersonalResponse])
def listar_personal(tipo: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if tipo == "admin":
        registros = db.query(models.Administrador).options(joinedload(models.Administrador.usuario)).all()
    elif tipo == "docente":
        registros = db.query(Docente).options(joinedload(Docente.usuario)).all()
    elif tipo == "auxiliar":
        registros = db.query(models.Auxiliar).options(joinedload(models.Auxiliar.usuario)).all()
    elif tipo == "psicologo":
        registros = db.query(models.Psicologo).options(joinedload(models.Psicologo.usuario)).all()
    else:
        raise HTTPException(status_code=400, detail="Tipo inválido")
    
    return [to_response(r, tipo) for r in registros]

@router.post("/{tipo}", response_model=schemas.PersonalResponse)
def crear_personal(tipo: str, personal: schemas.PersonalCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if tipo == "admin": rol = "ADMIN"
    elif tipo == "docente": rol = "DOCENTE"
    elif tipo == "auxiliar": rol = "AUXILIAR"
    elif tipo == "psicologo": rol = "PSICOLOGO"
    else: raise HTTPException(status_code=400, detail="Tipo inválido")
    
    nuevo_usuario = Usuario(
        username=personal.dni,
        password_hash=get_password_hash(personal.password),
        rol=rol,
        activo=True
    )
    db.add(nuevo_usuario)
    db.commit()
    db.refresh(nuevo_usuario)
    
    datos_perfil = personal.model_dump(exclude={'password'})
    if tipo == "admin":
        nuevo_perfil = models.Administrador(id_usuario=nuevo_usuario.id_usuario, **datos_perfil)
    elif tipo == "docente":
        nuevo_perfil = Docente(id_usuario=nuevo_usuario.id_usuario, **datos_perfil)
    elif tipo == "auxiliar":
        nuevo_perfil = models.Auxiliar(id_usuario=nuevo_usuario.id_usuario, **datos_perfil)
    elif tipo == "psicologo":
        nuevo_perfil = models.Psicologo(id_usuario=nuevo_usuario.id_usuario, **datos_perfil)
        
    db.add(nuevo_perfil)
    db.commit()
    db.refresh(nuevo_perfil)
    
    return to_response(nuevo_perfil, tipo)

@router.put("/{tipo}/{id}", response_model=schemas.PersonalResponse)
def editar_personal(tipo: str, id: int, data: schemas.PersonalUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if tipo == "admin":
        perfil = db.query(models.Administrador).filter(models.Administrador.id_admin == id).first()
    elif tipo == "docente":
        perfil = db.query(Docente).filter(Docente.id_docente == id).first()
    elif tipo == "auxiliar":
        perfil = db.query(models.Auxiliar).filter(models.Auxiliar.id_auxiliar == id).first()
    elif tipo == "psicologo":
        perfil = db.query(models.Psicologo).filter(models.Psicologo.id_psicologo == id).first()
        
    if not perfil:
        raise HTTPException(status_code=404, detail="Personal no encontrado")
        
    perfil.nombres = data.nombres
    perfil.apellidos = data.apellidos
    perfil.dni = data.dni
    perfil.email = data.email
    perfil.telefono = data.telefono
    perfil.sueldo = data.sueldo
    
    if data.password:
        usuario = db.query(Usuario).filter(Usuario.id_usuario == perfil.id_usuario).first()
        usuario.password_hash = get_password_hash(data.password)
        
    db.commit()
    db.refresh(perfil)
    return to_response(perfil, tipo)

@router.patch("/{tipo}/{id}/estado")
def cambiar_estado(tipo: str, id: int, activo: bool, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if tipo == "admin":
        perfil = db.query(models.Administrador).filter(models.Administrador.id_admin == id).first()
    elif tipo == "docente":
        perfil = db.query(Docente).filter(Docente.id_docente == id).first()
    elif tipo == "auxiliar":
        perfil = db.query(models.Auxiliar).filter(models.Auxiliar.id_auxiliar == id).first()
    elif tipo == "psicologo":
        perfil = db.query(models.Psicologo).filter(models.Psicologo.id_psicologo == id).first()
        
    usuario = db.query(Usuario).filter(Usuario.id_usuario == perfil.id_usuario).first()
    usuario.activo = activo
    db.commit()
    return {"message": "Estado actualizado"}


@router.patch("/admin/{id_admin}/permisos", response_model=schemas.AdminPermisosResponse)
def actualizar_permisos_admin(
    id_admin: int, 
    data: schemas.AdminPermisosUpdate, 
    db: Session = Depends(get_db), 
    current_user: dict = Depends(get_current_user)
):
    # 1. Buscar al administrador
    admin = db.query(models.Administrador).filter(models.Administrador.id_admin == id_admin).first()
    
    if not admin:
        raise HTTPException(status_code=404, detail="Administrador no encontrado")

    # 2. Validar que quien hace la petición sea un ADMIN (Opcional pero recomendado)
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No tienes permiso para alterar privilegios")

    # 3. Actualizar el campo JSON
    admin.permisos = data.permisos
    
    db.commit()
    db.refresh(admin)
    
    return admin