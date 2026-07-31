from fastapi import APIRouter, Depends, HTTPException, status, Query, Body, BackgroundTasks
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from app.db.database import get_db
from . import models, schemas
from typing import List, Optional
from datetime import date
from pydantic import BaseModel  # <--- NUEVO: Importación para el endpoint de edición
from app.core.util.security import get_current_user
from app.modules.management.models import CargaAcademica  # <--- Importar CargaAcademica
from app.modules.users.models import Usuario, RolEnum     # <--- Importar Usuario y RolEnum
from app.modules.users.docente.models import Docente      # <--- Importar Docente

router = APIRouter(prefix="/academic", tags=["Académico"])

# --- NUEVO: Esquema local para editar el año ---
class EditarAnioRequest(BaseModel):
    fecha_inicio: date
    fecha_fin: date
    tipo: str

# --- AÑO ESCOLAR ---
def _procesar_cierre_automatico(db: Session, anio_id: str):
    """Cierre automático de un año que acaba de terminar (por fecha):
    inhabilita a los docentes del año y ejecuta la evaluación de fin de año
    (desaprobados / nivelación / repitencia) enviando los correos a los padres."""
    # 1. Inhabilitar docentes del año
    docentes_ids = [d[0] for d in db.query(CargaAcademica.id_docente).filter(
        CargaAcademica.id_anio_escolar == anio_id
    ).distinct().all()]
    if docentes_ids:
        subquery_usuarios = db.query(Docente.id_usuario).filter(Docente.id_docente.in_(docentes_ids))
        db.query(Usuario).filter(
            Usuario.id_usuario.in_(subquery_usuarios),
            Usuario.rol == RolEnum.DOCENTE
        ).update({Usuario.activo: False}, synchronize_session=False)
        db.commit()

    # 2. Evaluación de fin de año + correos a los padres
    from app.modules.verano import service as verano_service
    resultado = verano_service.evaluar_cierre_anio(db, anio_id)
    correos = resultado.get("correos", [])
    if correos:
        from app.core.util.email import enviar_correos
        enviar_correos(correos)


def actualizar_estado_anios(db: Session):
    """
    Recorre todos los años y actualiza su estado 'activo' según la fecha actual.
    Cuando un año pasa de activo a inactivo (terminó su periodo), se ejecuta el
    cierre automático (inhabilitar docentes + evaluación de fin de año).
    """
    hoy = date.today()
    anios = db.query(models.AnioEscolar).all()
    cambios = False
    recien_cerrados = []

    for anio in anios:
        # Lógica: Está activo SI hoy es >= inicio Y hoy <= fin
        deberia_estar_activo = anio.fecha_inicio <= hoy <= anio.fecha_fin

        if anio.activo != deberia_estar_activo:
            # Transición activo -> inactivo = el año acaba de terminar
            if anio.activo and not deberia_estar_activo:
                recien_cerrados.append(anio.id_anio_escolar)
            anio.activo = deberia_estar_activo
            cambios = True

    if cambios:
        db.commit()

    # Cierre automático de los años que acaban de terminar (idempotente)
    for anio_id in recien_cerrados:
        try:
            _procesar_cierre_automatico(db, anio_id)
        except Exception as e:
            print(f"Error en cierre automático del año {anio_id}: {e}")

@router.get("/anios/ultimo", response_model=schemas.AnioEscolarResponse)
def obtener_ultimo_anio_creado(db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user) ):
    # Buscamos el año con la fecha de inicio más alta (el más nuevo en el calendario)
    anio = db.query(models.AnioEscolar).order_by(models.AnioEscolar.fecha_inicio.desc()).first()
    
    if not anio:
        raise HTTPException(status_code=404, detail="No hay años escolares registrados")
        
    return anio

def _generar_estructura_para_anio(db: Session, anio_id: str) -> int:
    """Crea automáticamente las secciones de un año nuevo.
    - Si ya tiene secciones, no hace nada.
    - Si existe un año previo con secciones, replica su estructura (grados + secciones).
    - Si no hay ningún año previo con secciones, crea una sección 'A' por cada grado.
    Devuelve cuántas secciones se crearon."""
    ya_tiene = db.query(models.Seccion).filter_by(id_anio_escolar=anio_id).count()
    if ya_tiene:
        return 0

    # Buscar el año más reciente (distinto de este) que tenga secciones, como plantilla
    plantilla = None
    otros = db.query(models.AnioEscolar).filter(
        models.AnioEscolar.id_anio_escolar != anio_id
    ).order_by(models.AnioEscolar.fecha_inicio.desc()).all()
    for a in otros:
        if db.query(models.Seccion).filter_by(id_anio_escolar=a.id_anio_escolar).count() > 0:
            plantilla = a.id_anio_escolar
            break

    count = 0
    if plantilla:
        for sec in db.query(models.Seccion).filter_by(id_anio_escolar=plantilla).all():
            db.add(models.Seccion(
                id_grado=sec.id_grado,
                id_anio_escolar=anio_id,
                nombre=sec.nombre,
                vacantes=sec.vacantes,
            ))
            count += 1
    else:
        # Sin plantilla: una sección "A" por cada grado existente
        for grado in db.query(models.Grado).all():
            db.add(models.Seccion(
                id_grado=grado.id_grado,
                id_anio_escolar=anio_id,
                nombre="A",
                vacantes=30,
            ))
            count += 1

    db.commit()
    return count


@router.post("/anios/", response_model=schemas.AnioEscolarResponse, status_code=status.HTTP_201_CREATED)
def crear_anio(anio: schemas.AnioEscolarCreate, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user) ):
    
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información.")
    # 1. Validación de Fechas
    if anio.fecha_fin and anio.fecha_fin <= anio.fecha_inicio:
        raise HTTPException(
            status_code=400, 
            detail="La fecha de fin debe ser posterior a la fecha de inicio."
        )
    
    try:
        # 2. Calcular estado inicial según la fecha de hoy
        hoy = date.today()
        estado_inicial = anio.fecha_inicio <= hoy <= anio.fecha_fin

        # 3. Intentar Crear
        # Ignoramos el campo 'activo' que viene del front, usamos el calculado
        datos_anio = anio.model_dump()
        datos_anio['activo'] = estado_inicial
        
        nuevo = models.AnioEscolar(**datos_anio)
        db.add(nuevo)
        db.commit()
        db.refresh(nuevo)

        # Ejecutamos la revisión general por si hay solapamientos (opcional)
        actualizar_estado_anios(db)

        # Generar automáticamente los grados/secciones del nuevo año
        try:
            _generar_estructura_para_anio(db, nuevo.id_anio_escolar)
        except Exception as e:
            print(f"Error generando estructura para el año {nuevo.id_anio_escolar}: {e}")

        return nuevo

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400, 
            detail=f"El ID '{anio.id_anio_escolar}' ya existe. Por favor usa otro."
        )
    except Exception as e:
        db.rollback()
        print(f"Error no controlado: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")

# --- NUEVO ENDPOINT: Editar fechas de un año existente ---
@router.patch("/anios/{anio_id}")
def editar_anio(anio_id: str, datos: EditarAnioRequest, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información.")
    
    db_anio = db.query(models.AnioEscolar).filter(models.AnioEscolar.id_anio_escolar == anio_id).first()
    if not db_anio:
        raise HTTPException(status_code=404, detail="Año no encontrado")
    
    if datos.fecha_fin <= datos.fecha_inicio:
        raise HTTPException(status_code=400, detail="La fecha de fin debe ser posterior a la fecha de inicio.")

    db_anio.fecha_inicio = datos.fecha_inicio
    db_anio.fecha_fin = datos.fecha_fin
    db_anio.tipo = datos.tipo
    
    hoy = date.today()
    db_anio.activo = datos.fecha_inicio <= hoy <= datos.fecha_fin

    db.commit()
    actualizar_estado_anios(db)

    # Al cambiar las fechas, las pensiones pendientes que quedaron fuera del nuevo
    # rango de meses ya no tienen sentido: se limpian automáticamente para los
    # alumnos matriculados en este año (respeta verano y no toca pensiones pagadas).
    from app.modules.enrollment import models as er_models
    from app.modules.finance.service import FinanceService
    ids_alumnos = [row[0] for row in db.query(er_models.Matricula.id_alumno).filter(
        er_models.Matricula.id_anio_escolar == anio_id
    ).distinct().all()]
    eliminadas = 0
    if ids_alumnos:
        eliminadas = FinanceService.limpiar_pensiones_fuera_de_rango(db, ids_alumnos=ids_alumnos)

    return {"message": "Año académico actualizado correctamente", "pensiones_fuera_de_rango_eliminadas": eliminadas}

@router.patch("/anios/{anio_id}/inscripciones")
def configurar_inscripciones(anio_id: str, fechas: schemas.InscripcionUpdate, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información.")

    
    db_anio = db.query(models.AnioEscolar).filter(models.AnioEscolar.id_anio_escolar == anio_id).first()
    if not db_anio:
        raise HTTPException(status_code=404, detail="Año no encontrado")
    
    # Validación simple
    if fechas.fin_inscripcion < fechas.inicio_inscripcion:
        raise HTTPException(status_code=400, detail="La fecha de fin no puede ser anterior al inicio.")

    db_anio.inicio_inscripcion = fechas.inicio_inscripcion
    db_anio.fin_inscripcion = fechas.fin_inscripcion
    
    db.commit()
    return {"message": "Fechas de inscripción actualizadas correctamente"}

# NOTA: el cierre de año ya NO es manual. Ocurre automáticamente cuando pasa la
# fecha de fin del año (ver `actualizar_estado_anios` -> `_procesar_cierre_automatico`),
# que inhabilita a los docentes y ejecuta la evaluación de fin de año + correos.

@router.post("/anios/copiar-estructura")
def copiar_estructura(data: schemas.CopiarEstructuraRequest, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    # 1. Validar destino
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información.")

    anio_dest = db.query(models.AnioEscolar).filter_by(id_anio_escolar=data.anio_destino).first()
    if not anio_dest:
        raise HTTPException(status_code=404, detail="Año destino no existe")

    # 2. Obtener secciones origen
    secciones_origen = db.query(models.Seccion).filter_by(id_anio_escolar=data.anio_origen).all()
    
    if not secciones_origen:
        raise HTTPException(status_code=400, detail="El año origen no tiene secciones")

    count = 0
    for sec in secciones_origen:
        # Verificar si ya existe para no duplicar
        existe = db.query(models.Seccion).filter_by(
            id_anio_escolar=data.anio_destino,
            id_grado=sec.id_grado,
            nombre=sec.nombre
        ).first()

        if not existe:
            nueva = models.Seccion(
                id_grado=sec.id_grado,
                id_anio_escolar=data.anio_destino,
                nombre=sec.nombre,
                vacantes=sec.vacantes
            )
            db.add(nueva)
            count += 1
    
    db.commit()
    return {"message": f"Se copiaron {count} secciones correctamente."}

@router.get("/anios/", response_model=List[schemas.AnioEscolarResponse])
def listar_anios(db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    # ¡MAGIA AQUÍ! 
    # Antes de devolver la lista, actualizamos los estados automáticamente
    actualizar_estado_anios(db)
    
    return db.query(models.AnioEscolar).all()


# --- NIVELES ---
@router.post("/niveles/", response_model=schemas.NivelResponse)
def crear_nivel(nivel: schemas.NivelCreate, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información.")


    nuevo = models.Nivel(**nivel.model_dump())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

@router.get("/niveles/", response_model=List[schemas.NivelResponse])
def listar_niveles(db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    return db.query(models.Nivel).all()

@router.get("/niveles-cursos/", response_model=List[schemas.NivelConCursosResponse])
def listar_niveles_con_cursos(db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes acceder esta información.")
    return db.query(models.Nivel).options(
        joinedload(models.Nivel.grados).joinedload(models.Grado.planes_estudio).joinedload(models.PlanEstudio.curso)
    ).all()


# --- GRADOS ---
@router.post("/grados/", response_model=schemas.GradoResponse)
def crear_grado(grado: schemas.GradoCreate, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información.")

    nuevo = models.Grado(**grado.model_dump())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

@router.get("/grados/", response_model=List[schemas.GradoResponse])
def listar_grados(nivel_id: int = None, db: Session = Depends(get_db)):
    # Agregamos filtro por nivel si se necesita
    query = db.query(models.Grado).options(joinedload(models.Grado.nivel))
    if nivel_id:
        query = query.filter(models.Grado.id_nivel == nivel_id)
    return query.all()

@router.put("/grados/{grado_id}", response_model=schemas.GradoResponse)
def actualizar_grado(grado_id: int, grado: schemas.GradoCreate, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información.")

    db_grado = db.query(models.Grado).filter(models.Grado.id_grado == grado_id).first()
    if not db_grado:
        raise HTTPException(status_code=404, detail="Grado no encontrado")
    
    for key, value in grado.model_dump().items():
        setattr(db_grado, key, value)
    
    db.commit()
    db.refresh(db_grado)
    return db_grado

@router.delete("/grados/{grado_id}")
def eliminar_grado(grado_id: int, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información.")

    db_grado = db.query(models.Grado).filter(models.Grado.id_grado == grado_id).first()
    if not db_grado:
        raise HTTPException(status_code=404, detail="Grado no encontrado")
    
    # Verificar si tiene secciones (relación backref en models)
    # Nota: Asegúrate de que tu modelo Grado tenga la relación 'secciones' o haz query manual
    secciones_count = db.query(models.Seccion).filter(models.Seccion.id_grado == grado_id).count()
    if secciones_count > 0:
         raise HTTPException(
            status_code=400, 
            detail=f"No se puede eliminar: El grado tiene {secciones_count} secciones asignadas."
        )
    
    db.delete(db_grado)
    db.commit()
    return {"message": "Grado eliminado"}


# --- SECCIONES (¡MODIFICADO!) ---
@router.post("/secciones/", response_model=schemas.SeccionResponse)
def crear_seccion(seccion: schemas.SeccionCreate, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información.")

    # 1. Validar que el año escolar exista
    anio = db.query(models.AnioEscolar).filter(models.AnioEscolar.id_anio_escolar == seccion.id_anio_escolar).first()
    if not anio:
        raise HTTPException(status_code=404, detail="El año escolar indicado no existe")

    # 2. VALIDACIÓN DE DUPLICADOS (NUEVO)
    # Buscamos si ya existe una sección con el mismo nombre, en el mismo grado y año.
    seccion_existente = db.query(models.Seccion).filter(
        models.Seccion.id_anio_escolar == seccion.id_anio_escolar,
        models.Seccion.id_grado == seccion.id_grado,
        models.Seccion.nombre == seccion.nombre
    ).first()

    if seccion_existente:
        raise HTTPException(
            status_code=400, 
            detail=f"La sección '{seccion.nombre}' ya existe en este grado para el año {seccion.id_anio_escolar}."
        )

    # 3. Crear si no existe
    nuevo = models.Seccion(**seccion.model_dump())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

@router.get("/secciones/", response_model=List[schemas.SeccionResponse])
def listar_secciones(
    grado_id: int = None, 
    anio_id: str = None, 
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Lista secciones con filtros obligatorios para el frontend:
    - grado_id: Para ver secciones.
    - anio_id: Para ver solo las del año.
    """
    query = db.query(models.Seccion).options(joinedload(models.Seccion.grado))

    if grado_id:
        query = query.filter(models.Seccion.id_grado == grado_id)

    if anio_id:
        query = query.filter(models.Seccion.id_anio_escolar == anio_id)

    secciones = query.all()
    _adjuntar_ocupacion(db, secciones)
    return secciones


def _adjuntar_ocupacion(db: Session, secciones):
    """Calcula y adjunta el atributo 'ocupadas' (matrículas activas) a cada sección."""
    from sqlalchemy import func
    from app.modules.enrollment import models as enrollment_models

    ids = [s.id_seccion for s in secciones]
    if not ids:
        return

    conteos = dict(
        db.query(
            enrollment_models.Matricula.id_seccion,
            func.count(enrollment_models.Matricula.id_matricula)
        ).filter(
            enrollment_models.Matricula.id_seccion.in_(ids),
            enrollment_models.Matricula.estado.notin_(["RETIRADO", "ANULADO"])
        ).group_by(enrollment_models.Matricula.id_seccion).all()
    )

    for s in secciones:
        s.ocupadas = conteos.get(s.id_seccion, 0)

@router.get("/secciones/{anio_id}", response_model=List[schemas.SeccionResponse])
def listar_secciones_por_anio_url(anio_id: str, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    """
    Este endpoint ahora coincide con la ruta: /academic/secciones/2025-1
    """
    return db.query(models.Seccion)\
             .options(joinedload(models.Seccion.grado))\
             .filter(models.Seccion.id_anio_escolar == anio_id).all()

@router.get("/cursos-por-seccion/{seccion_id}", response_model=List[schemas.CursoResponse])
def obtener_cursos_de_seccion(seccion_id: int, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    # 1. Buscamos la sección para saber qué grado es
    seccion = db.query(models.Seccion).filter(models.Seccion.id_seccion == seccion_id).first()
    if not seccion:
        raise HTTPException(status_code=404, detail="Sección no encontrada")
    
    # 2. Buscamos los cursos vinculados a ese grado en el Plan de Estudios
    cursos = db.query(models.Curso)\
               .join(models.PlanEstudio, models.PlanEstudio.id_curso == models.Curso.id_curso)\
               .filter(models.PlanEstudio.id_grado == seccion.id_grado).all()
    
    return cursos


@router.put("/secciones/{seccion_id}", response_model=schemas.SeccionResponse)
def actualizar_seccion(seccion_id: int, seccion: schemas.SeccionCreate, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información.")


    db_seccion = db.query(models.Seccion).filter(models.Seccion.id_seccion == seccion_id).first()
    if not db_seccion:
        raise HTTPException(status_code=404, detail="Sección no encontrada")
    
    for key, value in seccion.model_dump().items():
        setattr(db_seccion, key, value)
    
    db.commit()
    db.refresh(db_seccion)
    return db_seccion

@router.delete("/secciones/{seccion_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_seccion(seccion_id: int, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información.")

    db_seccion = db.query(models.Seccion).filter(models.Seccion.id_seccion == seccion_id).first()
    if not db_seccion:
        raise HTTPException(status_code=404, detail="Sección no encontrada")
    
    db.delete(db_seccion)
    db.commit()
    return None


# --- ÁREAS ---
@router.post("/areas/", response_model=schemas.AreaResponse)
def crear_area(area: schemas.AreaCreate, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información.")

    nuevo = models.Area(**area.model_dump())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

@router.get("/areas/", response_model=List[schemas.AreaResponse])
def listar_areas(db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    return db.query(models.Area).all()


# --- CURSOS ---
@router.post("/cursos/", response_model=schemas.CursoResponse)
def crear_curso(curso: schemas.CursoCreate, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información.")

    nuevo = models.Curso(**curso.model_dump())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

@router.get("/cursos/", response_model=List[schemas.CursoResponse])
def listar_cursos(db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    # Puedes agregar joinedload(models.Curso.area) si quieres ver el nombre del área
    return db.query(models.Curso).all()

# Grupos de verano (clave -> etiqueta), en el orden en que se muestran
GRUPOS_VERANO = [
    ("PRIM_1_2", "1ro y 2do de Primaria"),
    ("PRIM_3_4", "3ro y 4to de Primaria"),
    ("PRIM_5_6", "5to y 6to de Primaria"),
    ("SEC_1", "1ro de Secundaria"),
    ("SEC_2", "2do de Secundaria"),
    ("SEC_3", "3ro de Secundaria"),
    ("PRE_ACADEMIA", "Pre Academia"),
]

@router.get("/cursos-verano/")
def listar_cursos_verano(db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    """Cursos de verano organizados por grupo (fijos) + talleres."""
    fijos = db.query(models.Curso).filter(
        models.Curso.es_verano == True,          # noqa: E712
        models.Curso.tipo_verano == "FIJO",
    ).all()
    talleres = db.query(models.Curso).filter(
        models.Curso.es_verano == True,          # noqa: E712
        models.Curso.tipo_verano == "TALLER",
    ).all()

    grupos = []
    for clave, etiqueta in GRUPOS_VERANO:
        cursos = [
            {"id_curso": c.id_curso, "nombre": c.nombre, "id_area": c.id_area, "minutos_semanales": c.minutos_semanales}
            for c in fijos if c.grupo_verano == clave
        ]
        grupos.append({"clave": clave, "etiqueta": etiqueta, "cursos": cursos})

    return {
        "grupos": grupos,
        "talleres": [
            {"id_curso": c.id_curso, "nombre": c.nombre, "id_area": c.id_area, "minutos_semanales": c.minutos_semanales}
            for c in talleres
        ],
    }

@router.put("/cursos/{curso_id}", response_model=schemas.CursoResponse)
def actualizar_curso(curso_id: int, curso_data: schemas.CursoCreate, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información.")

    db_curso = db.query(models.Curso).filter(models.Curso.id_curso == curso_id).first()
    if not db_curso:
        raise HTTPException(status_code=404, detail="Curso no encontrado")
    
    for key, value in curso_data.model_dump().items():
        setattr(db_curso, key, value)
    
    db.commit()
    db.refresh(db_curso)
    return db_curso

@router.delete("/cursos/{curso_id}")
def eliminar_curso(
    curso_id: int, 
    grados_ids: Optional[List[int]] = Query(None), 
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información.")

    db_curso = db.query(models.Curso).filter(models.Curso.id_curso == curso_id).first()
    if not db_curso:
        raise HTTPException(status_code=404, detail="Curso no encontrado")
    
    if grados_ids:
        # Desvincular de grados específicos
        db.query(models.PlanEstudio).filter(
            models.PlanEstudio.id_curso == curso_id,
            models.PlanEstudio.id_grado.in_(grados_ids)
        ).delete(synchronize_session=False)
        mensaje = "Curso desvinculado de los grados seleccionados"
    else:
        # Eliminación total
        db.query(models.PlanEstudio).filter(models.PlanEstudio.id_curso == curso_id).delete(synchronize_session=False)
        db.delete(db_curso)
        mensaje = "Curso eliminado por completo del sistema"
    
    db.commit()
    return {"message": mensaje}


# --- PLAN ESTUDIO (Asignación Masiva) ---
@router.put("/plan-estudio/batch/{curso_id}")
def actualizar_plan_estudio_batch(
    curso_id: int, 
    grados: List[int] = Body(...), # Usamos Body explícito para recibir la lista [1, 2, 3]
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información.")

    # 1. Limpiar asignaciones previas
    db.query(models.PlanEstudio).filter(
        models.PlanEstudio.id_curso == curso_id
    ).delete(synchronize_session=False)
    
    # 2. Insertar nuevas
    for grado_id in grados:
        nuevo = models.PlanEstudio(id_curso=curso_id, id_grado=grado_id)
        db.add(nuevo)
    
    db.commit()
    return {"message": "Plan de estudio actualizado correctamente"}

@router.post("/plan-estudio/", response_model=schemas.PlanEstudioResponse)
def asignar_curso_a_grado(plan: schemas.PlanEstudioCreate, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información.")

    existe = db.query(models.PlanEstudio).filter(
        models.PlanEstudio.id_curso == plan.id_curso,
        models.PlanEstudio.id_grado == plan.id_grado
    ).first()
    
    if existe:
        raise HTTPException(status_code=400, detail="Este curso ya está asignado a este grado")

    nuevo = models.PlanEstudio(**plan.model_dump())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

#--- Para el horario
@router.get("/secciones-horario/{anio_id}", response_model=List[schemas.SeccionHorarioResponse])
def obtener_secciones_para_constructor(anio_id: str, db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)):
    """
    Endpoint exclusivo para el constructor de horarios.
    Trae las secciones de un año específico incluyendo la info del grado.
    """
    secciones = db.query(models.Seccion)\
        .options(joinedload(models.Seccion.grado))\
        .filter(models.Seccion.id_anio_escolar == anio_id)\
        .all()
    
    return secciones