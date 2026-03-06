import os
import uuid
import shutil
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Form, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
from sqlalchemy import or_
from sqlalchemy import func
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


# 1. Obtenemos la ruta de este archivo (virtual)
FILE_DIR = os.path.dirname(os.path.abspath(__file__)) 

# 2. Subimos 3 niveles: virtual -> modules -> app -> Backend
# Esto garantiza que BASE_DIR sea la carpeta raíz del proyecto Backend
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(FILE_DIR)))

# 3. Configuramos UPLOAD_DIR (esto ahora apuntará a Backend/media/entregas_tareas)
UPLOAD_DIR = os.path.join(BASE_DIR, "media", "entregas_tareas")
DOCS_TAREAS_DIR = os.path.join(BASE_DIR, "media", "recursos_tareas")
# --- DEBUG: Añade este print temporal para estar 100% seguro ---
print(f"📂 Router configurado para guardar en: {UPLOAD_DIR}")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DOCS_TAREAS_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png"}
# Definición de la constante (10 MB)
MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


router = APIRouter(prefix="/virtual", tags=["Aula Virtual"])


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

#--- Tareas
@router.post("/tareas/", response_model=schemas.TareaResponse)
async def crear_tarea(
    id_carga_academica: int = Form(...),
    titulo: str = Form(...),
    descripcion: Optional[str] = Form(None),
    fecha_entrega: datetime = Form(...),
    tipo_evaluacion: str = Form("TAREA"),
    bimestre: int = Form(...),
    peso: int = Form(0),
    archivo: Optional[UploadFile] = File(None), # <-- Archivo opcional del docente
    db: Session = Depends(get_db)
):
    # 1. Validar existencia de Carga Académica
    carga = db.query(models_mn.CargaAcademica).filter(
        models_mn.CargaAcademica.id_carga_academica == id_carga_academica
    ).first()
    if not carga:
        raise HTTPException(status_code=404, detail="La carga académica no existe.")

    # 2. Validación de Peso Máximo (Manteniendo tu lógica original)
    peso_actual = db.query(func.sum(models.Tarea.peso)).filter(
        models.Tarea.id_carga_academica == id_carga_academica,
        models.Tarea.bimestre == bimestre,
        models.Tarea.estado == "ACTIVO"
    ).scalar() or 0

    if peso_actual + peso > 100:
        raise HTTPException(
            status_code=400, 
            detail=f"El peso acumulado ({peso_actual + peso}%) excede el 100% del bimestre."
        )

    # 3. Procesamiento del Archivo (Si el docente lo subió)
    url_adjunto = None
    if archivo and archivo.filename:
        # Validar extensión
        ext = os.path.splitext(archivo.filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail="Tipo de archivo no permitido.")

        # Definir ruta: media/recursos_tareas/carga_X/
        rel_folder = os.path.join("media", "recursos_tareas", f"carga_{id_carga_academica}")
        abs_folder = os.path.join(BASE_DIR, rel_folder)
        os.makedirs(abs_folder, exist_ok=True)

        # Nombre único para evitar colisiones
        filename = f"ref_{uuid.uuid4().hex[:6]}{ext}"
        file_path = os.path.join(abs_folder, filename)

        # Guardado físico
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(archivo.file, buffer)
        
        url_adjunto = f"/{rel_folder}/{filename}".replace("\\", "/")

    # 4. Crear registro en BD
    nueva_tarea = models.Tarea(
        id_carga_academica=id_carga_academica,
        titulo=titulo,
        descripcion=descripcion,
        fecha_entrega=fecha_entrega,
        tipo_evaluacion=tipo_evaluacion,
        bimestre=bimestre,
        peso=peso,
        archivo_adjunto_url=url_adjunto, # <-- Guardamos la ruta
        fecha_publicacion=datetime.now(),
        estado="ACTIVO"
    )
    
    db.add(nueva_tarea)
    db.commit()
    db.refresh(nueva_tarea)
    return nueva_tarea

@router.get("/sabana-notas/{id_carga}/{bimestre}", response_model=schemas.SabanaNotasResponse)
def obtener_sabana_notas(id_carga: int, bimestre: int, db: Session = Depends(get_db)):
    
    # 1. Obtener la información de la carga académica
    carga = db.query(models_mn.CargaAcademica).filter(models_mn.CargaAcademica.id_carga_academica == id_carga).first()
    if not carga:
        raise HTTPException(status_code=404, detail="Carga académica no encontrada")

    # 2. Obtener los alumnos matriculados
    alumnos = db.query(models_al.Alumno).join(
        models_en.Matricula, models_al.Alumno.id_alumno == models_en.Matricula.id_alumno
    ).filter(
        models_en.Matricula.id_seccion == carga.id_seccion,
        models_en.Matricula.id_anio_escolar == carga.id_anio_escolar
    ).order_by(models_al.Alumno.apellidos).all()

    # 3. Obtener tareas
    tareas = db.query(models.Tarea).filter(
        models.Tarea.id_carga_academica == id_carga,
        models.Tarea.bimestre == bimestre,
        models.Tarea.estado == "ACTIVO"
    ).order_by(models.Tarea.fecha_publicacion).all()

    # --- NUEVA LÓGICA PARA EVALUACIONES ---
    lista_evaluaciones = []
    for t in tareas:
        # Contar cuántos archivos se han subido para esta tarea
        entregas_con_archivo = [e for e in t.entregas if e.archivo_url]
        conteo_envios = len(entregas_con_archivo)

        lista_evaluaciones.append({
            "id_tarea": t.id_tarea,
            "titulo": t.titulo,
            "tipo": t.tipo_evaluacion,
            "descripcion": t.descripcion,
            "fecha_entrega": t.fecha_entrega,
            "bimestre": t.bimestre,
            "peso": t.peso,
            "total_entregas": conteo_envios,
            "editable_total": conteo_envios == 0,  
            "archivo_adjunto_url": t.archivo_adjunto_url
        })

    # 4. Construir la respuesta de alumnos (Mantenemos tu lógica de promedios)
    resultado_alumnos = []
    for alumno in alumnos:
        dict_notas = {}
        promedio_final = 0.0

        for tarea in tareas:
            entrega = db.query(models.EntregaTarea).filter(
                models.EntregaTarea.id_tarea == tarea.id_tarea,
                models.EntregaTarea.id_alumno == alumno.id_alumno
            ).first()

            valor_nota = float(entrega.calificacion) if entrega and entrega.calificacion else 0.0
            dict_notas[str(tarea.id_tarea)] = valor_nota
            
            # --- LÓGICA DE PESOS ---
            # Si la tarea vale 20%, multiplicamos nota * 0.20
            promedio_final += (valor_nota * (tarea.peso / 100.0))

        resultado_alumnos.append({
            "id_alumno": alumno.id_alumno,
            "nombres_completos": f"{alumno.apellidos}, {alumno.nombres}",
            "notas": dict_notas,
            "promedio": round(promedio_final, 2)
        })

    return {
        "evaluaciones": lista_evaluaciones,
        "alumnos_notas": resultado_alumnos
    }

@router.post("/guardar-notas-masivo/")
def guardar_notas_masivo(payload: schemas.NotasMasivasCreate, db: Session = Depends(get_db)):
    """
    Se espera un payload como: 
    { "id_tarea": 10, "notas": { "id_alumno_1": 15, "id_alumno_2": 20 } }
    """
    id_tarea = payload.id_tarea
    notas = payload.notas

    for id_alumno_str, calificacion in notas.items():
        id_alumno = int(id_alumno_str)
        # Buscar si ya existe una entrega para actualizarla, sino crearla
        entrega = db.query(models.EntregaTarea).filter(
            models.EntregaTarea.id_tarea == id_tarea,
            models.EntregaTarea.id_alumno == int(id_alumno)
        ).first()

        if entrega:
            entrega.calificacion = calificacion
            entrega.fecha_envio = datetime.now() # Opcional: marcar actualización
        else:
            nueva_entrega = models.EntregaTarea(
                id_tarea=id_tarea,
                id_alumno=int(id_alumno),
                calificacion=calificacion
            )
            db.add(nueva_entrega)
    
    db.commit()
    return {"message": "Notas actualizadas correctamente"}

@router.put("/calificar-entrega/{id_entrega}")
def calificar_entrega(id_entrega: int, calificacion: float, retroalimentacion: str = None, db: Session = Depends(get_db)):
    entrega = db.query(models.EntregaTarea).filter(models.EntregaTarea.id_entrega == id_entrega).first()
    if not entrega:
        raise HTTPException(status_code=404, detail="Entrega no encontrada")
    
    entrega.calificacion = calificacion
    entrega.retroalimentacion_docente = retroalimentacion
    db.commit()
    return {"message": "Calificación registrada con éxito"}

@router.get("/mis-notas/{id_carga}/{id_alumno}")
def obtener_mis_notas(id_carga: int, id_alumno: int, db: Session = Depends(get_db)):
    # Trae todas las tareas del curso
    tareas = db.query(models.Tarea).filter(models.Tarea.id_carga_academica == id_carga).all()
    
    notas_detalle = []
    for t in tareas:
        entrega = db.query(models.EntregaTarea).filter(
            models.EntregaTarea.id_tarea == t.id_tarea,
            models.EntregaTarea.id_alumno == id_alumno
        ).first()
        
        notas_detalle.append({
            "tarea": t.titulo,
            "tipo": t.tipo_evaluacion,
            "nota": float(entrega.calificacion) if entrega and entrega.calificacion else None,
            "fecha_entrega": t.fecha_entrega
        })
    
    return notas_detalle


@router.put("/tareas/{id_tarea}", response_model=schemas.TareaResponse)
async def editar_tarea(
    id_tarea: int,
    titulo: str = Form(...),
    descripcion: Optional[str] = Form(None),
    fecha_entrega: datetime = Form(...),
    tipo_evaluacion: str = Form(...),
    bimestre: int = Form(...),
    peso: int = Form(...),
    archivo: Optional[UploadFile] = File(None), # Nuevo archivo opcional
    db: Session = Depends(get_db)
):
    tarea = db.query(models.Tarea).filter(models.Tarea.id_tarea == id_tarea).first()
    if not tarea:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")

    # 1. Verificar si hay entregas de alumnos
    tiene_entregas = any(e.archivo_url for e in tarea.entregas)

    if tiene_entregas:
        # Bloqueo parcial: Solo permitimos cambiar la fecha si ya hay alumnos que entregaron
        tarea.fecha_entrega = fecha_entrega
        db.commit()
        return tarea

    # 2. Gestión del archivo adjunto del docente (si se sube uno nuevo)
    if archivo and archivo.filename:
        # Borrar el archivo físico anterior si existía
        if tarea.archivo_adjunto_url:
            old_path = os.path.join(BASE_DIR, tarea.archivo_adjunto_url.lstrip("/"))
            if os.path.exists(old_path):
                try: os.remove(old_path)
                except: pass

        # Guardar el nuevo archivo
        rel_folder = os.path.join("media", "recursos_tareas", f"carga_{tarea.id_carga_academica}")
        abs_folder = os.path.join(BASE_DIR, rel_folder)
        os.makedirs(abs_folder, exist_ok=True)
        
        ext = os.path.splitext(archivo.filename)[1].lower()
        filename = f"ref_{uuid.uuid4().hex[:6]}{ext}"
        file_path = os.path.join(abs_folder, filename)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(archivo.file, buffer)
        
        tarea.archivo_adjunto_url = f"/{rel_folder}/{filename}".replace("\\", "/")

    # 3. Actualizar campos de texto
    tarea.titulo = titulo
    tarea.descripcion = descripcion
    tarea.fecha_entrega = fecha_entrega
    tarea.tipo_evaluacion = tipo_evaluacion
    tarea.bimestre = bimestre
    tarea.peso = peso
    
    db.commit()
    db.refresh(tarea)
    return tarea

@router.delete("/tareas/{id_tarea}")
def eliminar_tarea(id_tarea: int, db: Session = Depends(get_db)):
    tarea = db.get(models.Tarea, id_tarea)
    if not tarea:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")

    # 1. Bloqueo de seguridad: No borrar si alumnos ya subieron archivos
    if any(e.archivo_url for e in tarea.entregas):
        raise HTTPException(
            status_code=400, 
            detail="No se puede eliminar: Alumnos ya han subido archivos."
        )

    # 2. Borrar archivo físico del DOCENTE (el recurso adjunto)
    if tarea.archivo_adjunto_url:
        full_path = os.path.join(BASE_DIR, tarea.archivo_adjunto_url.lstrip("/"))
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
            except Exception as e:
                print(f"Error al borrar archivo de tarea: {e}")

    # 3. Eliminar de la base de datos
    db.delete(tarea)
    db.commit()
    return {"message": "Actividad y recursos eliminados con éxito"}

@router.get("/tareas/{id_tarea}/entregas", response_model=List[schemas.EntregaDetalleResponse])
def listar_entregas_con_archivos(id_tarea: int, db: Session = Depends(get_db)):
    # Buscamos directamente en entregas usando la relación cargada
    entregas = db.query(models.EntregaTarea).filter(
        models.EntregaTarea.id_tarea == id_tarea,
        models.EntregaTarea.archivo_url != None
    ).all()

    return [
        {
            "id_entrega": e.id_entrega,
            "alumno": f"{e.alumno.apellidos}, {e.alumno.nombres}", # Usamos la relación
            "archivo_url": e.archivo_url,
            "comentario": e.comentario_alumno,
            "fecha_envio": e.fecha_envio.strftime("%d/%m/%Y %H:%M"),
            "calificacion": e.calificacion
        } for e in entregas
    ]

@router.get("/tareas/{id_tarea}", response_model=schemas.TareaResponse)
def obtener_detalle_tarea(id_tarea: int, db: Session = Depends(get_db)):
    tarea = db.query(models.Tarea).filter(models.Tarea.id_tarea == id_tarea).first()
    if not tarea:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    return tarea

@router.post("/entregar-tarea/")
async def entregar_tarea(
    id_tarea: int = Form(...),
    id_usuario: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    # 1. VALIDACIÓN PREVIA: ¿Existe la tarea y el alumno?
    tarea_existe = db.query(models.Tarea).filter(models.Tarea.id_tarea == id_tarea).first()
    if not tarea_existe:
        raise HTTPException(status_code=404, detail="La tarea no existe.")

    alumno = db.query(models_al.Alumno).filter(models_al.Alumno.id_usuario == id_usuario).first()
    if not alumno:
        raise HTTPException(status_code=404, detail="Perfil de alumno no encontrado")

    # 2. VALIDACIONES DE ARCHIVO
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Formato {file_ext} no permitido.")

    # --- SOLUCIÓN DEFINITIVA ---
    # Accedemos a file.file (objeto SpooledTemporaryFile de Python) 
    # que sí acepta 2 argumentos en seek()
    file.file.seek(0, 2) 
    file_size = file.file.tell()
    file.file.seek(0)

    if file_size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail=f"El archivo es muy grande ({round(file_size/1024/1024, 2)}MB). Máximo 10MB.")

    # 3. GESTIÓN DE DIRECTORIOS
    relative_folder = os.path.join("media", "entregas_tareas", f"tarea_{id_tarea}")
    absolute_folder = os.path.join(BASE_DIR, relative_folder)
    
    # Asegurar que los directorios existan
    try:
        os.makedirs(absolute_folder, exist_ok=True)
    except Exception as e:
        print(f"Error creando carpetas: {e}")
        raise HTTPException(status_code=500, detail="Error de permisos en el servidor.")

    # Nombre único para evitar colisiones
    unique_filename = f"alu_{alumno.id_alumno}_{uuid.uuid4().hex[:8]}{file_ext}"
    file_path = os.path.join(absolute_folder, unique_filename)

    # 4. GUARDADO FÍSICO
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        print(f"Error al guardar archivo: {e}")
        raise HTTPException(status_code=500, detail="Error al escribir el archivo en disco.")

    # 5. ACTUALIZACIÓN DE BASE DE DATOS
    entrega = db.query(models.EntregaTarea).filter(
        models.EntregaTarea.id_tarea == id_tarea,
        models.EntregaTarea.id_alumno == alumno.id_alumno
    ).first()

    url_db = f"/{relative_folder}/{unique_filename}".replace("\\", "/")

    if entrega:
        # Borrar archivo físico anterior si existe para no llenar el disco de basura
        if entrega.archivo_url:
            old_file_path = os.path.join(BASE_DIR, entrega.archivo_url.lstrip("/"))
            if os.path.exists(old_file_path):
                try:
                    os.remove(old_file_path)
                except:
                    pass 
        
        entrega.archivo_url = url_db
        entrega.fecha_envio = datetime.now()
    else:
        entrega = models.EntregaTarea(
            id_tarea=id_tarea,
            id_alumno=alumno.id_alumno,
            archivo_url=url_db,
            fecha_envio=datetime.now()
        )
        db.add(entrega)

    db.commit()
    return {"message": "Tarea subida exitosamente", "url": url_db}

@router.get("/tareas/{id_tarea}/{id_usuario}")
def obtener_detalle_tarea_estudiante(id_tarea: int, id_usuario: int, db: Session = Depends(get_db)):
    # 1. Buscar la tarea básica
    tarea = db.query(models.Tarea).filter(models.Tarea.id_tarea == id_tarea).first()
    if not tarea:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")

    # 2. Buscar si el alumno ya tiene una entrega para esta tarea
    # Primero necesitamos el id_alumno a partir del id_usuario
    alumno = db.query(models_al.Alumno).filter(models_al.Alumno.id_usuario == id_usuario).first()
    
    entrega = None
    if alumno:
        entrega = db.query(models.EntregaTarea).filter(
            models.EntregaTarea.id_tarea == id_tarea,
            models.EntregaTarea.id_alumno == alumno.id_alumno
        ).first()

    # 3. Construimos una respuesta combinada
    return {
        "id_tarea": tarea.id_tarea,
        "titulo": tarea.titulo,
        "descripcion": tarea.descripcion,
        "fecha_entrega": tarea.fecha_entrega,
        "bimestre": tarea.bimestre,
        "entregado": True if (entrega and entrega.archivo_url) else False,
        "nota": entrega.calificacion if entrega else None,
        "peso": tarea.peso,
        "archivo_adjunto_url": tarea.archivo_adjunto_url,
        "retroalimentacion_docente": entrega.retroalimentacion_docente if entrega else None,
        "archivo_url": entrega.archivo_url if entrega else None
    }

@router.get("/api/dashboard/estudiante/{id_usuario}")
def obtener_dashboard_estudiante(id_usuario: int, db: Session = Depends(get_db)):
    # --- NUEVO: Buscar el año escolar activo ---
    anio_activo = db.query(models_ac.AnioEscolar).filter(models_ac.AnioEscolar.activo == True).first()
    
    if not anio_activo:
        raise HTTPException(status_code=404, detail="No hay un año escolar activo configurado")
    
    # Usamos el id del año escolar (o el campo 'nombre'/'anio' según tu modelo)
    id_anio = anio_activo.id_anio_escolar 
    # -------------------------------------------

    # 1. Buscar alumno
    alumno = db.query(models_al.Alumno).filter(models_al.Alumno.id_usuario == id_usuario).first()
    if not alumno:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    # 2. Obtenemos los cursos usando el id_anio dinámico
    cursos_query = (
        db.query(
            models_ac.Curso.id_curso,
            models_ac.Curso.nombre.label("curso_nombre"),
            models_mn.CargaAcademica.id_carga_academica,
            models_doc.Docente.nombres.label("docente_nombres"),
            models_doc.Docente.apellidos.label("docente_apellidos")
        )
        .select_from(models_en.Matricula)
        .join(models_ac.Seccion, models_ac.Seccion.id_seccion == models_en.Matricula.id_seccion)
        .join(models_ac.Grado, models_ac.Grado.id_grado == models_ac.Seccion.id_grado)
        .join(models_ac.PlanEstudio, models_ac.PlanEstudio.id_grado == models_ac.Grado.id_grado)
        .join(models_ac.Curso, models_ac.Curso.id_curso == models_ac.PlanEstudio.id_curso)
        .outerjoin(models_mn.CargaAcademica, 
            (models_mn.CargaAcademica.id_curso == models_ac.Curso.id_curso) & 
            (models_mn.CargaAcademica.id_seccion == models_en.Matricula.id_seccion) &
            (models_mn.CargaAcademica.id_anio_escolar == id_anio) # <--- Usamos el ID dinámico
        )
        .outerjoin(models_doc.Docente, models_mn.CargaAcademica.id_docente == models_doc.Docente.id_docente)
        .filter(
            models_en.Matricula.id_alumno == alumno.id_alumno, 
            models_en.Matricula.id_anio_escolar == id_anio # <--- Usamos el ID dinámico
        )
        .all()
    )

    lista_cursos = []
    lista_tareas = []

    for c in cursos_query:
        # A. Agregar al listado de cursos
        lista_cursos.append({
            "id_curso": c.id_curso,
            "nombre": c.curso_nombre,
            "docente": f"{c.docente_nombres or ''} {c.docente_apellidos or ''}".strip()
        })

        # B. Buscar tareas usando el id_carga_academica obtenido en la query
        if c.id_carga_academica:
            tareas = db.query(models.Tarea).filter(
                models.Tarea.id_carga_academica == c.id_carga_academica,
                models.Tarea.fecha_entrega >= datetime.now()
            ).all()

            for t in tareas:
                # Verificar entrega
                entrega = db.query(models.EntregaTarea).filter(
                    models.EntregaTarea.id_tarea == t.id_tarea,
                    models.EntregaTarea.id_alumno == alumno.id_alumno
                ).first()
                
                if not entrega:
                    lista_tareas.append({
                        "id_tarea": t.id_tarea,
                        "curso": c.curso_nombre,
                        "titulo": t.titulo,
                        "fecha_entrega": t.fecha_entrega
                    })

    return {
        "nombre_completo": f"{alumno.nombres} {alumno.apellidos}",
        "cursos": lista_cursos,
        "tareas_pendientes": lista_tareas,
        "anio_actual": anio_activo.id_anio_escolar
    }

