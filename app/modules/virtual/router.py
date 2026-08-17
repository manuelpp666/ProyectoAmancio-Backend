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
from app.modules.personal import models as models_psi
from app.core.util.security import get_current_user, ensure_owner_or_roles
from . import models, schemas


# 1. Obtenemos la ruta de este archivo (virtual)
FILE_DIR = os.path.dirname(os.path.abspath(__file__)) 

# 2. Subimos 3 niveles: virtual -> modules -> app -> Backend
# Esto garantiza que BASE_DIR sea la carpeta raíz del proyecto Backend
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(FILE_DIR)))

# 3. Configuramos UPLOAD_DIR (esto ahora apuntará a Backend/media/entregas_tareas)
UPLOAD_DIR = os.path.join(BASE_DIR, "media", "entregas_tareas")
DOCS_TAREAS_DIR = os.path.join(BASE_DIR, "media", "recursos_tareas")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DOCS_TAREAS_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png"}
# Definición de la constante (10 MB)
MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


router = APIRouter(prefix="/virtual", tags=["Aula Virtual"])


# ===========================================================================
# REGLAS DE MENSAJERÍA
# ===========================================================================
# A quién puede ESCRIBIR PRIMERO cada rol. La secretaría del colegio trabaja
# con cuenta de ADMIN, por eso ADMIN alcanza a todos.
#
# Las parejas alumno–docente además exigen vínculo académico: el docente tiene
# que dictar en la sección del alumno en el año escolar activo.
DESTINATARIOS_POR_ROL = {
    "ADMIN":     {"ADMIN", "DOCENTE", "ALUMNO", "PSICOLOGO", "AUXILIAR"},
    "ALUMNO":    {"DOCENTE", "PSICOLOGO"},
    "DOCENTE":   {"ALUMNO", "DOCENTE", "PSICOLOGO", "AUXILIAR"},
    "AUXILIAR":  {"DOCENTE"},
    "PSICOLOGO": {"ALUMNO", "DOCENTE", "PSICOLOGO"},
}

# Dónde vive el nombre real de cada rol. La cuenta (`usuario`) solo guarda el
# username; los nombres y apellidos están en la ficha de cada rol.
PERFIL_POR_ROL = {
    "ALUMNO": models_al.Alumno,
    "DOCENTE": models_doc.Docente,
    "PSICOLOGO": models_psi.Psicologo,
    "AUXILIAR": models_psi.Auxiliar,
    "ADMIN": models_psi.Administrador,
}


def nombre_de(db, usuario):
    """
    Nombre y apellidos reales de una cuenta.

    Se consulta siempre por aquí para que ningún rol acabe mostrándose por su
    username: en la lista de conversaciones, ADMIN y AUXILIAR no estaban
    contemplados y salían como "ADM-73193257" en lugar de la persona.
    """
    modelo = PERFIL_POR_ROL.get(usuario.rol) if usuario else None
    if modelo:
        perfil = db.query(modelo).filter(modelo.id_usuario == usuario.id_usuario).first()
        if perfil:
            return (perfil.nombres or "").strip(), (perfil.apellidos or "").strip()
    # Cuenta sin ficha: se muestra el username antes que dejarlo en blanco
    return (usuario.username if usuario else "Sin nombre"), ""


def _hay_vinculo_academico(db, usuario_docente, usuario_alumno, anio_activo) -> bool:
    """¿El docente dicta en la sección donde está matriculado el alumno?"""
    docente = db.query(models_doc.Docente).filter(
        models_doc.Docente.id_usuario == usuario_docente.id_usuario
    ).first()
    alumno = db.query(models_al.Alumno).filter(
        models_al.Alumno.id_usuario == usuario_alumno.id_usuario
    ).first()
    if not docente or not alumno:
        return False

    return db.query(models_mn.CargaAcademica).join(
        models_en.Matricula,
        models_en.Matricula.id_seccion == models_mn.CargaAcademica.id_seccion,
    ).filter(
        models_mn.CargaAcademica.id_docente == docente.id_docente,
        models_mn.CargaAcademica.id_anio_escolar == anio_activo.id_anio_escolar,
        models_en.Matricula.id_alumno == alumno.id_alumno,
        models_en.Matricula.id_anio_escolar == anio_activo.id_anio_escolar,
    ).first() is not None


def puede_iniciar(db, emisor, receptor, anio_activo) -> bool:
    """¿`emisor` puede abrir una conversación con `receptor`?"""
    if not emisor or not receptor or emisor.id_usuario == receptor.id_usuario:
        return False
    if receptor.rol not in DESTINATARIOS_POR_ROL.get(emisor.rol, set()):
        return False

    # Alumno y docente solo si comparten aula
    if {emisor.rol, receptor.rol} == {"ALUMNO", "DOCENTE"}:
        docente, alumno = (emisor, receptor) if emisor.rol == "DOCENTE" else (receptor, emisor)
        return _hay_vinculo_academico(db, docente, alumno, anio_activo)

    return True


def puede_conversar(db, uno, otro, anio_activo) -> bool:
    """
    ¿Pueden intercambiar mensajes en una conversación ya abierta?

    Basta con que a alguno de los dos se le permita iniciarla. Así el alumno
    contesta al administrador que le escribió, aunque él no pueda escribirle
    primero: sin esto quedarían conversaciones donde una parte no responde.
    """
    return (puede_iniciar(db, uno, otro, anio_activo)
            or puede_iniciar(db, otro, uno, anio_activo))


@router.post("/chat/mensaje/")
async def enviar_mensaje(mensaje: schemas.MensajeCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    
    # El remitente SIEMPRE debe ser el usuario autenticado: impide enviar
    # mensajes suplantando a otra persona (spoofing de remitente_id).
    if current_user.get("id") != mensaje.remitente_id:
        raise HTTPException(status_code=403, detail="No autorizado para enviar este mensaje")

    conv = db.query(models.Conversacion).filter(models.Conversacion.id_conversacion == mensaje.id_conversacion).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    # El remitente debe ser uno de los dos participantes de la conversación
    if mensaje.remitente_id not in (conv.usuario1_id, conv.usuario2_id):
        raise HTTPException(status_code=403, detail="No perteneces a esta conversación")

    receptor_id = conv.usuario2_id if mensaje.remitente_id == conv.usuario1_id else conv.usuario1_id
    
    remitente = db.query(models_usuario.Usuario).filter(models_usuario.Usuario.id_usuario == mensaje.remitente_id).first()
    receptor = db.query(models_usuario.Usuario).filter(models_usuario.Usuario.id_usuario == receptor_id).first()
    
    anio_activo = db.query(models_ac.AnioEscolar).filter(models_ac.AnioEscolar.activo == 1).first()
    if not anio_activo:
        raise HTTPException(status_code=400, detail="No hay un año escolar activo")

    if not puede_conversar(db, remitente, receptor, anio_activo):
        raise HTTPException(
            status_code=403,
            detail="No puedes intercambiar mensajes con este usuario.",
        )

    # Persistencia y Notificación (se mantiene igual)
    nuevo_mensaje = models.Mensaje(**mensaje.model_dump())
    db.add(nuevo_mensaje)
    conv.ultimo_mensaje = mensaje.contenido
    conv.fecha_actualizacion = datetime.now()
    db.commit()
    db.refresh(nuevo_mensaje)

    payload = {
        "tipo": "NUEVO_MENSAJE",
        "data": {
            # El id real del mensaje: el front lo necesita para no pintar dos
            # veces lo que ya recibió (por el socket y por la consulta
            # periódica de respaldo, que pueden solaparse).
            "id_mensaje": nuevo_mensaje.id_mensaje,
            "id_conversacion": mensaje.id_conversacion,
            "contenido": mensaje.contenido,
            "remitente_id": mensaje.remitente_id,
            "fecha_envio": nuevo_mensaje.fecha_envio.strftime("%H:%M")
        }
    }
    await socket_manager.send_personal_message(receptor_id, payload)

    # Se devuelve un diccionario explícito en vez del modelo de SQLAlchemy: el
    # front necesita id_mensaje para pintar el mensaje con su id real (y no
    # duplicarlo cuando llegue por el socket o por el sondeo de respaldo), y
    # serializar el modelo directamente depende de detalles internos del ORM.
    return {
        "id_mensaje": nuevo_mensaje.id_mensaje,
        "id_conversacion": nuevo_mensaje.id_conversacion,
        "remitente_id": nuevo_mensaje.remitente_id,
        "contenido": nuevo_mensaje.contenido,
        "leido": bool(nuevo_mensaje.leido),
        "fecha_envio": nuevo_mensaje.fecha_envio.isoformat() if nuevo_mensaje.fecha_envio else None,
        "hora": nuevo_mensaje.fecha_envio.strftime("%H:%M") if nuevo_mensaje.fecha_envio else None,
    }


@router.get("/chat/contactos/{id_usuario}")
def buscar_contactos(id_usuario: int, query: str = None, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") not in ["ADMIN", "DOCENTE", "PSICOLOGO"] and current_user.get("id") != id_usuario:
        raise HTTPException(status_code=403, detail="No puedes ver perfiles ajenos")
    
    user = db.query(models_usuario.Usuario).get(id_usuario)
    anio_activo = db.query(models_ac.AnioEscolar).filter(models_ac.AnioEscolar.activo == 1).first()
    
    if not anio_activo or not user: return []

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

    # Solo se listan los roles que este usuario tiene permitido contactar
    permitidos = DESTINATARIOS_POR_ROL.get(user.rol, set())

    # Alumno y docente se ven únicamente si comparten aula: se resuelve con una
    # consulta acotada en vez de traer a todos y descartar uno por uno.
    seccion_alumno = None
    id_docente = None
    if user.rol == "ALUMNO":
        alumno = db.query(models_al.Alumno).filter(models_al.Alumno.id_usuario == id_usuario).first()
        if alumno:
            matricula = db.query(models_en.Matricula).filter(
                models_en.Matricula.id_alumno == alumno.id_alumno,
                models_en.Matricula.id_anio_escolar == anio_activo.id_anio_escolar,
            ).first()
            seccion_alumno = matricula.id_seccion if matricula else None
    elif user.rol == "DOCENTE":
        docente = db.query(models_doc.Docente).filter(models_doc.Docente.id_usuario == id_usuario).first()
        id_docente = docente.id_docente if docente else None

    contactos_validos = []
    for rol_destino in sorted(permitidos):
        modelo = PERFIL_POR_ROL[rol_destino]
        q = db.query(modelo).filter(modelo.id_usuario != id_usuario)

        if user.rol == "ALUMNO" and rol_destino == "DOCENTE":
            if seccion_alumno is None:
                continue  # sin matrícula activa no tiene docentes asignados
            q = q.join(
                models_mn.CargaAcademica,
                models_mn.CargaAcademica.id_docente == models_doc.Docente.id_docente,
            ).filter(
                models_mn.CargaAcademica.id_seccion == seccion_alumno,
                models_mn.CargaAcademica.id_anio_escolar == anio_activo.id_anio_escolar,
            ).distinct()

        elif user.rol == "DOCENTE" and rol_destino == "ALUMNO":
            if id_docente is None:
                continue
            q = q.join(
                models_en.Matricula,
                models_en.Matricula.id_alumno == models_al.Alumno.id_alumno,
            ).join(
                models_mn.CargaAcademica,
                models_mn.CargaAcademica.id_seccion == models_en.Matricula.id_seccion,
            ).filter(
                models_mn.CargaAcademica.id_docente == id_docente,
                models_mn.CargaAcademica.id_anio_escolar == anio_activo.id_anio_escolar,
                models_en.Matricula.id_anio_escolar == anio_activo.id_anio_escolar,
            ).distinct()

        for p in aplicar_filtro(q, modelo).all():
            contactos_validos.append({
                "id_usuario": p.id_usuario,
                "nombre": f"{p.nombres} {p.apellidos}",
                "dni": p.dni,
                "rol": rol_destino,
            })

    return contactos_validos

@router.get("/chat/conversaciones/{id_usuario}")
def listar_conversaciones(id_usuario: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    
    ensure_owner_or_roles(current_user, id_usuario, "ADMIN")

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

        # 2. Nombre real de la persona (nunca su username)
        nombre_real, apellidos_real = nombre_de(db, otro_usuario)

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
            # Sin el guardia, un perfil con el nombre vacío rompía la lista entera
            "iniciales": ((nombre_real[:1]) + (apellidos_real[:1])).upper() or "?",
            "color": "bg-[#701C32]" if otro_usuario.rol == "DOCENTE" else "bg-blue-600",
            "mensajes": [] 
        })
        
    return resultado


@router.post("/chat/conversacion/")
def obtener_o_crear_conversacion(req: schemas.ConversacionCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):

    # Solo puede crearla un ADMIN o uno de los dos participantes de la conversación
    if current_user.get("rol") != "ADMIN" and current_user.get("id") not in [req.usuario1_id, req.usuario2_id]:
        raise HTTPException(status_code=403, detail="No puedes modificar esta información")

    # 1. Verificar si ya existe una conversación entre estos dos usuarios
    existente = db.query(models.Conversacion).filter(
        or_(
            (models.Conversacion.usuario1_id == req.usuario1_id) & (models.Conversacion.usuario2_id == req.usuario2_id),
            (models.Conversacion.usuario1_id == req.usuario2_id) & (models.Conversacion.usuario2_id == req.usuario1_id)
        )
    ).first()

    if existente:
        return existente

    # 2. Antes de abrir una conversación nueva se comprueban las mismas reglas
    #    que al enviar. Sin esto quedaban chats vacíos entre personas que
    #    después no podían escribirse.
    anio_activo = db.query(models_ac.AnioEscolar).filter(models_ac.AnioEscolar.activo == 1).first()
    if not anio_activo:
        raise HTTPException(status_code=400, detail="No hay un año escolar activo")

    uno = db.query(models_usuario.Usuario).get(req.usuario1_id)
    otro = db.query(models_usuario.Usuario).get(req.usuario2_id)
    if not uno or not otro:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if not puede_conversar(db, uno, otro, anio_activo):
        raise HTTPException(
            status_code=403,
            detail="No puedes iniciar una conversación con este usuario.",
        )

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
def obtener_historial(
    id_conversacion: int,
    desde_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Mensajes de una conversación.

    Con `desde_id` devuelve solo los posteriores a ese mensaje. Es lo que usa el
    chat para preguntar "¿hay algo nuevo?" cada pocos segundos cuando el
    WebSocket no está disponible (ver el hook useChat en el front): sin esto
    cada consulta reenviaría la conversación entera, y con ~500 cuentas eso es
    mucho tráfico para nada.

    El filtro va por id_mensaje y no por fecha porque el id es autoincremental:
    dos mensajes escritos en el mismo segundo no se pierden ni se repiten.
    Sin el parámetro se comporta igual que antes, así que el front viejo sigue
    funcionando contra este backend.
    """
    conv = db.query(models.Conversacion).filter(models.Conversacion.id_conversacion == id_conversacion).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    # Solo el ADMIN o los participantes de la conversación pueden ver el historial
    if current_user.get("rol") != "ADMIN" and current_user.get("id") not in [conv.usuario1_id, conv.usuario2_id]:
        raise HTTPException(status_code=403, detail="No puedes ver esta información")

    consulta = db.query(models.Mensaje).filter(
        models.Mensaje.id_conversacion == id_conversacion
    )
    if desde_id:
        consulta = consulta.filter(models.Mensaje.id_mensaje > desde_id)

    mensajes = consulta.order_by(models.Mensaje.id_mensaje.asc()).all()

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
    fecha_entrega: Optional[datetime] = Form(None),
    tipo_evaluacion: str = Form("TAREA"),
    bimestre: int = Form(...),
    peso: int = Form(0),
    archivo: Optional[UploadFile] = File(None), # <-- Archivo opcional del docente
    db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    if current_user.get("rol") != "DOCENTE":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información")

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

@router.get("/curso-docente-detalle/{id_carga}")
def obtener_detalle_curso_docente(id_carga: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "DOCENTE":
        raise HTTPException(status_code=403, detail="No puedes acceder a esta información.")

    # 1. Carga académica con información del curso, sección, grado y docente
    carga = (
        db.query(
            models_mn.CargaAcademica.id_carga_academica,
            models_ac.Curso.nombre.label("curso_nombre"),
            models_ac.Grado.nombre.label("grado_nombre"),
            models_ac.Seccion.nombre.label("seccion_nombre"),
            models_ac.Seccion.id_seccion,
            models_mn.CargaAcademica.id_anio_escolar,
            models_doc.Docente.nombres.label("docente_nombres"),
            models_doc.Docente.apellidos.label("docente_apellidos"),
        )
        .join(models_ac.Curso, models_mn.CargaAcademica.id_curso == models_ac.Curso.id_curso)
        .join(models_ac.Seccion, models_mn.CargaAcademica.id_seccion == models_ac.Seccion.id_seccion)
        .join(models_ac.Grado, models_ac.Seccion.id_grado == models_ac.Grado.id_grado)
        .outerjoin(models_doc.Docente, models_mn.CargaAcademica.id_docente == models_doc.Docente.id_docente)
        .filter(models_mn.CargaAcademica.id_carga_academica == id_carga)
        .first()
    )
    if not carga:
        raise HTTPException(status_code=404, detail="Carga académica no encontrada")

    # 2. Total de alumnos matriculados activos en la sección
    num_alumnos = (
        db.query(func.count(models_en.Matricula.id_alumno))
        .join(models_al.Alumno, models_al.Alumno.id_alumno == models_en.Matricula.id_alumno)
        .filter(
            models_en.Matricula.id_seccion == carga.id_seccion,
            models_en.Matricula.id_anio_escolar == carga.id_anio_escolar,
            models_al.Alumno.estado_ingreso != "RETIRADO"
        )
        .scalar() or 0
    )

    # 3. Todas las tareas/evaluaciones activas del curso (los 4 bimestres)
    tareas = db.query(models.Tarea).filter(
        models.Tarea.id_carga_academica == id_carga,
        models.Tarea.estado == "ACTIVO"
    ).order_by(models.Tarea.bimestre, models.Tarea.fecha_publicacion).all()

    lista_tareas = []
    for t in tareas:
        conteo_envios = len([e for e in t.entregas if e.archivo_url])
        lista_tareas.append({
            "id_tarea": t.id_tarea,
            "titulo": t.titulo,
            "tipo": t.tipo_evaluacion,
            "descripcion": t.descripcion,
            "fecha_entrega": t.fecha_entrega,
            "bimestre": t.bimestre,
            "peso": t.peso or 0,
            "total_entregas": conteo_envios,
            "editable_total": conteo_envios == 0,
            "archivo_adjunto_url": t.archivo_adjunto_url
        })

    # 4. Materiales / contenido de clase (los 4 bimestres)
    materiales = db.query(models.MaterialClase).filter(
        models.MaterialClase.id_carga_academica == id_carga
    ).order_by(models.MaterialClase.bimestre, models.MaterialClase.fecha_publicacion).all()

    lista_materiales = [
        {
            "id_material": m.id_material,
            "titulo": m.titulo,
            "descripcion": m.descripcion,
            "archivo_url": m.archivo_url,
            "bimestre": m.bimestre
        }
        for m in materiales
    ]

    docente_nombre = f"{carga.docente_nombres or ''} {carga.docente_apellidos or ''}".strip()

    return {
        "id_carga": carga.id_carga_academica,
        "curso_nombre": carga.curso_nombre,
        "docente_nombre": docente_nombre or "Docente por asignar",
        "grado_nombre": carga.grado_nombre,
        "seccion_nombre": carga.seccion_nombre,
        "anio": carga.id_anio_escolar,
        "num_alumnos": num_alumnos,
        "tareas": lista_tareas,
        "materiales": lista_materiales
    }


@router.post("/materiales/")
async def crear_material(
    id_carga_academica: int = Form(...),
    titulo: str = Form(...),
    descripcion: Optional[str] = Form(None),
    bimestre: int = Form(...),
    archivo: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    if current_user.get("rol") != "DOCENTE":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información")

    carga = db.query(models_mn.CargaAcademica).filter(
        models_mn.CargaAcademica.id_carga_academica == id_carga_academica
    ).first()
    if not carga:
        raise HTTPException(status_code=404, detail="La carga académica no existe.")

    url_adjunto = None
    if archivo and archivo.filename:
        ext = os.path.splitext(archivo.filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail="Tipo de archivo no permitido.")

        rel_folder = os.path.join("media", "materiales_clase", f"carga_{id_carga_academica}")
        abs_folder = os.path.join(BASE_DIR, rel_folder)
        os.makedirs(abs_folder, exist_ok=True)

        filename = f"mat_{uuid.uuid4().hex[:6]}{ext}"
        file_path = os.path.join(abs_folder, filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(archivo.file, buffer)
        url_adjunto = f"/{rel_folder}/{filename}".replace("\\", "/")

    nuevo = models.MaterialClase(
        id_carga_academica=id_carga_academica,
        titulo=titulo,
        descripcion=descripcion,
        bimestre=bimestre,
        archivo_url=url_adjunto,
        fecha_publicacion=datetime.now()
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return {
        "message": "Material publicado con éxito",
        "material": {
            "id_material": nuevo.id_material,
            "titulo": nuevo.titulo,
            "descripcion": nuevo.descripcion,
            "archivo_url": nuevo.archivo_url,
            "bimestre": nuevo.bimestre
        }
    }


@router.delete("/materiales/{id_material}")
def eliminar_material(id_material: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "DOCENTE":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información")

    material = db.get(models.MaterialClase, id_material)
    if not material:
        raise HTTPException(status_code=404, detail="Material no encontrado")

    if material.archivo_url:
        full_path = os.path.join(BASE_DIR, material.archivo_url.lstrip("/"))
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
            except Exception as e:
                print(f"Error al borrar material: {e}")

    db.delete(material)
    db.commit()
    return {"message": "Material eliminado con éxito"}


# =========================================================
# CLASES VIRTUALES
# =========================================================

def _drive_url_de_carga(db: Session, id_carga: int) -> str:
    row = db.query(models.DriveClases).filter(
        models.DriveClases.id_carga_academica == id_carga
    ).first()
    return row.url if row else ""


def _serializar_clase(c: "models.ClaseVirtual") -> dict:
    return {
        "id_clase_virtual": c.id_clase_virtual,
        "tema": c.tema,
        "fecha": c.fecha,
        "enlace": c.enlace,
    }


@router.get("/clases-virtuales/{id_carga}")
def listar_clases_virtuales_docente(id_carga: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "DOCENTE":
        raise HTTPException(status_code=403, detail="No puedes acceder a esta información.")
    clases = db.query(models.ClaseVirtual).filter(
        models.ClaseVirtual.id_carga_academica == id_carga
    ).order_by(models.ClaseVirtual.fecha.desc()).all()
    return {
        "drive_url": _drive_url_de_carga(db, id_carga),
        "clases": [_serializar_clase(c) for c in clases],
    }


@router.post("/clases-virtuales", response_model=schemas.ClaseVirtualResponse)
def crear_clase_virtual(payload: schemas.ClaseVirtualCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "DOCENTE":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información")
    carga = db.query(models_mn.CargaAcademica).filter(
        models_mn.CargaAcademica.id_carga_academica == payload.id_carga_academica
    ).first()
    if not carga:
        raise HTTPException(status_code=404, detail="La carga académica no existe.")
    nueva = models.ClaseVirtual(
        id_carga_academica=payload.id_carga_academica,
        tema=(payload.tema or None),
        fecha=payload.fecha,
        enlace=payload.enlace,
    )
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva


@router.delete("/clases-virtuales/{id_clase}")
def eliminar_clase_virtual(id_clase: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "DOCENTE":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información")
    clase = db.get(models.ClaseVirtual, id_clase)
    if not clase:
        raise HTTPException(status_code=404, detail="Clase no encontrada")
    db.delete(clase)
    db.commit()
    return {"message": "Clase eliminada"}


@router.put("/clases-virtuales/drive")
def actualizar_drive_clases(payload: schemas.DriveClasesUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "DOCENTE":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información")
    url = (payload.url or "").strip()
    row = db.query(models.DriveClases).filter(
        models.DriveClases.id_carga_academica == payload.id_carga_academica
    ).first()
    if not url:
        if row:
            db.delete(row)
            db.commit()
        return {"drive_url": ""}
    if row:
        row.url = url
    else:
        row = models.DriveClases(id_carga_academica=payload.id_carga_academica, url=url)
        db.add(row)
    db.commit()
    return {"drive_url": url}


@router.get("/clases-virtuales-alumno/{id_curso}/{id_usuario}")
def listar_clases_virtuales_alumno(id_curso: int, id_usuario: int, anio: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("id") != id_usuario:
        raise HTTPException(status_code=403, detail="No puedes acceder a esta información.")
    alumno = db.query(models_al.Alumno).filter(models_al.Alumno.id_usuario == id_usuario).first()
    if not alumno:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")
    matricula = db.query(models_en.Matricula).filter(
        models_en.Matricula.id_alumno == alumno.id_alumno,
        models_en.Matricula.id_anio_escolar == anio
    ).first()
    if not matricula:
        return {"drive_url": "", "clases": []}
    carga = db.query(models_mn.CargaAcademica).filter(
        models_mn.CargaAcademica.id_curso == id_curso,
        models_mn.CargaAcademica.id_seccion == matricula.id_seccion,
        models_mn.CargaAcademica.id_anio_escolar == anio
    ).first()
    if not carga:
        return {"drive_url": "", "clases": []}
    clases = db.query(models.ClaseVirtual).filter(
        models.ClaseVirtual.id_carga_academica == carga.id_carga_academica
    ).order_by(models.ClaseVirtual.fecha.desc()).all()
    return {
        "drive_url": _drive_url_de_carga(db, carga.id_carga_academica),
        "clases": [_serializar_clase(c) for c in clases],
    }


@router.get("/sabana-notas/{id_carga}/{bimestre}", response_model=schemas.SabanaNotasResponse)
def obtener_sabana_notas(id_carga: int, bimestre: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "DOCENTE":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información")
    # 1. Obtener la información de la carga académica
    carga = db.query(models_mn.CargaAcademica).filter(models_mn.CargaAcademica.id_carga_academica == id_carga).first()
    if not carga:
        raise HTTPException(status_code=404, detail="Carga académica no encontrada")

    # 2. Obtener los alumnos matriculados activos (no retirados)
    alumnos = db.query(models_al.Alumno).join(
        models_en.Matricula, models_al.Alumno.id_alumno == models_en.Matricula.id_alumno
    ).filter(
        models_en.Matricula.id_seccion == carga.id_seccion,
        models_en.Matricula.id_anio_escolar == carga.id_anio_escolar,
        models_al.Alumno.estado_ingreso != "RETIRADO"
    ).order_by(models_al.Alumno.apellidos).all()

    # Condición de matrícula por alumno (NORMAL / CONDICIONADA / REPITE)
    condiciones = {
        m.id_alumno: m.condicion
        for m in db.query(models_en.Matricula).filter(
            models_en.Matricula.id_seccion == carga.id_seccion,
            models_en.Matricula.id_anio_escolar == carga.id_anio_escolar
        ).all()
    }

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
            "promedio": round(promedio_final, 2),
            "condicion": condiciones.get(alumno.id_alumno)
        })

    return {
        "evaluaciones": lista_evaluaciones,
        "alumnos_notas": resultado_alumnos
    }

@router.post("/guardar-notas-masivo/")
def guardar_notas_masivo(payload: schemas.NotasMasivasCreate, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    
    """
    Se espera un payload como: 
    { "id_tarea": 10, "notas": { "id_alumno_1": 15, "id_alumno_2": 20 } }
    """
    if current_user.get("rol") != "DOCENTE":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información")
    
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
def calificar_entrega(id_entrega: int, calificacion: float, retroalimentacion: str = None, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "DOCENTE":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información")
    
    entrega = db.query(models.EntregaTarea).filter(models.EntregaTarea.id_entrega == id_entrega).first()
    if not entrega:
        raise HTTPException(status_code=404, detail="Entrega no encontrada")
    
    entrega.calificacion = calificacion
    entrega.retroalimentacion_docente = retroalimentacion
    db.commit()
    return {"message": "Calificación registrada con éxito"}

@router.get("/mis-notas/{id_carga}/{id_alumno}")
def obtener_mis_notas(id_carga: int, id_alumno: int, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    # Solo el propio alumno (o un ADMIN) puede consultar estas notas
    if current_user.get("rol") != "ADMIN":
        alumno = db.query(models_al.Alumno).filter(models_al.Alumno.id_alumno == id_alumno).first()
        if not alumno or alumno.id_usuario != current_user.get("id"):
            raise HTTPException(status_code=403, detail="No puedes ver las notas de otro alumno")
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
    fecha_entrega: Optional[datetime] = Form(None),
    tipo_evaluacion: str = Form(...),
    bimestre: int = Form(...),
    peso: int = Form(0),
    archivo: Optional[UploadFile] = File(None), # Nuevo archivo opcional
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("rol") != "DOCENTE":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información")
    
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
def eliminar_tarea(id_tarea: int, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "DOCENTE":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información")
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
def listar_entregas_con_archivos(id_tarea: int, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "DOCENTE":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información")
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
def obtener_detalle_tarea(id_tarea: int, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "DOCENTE" and current_user.get("rol") != "ALUMNO":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información")
    tarea = db.query(models.Tarea).filter(models.Tarea.id_tarea == id_tarea).first()
    if not tarea:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    return tarea

@router.post("/entregar-tarea/")
async def entregar_tarea(
    id_tarea: int = Form(...),
    id_usuario: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("rol") != "ALUMNO" or current_user.get("id") != id_usuario:
        raise HTTPException(status_code=403, detail="No puedes modificar esta información")
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
def obtener_detalle_tarea_estudiante(id_tarea: int, id_usuario: int, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    if current_user.get("id") != id_usuario:
        raise HTTPException(status_code=403, detail="No puedes modificar esta información")
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
def obtener_dashboard_estudiante(id_usuario: int, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    # VALIDACIÓN DE ROL: solo el propio alumno (o un ADMIN) ve su dashboard
    ensure_owner_or_roles(current_user, id_usuario, "ADMIN")
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

