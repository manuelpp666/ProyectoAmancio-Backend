from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from typing import List
from app.db.database import get_db
from . import models, schemas
from app.modules.users.models import Usuario
from app.modules.users.docente.models import Docente
from app.core.util.password import get_password_hash
from app.core.util.security import get_current_user
from app.core.util.usuarios import generar_username
from app.core.util.permisos import permisos_completos, normalizar

router = APIRouter(prefix="/personal", tags=["Gestión de Personal"])

# Función auxiliar para unificar la respuesta
def to_response(registro, tipo):
    id_val = getattr(registro, f"id_{tipo}")
    # Solo el administrador tiene permisos. Se devuelven completados con el
    # catálogo actual para que la pantalla muestre también las pestañas que se
    # añadieron después de la última vez que se guardaron.
    permisos = getattr(registro, "permisos", None)
    return {
        "id": id_val,
        "id_usuario": registro.id_usuario,
        "dni": registro.dni,
        "nombres": registro.nombres,
        "apellidos": registro.apellidos,
        "telefono": registro.telefono,
        "email": registro.email,
        "usuario": registro.usuario,
        "permisos": normalizar(permisos) if tipo == "admin" else None,
    }

@router.get("/{tipo}", response_model=List[schemas.PersonalResponse])
def listar_personal(tipo: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes ver modificar esta información")

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
    
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No tienes permiso para realizar esta acción")

    # 1. Mapeo de roles
    roles_map = {
        "admin": "ADMIN",
        "docente": "DOCENTE",
        "auxiliar": "AUXILIAR",
        "psicologo": "PSICOLOGO"
    }
    
    rol = roles_map.get(tipo.lower())
    if not rol:
        raise HTTPException(status_code=400, detail="Tipo de personal inválido")
    
    # 2. Crear el Usuario base
    # El username lleva el prefijo del rol (ej. AUX-16714260): así una misma
    # persona puede tener cuenta como docente y como auxiliar sin chocar con
    # la restricción UNIQUE de usuario.username.
    username = generar_username(personal.dni, rol)
    if db.query(Usuario).filter(Usuario.username == username).first():
        raise HTTPException(
            status_code=400,
            detail=f"Ya existe un usuario {rol} con el DNI {personal.dni}."
        )

    nuevo_usuario = Usuario(
        username=username,
        password_hash=get_password_hash(personal.password),
        rol=rol,
        activo=True
    )
    db.add(nuevo_usuario)
    db.commit()
    db.refresh(nuevo_usuario)
    
    # 3. Preparar datos del perfil
    # Extraemos password (que no va al perfil) y permisos (que es condicional)
    datos_perfil = personal.model_dump(exclude={'password'})
    permisos_data = datos_perfil.pop('permisos', None) # Se quita de datos_perfil pase lo que pase

    # 4. Crear el perfil específico según el tipos
    if tipo == "admin":
        # Un administrador nuevo entra con todo el panel activado; el director
        # le cierra después lo que no le corresponda desde Gestión de Personal.
        # Si el formulario mandó permisos, se completan con el catálogo actual.
        nuevo_perfil = models.Administrador(
            id_usuario=nuevo_usuario.id_usuario,
            permisos=normalizar(permisos_data) if permisos_data else permisos_completos(),
            **datos_perfil
        )
    elif tipo == "docente":
        # Aquí 'datos_perfil' ya no tiene la clave 'permisos', el error desaparece
        nuevo_perfil = Docente(id_usuario=nuevo_usuario.id_usuario, **datos_perfil)
    elif tipo == "auxiliar":
        nuevo_perfil = models.Auxiliar(id_usuario=nuevo_usuario.id_usuario, **datos_perfil)
    elif tipo == "psicologo":
        nuevo_perfil = models.Psicologo(id_usuario=nuevo_usuario.id_usuario, **datos_perfil)
        
    db.add(nuevo_perfil)
    try:
        db.commit()
        db.refresh(nuevo_perfil)
    except Exception as e:
        db.rollback()
        # Si algo falla al crear el perfil, borramos el usuario creado para no dejar basura
        db.delete(nuevo_usuario)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Error al crear el perfil: {str(e)}")
    
    return to_response(nuevo_perfil, tipo)

@router.put("/{tipo}/{id}", response_model=schemas.PersonalResponse)
def editar_personal(tipo: str, id: int, data: schemas.PersonalUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes ver modificar esta información")

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

    usuario = db.query(Usuario).filter(Usuario.id_usuario == perfil.id_usuario).first()

    # Si cambia el DNI, el username debe seguirlo manteniendo el prefijo del rol
    if usuario and data.dni and data.dni != perfil.dni:
        nuevo_username = generar_username(data.dni, usuario.rol)
        existe = db.query(Usuario).filter(
            Usuario.username == nuevo_username,
            Usuario.id_usuario != usuario.id_usuario
        ).first()
        if existe:
            raise HTTPException(
                status_code=400,
                detail=f"Ya existe un usuario {usuario.rol} con el DNI {data.dni}."
            )
        usuario.username = nuevo_username

    perfil.nombres = data.nombres
    perfil.apellidos = data.apellidos
    perfil.dni = data.dni
    perfil.email = data.email
    perfil.telefono = data.telefono

    if data.password and usuario:
        usuario.password_hash = get_password_hash(data.password)

    db.commit()
    db.refresh(perfil)
    return to_response(perfil, tipo)

@router.patch("/{tipo}/{id}/estado")
def cambiar_estado(tipo: str, id: int, activo: bool, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes ver modificar esta información")
    
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

    # 3. Se guarda el árbol completo, no solo lo que mandó la pantalla: así una
    #    clave ausente no queda a merced del valor por defecto y lo marcado es
    #    exactamente lo único a lo que tendrá acceso.
    admin.permisos = normalizar(data.permisos)

    db.commit()
    db.refresh(admin)
    
    return admin