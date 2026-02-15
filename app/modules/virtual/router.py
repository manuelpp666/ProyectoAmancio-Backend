from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.db.database import get_db
from app.core.socket_manager import socket_manager # Importa la instancia única
from datetime import datetime
from app.modules.users import models as models_usuario
from app.modules.academic import models as models_ac
from app.modules.enrollment import models as models_en
from app.modules.management import models as models_mn
from app.modules.users.alumno import models as models_al
from app.modules.users.docente import models as models_doc

from . import models, schemas

router = APIRouter(prefix="/virtual", tags=["Aula Virtual"])

@router.post("/tareas/")
def crear_tarea(tarea: schemas.TareaCreate, db: Session = Depends(get_db)):
    nuevo = models.Tarea(**tarea.model_dump())
    db.add(nuevo)
    db.commit()
    return nuevo

@router.post("/chat/mensaje/")
async def enviar_mensaje(mensaje: schemas.MensajeCreate, db: Session = Depends(get_db)):
    # 1. Obtener la conversación y determinar quién es el receptor
    conv = db.query(models.Conversacion).filter(models.Conversacion.id_conversacion == mensaje.id_conversacion).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    receptor_id = conv.usuario2_id if mensaje.remitente_id == conv.usuario1_id else conv.usuario1_id
    
    # 2. Obtener Roles y Perfiles Académicos
    remitente = db.query(models_usuario.Usuario).filter(models_usuario.Usuario.id_usuario == mensaje.remitente_id).first()
    receptor = db.query(models_usuario.Usuario).filter(models_usuario.Usuario.id_usuario == receptor_id).first()
    
    # Obtener el año escolar activo
    anio_activo = db.query(models_ac.AnioEscolar).filter(models_ac.AnioEscolar.activo == 1).first()
    if not anio_activo:
        raise HTTPException(status_code=400, detail="No hay un año escolar activo configurado")

    puede_enviar = False

    # --- REGLA: DOCENTE ENVÍA ---
    if remitente.rol == 'DOCENTE':
        if receptor.rol == 'DOCENTE':
            puede_enviar = True # Docentes hablan entre sí libremente
        
        elif receptor.rol == 'ALUMNO':
            # Verificar si el docente dicta en la sección donde el alumno está matriculado
            docente_perfil = db.query(models_doc.Docente).filter(models_doc.Docente.id_usuario == remitente.id_usuario).first()
            alumno_perfil = db.query(models_al.Alumno).filter(models_al.Alumno.id_usuario == receptor.id_usuario).first()
            
            es_su_alumno = db.query(models_mn.CargaAcademica).join(
                models_en.Matricula, models_en.Matricula.id_seccion == models_mn.CargaAcademica.id_seccion
            ).filter(
                models_mn.CargaAcademica.id_docente == docente_perfil.id_docente,
                models_en.Matricula.id_alumno == alumno_perfil.id_alumno,
                models_mn.CargaAcademica.id_anio_escolar == anio_activo.id_anio_escolar
            ).first()
            if es_su_alumno: puede_enviar = True

    # --- REGLA: ALUMNO ENVÍA ---
    elif remitente.rol == 'ALUMNO':
        alumno_perfil = db.query(models_al.Alumno).filter(models_al.Alumno.id_usuario == remitente.id_usuario).first()
        # Obtener matrícula del remitente para este año
        matricula_remitente = db.query(models_en.Matricula).filter(
            models_en.Matricula.id_alumno == alumno_perfil.id_alumno,
            models_en.Matricula.id_anio_escolar == anio_activo.id_anio_escolar
        ).first()

        if not matricula_remitente:
            raise HTTPException(status_code=403, detail="El alumno no tiene matrícula activa este año")

        if receptor.rol == 'DOCENTE':
            # Verificar si el docente receptor tiene carga en la sección del alumno
            docente_receptor = db.query(models_doc.Docente).filter(models_doc.Docente.id_usuario == receptor.id_usuario).first()
            le_ensenha = db.query(models_mn.CargaAcademica).filter(
                models_mn.CargaAcademica.id_docente == docente_receptor.id_docente,
                models_mn.CargaAcademica.id_seccion == matricula_remitente.id_seccion,
                models_mn.CargaAcademica.id_anio_escolar == anio_activo.id_anio_escolar
            ).first()
            if le_ensenha: puede_enviar = True

        elif receptor.rol == 'ALUMNO':
            # Verificar si el receptor está en la misma sección y año
            alumno_receptor = db.query(models_al.Alumno).filter(models_al.Alumno.id_usuario == receptor.id_usuario).first()
            misma_seccion = db.query(models_en.Matricula).filter(
                models_en.Matricula.id_alumno == alumno_receptor.id_alumno,
                models_en.Matricula.id_seccion == matricula_remitente.id_seccion,
                models_en.Matricula.id_anio_escolar == anio_activo.id_anio_escolar
            ).first()
            if misma_seccion: puede_enviar = True

    # 3. Respuesta Final
    if not puede_enviar:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Restricción académica: No puedes enviar mensajes a este usuario."
        )

    # Si pasa las reglas, guardamos
    nuevo_mensaje = models.Mensaje(**mensaje.model_dump())
    db.add(nuevo_mensaje)
    
    # Actualizar la conversación (denormalización para rapidez en el front)
    conv.ultimo_mensaje = mensaje.contenido
    conv.fecha_actualizacion = datetime.now()
    
    db.commit()
    db.refresh(nuevo_mensaje)
    # 4. ENVIAR NOTIFICACIÓN POR WEBSOCKET (TIEMPO REAL)
    payload = {
        "tipo": "NUEVO_MENSAJE",
        "data": {
            "id_conversacion": mensaje.id_conversacion,
            "contenido": mensaje.contenido,
            "remitente_id": mensaje.remitente_id,
            "fecha_envio": nuevo_mensaje.fecha_envio.strftime("%H:%M")
        }
    }
    
    # Usamos await para enviar al receptor a través del manager que ya tienes en main
    await socket_manager.send_personal_message(receptor_id, payload)

    return nuevo_mensaje


@router.get("/chat/contactos/{id_usuario}")
def buscar_contactos(id_usuario: int, query: str = None, db: Session = Depends(get_db)):
    user = db.query(models_usuario.Usuario).get(id_usuario)
    anio_activo = db.query(models_ac.AnioEscolar).filter(models_ac.AnioEscolar.activo == 1).first()
    
    if not anio_activo or not user:
        return []

    contactos_validos = []

    # --- Función auxiliar para filtrar por DNI o Nombre ---
    def aplicar_filtro(query_obj, modelo):
        if query:
            return query_obj.filter(
                or_(
                    modelo.dni.like(f"{query}%"),
                    modelo.nombres.ilike(f"%{query}%"),
                    modelo.apellidos.ilike(f"%{query}%")
                )
            )
        return query_obj

    # --- LÓGICA SI EL QUE BUSCA ES UN ALUMNO ---
    if user.rol == 'ALUMNO':
        alumno = db.query(models_al.Alumno).filter(models_al.Alumno.id_usuario == id_usuario).first()
        matricula = db.query(models_en.Matricula).filter(
            models_en.Matricula.id_alumno == alumno.id_alumno, 
            models_en.Matricula.id_anio_escolar == anio_activo.id_anio_escolar
        ).first()

        if not matricula: return []

        # 1. Sus Docentes (Carga académica en su sección)
        q_docentes = db.query(models_doc.Docente).join(
            models_mn.CargaAcademica, models_mn.CargaAcademica.id_docente == models_doc.Docente.id_docente
        ).filter(
            models_mn.CargaAcademica.id_seccion == matricula.id_seccion,
            models_mn.CargaAcademica.id_anio_escolar == anio_activo.id_anio_escolar
        )
        
        # 2. Sus Compañeros (Misma sección)
        q_companheros = db.query(models_al.Alumno).join(
            models_en.Matricula, models_en.Matricula.id_alumno == models_al.Alumno.id_alumno
        ).filter(
            models_en.Matricula.id_seccion == matricula.id_seccion,
            models_en.Matricula.id_anio_escolar == anio_activo.id_anio_escolar,
            models_al.Alumno.id_usuario != id_usuario
        )

        docentes = aplicar_filtro(q_docentes, models_doc.Docente).all()
        companheros = aplicar_filtro(q_companheros, models_al.Alumno).all()

        for d in docentes:
            contactos_validos.append({"id_usuario": d.id_usuario, "nombre": f"{d.nombres} {d.apellidos}", "dni": d.dni, "rol": "DOCENTE"})
        for c in companheros:
            contactos_validos.append({"id_usuario": c.id_usuario, "nombre": f"{c.nombres} {c.apellidos}", "dni": c.dni, "rol": "ALUMNO"})

    # --- LÓGICA SI EL QUE BUSCA ES UN DOCENTE (Lo que te faltaba) ---
    elif user.rol == 'DOCENTE':
        docente = db.query(models_doc.Docente).filter(models_doc.Docente.id_usuario == id_usuario).first()
        
        # 1. Sus Alumnos (Alumnos matriculados en las secciones donde el docente dicta)
        q_alumnos = db.query(models_al.Alumno).join(
            models_en.Matricula, models_en.Matricula.id_alumno == models_al.Alumno.id_alumno
        ).join(
            models_mn.CargaAcademica, models_mn.CargaAcademica.id_seccion == models_en.Matricula.id_seccion
        ).filter(
            models_mn.CargaAcademica.id_docente == docente.id_docente,
            models_mn.CargaAcademica.id_anio_escolar == anio_activo.id_anio_escolar,
            models_en.Matricula.id_anio_escolar == anio_activo.id_anio_escolar
        ).distinct() # distinct por si un alumno está en 2 cursos con el mismo docente

        # 2. Otros Docentes (Todos los docentes del sistema según tu regla)
        q_colegas = db.query(models_doc.Docente).filter(models_doc.Docente.id_usuario != id_usuario)

        alumnos = aplicar_filtro(q_alumnos, models_al.Alumno).all()
        colegas = aplicar_filtro(q_colegas, models_doc.Docente).all()

        for a in alumnos:
            contactos_validos.append({"id_usuario": a.id_usuario, "nombre": f"{a.nombres} {a.apellidos}", "dni": a.dni, "rol": "ALUMNO"})
        for col in colegas:
            contactos_validos.append({"id_usuario": col.id_usuario, "nombre": f"{col.nombres} {col.apellidos}", "dni": col.dni, "rol": "DOCENTE"})

    return contactos_validos

@router.get("/chat/conversaciones/{id_usuario}")
def listar_conversaciones(id_usuario: int, db: Session = Depends(get_db)):
    # 1. Busca conversaciones donde el usuario participa
    convs = db.query(models.Conversacion).filter(
        or_(models.Conversacion.usuario1_id == id_usuario, 
            models.Conversacion.usuario2_id == id_usuario)
    ).order_by(models.Conversacion.fecha_actualizacion.desc()).all()
    
    resultado = []
    for c in convs:
        # Identificar quién es el "otro"
        otro_id = c.usuario2_id if c.usuario1_id == id_usuario else c.usuario1_id
        otro_usuario = db.query(models_usuario.Usuario).get(otro_id)
        
        if not otro_usuario:
            continue

        # 2. Lógica para obtener el nombre real desde Alumno o Docente
        nombre_real = "Sin nombre"
        apellidos_real = ""
        
        if otro_usuario.rol == 'DOCENTE':
            perfil = db.query(models_doc.Docente).filter(models_doc.Docente.id_usuario == otro_id).first()
            if perfil:
                nombre_real = perfil.nombres
                apellidos_real = perfil.apellidos
        elif otro_usuario.rol == 'ALUMNO':
            perfil = db.query(models_al.Alumno).filter(models_al.Alumno.id_usuario == otro_id).first()
            if perfil:
                nombre_real = perfil.nombres
                apellidos_real = perfil.apellidos
        else:
            # Fallback por si es ADMIN o FAMILIAR
            nombre_real = otro_usuario.username
            apellidos_real = ""

        # 3. Obtener último mensaje
        ultimo_msj = db.query(models.Mensaje).filter(
            models.Mensaje.id_conversacion == c.id_conversacion
        ).order_by(models.Mensaje.fecha_envio.desc()).first()

        resultado.append({
            "id": c.id_conversacion,
            "receptor_id": otro_id,
            "nombre": f"{nombre_real} {apellidos_real}".strip(),
            "rol": otro_usuario.rol,
            "ultimoMensaje": ultimo_msj.contenido if ultimo_msj else "Empieza a chatear",
            "hora": ultimo_msj.fecha_envio.strftime("%H:%M") if ultimo_msj else "",
            "iniciales": (nombre_real[0] + (apellidos_real[0] if apellidos_real else "")).upper(),
            "color": "bg-[#701C32]" if otro_usuario.rol == "DOCENTE" else "bg-blue-600",
            "mensajes": [] 
        })
        
    return resultado


@router.post("/chat/conversacion/")
def obtener_o_crear_conversacion(req: schemas.ConversacionCreate, db: Session = Depends(get_db)):
    # 1. Verificar si ya existe una conversación entre estos dos usuarios
    existente = db.query(models.Conversacion).filter(
        or_(
            (models.Conversacion.usuario1_id == req.usuario1_id) & (models.Conversacion.usuario2_id == req.usuario2_id),
            (models.Conversacion.usuario1_id == req.usuario2_id) & (models.Conversacion.usuario2_id == req.usuario1_id)
        )
    ).first()

    if existente:
        return existente

    # 2. Si no existe, crearla
    nueva = models.Conversacion(
        usuario1_id=req.usuario1_id,
        usuario2_id=req.usuario2_id,
        fecha_actualizacion=datetime.now()
    )
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva


@router.get("/chat/historial/{id_conversacion}")
def obtener_historial(id_conversacion: int, db: Session = Depends(get_db)):
    mensajes = db.query(models.Mensaje).filter(
        models.Mensaje.id_conversacion == id_conversacion
    ).order_by(models.Mensaje.fecha_envio.asc()).all()

    return [
        {
            "id": m.id_mensaje,
            "texto": m.contenido,
            "remitente_id": m.remitente_id,  # <--- Agregamos esto
            "hora": m.fecha_envio.strftime("%H:%M")
        }
        for m in mensajes
    ]