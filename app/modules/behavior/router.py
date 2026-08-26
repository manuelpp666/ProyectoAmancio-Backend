from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import bindparam, extract, func, or_, text
from app.db.database import get_db
from app.modules.users.alumno import models as alumno_models
from app.modules.academic import models as academic_models
from app.modules.enrollment import models as matricula_models
from app.core.util.security import get_current_user, require_roles
from app.core.util import busqueda as busqueda_util
from app.core.util.correo_usuario import PRIORIDAD_PARENTESCO
from app.modules.users.relacion_familiar.models import RelacionFamiliar
from app.modules.personal import models as personal_models
from . import models, schemas
from . import bimestres as bimestres_util
from .constants import (PUNTAJE_MAXIMO, UMBRAL_OBSERVACION, UMBRAL_CRITICO,
                        ESTADOS_CONDUCTA, calcular_puntaje, estado_visual,
                        normalizar_estado)
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from typing import Optional, Tuple
from datetime import datetime, date

router = APIRouter(prefix="/conducta", tags=["Conducta y Psicología"])


def _periodo(db: Session, anio: int, numero_bimestre: Optional[int] = None
             ) -> Tuple[date, date, Optional[int]]:
    """Desde/hasta sobre los que se cuenta la conducta, y qué bimestre es.

    La nota de conducta se reinicia cada bimestre, así que el periodo por
    defecto es el bimestre en curso y no el año entero. Si la fecha de hoy cae
    fuera del año escolar (vacaciones, o un año ya cerrado) se devuelve el año
    completo: es preferible enseñar el acumulado a no enseñar nada.
    """
    from app.modules.academic.models import AnioEscolar

    ae = (db.query(AnioEscolar)
          .filter(AnioEscolar.id_anio_escolar == str(anio)).first())
    tramos = bimestres_util.calendario(
        db, str(anio),
        getattr(ae, "fecha_inicio", None), getattr(ae, "fecha_fin", None))

    if tramos:
        buscado = numero_bimestre or bimestres_util.bimestre_de(date.today(), tramos)
        for n, desde, hasta in tramos:
            if n == buscado:
                return desde, hasta, n

    return date(anio, 1, 1), date(anio, 12, 31), None


def _conducta_migrada(db: Session, id_alumno: int, anio: str,
                      numero_bimestre: Optional[int]) -> Optional[int]:
    """La nota de conducta que ya traía el sistema antiguo, si la hay.

    Los bimestres cargados desde el sistema PHP tienen la nota puesta a mano
    por el colegio y ningún reporte detrás. Calcularla desde los reportes daría
    20 para todos y no coincidiría con la libreta que las familias ya tienen.

    Devuelve None si no hay nota migrada, si la tabla todavía no existe (base
    sin el script 20) o si no se sabe en qué bimestre estamos.
    """
    if not numero_bimestre:
        return None
    try:
        valor = db.execute(
            text("SELECT nc.valor FROM nota_conducta nc "
                 "JOIN matricula m ON m.id_matricula = nc.id_matricula "
                 "WHERE m.id_alumno = :al AND m.id_anio_escolar = :anio "
                 "  AND nc.bimestre = :bim LIMIT 1"),
            {"al": id_alumno, "anio": anio, "bim": numero_bimestre},
        ).scalar()
    except Exception:
        # La tabla puede no existir aún. No es motivo para tumbar la pantalla
        # del alumno: se sigue con el puntaje calculado.
        db.rollback()
        return None
    return int(round(float(valor))) if valor is not None else None


def _puntos_perdidos_anio(db: Session, id_alumno: int, anio: int,
                          numero_bimestre: Optional[int] = None) -> int:
    """Suma de puntos descontados al alumno en el bimestre en curso.

    Conserva el nombre por compatibilidad con quien ya lo llama, pero el
    periodo ya no es el año: es el bimestre, porque la nota de conducta de la
    libreta se reinicia en cada uno.
    """
    desde, hasta, _ = _periodo(db, anio, numero_bimestre)
    total = db.query(func.coalesce(func.sum(models.NivelConducta.puntos), 0)).select_from(
        models.ReporteConducta
    ).join(models.NivelConducta).filter(
        models.ReporteConducta.id_alumno == id_alumno,
        func.date(models.ReporteConducta.fecha_reporte) >= desde,
        func.date(models.ReporteConducta.fecha_reporte) <= hasta,
    ).scalar()
    return int(total or 0)

def _recalcular_nota_conducta_alumno_bimestre(
    db: Session,
    id_alumno: int,
    fecha_reporte: Optional[datetime] = None
) -> dict:
    """
    Recalcula automáticamente la nota de conducta sobre 20 del alumno
    en el bimestre correspondiente a la fecha del reporte, y actualiza
    el registro en `nota_conducta` (tabla oficial de notas de conducta).
    """
    from app.modules.enrollment.models import Matricula
    from app.modules.academic.models import AnioEscolar

    if not fecha_reporte:
        fecha_reporte = datetime.now()

    fecha_dt = fecha_reporte.date() if isinstance(fecha_reporte, datetime) else fecha_reporte
    anio_str = str(fecha_dt.year)

    # 1. Buscar matrícula activa del alumno en el año del reporte
    matricula = db.query(Matricula).filter(
        Matricula.id_alumno == id_alumno,
        Matricula.id_anio_escolar == anio_str
    ).first()

    if not matricula:
        matricula = db.query(Matricula).filter(
            Matricula.id_alumno == id_alumno
        ).order_by(Matricula.id_matricula.desc()).first()

    if not matricula:
        puntos_perdidos = db.query(func.coalesce(func.sum(models.NivelConducta.puntos), 0)).select_from(
            models.ReporteConducta
        ).join(models.NivelConducta).filter(
            models.ReporteConducta.id_alumno == id_alumno,
            extract('year', models.ReporteConducta.fecha_reporte) == fecha_dt.year
        ).scalar() or 0
        nueva_nota = calcular_puntaje(int(puntos_perdidos))
        return {
            "bimestre": None,
            "puntos_descontados": int(puntos_perdidos),
            "nota_calculada": nueva_nota,
            "id_matricula": None
        }

    ae = db.query(AnioEscolar).filter(AnioEscolar.id_anio_escolar == matricula.id_anio_escolar).first()
    tramos = bimestres_util.calendario(
        db, matricula.id_anio_escolar,
        getattr(ae, "fecha_inicio", None), getattr(ae, "fecha_fin", None)
    )

    num_bimestre = bimestres_util.bimestre_de(fecha_dt, tramos) or 1
    rango_bim = bimestres_util.rango(
        db, matricula.id_anio_escolar, num_bimestre,
        getattr(ae, "fecha_inicio", None), getattr(ae, "fecha_fin", None)
    )

    if rango_bim:
        desde, hasta = rango_bim
    else:
        desde = date(fecha_dt.year, 1, 1)
        hasta = date(fecha_dt.year, 12, 31)

    # 2. Sumar todos los puntos de reportes del alumno en el bimestre
    puntos_perdidos = db.query(func.coalesce(func.sum(models.NivelConducta.puntos), 0)).select_from(
        models.ReporteConducta
    ).join(models.NivelConducta).filter(
        models.ReporteConducta.id_alumno == id_alumno,
        func.date(models.ReporteConducta.fecha_reporte) >= desde,
        func.date(models.ReporteConducta.fecha_reporte) <= hasta,
    ).scalar() or 0

    nueva_nota = calcular_puntaje(int(puntos_perdidos))

    # 3. Actualizar o insertar en `nota_conducta`
    reg = db.query(models.NotaConducta).filter(
        models.NotaConducta.id_matricula == matricula.id_matricula,
        models.NotaConducta.bimestre == num_bimestre,
    ).first()

    if reg:
        reg.valor = nueva_nota
        reg.origen = "CALCULADO"
        reg.fecha_registro = datetime.now()
    else:
        reg = models.NotaConducta(
            id_matricula=matricula.id_matricula,
            bimestre=num_bimestre,
            valor=nueva_nota,
            origen="CALCULADO",
        )
        db.add(reg)

    return {
        "bimestre": num_bimestre,
        "puntos_descontados": int(puntos_perdidos),
        "nota_calculada": nueva_nota,
        "id_matricula": matricula.id_matricula
    }

def _serializar_reporte(r: "models.ReporteConducta") -> dict:
    """Forma común de un reporte para las bandejas del auxiliar y del psicólogo."""
    return {
        "id_reporte": r.id_reporte,
        "id_alumno": r.id_alumno,
        "id_nivel_conducta": r.id_nivel_conducta,
        "id_tipo_falta": r.nivel.id_tipo_falta if r.nivel else None,
        "fecha": r.fecha_reporte.strftime("%d/%m/%Y %H:%M") if r.fecha_reporte else "",
        "alumno": f"{r.alumno.nombres} {r.alumno.apellidos}" if r.alumno else "Alumno no disponible",
        "dni": r.alumno.dni if r.alumno else None,
        "falta": r.nivel.nombre if r.nivel else "Falta registrada",
        "tipo_falta": r.nivel.tipo.nombre if r.nivel and r.nivel.tipo else None,
        "puntos": r.nivel.puntos if r.nivel else 0,
        "medida": r.nivel.medida if r.nivel else None,
        "cambio_ie": bool(r.nivel.cambio_ie) if r.nivel else False,
        "descripcion": r.descripcion_suceso,
    }

def _serializar_eliminado(e: "models.ReporteConductaEliminado") -> dict:
    """Forma de un reporte borrado para el historial de eliminados."""
    return {
        "id_eliminado": e.id_eliminado,
        "id_reporte": e.id_reporte,
        "id_alumno": e.id_alumno,
        "alumno": e.alumno or "Alumno no disponible",
        "dni": e.dni,
        "falta": e.falta or "Falta registrada",
        "tipo_falta": e.tipo_falta,
        "puntos": e.puntos or 0,
        "medida": e.medida,
        "cambio_ie": bool(e.cambio_ie),
        "descripcion": e.descripcion_suceso,
        "fecha": e.fecha_reporte.strftime("%d/%m/%Y %H:%M") if e.fecha_reporte else "",
        "motivo": e.motivo,
        "eliminado_por": e.eliminado_por or "Usuario no disponible",
        "rol_elimina": e.rol_elimina,
        "fecha_eliminacion": (e.fecha_eliminacion.strftime("%d/%m/%Y %H:%M")
                              if e.fecha_eliminacion else ""),
    }


def _nombre_de_usuario(db: Session, id_usuario: Optional[int], rol: Optional[str]) -> Optional[str]:
    """Nombre y apellidos de quien está usando el sistema.

    El historial de borrados guarda el nombre escrito, no solo el id: quien
    borra un reporte hoy puede no seguir en el colegio dentro de dos años, y el
    registro tiene que seguir diciendo quién fue.
    """
    tabla = {
        "AUXILIAR": personal_models.Auxiliar,
        "ADMIN": personal_models.Administrador,
        "PSICOLOGO": personal_models.Psicologo,
    }.get((rol or "").strip().upper())
    if not id_usuario or tabla is None:
        return None

    fila = (db.query(tabla.nombres, tabla.apellidos)
            .filter(tabla.id_usuario == id_usuario).first())
    return f"{fila[0]} {fila[1]}".strip() if fila else None


def _tiene_cambio_ie(db: Session, id_alumno: int, anio: int) -> bool:
    """True si el alumno tiene registrada en el año una falta que amerita cambio de I.E."""
    return db.query(models.ReporteConducta.id_reporte).join(models.NivelConducta).filter(
        models.ReporteConducta.id_alumno == id_alumno,
        extract('year', models.ReporteConducta.fecha_reporte) == anio,
        models.NivelConducta.cambio_ie.is_(True)
    ).first() is not None

@router.post("/reportes/")
def crear_reporte_auxiliar(reporte: schemas.ReporteCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") not in ["AUXILIAR", "ADMIN"]:
        raise HTTPException(status_code=403, detail="No tienes permisos para registrar reportes")

    alumno = db.query(alumno_models.Alumno).filter(
        alumno_models.Alumno.id_alumno == reporte.id_alumno
    ).first()
    if not alumno:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    nivel = db.query(models.NivelConducta).filter(
        models.NivelConducta.id_nivel_conducta == reporte.id_nivel_conducta
    ).first()
    if not nivel:
        raise HTTPException(status_code=404, detail="El tipo de falta seleccionado no existe")

    nuevo_reporte = models.ReporteConducta(
        id_alumno=reporte.id_alumno,
        id_nivel_conducta=reporte.id_nivel_conducta,
        descripcion_suceso=reporte.descripcion_suceso,
    )
    db.add(nuevo_reporte)
    db.commit()
    db.refresh(nuevo_reporte)

    # Recalcular automáticamente nota de conducta del bimestre y actualizar en BD
    recalc = _recalcular_nota_conducta_alumno_bimestre(db, nuevo_reporte.id_alumno, nuevo_reporte.fecha_reporte)
    db.commit()

    anio_actual = datetime.now().year
    puntaje = recalc["nota_calculada"]
    numero_bimestre = recalc["bimestre"]
    requiere_cambio_ie = bool(nivel.cambio_ie) or _tiene_cambio_ie(db, reporte.id_alumno, anio_actual)

    return {
        "mensaje": "Reporte registrado con éxito",
        "id_reporte": nuevo_reporte.id_reporte,
        "falta": nivel.nombre,
        "puntos_descontados": nivel.puntos,
        "medida": nivel.medida,
        "alumno": f"{alumno.nombres} {alumno.apellidos}",
        "puntaje_actual": puntaje,
        "estado_color": estado_visual(puntaje, requiere_cambio_ie),
        "requiere_cambio_ie": requiere_cambio_ie,
        "bimestre": numero_bimestre,
        "puntaje_maximo": PUNTAJE_MAXIMO,
        "umbral_observacion": UMBRAL_OBSERVACION,
        "umbral_critico": UMBRAL_CRITICO,
    }

@router.put("/reportes/{id_reporte}")
def actualizar_reporte_auxiliar(
    id_reporte: int,
    datos: schemas.ReporteUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Permite editar un reporte de conducta y recalcula automáticamente
    la nota de conducta del bimestre correspondiente del estudiante.
    """
    if current_user.get("rol") not in ["AUXILIAR", "ADMIN"]:
        raise HTTPException(status_code=403, detail="No tienes permisos para editar reportes de conducta")

    reporte = db.query(models.ReporteConducta).filter(
        models.ReporteConducta.id_reporte == id_reporte
    ).first()
    if not reporte:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")

    nivel = db.query(models.NivelConducta).filter(
        models.NivelConducta.id_nivel_conducta == datos.id_nivel_conducta
    ).first()
    if not nivel:
        raise HTTPException(status_code=404, detail="El tipo de falta seleccionado no existe")

    reporte.id_nivel_conducta = datos.id_nivel_conducta
    reporte.descripcion_suceso = datos.descripcion_suceso
    db.commit()
    db.refresh(reporte)

    # Recalcular automáticamente la nota de conducta del bimestre
    recalc = _recalcular_nota_conducta_alumno_bimestre(db, reporte.id_alumno, reporte.fecha_reporte)
    db.commit()

    puntaje = recalc["nota_calculada"]
    numero_bimestre = recalc["bimestre"]
    anio_actual = reporte.fecha_reporte.year if reporte.fecha_reporte else datetime.now().year
    requiere_cambio_ie = bool(nivel.cambio_ie) or _tiene_cambio_ie(db, reporte.id_alumno, anio_actual)

    alumno_nombre = f"{reporte.alumno.nombres} {reporte.alumno.apellidos}" if reporte.alumno else "Alumno"

    return {
        "mensaje": "Reporte actualizado con éxito",
        "id_reporte": reporte.id_reporte,
        "falta": nivel.nombre,
        "puntos_descontados": nivel.puntos,
        "medida": nivel.medida,
        "alumno": alumno_nombre,
        "puntaje_actual": puntaje,
        "estado_color": estado_visual(puntaje, requiere_cambio_ie),
        "requiere_cambio_ie": requiere_cambio_ie,
        "bimestre": numero_bimestre,
        "puntaje_maximo": PUNTAJE_MAXIMO,
        "umbral_observacion": UMBRAL_OBSERVACION,
        "umbral_critico": UMBRAL_CRITICO,
    }

@router.post("/reportes/{id_reporte}/eliminar")
def eliminar_reporte_auxiliar(
    id_reporte: int,
    datos: schemas.ReporteEliminar,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Elimina un reporte de conducta, deja constancia del motivo en el historial
    de eliminados y recalcula la nota de conducta del bimestre del estudiante.

    Es POST y no DELETE porque el motivo viaja en el cuerpo de la petición, y
    hay servidores intermedios que descartan el cuerpo de un DELETE. Sigue el
    mismo patrón que /citas/{id_cita}/cancelar.
    """
    if current_user.get("rol") not in ["AUXILIAR", "ADMIN"]:
        raise HTTPException(status_code=403, detail="No tienes permisos para eliminar reportes de conducta")

    reporte = (db.query(models.ReporteConducta)
               .options(joinedload(models.ReporteConducta.nivel).joinedload(models.NivelConducta.tipo),
                        joinedload(models.ReporteConducta.alumno))
               .filter(models.ReporteConducta.id_reporte == id_reporte).first())
    if not reporte:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")

    id_alumno = reporte.id_alumno
    fecha_reporte = reporte.fecha_reporte

    # Foto del reporte ANTES de borrarlo: nombre del alumno, de la falta y
    # puntos tal como estaban hoy. El catálogo de faltas se puede editar desde
    # el panel, así que guardar solo los ids dejaría el historial mintiendo.
    nivel, alumno = reporte.nivel, reporte.alumno
    borrado = models.ReporteConductaEliminado(
        id_reporte=reporte.id_reporte,
        id_alumno=id_alumno,
        alumno=f"{alumno.nombres} {alumno.apellidos}" if alumno else None,
        dni=alumno.dni if alumno else None,
        falta=nivel.nombre if nivel else None,
        tipo_falta=nivel.tipo.nombre if nivel and nivel.tipo else None,
        puntos=nivel.puntos if nivel else 0,
        medida=nivel.medida if nivel else None,
        cambio_ie=bool(nivel.cambio_ie) if nivel else False,
        descripcion_suceso=reporte.descripcion_suceso,
        fecha_reporte=fecha_reporte,
        motivo=datos.motivo,
        id_usuario=current_user.get("id"),
        eliminado_por=(_nombre_de_usuario(db, current_user.get("id"), current_user.get("rol"))
                       or current_user.get("sub")),
        rol_elimina=current_user.get("rol"),
    )

    # Constancia y borrado van en la misma transacción: si no se puede guardar
    # el motivo, el reporte no se borra. Un borrado sin constancia devuelve
    # puntos de conducta sin que quede dicho por qué.
    try:
        db.add(borrado)
        db.delete(reporte)
        db.commit()
    except (ProgrammingError, OperationalError):
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=("No se pudo registrar el borrado en el historial de eliminados, "
                    "así que el reporte no se eliminó. Avise al área de sistemas."))

    # Recalcular automáticamente la nota de conducta del bimestre
    recalc = _recalcular_nota_conducta_alumno_bimestre(db, id_alumno, fecha_reporte)
    db.commit()

    puntaje = recalc["nota_calculada"]
    numero_bimestre = recalc["bimestre"]

    return {
        "mensaje": "Reporte eliminado con éxito",
        "id_reporte": id_reporte,
        "puntaje_actual": puntaje,
        "bimestre": numero_bimestre,
        "eliminado": _serializar_eliminado(borrado),
    }

@router.get("/reportes/")
def listar_reportes(
    q: Optional[str] = Query(None, max_length=60),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Reportes de conducta, del más reciente al más antiguo.
    Sirve tanto a la bandeja del auxiliar (limit bajo) como al historial
    completo, que filtra por alumno con `q` y pagina con `offset`.
    """
    if current_user.get("rol") not in ["AUXILIAR", "PSICOLOGO"]:
        raise HTTPException(status_code=403, detail="No tienes permisos para ver los reportes")

    consulta = db.query(models.ReporteConducta).join(
        alumno_models.Alumno, models.ReporteConducta.id_alumno == alumno_models.Alumno.id_alumno
    )

    # Búsqueda por alumno: nombres, apellidos o DNI, palabra a palabra, para que
    # escribir el nombre completo tal como aparece en la lista encuentre al alumno.
    termino = (q or "").strip()
    if len(termino) >= 3:
        consulta = busqueda_util.filtrar(
            consulta, termino,
            alumno_models.Alumno.nombres,
            alumno_models.Alumno.apellidos,
            alumno_models.Alumno.dni,
        )

    total = consulta.count()
    reportes = consulta.order_by(
        models.ReporteConducta.fecha_reporte.desc(),
        models.ReporteConducta.id_reporte.desc()
    ).offset(offset).limit(limit).all()

    return {"total": total, "items": [_serializar_reporte(r) for r in reportes]}


@router.get("/reportes/eliminados")
def listar_reportes_eliminados(
    q: Optional[str] = Query(None, max_length=60),
    limit: int = Query(15, ge=1, le=50),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Reportes de conducta borrados, del borrado más reciente al más antiguo.

    Busca por el nombre y el DNI que tenía el alumno cuando se borró, igual que
    el historial normal, para que el mismo buscador filtre las dos listas.
    """
    if current_user.get("rol") not in ["AUXILIAR", "ADMIN", "PSICOLOGO"]:
        raise HTTPException(status_code=403, detail="No tienes permisos para ver los reportes eliminados")

    modelo = models.ReporteConductaEliminado
    try:
        consulta = db.query(modelo)

        termino = (q or "").strip()
        if len(termino) >= 3:
            consulta = busqueda_util.filtrar(consulta, termino, modelo.alumno, modelo.dni)

        total = consulta.count()
        filas = (consulta.order_by(modelo.fecha_eliminacion.desc(), modelo.id_eliminado.desc())
                 .offset(offset).limit(limit).all())
    except (ProgrammingError, OperationalError):
        # La tabla se crea con un SQL aparte. Mientras no esté, el historial
        # sale vacío en vez de tumbar la pantalla entera del auxiliar.
        db.rollback()
        return {"total": 0, "items": [], "disponible": False}

    return {"total": total, "items": [_serializar_eliminado(e) for e in filas], "disponible": True}


@router.get("/usuario/{id_usuario}/estado-conducta")
def obtener_estado_por_usuario(
    id_usuario: int, 
    anio: Optional[int] = Query(None), 
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("id") != id_usuario:
        raise HTTPException(status_code=403, detail="No puedes ver esta información")
    # 1. Buscar al alumno asociado
    alumno = db.query(alumno_models.Alumno).filter(
        alumno_models.Alumno.id_usuario == id_usuario
    ).first()

    if not alumno:
        raise HTTPException(status_code=404, detail="El usuario no tiene un perfil de alumno asociado")

    # 2. Definir el año a consultar (si no viene, usar el actual)
    if anio is None:
        anio = datetime.now().year

    # 3. Base de la consulta filtrada POR ALUMNO Y AÑO (Siempre)
    reportes = db.query(models.ReporteConducta).filter(
        models.ReporteConducta.id_alumno == alumno.id_alumno,
        extract('year', models.ReporteConducta.fecha_reporte) == anio
    ).order_by(models.ReporteConducta.fecha_reporte.desc()).all()

    # 4. Cálculo de puntos (los niveles guardan el descuento en positivo)
    #
    # El historial se sigue enseñando entero: al alumno le sirve ver todo lo
    # del año. Pero el PUNTAJE solo cuenta los reportes del bimestre en curso,
    # porque la nota de conducta se reinicia en cada uno.
    desde, hasta, numero_bimestre = _periodo(db, anio)
    del_bimestre = [r for r in reportes
                    if r.fecha_reporte and desde <= r.fecha_reporte.date() <= hasta]
    total_penalizacion = sum(r.nivel.puntos for r in del_bimestre if r.nivel)
    puntaje_actual = calcular_puntaje(total_penalizacion)
    # El cambio de I.E. es una medida extrema del reglamento: no se borra al
    # empezar un bimestre nuevo, se arrastra todo el año.
    requiere_cambio_ie = any(r.nivel.cambio_ie for r in reportes if r.nivel)

    # Los bimestres que vienen del sistema antiguo traen la nota de conducta ya
    # puesta por el colegio, y no hay reportes que la respalden: si se
    # recalculara saldría 20 para todos y no cuadraría con la libreta impresa.
    # Cuando existe esa nota migrada, manda ella.
    migrada = _conducta_migrada(db, alumno.id_alumno, str(anio), numero_bimestre)
    if migrada is not None:
        puntaje_actual = migrada

    return {
        "id_usuario": id_usuario,
        "id_alumno": alumno.id_alumno,
        "nombre_alumno": f"{alumno.nombres} {alumno.apellidos}",
        "anio_consultado": anio, # Es bueno devolver qué año se calculó
        "bimestre": numero_bimestre,
        "reportes_del_bimestre": len(del_bimestre),
        "nota_de_registro_anterior": migrada is not None,
        "puntaje_actual": puntaje_actual,
        "puntaje_maximo": PUNTAJE_MAXIMO,
        "umbral_observacion": UMBRAL_OBSERVACION,
        "umbral_critico": UMBRAL_CRITICO,
        "porcentaje_progreso": f"{round(puntaje_actual * 100 / PUNTAJE_MAXIMO)}%",
        "estado_color": estado_visual(puntaje_actual, requiere_cambio_ie),
        "requiere_cambio_ie": requiere_cambio_ie,
        "total_reportes": len(reportes),
        "historial": [
            {
                "id_reporte": r.id_reporte,
                "fecha": r.fecha_reporte.strftime("%d/%m/%Y"),
                "motivo": r.nivel.nombre if r.nivel else "Falta registrada",
                "puntos_restados": r.nivel.puntos if r.nivel else 0,
                "medida": r.nivel.medida if r.nivel else None,
                "cambio_ie": bool(r.nivel.cambio_ie) if r.nivel else False,
                "nota_reglamento": r.descripcion_suceso or (r.nivel.descripcion if r.nivel else "")
            } for r in reportes
        ]
    }


@router.get("/usuario/{id_usuario}/anios-reportes")
def obtener_anios_con_reportes(id_usuario: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if  current_user.get("id") != id_usuario:
        raise HTTPException(status_code=403, detail="No puedes ver esta información")
    # 1. Buscar al alumno
    alumno = db.query(alumno_models.Alumno).filter(
        alumno_models.Alumno.id_usuario == id_usuario
    ).first()

    if not alumno:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    # 2. Obtener años únicos de sus reportes
    # Usamos extract('year') y distinct para no repetir años
    anios = db.query(
        extract('year', models.ReporteConducta.fecha_reporte).label('anio')
    ).filter(
        models.ReporteConducta.id_alumno == alumno.id_alumno
    ).distinct().order_by(extract('year', models.ReporteConducta.fecha_reporte).desc()).all()

    # Retornamos una lista simple de enteros: [2026, 2025]
    return [int(a.anio) for a in anios]

@router.get("/niveles-conducta")
def listar_niveles_disponibles(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    # Llena el selector de faltas en la interfaz del auxiliar, agrupado por el
    # tipo de falta (criterio del Reglamento Interno).
    niveles = db.query(models.NivelConducta).join(models.TipoFalta).order_by(
        models.TipoFalta.id_tipo_falta, models.NivelConducta.id_nivel_conducta
    ).all()
    return [
        {
            "id_nivel_conducta": n.id_nivel_conducta,
            "nombre": n.nombre,
            "id_tipo_falta": n.id_tipo_falta,
            "tipo_falta": n.tipo.nombre,
            "puntos": n.puntos,
            "medida": n.medida,
            "cambio_ie": bool(n.cambio_ie),
            "descripcion": n.descripcion,
        } for n in niveles
    ]

# ---------------------------------------------------------------------------
# CATÁLOGO DE FALTAS  (Panel del administrador → Gestión de Estudiantes)
# ---------------------------------------------------------------------------
#
# Dos niveles, los mismos del Reglamento Interno:
#
#   tipo_falta       agrupa por criterio: "Respeto", "Honradez", "Asistencia y
#                    Puntualidad"...
#   nivel_conducta   la falta concreta y los puntos que descuenta.
#
# Es lo que llena el selector del auxiliar (`/conducta/niveles-conducta`) y lo
# que resta de los 20 puntos con los que cada alumno empieza el bimestre.
#
# Solo ADMIN: el auxiliar reporta faltas, pero no decide cuánto valen.
#
# Ojo con los puntos: la nota de conducta NO se guarda calculada, se deduce al
# vuelo sumando los reportes del bimestre. Cambiar los puntos de una falta ya
# usada recalcula hacia atrás la nota de todos los que la tienen. Por eso cada
# falta viaja con su número de usos, para que la pantalla pueda avisarlo.


def _usos_por_falta(db: Session, ids: Optional[list] = None) -> dict:
    """Cuántos reportes usa cada falta: {id_nivel_conducta: cuántos}.

    Una sola consulta agrupada para todo el catálogo. Con 26 faltas, preguntar
    una por una serían 26 viajes a la base cada vez que se abre la pantalla.
    """
    q = db.query(models.ReporteConducta.id_nivel_conducta,
                 func.count(models.ReporteConducta.id_reporte))
    if ids is not None:
        if not ids:
            return {}
        q = q.filter(models.ReporteConducta.id_nivel_conducta.in_(ids))
    return {fila[0]: int(fila[1] or 0)
            for fila in q.group_by(models.ReporteConducta.id_nivel_conducta).all()
            if fila[0] is not None}


def _falta_a_dict(n, usos: int) -> dict:
    return {
        "id_nivel_conducta": n.id_nivel_conducta,
        "id_tipo_falta": n.id_tipo_falta,
        "nombre": n.nombre,
        "puntos": n.puntos,
        "medida": n.medida,
        "cambio_ie": bool(n.cambio_ie),
        "descripcion": n.descripcion,
        "usos": usos,
    }


@router.get("/catalogo")
def catalogo_de_faltas(db: Session = Depends(get_db),
                       current_user: dict = Depends(require_roles("ADMIN"))):
    """Todo el catálogo en una sola petición, ya agrupado.

    Tres consultas para la pantalla entera —tipos, faltas y usos— en vez de
    una por cada grupo. `usos` es cuántos reportes de conducta apuntan a esa
    falta: la pantalla lo necesita para avisar antes de borrar o de cambiarle
    los puntos, y traerlo aquí evita una llamada extra por fila.
    """
    tipos = db.query(models.TipoFalta).order_by(models.TipoFalta.nombre).all()
    faltas = (db.query(models.NivelConducta)
              .order_by(models.NivelConducta.puntos.desc(),
                        models.NivelConducta.nombre)
              .all())
    usos = _usos_por_falta(db)

    por_tipo: dict = {}
    for n in faltas:
        por_tipo.setdefault(n.id_tipo_falta, []).append(
            _falta_a_dict(n, usos.get(n.id_nivel_conducta, 0)))

    ids_tipo = {t.id_tipo_falta for t in tipos}
    salida = []
    for t in tipos:
        hijas = por_tipo.get(t.id_tipo_falta, [])
        salida.append({
            "id_tipo_falta": t.id_tipo_falta,
            "nombre": t.nombre,
            "faltas": hijas,
            "total_faltas": len(hijas),
            "usos": sum(f["usos"] for f in hijas),
        })

    # Faltas cuyo tipo ya no existe. No debería pasar (hay clave foránea), pero
    # si pasara quedarían invisibles en la pantalla y sin forma de arreglarlas.
    huerfanas = [f for id_tipo, lista in por_tipo.items()
                 if id_tipo not in ids_tipo for f in lista]

    return {
        "puntaje_maximo": PUNTAJE_MAXIMO,
        "total_tipos": len(salida),
        "total_faltas": len(faltas),
        "tipos": salida,
        "huerfanas": huerfanas,
    }


# --- tipos de falta ---

@router.post("/tipos-falta")
def crear_tipo_falta(datos: schemas.TipoFaltaGuardar, db: Session = Depends(get_db),
                     current_user: dict = Depends(require_roles("ADMIN"))):
    existe = (db.query(models.TipoFalta)
              .filter(func.lower(models.TipoFalta.nombre) == datos.nombre.lower())
              .first())
    if existe:
        raise HTTPException(409, f"Ya existe un tipo de falta llamado «{existe.nombre}».")

    tipo = models.TipoFalta(nombre=datos.nombre)
    db.add(tipo)
    try:
        db.commit()
    except IntegrityError:
        # La columna es UNIQUE. La comprobación de arriba cubre el caso normal;
        # esto cubre que dos administradores guarden lo mismo a la vez.
        db.rollback()
        raise HTTPException(409, "Ya existe un tipo de falta con ese nombre.")
    db.refresh(tipo)
    return {"id_tipo_falta": tipo.id_tipo_falta, "nombre": tipo.nombre,
            "faltas": [], "total_faltas": 0, "usos": 0}


@router.put("/tipos-falta/{id_tipo_falta}")
def editar_tipo_falta(id_tipo_falta: int, datos: schemas.TipoFaltaGuardar,
                      db: Session = Depends(get_db),
                      current_user: dict = Depends(require_roles("ADMIN"))):
    tipo = (db.query(models.TipoFalta)
            .filter(models.TipoFalta.id_tipo_falta == id_tipo_falta).first())
    if not tipo:
        raise HTTPException(404, "Ese tipo de falta ya no existe.")

    repetido = (db.query(models.TipoFalta)
                .filter(func.lower(models.TipoFalta.nombre) == datos.nombre.lower(),
                        models.TipoFalta.id_tipo_falta != id_tipo_falta)
                .first())
    if repetido:
        raise HTTPException(409, f"Ya existe otro tipo de falta llamado «{repetido.nombre}».")

    tipo.nombre = datos.nombre
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe otro tipo de falta con ese nombre.")
    db.refresh(tipo)
    return {"id_tipo_falta": tipo.id_tipo_falta, "nombre": tipo.nombre}


@router.delete("/tipos-falta/{id_tipo_falta}")
def eliminar_tipo_falta(id_tipo_falta: int, db: Session = Depends(get_db),
                        current_user: dict = Depends(require_roles("ADMIN"))):
    """Solo se borra un tipo vacío.

    Borrarlo con faltas dentro rompería la clave foránea —error 500 y sin
    explicación— o dejaría faltas colgando de un tipo inexistente. Se responde
    diciendo cuántas hay que mover o borrar antes.
    """
    tipo = (db.query(models.TipoFalta)
            .filter(models.TipoFalta.id_tipo_falta == id_tipo_falta).first())
    if not tipo:
        raise HTTPException(404, "Ese tipo de falta ya no existe.")

    dentro = (db.query(func.count(models.NivelConducta.id_nivel_conducta))
              .filter(models.NivelConducta.id_tipo_falta == id_tipo_falta).scalar() or 0)
    if dentro:
        raise HTTPException(
            409,
            f"«{tipo.nombre}» tiene {dentro} "
            f"{'falta' if dentro == 1 else 'faltas'} dentro. "
            f"Bórralas o cámbialas de tipo antes de quitar el grupo.")

    nombre = tipo.nombre
    db.delete(tipo)
    db.commit()
    return {"message": f"Tipo de falta «{nombre}» eliminado."}


# --- faltas concretas ---

def _tipo_o_404(db: Session, id_tipo_falta: int) -> None:
    existe = (db.query(models.TipoFalta.id_tipo_falta)
              .filter(models.TipoFalta.id_tipo_falta == id_tipo_falta).first())
    if not existe:
        raise HTTPException(404, "El tipo de falta elegido ya no existe. Recarga la pantalla.")


def _falta_repetida(db: Session, id_tipo_falta: int, nombre: str,
                    excluir: Optional[int] = None):
    """Misma falta dos veces dentro del mismo tipo.

    Se compara sin distinguir mayúsculas: dos entradas que solo se diferencian
    en eso son la misma para quien tiene que elegir una en el desplegable.
    """
    q = (db.query(models.NivelConducta)
         .filter(models.NivelConducta.id_tipo_falta == id_tipo_falta,
                 func.lower(models.NivelConducta.nombre) == nombre.lower()))
    if excluir is not None:
        q = q.filter(models.NivelConducta.id_nivel_conducta != excluir)
    return q.first()


@router.post("/faltas")
def crear_falta(datos: schemas.FaltaGuardar, db: Session = Depends(get_db),
                current_user: dict = Depends(require_roles("ADMIN"))):
    _tipo_o_404(db, datos.id_tipo_falta)

    repetida = _falta_repetida(db, datos.id_tipo_falta, datos.nombre)
    if repetida:
        raise HTTPException(409, f"Ese tipo ya tiene una falta llamada «{repetida.nombre}».")

    falta = models.NivelConducta(**datos.model_dump())
    db.add(falta)
    db.commit()
    db.refresh(falta)
    return _falta_a_dict(falta, 0)


@router.put("/faltas/{id_nivel_conducta}")
def editar_falta(id_nivel_conducta: int, datos: schemas.FaltaGuardar,
                 db: Session = Depends(get_db),
                 current_user: dict = Depends(require_roles("ADMIN"))):
    """Cambiar los puntos de una falta recalcula la conducta hacia atrás.

    No es un descuido: la nota se deduce al vuelo restando de 20 los puntos de
    los reportes del bimestre, así que corregir un valor mal puesto arregla
    también las notas que salieron mal. Se devuelve cuántos reportes usan la
    falta para que la pantalla lo diga antes y después de guardar.
    """
    falta = (db.query(models.NivelConducta)
             .filter(models.NivelConducta.id_nivel_conducta == id_nivel_conducta).first())
    if not falta:
        raise HTTPException(404, "Esa falta ya no existe.")

    _tipo_o_404(db, datos.id_tipo_falta)

    repetida = _falta_repetida(db, datos.id_tipo_falta, datos.nombre,
                               excluir=id_nivel_conducta)
    if repetida:
        raise HTTPException(409, f"Ese tipo ya tiene una falta llamada «{repetida.nombre}».")

    for campo, valor in datos.model_dump().items():
        setattr(falta, campo, valor)
    db.commit()
    db.refresh(falta)

    usos = _usos_por_falta(db, [id_nivel_conducta]).get(id_nivel_conducta, 0)
    return _falta_a_dict(falta, usos)


@router.delete("/faltas/{id_nivel_conducta}")
def eliminar_falta(id_nivel_conducta: int, db: Session = Depends(get_db),
                   current_user: dict = Depends(require_roles("ADMIN"))):
    """No se borra una falta que ya se le puso a alguien.

    `reporte_conducta` apunta aquí. Borrarla dejaría reportes sin motivo y
    cambiaría sola la nota de conducta de esos alumnos. Para retirar una falta
    del reglamento sin perder el historial, lo suyo es dejar de usarla.
    """
    falta = (db.query(models.NivelConducta)
             .filter(models.NivelConducta.id_nivel_conducta == id_nivel_conducta).first())
    if not falta:
        raise HTTPException(404, "Esa falta ya no existe.")

    usos = _usos_por_falta(db, [id_nivel_conducta]).get(id_nivel_conducta, 0)
    if usos:
        raise HTTPException(
            409,
            f"«{falta.nombre}» está en {usos} "
            f"{'reporte' if usos == 1 else 'reportes'} de conducta. "
            f"Si se borra, esos partes se quedan sin motivo y cambia la nota de "
            f"esos alumnos. Puedes editarla, pero no quitarla.")

    nombre = falta.nombre
    db.delete(falta)
    db.commit()
    return {"message": f"Falta «{nombre}» eliminada."}


# --- ENDPOINTS DE CITAS PSICOLÓGICAS ---

@router.post("/citas/")
def programar_cita(cita: schemas.CitaCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Permite al psicólogo o auxiliar agendar una nueva cita."""
    if current_user.get("rol") != "AUXILIAR" and current_user.get("rol") != "PSICOLOGO":
        raise HTTPException(status_code=403, detail="No puedes mddificar esta información")
    
    # Validación 1: Fecha en el futuro
    if cita.fecha_cita <= datetime.now():
        raise HTTPException(status_code=400, detail="La fecha y hora de la cita debe ser posterior al momento actual.")

    # Validación 2: Prevención de colisión de horarios
    cita_existente = db.query(models.CitaPsicologia).filter(
        models.CitaPsicologia.fecha_cita == cita.fecha_cita,
        models.CitaPsicologia.estado.in_(["PROGRAMADA", "REPROGRAMADA"])
    ).first()

    if cita_existente:
        raise HTTPException(status_code=400, detail="El horario seleccionado ya se encuentra ocupado por otra cita.")
    
    nueva_cita = models.CitaPsicologia(**cita.model_dump())
    db.add(nueva_cita)
    db.commit()
    db.refresh(nueva_cita)
    return {"mensaje": "Cita programada exitosamente", "data": nueva_cita}

@router.get("/usuario/{id_usuario}/citas")
def obtener_citas_estudiante(
    id_usuario: int, 
    solo_pendientes: bool = True,
    db: Session = Depends(get_db), 
    current_user: dict = Depends(get_current_user)
):
    """
    Lista las citas programadas pendientes para el estudiante logueado.
    """
    if current_user.get("id") != id_usuario:
        raise HTTPException(status_code=403, detail="No puedes ver esta información")
    # 1. Buscar al alumno asociado al usuario
    alumno = db.query(alumno_models.Alumno).filter(
        alumno_models.Alumno.id_usuario == id_usuario
    ).first()

    if not alumno:
        raise HTTPException(status_code=404, detail="Perfil de alumno no encontrado")

    # 2. Obtener citas pendientes ordenadas por fecha (las más próximas primero)
    query = db.query(models.CitaPsicologia).filter(
        models.CitaPsicologia.id_alumno == alumno.id_alumno
    )
    if solo_pendientes:
        query = query.filter(models.CitaPsicologia.estado.in_(["PROGRAMADA", "REPROGRAMADA"]))

    citas = query.order_by(models.CitaPsicologia.fecha_cita.asc()).all()

    return [
        {
            "id_cita": c.id_cita,
            "motivo": c.motivo,
            "fecha": c.fecha_cita.strftime("%d/%m/%Y"),
            "hora": c.fecha_cita.strftime("%H:%M %p"),
            "estado": c.estado,
            "resultado": c.resultado_reunion,
            "es_hoy": c.fecha_cita.date() == datetime.now().date()
        } for c in citas
    ]

@router.patch("/citas/{id_cita}/completar")
def finalizar_cita(
    id_cita: int,
    datos: schemas.CitaResultado,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    El psicólogo registra lo ocurrido en la reunión y cierra la cita.

    El texto llega en el cuerpo de la petición. Antes se recibía como query
    param, lo que obligaba a meter el relato de la sesión en la URL.
    """
    if current_user.get("rol") not in ("AUXILIAR", "PSICOLOGO"):
        raise HTTPException(status_code=403, detail="No puedes modificar esta información")

    cita = db.query(models.CitaPsicologia).filter(models.CitaPsicologia.id_cita == id_cita).first()
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada")

    # Una cita cancelada no se atendió, y una ya cerrada no se cierra dos veces.
    if cita.estado not in ("PROGRAMADA", "REPROGRAMADA"):
        raise HTTPException(
            status_code=400,
            detail=f"Solo se pueden cerrar citas pendientes. Esta cita está {cita.estado}.",
        )

    cita.estado = "COMPLETADA"
    cita.resultado_reunion = datos.resultado.strip()
    db.commit()
    return {"mensaje": "Cita finalizada y registrada"}




# 1. Endpoint para el Resumen (Solo envía LA PRÓXIMA CITA activa)
@router.get("/usuario/{id_usuario}/proxima-cita")
def obtener_proxima_cita(id_usuario: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("id") != id_usuario:
        raise HTTPException(status_code=403, detail="No puedes ver esta información")
    alumno = db.query(alumno_models.Alumno).filter(alumno_models.Alumno.id_usuario == id_usuario).first()
    if not alumno:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    # Filtramos en la base de datos: solo citas activas (programadas o reprogramadas) y fecha futura
    cita = db.query(models.CitaPsicologia).filter(
        models.CitaPsicologia.id_alumno == alumno.id_alumno,
        models.CitaPsicologia.estado.in_(["PROGRAMADA", "REPROGRAMADA"]),
        models.CitaPsicologia.fecha_cita >= datetime.now()
    ).order_by(models.CitaPsicologia.fecha_cita.asc()).first() # .first() solo trae UNA

    if not cita:
        return None # El front recibirá un null, muy fácil de manejar

    return {
        "id_cita": cita.id_cita,
        "motivo": cita.motivo,
        "fecha": cita.fecha_cita.strftime("%d/%m/%Y"),
        "hora": cita.fecha_cita.strftime("%H:%M %p"),
        "es_hoy": cita.fecha_cita.date() == datetime.now().date()
    }

# 2. Endpoint para el Historial (Filtrado por año en DB)
@router.get("/usuario/{id_usuario}/historial-citas")
def obtener_historial_citas(
    id_usuario: int, 
    anio: Optional[int] = Query(None), 
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("id") != id_usuario:
        raise HTTPException(status_code=403, detail="No puedes ver esta información")
    
    alumno = db.query(alumno_models.Alumno).filter(alumno_models.Alumno.id_usuario == id_usuario).first()
    if not alumno:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    if not anio:
        anio = datetime.now().year

    # El filtro se hace en el motor de la base de datos
    citas = db.query(models.CitaPsicologia).filter(
        models.CitaPsicologia.id_alumno == alumno.id_alumno,
        extract('year', models.CitaPsicologia.fecha_cita) == anio
    ).order_by(models.CitaPsicologia.fecha_cita.desc()).all()

    return [
        {
            "id_cita": c.id_cita,
            "motivo": c.motivo,
            "fecha": c.fecha_cita.strftime("%d/%m/%Y"),
            "hora": c.fecha_cita.strftime("%H:%M"),
            "estado": c.estado,
            "resultado": c.resultado_reunion # Solo el historial ve el resultado
        } for c in citas
    ]


@router.get("/usuario/{id_usuario}/anios-citas")
def obtener_anios_con_citas(id_usuario: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Años en los que el alumno tiene citas registradas (para el selector del historial)."""
    if current_user.get("id") != id_usuario:
        raise HTTPException(status_code=403, detail="No puedes ver esta información")

    alumno = db.query(alumno_models.Alumno).filter(alumno_models.Alumno.id_usuario == id_usuario).first()
    if not alumno:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    anios = db.query(
        extract('year', models.CitaPsicologia.fecha_cita).label('anio')
    ).filter(
        models.CitaPsicologia.id_alumno == alumno.id_alumno
    ).distinct().order_by(extract('year', models.CitaPsicologia.fecha_cita).desc()).all()

    return [int(a.anio) for a in anios]


@router.patch("/citas/{id_cita}/reprogramar")
def reprogramar_cita(
    id_cita: int, 
    nueva_fecha: datetime, 
    db: Session = Depends(get_db), 
    current_user: dict = Depends(get_current_user)
):
    """Permite cambiar la fecha y hora de una cita pendiente."""
    if current_user.get("rol") not in ["AUXILIAR", "PSICOLOGO"]:
        raise HTTPException(status_code=403, detail="No tienes permisos")
    
    cita = db.query(models.CitaPsicologia).filter(models.CitaPsicologia.id_cita == id_cita).first()
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada")

    if cita.estado not in ("PROGRAMADA", "REPROGRAMADA"):
        raise HTTPException(status_code=400, detail="Solo se pueden reprogramar citas pendientes")

    # Validación 1: Fecha en el futuro
    if nueva_fecha <= datetime.now():
        raise HTTPException(status_code=400, detail="La nueva fecha y hora debe ser posterior al momento actual.")

    # Validación 2: Prevención de colisión de horarios (excluyendo la cita actual)
    cita_existente = db.query(models.CitaPsicologia).filter(
        models.CitaPsicologia.fecha_cita == nueva_fecha,
        models.CitaPsicologia.estado.in_(["PROGRAMADA", "REPROGRAMADA"]),
        models.CitaPsicologia.id_cita != id_cita
    ).first()

    if cita_existente:
        raise HTTPException(status_code=400, detail="El nuevo horario seleccionado ya se encuentra ocupado por otra cita.")
    
    cita.fecha_cita = nueva_fecha
    cita.estado = "REPROGRAMADA" # Opcional, o mantener como PROGRAMADA
    db.commit()
    return {"mensaje": "Cita reprogramada con éxito", "nueva_fecha": nueva_fecha.strftime("%d/%m/%Y %H:%M")}

@router.patch("/citas/{id_cita}/cancelar")
def cancelar_cita(id_cita: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") not in ["AUXILIAR", "PSICOLOGO"]:
        raise HTTPException(status_code=403, detail="No tienes permisos")
    
    cita = db.query(models.CitaPsicologia).filter(models.CitaPsicologia.id_cita == id_cita).first()
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    
    cita.estado = "CANCELADA"
    db.commit()
    return {"mensaje": "Cita cancelada"}

@router.get("/citas/agenda-diaria")
def obtener_agenda_dia(
    fecha: Optional[str] = Query(None, description="Fecha en formato YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("rol") not in ["AUXILIAR", "PSICOLOGO", "ADMIN"]:
        raise HTTPException(status_code=403, detail="Acceso denegado")

    query = db.query(
        models.CitaPsicologia.id_cita,
        models.CitaPsicologia.id_alumno,
        models.CitaPsicologia.motivo,
        models.CitaPsicologia.fecha_cita,
        models.CitaPsicologia.estado,
        models.CitaPsicologia.resultado_reunion,
        models.CitaPsicologia.id_familiar,
        (alumno_models.Alumno.nombres + " " + alumno_models.Alumno.apellidos).label("alumno_nombre"),
        alumno_models.Alumno.dni.label("alumno_dni")
    ).join(alumno_models.Alumno, models.CitaPsicologia.id_alumno == alumno_models.Alumno.id_alumno)

    if fecha and isinstance(fecha, str) and fecha.strip():
        # Filtrar por fecha específica
        query = query.filter(func.date(models.CitaPsicologia.fecha_cita) == fecha.strip())
        query = query.order_by(models.CitaPsicologia.fecha_cita.asc())
    else:
        # Por defecto muestra todas las citas, ordenadas por fecha más reciente
        query = query.order_by(models.CitaPsicologia.fecha_cita.desc())

    citas = query.all()

    return [
        {
            "id_cita": c.id_cita,
            "id_alumno": c.id_alumno,
            "motivo": c.motivo or "Sin motivo especificado",
            "fecha_cita": c.fecha_cita.isoformat() if hasattr(c.fecha_cita, "isoformat") else str(c.fecha_cita),
            "estado": c.estado,
            "resultado_reunion": c.resultado_reunion or "",
            "alumno_nombre": c.alumno_nombre,
            "alumno_dni": c.alumno_dni or "—",
        } for c in citas
    ]

def _apoderados_de_la_lista(db: Session, ids_alumnos: list) -> dict:
    """A quién llamar por cada alumno: {id_alumno: {apoderado, parentesco, telefono}}.

    Un alumno puede tener varios familiares registrados. Cuál manda no se
    decide aquí: se usa `PRIORIDAD_PARENTESCO` de `core/util/correo_usuario`,
    la misma lista con la que el sistema elige a quién mandarle los avisos.
    Si el psicólogo llamara a un familiar y el colegio escribiera a otro,
    tendríamos dos «apoderados» distintos para el mismo alumno.

    Entre los del mismo parentesco gana el que tenga teléfono: un apoderado
    sin número no sirve de nada en esta pantalla.
    """
    if not ids_alumnos:
        return {}
    relaciones = (
        db.query(RelacionFamiliar)
        .options(joinedload(RelacionFamiliar.familiar))
        .filter(RelacionFamiliar.id_alumno.in_(ids_alumnos))
        .all()
    )

    def prioridad(rel):
        tipo = (rel.tipo_parentesco or "").strip().upper()
        orden = (PRIORIDAD_PARENTESCO.index(tipo)
                 if tipo in PRIORIDAD_PARENTESCO else len(PRIORIDAD_PARENTESCO))
        sin_telefono = 0 if (rel.familiar and (rel.familiar.telefono or "").strip()) else 1
        return (sin_telefono, orden)

    mejor: dict = {}
    for rel in sorted(relaciones, key=prioridad):
        if not rel.familiar or rel.id_alumno in mejor:
            continue
        f = rel.familiar
        nombre = f"{f.apellidos or ''}, {f.nombres or ''}".strip(", ").strip()
        mejor[rel.id_alumno] = {
            "apoderado": nombre or None,
            "apoderado_parentesco": (rel.tipo_parentesco or "").strip() or None,
            "apoderado_telefono": (f.telefono or "").strip() or None,
        }
    return mejor


def _notas_migradas_varios(db: Session, ids_alumnos: list, anio: str,
                           numero_bimestre: Optional[int]) -> dict:
    """Las notas de conducta del sistema antiguo, para varios alumnos de una vez.

    Es `_conducta_migrada` en versión lista: una consulta en lugar de una por
    alumno, porque aquí se pintan todos los de la pantalla a la vez. Mismas
    salvaguardas: sin bimestre no hay nota que buscar, y si la tabla todavía
    no existe (base sin el script 20) se sigue con el puntaje calculado en vez
    de tumbar la pantalla.
    """
    if not numero_bimestre or not ids_alumnos:
        return {}
    try:
        filas = db.execute(
            text("SELECT m.id_alumno, nc.valor FROM nota_conducta nc "
                 "JOIN matricula m ON m.id_matricula = nc.id_matricula "
                 "WHERE m.id_anio_escolar = :anio AND nc.bimestre = :bim "
                 "  AND m.id_alumno IN :ids").bindparams(
                     bindparam("ids", expanding=True)),
            {"anio": anio, "bim": numero_bimestre, "ids": list(ids_alumnos)},
        ).all()
    except Exception:
        db.rollback()
        return {}
    return {f[0]: int(round(float(f[1]))) for f in filas if f[1] is not None}


def _conducta_de_la_lista(db: Session, ids_alumnos: list, reportes: list,
                          anio: int, numero_bimestre: Optional[int] = None) -> dict:
    """Estado de conducta de cada alumno de la lista: {id_alumno: {...}}.

    Calcula lo mismo que `/usuario/{id}/estado-conducta` y con las mismas
    reglas —el puntaje sale de los reportes del BIMESTRE en curso, el cambio
    de I.E. se arrastra todo el AÑO, y una nota migrada manda sobre el
    cálculo—, pero para todos los alumnos de golpe y reaprovechando los
    reportes que la pantalla ya había traído. Si las dos pantallas dieran
    colores distintos para el mismo alumno, nadie sabría a cuál creer.
    """
    desde, hasta, numero_bimestre = _periodo(db, anio, numero_bimestre)
    migradas = _notas_migradas_varios(db, ids_alumnos, str(anio), numero_bimestre)

    perdidos = {i: 0 for i in ids_alumnos}
    cambio_ie = {i: False for i in ids_alumnos}
    del_bimestre = {i: 0 for i in ids_alumnos}
    for r in reportes:
        if r.id_alumno not in perdidos or not r.nivel or not r.fecha_reporte:
            continue
        fecha = r.fecha_reporte.date()
        if fecha.year != anio:
            continue
        # El cambio de I.E. es medida extrema: no se borra al empezar un
        # bimestre nuevo, cuenta en todo el año.
        if r.nivel.cambio_ie:
            cambio_ie[r.id_alumno] = True
        if desde <= fecha <= hasta:
            perdidos[r.id_alumno] += r.nivel.puntos or 0
            del_bimestre[r.id_alumno] += 1

    resultado = {}
    for i in ids_alumnos:
        migrada = migradas.get(i)
        puntaje = migrada if migrada is not None else calcular_puntaje(perdidos[i])
        resultado[i] = {
            "estado_conducta": estado_visual(puntaje, cambio_ie[i]),
            "puntaje_conducta": puntaje,
            "puntaje_maximo": PUNTAJE_MAXIMO,
            "conducta_bimestre": numero_bimestre,
            "reportes_del_bimestre": del_bimestre[i],
            "conducta_cambio_ie": cambio_ie[i],
            # Cuando la nota viene del sistema antiguo, el número NO sale de
            # los reportes de esta pantalla. Conviene que se sepa.
            "conducta_de_registro_anterior": migrada is not None,
        }
    return resultado


# Cómo se puede ordenar la lista. "conducta" no se puede pedirle al SQL: el
# puntaje no es una columna, sale de los reportes del bimestre.
ORDENES = ("reciente", "antiguo", "conducta")


@router.get("/alumnos-con-reportes")
def obtener_alumnos_con_reportes(
    orden: str = Query("reciente", description="reciente, antiguo o conducta "
                                               "(peor conducta primero)"),
    q: Optional[str] = Query(None, description="Buscar por nombre o DNI"),
    estado_conducta: Optional[str] = Query(
        None, description="Filtra por el semáforo de conducta: Verde, Amarillo "
                          "o Rojo. Sin valor, todos."),
    anio: Optional[int] = Query(None, description="Año escolar; por defecto el actual"),
    bimestre: Optional[int] = Query(
        None, ge=1, le=bimestres_util.TOTAL_BIMESTRES,
        description="Bimestre sobre el que se calcula la conducta; por defecto "
                    "el que corresponde a hoy"),
    incluir_sin_reportes: bool = Query(
        False, description="False (por defecto): solo alumnos con reportes, "
                           "como siempre. True: todos los alumnos activos."),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("rol") not in ["AUXILIAR", "PSICOLOGO", "ADMIN"]:
        raise HTTPException(status_code=403, detail="Acceso denegado")

    # Se valida ANTES de consultar. Un valor que no se reconoce se rechaza en
    # vez de ignorarse: ignorándolo se devolvería la lista entera y el
    # psicólogo creería estar viendo solo los críticos.
    estado_pedido = None
    if estado_conducta is not None and estado_conducta.strip():
        estado_pedido = normalizar_estado(estado_conducta)
        if estado_pedido is None:
            raise HTTPException(
                status_code=400,
                detail=f"Estado de conducta no reconocido: "
                       f"{estado_conducta.strip()!r}. Valores válidos: "
                       f"{', '.join(ESTADOS_CONDUCTA)}")

    orden = (orden or "reciente").strip().lower()
    if orden not in ORDENES:
        raise HTTPException(
            status_code=400,
            detail=f"Orden no reconocido: {orden!r}. Valores válidos: "
                   f"{', '.join(ORDENES)}")

    anio = anio or datetime.now().year

    # Subquery: alumnos con fecha máxima y conteo de reportes de conducta
    reportes_sub = db.query(
        models.ReporteConducta.id_alumno.label("id_alumno"),
        func.max(models.ReporteConducta.fecha_reporte).label("max_fecha_reporte"),
        func.count(models.ReporteConducta.id_reporte).label("total_reportes")
    ).group_by(models.ReporteConducta.id_alumno).subquery()

    # Subquery: total de citas psicológicas
    citas_sub = db.query(
        models.CitaPsicologia.id_alumno.label("id_alumno"),
        func.count(models.CitaPsicologia.id_cita).label("total_citas")
    ).group_by(models.CitaPsicologia.id_alumno).subquery()

    query = (
        db.query(
            alumno_models.Alumno.id_alumno,
            alumno_models.Alumno.nombres,
            alumno_models.Alumno.apellidos,
            alumno_models.Alumno.dni,
            reportes_sub.c.max_fecha_reporte,
            func.coalesce(reportes_sub.c.total_reportes, 0).label("total_reportes"),
            func.coalesce(citas_sub.c.total_citas, 0).label("total_citas")
        )
        .outerjoin(citas_sub, alumno_models.Alumno.id_alumno == citas_sub.c.id_alumno)
    )

    if incluir_sin_reportes:
        # Todos los alumnos activos, tengan o no reportes. Los retirados
        # quedan fuera, igual que en el resto de pantallas de este módulo:
        # el psicólogo no puede citar a quien ya no está en el colegio.
        query = (query
                 .outerjoin(reportes_sub,
                            alumno_models.Alumno.id_alumno == reportes_sub.c.id_alumno)
                 .filter(alumno_models.Alumno.estado_ingreso != "RETIRADO"))
    else:
        # El comportamiento de siempre: solo quien tiene algún reporte.
        query = query.join(
            reportes_sub, alumno_models.Alumno.id_alumno == reportes_sub.c.id_alumno)

    if q and isinstance(q, str) and q.strip():
        termino = q.strip()
        query = query.filter(
            or_(
                alumno_models.Alumno.nombres.like(f"%{termino}%"),
                alumno_models.Alumno.apellidos.like(f"%{termino}%"),
                alumno_models.Alumno.dni.like(f"%{termino}%")
            )
        )

    # "conducta" se ordena al final, cuando ya está calculado el puntaje. Aquí
    # se deja por fecha igualmente, porque `sorted` es estable y así el
    # desempate entre dos puntajes iguales sigue siendo el reporte más
    # reciente.
    #
    # El desempate por apellidos NO es cosmético: en el modo «Todos» hay
    # cientos de alumnos sin ningún reporte, y para todos ellos la fecha es
    # NULL. Ordenando solo por fecha, MySQL puede devolverlos en cualquier
    # orden y dos cargas seguidas de la misma pantalla salían barajadas.
    por_fecha = (reportes_sub.c.max_fecha_reporte.asc() if orden == "antiguo"
                 else reportes_sub.c.max_fecha_reporte.desc())
    query = query.order_by(por_fecha,
                           alumno_models.Alumno.apellidos.asc(),
                           alumno_models.Alumno.nombres.asc(),
                           alumno_models.Alumno.id_alumno.asc())

    alumnos = query.all()

    # Para cada alumno, obtenemos su grado/sección actual si existe matrícula
    ids_alumnos = [a.id_alumno for a in alumnos]
    matriculas = (
        db.query(
            matricula_models.Matricula.id_alumno,
            academic_models.Grado.nombre.label("grado_nombre"),
            academic_models.Seccion.nombre.label("seccion_nombre"),
            academic_models.Nivel.nombre.label("nivel_nombre")
        )
        .join(academic_models.Seccion, matricula_models.Matricula.id_seccion == academic_models.Seccion.id_seccion)
        .join(academic_models.Grado, academic_models.Seccion.id_grado == academic_models.Grado.id_grado)
        .join(academic_models.Nivel, academic_models.Grado.id_nivel == academic_models.Nivel.id_nivel)
        .filter(matricula_models.Matricula.id_alumno.in_(ids_alumnos))
        .all()
    ) if ids_alumnos else []

    mapa_mat = {m.id_alumno: m for m in matriculas}

    # Traemos el último reporte con detalle del nivel
    ultimos_reportes = (
        db.query(models.ReporteConducta)
        .options(joinedload(models.ReporteConducta.nivel))
        .filter(models.ReporteConducta.id_alumno.in_(ids_alumnos))
        .order_by(models.ReporteConducta.fecha_reporte.desc())
        .all()
    ) if ids_alumnos else []

    mapa_ultimo_reporte: dict[int, models.ReporteConducta] = {}
    for ur in ultimos_reportes:
        if ur.id_alumno not in mapa_ultimo_reporte:
            mapa_ultimo_reporte[ur.id_alumno] = ur

    # Se reaprovechan los reportes ya traídos: el semáforo no cuesta ni una
    # consulta más de reportes.
    conducta = _conducta_de_la_lista(db, ids_alumnos, ultimos_reportes, anio, bimestre)
    apoderados = _apoderados_de_la_lista(db, ids_alumnos)

    # Un alumno puede no tener familiar registrado. Se devuelven las claves
    # igualmente, en nulo, para que la pantalla pueda decir «sin teléfono» en
    # vez de no enseñar nada y dejar dudando si es que no se cargó.
    sin_apoderado = {"apoderado": None, "apoderado_parentesco": None,
                     "apoderado_telefono": None}

    resultados = []
    for a in alumnos:
        mat = mapa_mat.get(a.id_alumno)
        ur = mapa_ultimo_reporte.get(a.id_alumno)
        cond = conducta.get(a.id_alumno, {})
        # El filtro se aplica aquí y no en el SQL porque el estado de conducta
        # no es una columna: se calcula a partir de los reportes del bimestre.
        if estado_pedido and cond.get("estado_conducta") != estado_pedido:
            continue
        resultados.append({
            "id_alumno": a.id_alumno,
            "nombres": a.nombres,
            "apellidos": a.apellidos,
            "nombre_completo": f"{a.apellidos}, {a.nombres}".strip(),
            "dni": a.dni or "—",
            **cond,
            **apoderados.get(a.id_alumno, sin_apoderado),
            "nivel": mat.nivel_nombre if mat else None,
            "grado": mat.grado_nombre if mat else None,
            "seccion": mat.seccion_nombre if mat else None,
            "total_reportes": int(a.total_reportes or 0),
            "total_citas": int(a.total_citas or 0),
            "ultima_fecha_reporte": a.max_fecha_reporte.strftime("%d/%m/%Y %H:%M") if a.max_fecha_reporte else "—",
            # Sin ningún reporte no hay «última falta» que enseñar. Antes esta
            # lista solo traía alumnos reportados y el caso no existía; ahora
            # sí, y poner "Reporte disciplinario" a quien no tiene ninguno
            # sería decir algo falso.
            "ultima_falta": (ur.nivel.nombre if ur and ur.nivel
                             else ("Reporte disciplinario" if ur else None)),
            "tipo_falta": ur.nivel.tipo.nombre if ur and ur.nivel and ur.nivel.tipo else None,
            "puntos_descontados": ur.nivel.puntos if ur and ur.nivel else None,
            "requiere_cambio_ie": bool(ur.nivel.cambio_ie) if ur and ur.nivel else False,
        })

    if orden == "conducta":
        # Peor conducta primero. El SQL ya los dejó ordenados por fecha, y
        # `sorted` es estable, así que entre dos alumnos con el mismo puntaje
        # sigue mandando el del reporte más reciente. El que no tenga puntaje
        # (no debería pasar) se va al final en vez de reventar la comparación.
        resultados.sort(key=lambda r: (r.get("puntaje_conducta") is None,
                                       r.get("puntaje_conducta") or 0))

    return resultados

@router.get("/citas/alumnos-recientes")
def obtener_alumnos_citas_recientes(
    limit: int = Query(8, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Alumnos con los que se ha tenido una cita recientemente (más reciente primero).
    Alimenta la lista por defecto del apartado de Seguimiento de Alumnos."""
    if current_user.get("rol") not in ["AUXILIAR", "PSICOLOGO"]:
        raise HTTPException(status_code=403, detail="Acceso denegado")

    # Última fecha de cita por alumno
    ultimas = db.query(
        models.CitaPsicologia.id_alumno.label("id_alumno"),
        func.max(models.CitaPsicologia.fecha_cita).label("ultima_cita")
    ).group_by(models.CitaPsicologia.id_alumno).subquery()

    filas = db.query(
        alumno_models.Alumno.id_alumno,
        alumno_models.Alumno.nombres,
        alumno_models.Alumno.apellidos,
        alumno_models.Alumno.dni,
        ultimas.c.ultima_cita
    ).join(ultimas, alumno_models.Alumno.id_alumno == ultimas.c.id_alumno)\
     .order_by(ultimas.c.ultima_cita.desc())\
     .limit(limit).all()

    return [
        {
            "id_alumno": f.id_alumno,
            "nombres": f.nombres,
            "apellidos": f.apellidos,
            "dni": f.dni,
            "ultima_cita": f.ultima_cita,
        }
        for f in filas
    ]


@router.get("/seguimiento/{id_alumno}")
def obtener_seguimiento_detallado(id_alumno: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Vista integral para el psicólogo: Reportes de conducta + Citas pasadas."""
    if current_user.get("rol") not in ["AUXILIAR", "PSICOLOGO"]:
        raise HTTPException(status_code=403, detail="Acceso denegado")

    reportes = db.query(models.ReporteConducta)\
        .filter(models.ReporteConducta.id_alumno == id_alumno)\
        .order_by(models.ReporteConducta.fecha_reporte.desc()).all()
    citas = db.query(models.CitaPsicologia)\
        .filter(models.CitaPsicologia.id_alumno == id_alumno)\
        .order_by(models.CitaPsicologia.fecha_cita.desc()).all()

    # Resolvemos el nivel de conducta para que el front muestre información
    # legible (nombre de la falta, tipo, puntos y medida) en vez del id crudo.
    historial_conducta = [
        {
            "id_reporte": r.id_reporte,
            "fecha_reporte": r.fecha_reporte,
            "descripcion": r.descripcion_suceso,
            "id_nivel_conducta": r.id_nivel_conducta,
            "nivel_nombre": r.nivel.nombre if r.nivel else None,
            "tipo_falta": r.nivel.tipo.nombre if r.nivel and r.nivel.tipo else None,
            "puntos": r.nivel.puntos if r.nivel else None,
            "medida": r.nivel.medida if r.nivel else None,
            "cambio_ie": bool(r.nivel.cambio_ie) if r.nivel else False,
        }
        for r in reportes
    ]

    historial_psicologico = [
        {
            "id_cita": c.id_cita,
            "motivo": c.motivo,
            "fecha_cita": c.fecha_cita,
            "estado": c.estado,
            "resultado_reunion": c.resultado_reunion,
        }
        for c in citas
    ]

    return {
        "id_alumno": id_alumno,
        "total_incidentes": len(reportes),
        "total_citas": len(citas),
        "historial_conducta": historial_conducta,
        "historial_psicologico": historial_psicologico
    }

@router.get("/resumen-psicologo")
def obtener_resumen_dashboard(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") not in ["PSICOLOGO", "AUXILIAR"]:
        raise HTTPException(status_code=403, detail="No autorizado")
    
    anio_actual = datetime.now().year

    # Lógica para contar alumnos en riesgo (bajo el umbral de observación)
    # 1. Puntos perdidos por cada alumno EN EL BIMESTRE EN CURSO: el puntaje
    #    se reinicia en cada uno, así que sumar el año entero daría un número
    #    que no se corresponde con ninguna nota de conducta real.
    desde_bim, hasta_bim, _ = _periodo(db, anio_actual)
    subquery = db.query(
        models.ReporteConducta.id_alumno,
        func.sum(models.NivelConducta.puntos).label("total_perdido")
    ).join(models.NivelConducta).filter(
        func.date(models.ReporteConducta.fecha_reporte) >= desde_bim,
        func.date(models.ReporteConducta.fecha_reporte) <= hasta_bim,
    ).group_by(models.ReporteConducta.id_alumno).subquery()

    # 2. Contar en riesgo: bajo el umbral de observación o con falta de cambio de I.E.
    bajo_umbral = db.query(subquery.c.id_alumno).filter(
        (PUNTAJE_MAXIMO - subquery.c.total_perdido) < UMBRAL_OBSERVACION
    ).all()
    con_cambio_ie = db.query(models.ReporteConducta.id_alumno).join(models.NivelConducta).filter(
        extract('year', models.ReporteConducta.fecha_reporte) == anio_actual,
        models.NivelConducta.cambio_ie.is_(True)
    ).distinct().all()
    conteo_riesgo = len({fila[0] for fila in bajo_umbral} | {fila[0] for fila in con_cambio_ie})
    atenciones_mes = db.query(models.CitaPsicologia).filter(
        extract('month', models.CitaPsicologia.fecha_cita) == datetime.now().month,
        models.CitaPsicologia.estado == "COMPLETADA"
    ).count()

    # "Citas para Hoy": las de HOY que siguen pendientes de atender.
    # Antes contaba todas las citas en estado PROGRAMADA sin mirar la fecha, así
    # que el número crecía con el año y no coincidía con la agenda del día.
    # Se incluye REPROGRAMADA porque también está pendiente, y es el estado en
    # el que queda una cita a la que se le cambió la hora.
    citas_hoy = db.query(models.CitaPsicologia).filter(
        func.date(models.CitaPsicologia.fecha_cita) == datetime.now().date(),
        models.CitaPsicologia.estado.in_(["PROGRAMADA", "REPROGRAMADA"]),
    ).count()

    return {
        "citas_pendientes": citas_hoy,
        "alumnos_riesgo": conteo_riesgo,
        "atenciones_mes": atenciones_mes
    }

#Búsqueda de alumnos
@router.get("/buscar-alumnos")
def buscar_alumnos(
    q: str = Query(..., min_length=3),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Busca alumnos por nombre, apellidos o DNI (Escalable).

    Cada palabra debe aparecer en alguno de esos datos, sin importar el orden,
    para que escribir el nombre completo encuentre al alumno aunque nombres y
    apellidos estén en columnas distintas.
    """
    if current_user.get("rol") not in ["AUXILIAR", "PSICOLOGO", "ADMIN"]:
        raise HTTPException(status_code=403, detail="No tienes permisos para buscar alumnos")
    alumnos = busqueda_util.filtrar(
        db.query(alumno_models.Alumno).filter(alumno_models.Alumno.estado_ingreso != "RETIRADO"), q,
        alumno_models.Alumno.nombres,
        alumno_models.Alumno.apellidos,
        alumno_models.Alumno.dni,
    ).limit(10).all()  # Limitamos para que sea rápido

    return alumnos

@router.get("/alumnos-en-riesgo")
def obtener_alumnos_riesgo(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Devuelve la lista de alumnos que requieren atención psicológica por baja conducta."""
    if current_user.get("rol") not in ["PSICOLOGO", "AUXILIAR"]:
        raise HTTPException(status_code=403, detail="No autorizado")

    anio_actual = datetime.now().year
    
    # 1. Obtener todos los reportes del año actual con su respectivo alumno y nivel
    reportes = db.query(
        models.ReporteConducta
    ).join(
        alumno_models.Alumno, models.ReporteConducta.id_alumno == alumno_models.Alumno.id_alumno
    ).filter(
        extract('year', models.ReporteConducta.fecha_reporte) == anio_actual,
        alumno_models.Alumno.estado_ingreso != "RETIRADO"
    ).all()

    # 2. Agrupar puntos por alumno y detectar faltas con cambio de I.E.
    #
    # Los puntos solo cuentan dentro del bimestre en curso —se reinician en
    # cada uno—, pero el cambio de I.E. se arrastra todo el año: es una medida
    # extrema del reglamento y no se borra al pasar de bimestre.
    desde_bim, hasta_bim, _ = _periodo(db, anio_actual)
    puntajes_alumnos = {}
    alumnos_cambio_ie = set()
    for r in reportes:
        if r.alumno not in puntajes_alumnos:
            puntajes_alumnos[r.alumno] = 0
        if r.nivel:
            if r.fecha_reporte and desde_bim <= r.fecha_reporte.date() <= hasta_bim:
                puntajes_alumnos[r.alumno] += r.nivel.puntos
            if r.nivel.cambio_ie:
                alumnos_cambio_ie.add(r.alumno.id_alumno)

    # 3. Filtrar los que están en riesgo (bajo umbral o con falta de cambio de I.E.)
    alumnos_riesgo = []
    for alumno, puntos_perdidos in puntajes_alumnos.items():
        puntaje_actual = calcular_puntaje(puntos_perdidos)
        cambio_ie = alumno.id_alumno in alumnos_cambio_ie
        if puntaje_actual < UMBRAL_OBSERVACION or cambio_ie:
            alumnos_riesgo.append({
                "id_alumno": alumno.id_alumno,
                "nombre_completo": f"{alumno.nombres} {alumno.apellidos}",
                "dni": alumno.dni,
                "puntaje": puntaje_actual,
                "estado": estado_visual(puntaje_actual, cambio_ie),
                "requiere_cambio_ie": cambio_ie
            })

    # Ordenar priorizando los casos más críticos (menor puntaje)
    alumnos_riesgo.sort(key=lambda x: x["puntaje"])
    
    return alumnos_riesgo


# =========================================================================
# GESTIÓN Y LISTADO DE NOTAS DE CONDUCTA (PANEL AUXILIAR / DOCENTE TUTOR / ADMIN)
# =========================================================================

def _obtener_secciones_tutor(db: Session, current_user: dict, anio: str) -> Optional[list[int]]:
    """Si el usuario es DOCENTE, retorna la lista de id_seccion donde es tutor en ese año.
    Para otros roles (ADMIN, AUXILIAR, PSICOLOGO) retorna None (sin restricción)."""
    if current_user.get("rol") != "DOCENTE":
        return None
    from app.modules.users.docente import models as doc_models
    from app.modules.management import models as mng_models

    doc = db.query(doc_models.Docente).filter(doc_models.Docente.id_usuario == current_user.get("id")).first()
    if not doc:
        return []
    tutorias = (
        db.query(mng_models.TutorSeccion.id_seccion)
        .filter(
            mng_models.TutorSeccion.id_docente == doc.id_docente,
            mng_models.TutorSeccion.id_anio_escolar == anio,
        )
        .all()
    )
    return [t[0] for t in tutorias]


@router.get("/filtros")
def filtros_conducta(
    anio: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Opciones de filtros para la gestión de notas de conducta."""
    if current_user.get("rol") not in ["AUXILIAR", "ADMIN", "DOCENTE", "PSICOLOGO"]:
        raise HTTPException(status_code=403, detail="No tienes permisos para ver estos filtros")

    from app.modules.academic.models import AnioEscolar, Seccion, Grado, Nivel

    anios = [{"id": a.id_anio_escolar, "tipo": a.tipo, "activo": bool(a.activo)}
             for a in db.query(AnioEscolar).order_by(AnioEscolar.id_anio_escolar.desc()).all()]
    
    if not anio:
        activo = next((a for a in anios if a["activo"]), None)
        anio = activo["id"] if activo else (anios[0]["id"] if anios else "2026")

    secciones = []
    if anio:
        secciones = [{"id_seccion": s.id_seccion, "seccion": s.nombre,
                      "id_grado": g.id_grado, "grado": g.nombre,
                      "orden": g.orden or 0, "nivel": n.nombre}
                     for s, g, n in db.query(Seccion, Grado, Nivel)
                     .join(Grado, Grado.id_grado == Seccion.id_grado)
                     .join(Nivel, Nivel.id_nivel == Grado.id_nivel)
                     .filter(Seccion.id_anio_escolar == anio)
                     .order_by(Nivel.nombre, Grado.orden, Seccion.nombre).all()]

    secciones_tutor = _obtener_secciones_tutor(db, current_user, anio)
    es_tutor = True
    if secciones_tutor is not None:
        secciones = [s for s in secciones if s["id_seccion"] in secciones_tutor]
        es_tutor = len(secciones_tutor) > 0

    ae = db.query(AnioEscolar).filter(AnioEscolar.id_anio_escolar == anio).first()
    tipo_anio = ((getattr(ae, "tipo", None) or "REGULAR")).strip().upper()
    es_verano = tipo_anio == "VERANO"

    # El año de verano es un periodo continuo, no cuatro bimestres. Ofrecer los
    # cuatro dejaba elegir tramos que no existen y guardaba la conducta del
    # verano repartida en bimestres inventados.
    bimestres = [bimestres_util.BIMESTRE_UNICO_VERANO] if es_verano else [1, 2, 3, 4]

    bim_actual = bimestres_util.bimestre_actual(
        db, anio, getattr(ae, "fecha_inicio", None), getattr(ae, "fecha_fin", None),
        tipo=tipo_anio,
    ) or bimestres[0]

    return {
        "anios": anios,
        "anio": anio,
        "bimestres": bimestres,
        "bimestre_actual": bim_actual,
        "secciones": secciones,
        "es_tutor": es_tutor,
        # Para que la pantalla pueda ocultar el selector de bimestre y hablar de
        # "periodo" en vez de "bimestre" cuando el año es de verano.
        "es_verano": es_verano,
    }


@router.get("/notas", response_model=schemas.RespuestaListaConducta)
def listar_notas_conducta(
    anio: Optional[str] = Query(None, description="Año escolar; por defecto el activo"),
    bimestre: int = Query(1, ge=1, le=4, description="Número de bimestre (1-4)"),
    nivel: Optional[str] = Query(None),
    id_grado: Optional[int] = Query(None),
    id_seccion: Optional[int] = Query(None),
    q: Optional[str] = Query(None, description="Búsqueda por nombre, apellido o DNI"),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Lista las notas de conducta de los alumnos para un bimestre y año escolar.

    Permite al auxiliar, docente tutor y administrador visualizar:
      - Reportes de conducta en el bimestre y puntos descontados.
      - Nota calculada según reglamento (20 - puntos).
      - Nota manual o migrada guardada en la base.
      - Nota final efectiva e indicador de si coincide con el cálculo.
    """
    if current_user.get("rol") not in ["AUXILIAR", "ADMIN", "DOCENTE", "PSICOLOGO"]:
        raise HTTPException(status_code=403, detail="No tienes permisos para ver las notas de conducta")

    from app.modules.academic.models import AnioEscolar, Seccion, Grado, Nivel
    from app.modules.enrollment.models import Matricula

    # 1. Determinar año
    if not anio:
        activo = (db.query(AnioEscolar).filter(AnioEscolar.activo.is_(True))
                  .order_by(AnioEscolar.id_anio_escolar.desc()).first())
        anio = activo.id_anio_escolar if activo else "2026"

    # Restricción por tutoría si es docente
    secciones_tutor = _obtener_secciones_tutor(db, current_user, anio)
    if secciones_tutor is not None:
        if not secciones_tutor:
            return {
                "anio": anio,
                "bimestre": bimestre,
                "total": 0,
                "pagina": pagina,
                "por_pagina": por_pagina,
                "alumnos": [],
            }
        if id_seccion and id_seccion not in secciones_tutor:
            raise HTTPException(status_code=403, detail="Solo puedes consultar la conducta de la(s) sección(es) donde eres tutor.")

    ae = db.query(AnioEscolar).filter(AnioEscolar.id_anio_escolar == anio).first()
    fecha_inicio = getattr(ae, "fecha_inicio", None)
    fecha_fin = getattr(ae, "fecha_fin", None)
    tipo_anio = ((getattr(ae, "tipo", None) or "REGULAR")).strip().upper()

    # En verano solo hay un periodo. Se normaliza aquí para que una petición
    # con ?bimestre=3 (un enlace guardado del año regular, por ejemplo) devuelva
    # el periodo del verano en vez de una lista vacía.
    if tipo_anio == "VERANO":
        bimestre = bimestres_util.BIMESTRE_UNICO_VERANO

    # Rango de fechas del bimestre
    rango_bim = bimestres_util.rango(db, anio, bimestre, fecha_inicio, fecha_fin, tipo=tipo_anio)
    if rango_bim:
        desde, hasta = rango_bim
    else:
        # Fallback
        tramos = bimestres_util.calendario(db, anio, fecha_inicio, fecha_fin)
        if tramos:
            desde, hasta = next(((d, h) for n, d, h in tramos if n == bimestre), (date(int(anio), 1, 1), date(int(anio), 12, 31)))
        else:
            desde, hasta = date(int(anio), 1, 1), date(int(anio), 12, 31)

    # 2. Matrículas filtradas
    consulta = (
        db.query(
            Matricula.id_matricula,
            Matricula.id_alumno,
            alumno_models.Alumno.dni,
            alumno_models.Alumno.apellidos,
            alumno_models.Alumno.nombres,
            Nivel.nombre.label("nivel"),
            Grado.nombre.label("grado"),
            Grado.id_grado.label("id_grado"),
            Grado.orden.label("orden_grado"),
            Seccion.nombre.label("seccion"),
            Seccion.id_seccion.label("id_seccion"),
        )
        .join(alumno_models.Alumno, alumno_models.Alumno.id_alumno == Matricula.id_alumno)
        .join(Seccion, Seccion.id_seccion == Matricula.id_seccion)
        .join(Grado, Grado.id_grado == Seccion.id_grado)
        .join(Nivel, Nivel.id_nivel == Grado.id_nivel)
        .filter(
            Matricula.id_anio_escolar == anio,
            alumno_models.Alumno.estado_ingreso != "RETIRADO"
        )
    )

    if secciones_tutor is not None and not id_seccion:
        consulta = consulta.filter(Seccion.id_seccion.in_(secciones_tutor))

    if isinstance(nivel, str) and nivel:
        consulta = consulta.filter(Nivel.nombre == nivel)
    if isinstance(id_grado, int) and id_grado:
        consulta = consulta.filter(Grado.id_grado == id_grado)
    if isinstance(id_seccion, int) and id_seccion:
        consulta = consulta.filter(Seccion.id_seccion == id_seccion)

    termino = q.strip() if isinstance(q, str) else ""
    if termino:
        consulta = busqueda_util.filtrar(
            consulta, termino,
            alumno_models.Alumno.nombres,
            alumno_models.Alumno.apellidos,
            alumno_models.Alumno.dni,
        )

    total = consulta.count()

    filas = (
        consulta.order_by(
            Nivel.nombre.asc(),
            Grado.orden.asc(),
            Seccion.nombre.asc(),
            alumno_models.Alumno.apellidos.asc(),
            alumno_models.Alumno.nombres.asc(),
        )
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
        .all()
    )

    if not filas:
        return {
            "anio": anio,
            "bimestre": bimestre,
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "alumnos": []
        }

    ids_alumno = [f.id_alumno for f in filas]
    ids_matricula = [f.id_matricula for f in filas]

    # 3. Consultar reportes del bimestre para estos alumnos
    reportes_q = (
        db.query(
            models.ReporteConducta.id_alumno,
            func.count(models.ReporteConducta.id_reporte).label("num_reportes"),
            func.coalesce(func.sum(models.NivelConducta.puntos), 0).label("total_puntos"),
        )
        .join(models.NivelConducta, models.NivelConducta.id_nivel_conducta == models.ReporteConducta.id_nivel_conducta)
        .filter(
            models.ReporteConducta.id_alumno.in_(ids_alumno),
            func.date(models.ReporteConducta.fecha_reporte) >= desde,
            func.date(models.ReporteConducta.fecha_reporte) <= hasta,
        )
        .group_by(models.ReporteConducta.id_alumno)
        .all()
    )

    stats_reportes = {
        r.id_alumno: {
            "total_reportes": int(r.num_reportes or 0),
            "puntos_descontados": int(r.total_puntos or 0),
        }
        for r in reportes_q
    }

    # 4. Consultar notas de conducta guardadas (manuales o migradas)
    notas_guardadas_q = (
        db.query(models.NotaConducta)
        .filter(
            models.NotaConducta.id_matricula.in_(ids_matricula),
            models.NotaConducta.bimestre == bimestre,
        )
        .all()
    )
    notas_dict = {
        n.id_matricula: {
            "valor": float(n.valor),
            "origen": n.origen or "MANUAL"
        }
        for n in notas_guardadas_q
    }

    # 5. Construir respuesta
    alumnos_resultado = []
    for f in filas:
        rep = stats_reportes.get(f.id_alumno, {"total_reportes": 0, "puntos_descontados": 0})
        puntos_descontados = rep["puntos_descontados"]
        total_reportes = rep["total_reportes"]
        nota_calc = calcular_puntaje(puntos_descontados)

        guardada = notas_dict.get(f.id_matricula)
        if guardada is not None:
            nota_manual = guardada["valor"]
            origen = guardada["origen"]
            nota_final = nota_manual
            es_modificado = True
        else:
            nota_manual = None
            origen = "CALCULADO"
            nota_final = float(nota_calc)
            es_modificado = False

        cuadra = (round(nota_final) == nota_calc)

        nombre_completo = f"{f.apellidos or ''} {f.nombres or ''}".strip()

        alumnos_resultado.append({
            "id_matricula": f.id_matricula,
            "id_alumno": f.id_alumno,
            "dni": f.dni or "—",
            "alumno": nombre_completo,
            "nivel": f.nivel,
            "grado": f.grado,
            "id_grado": f.id_grado,
            "seccion": f.seccion,
            "id_seccion": f.id_seccion,
            "total_reportes": total_reportes,
            "puntos_descontados": puntos_descontados,
            "nota_calculada": nota_calc,
            "nota_manual": nota_manual,
            "nota_final": nota_final,
            "origen": origen,
            "es_modificado": es_modificado,
            "cuadra_con_calculo": cuadra,
        })

    return {
        "anio": anio,
        "bimestre": bimestre,
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "alumnos": alumnos_resultado,
    }


@router.post("/notas")
def guardar_nota_conducta(
    datos: schemas.NotaConductaUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Guarda o actualiza manualmente la nota de conducta de un estudiante."""
    if current_user.get("rol") not in ["AUXILIAR", "ADMIN", "DOCENTE"]:
        raise HTTPException(status_code=403, detail="No tienes permisos para modificar notas de conducta")

    if not (0 <= datos.nota <= 20):
        raise HTTPException(status_code=400, detail="La nota de conducta debe estar entre 0 y 20")

    from app.modules.enrollment.models import Matricula
    from app.modules.academic.models import AnioEscolar

    mat = db.query(Matricula).filter(Matricula.id_matricula == datos.id_matricula).first()
    if not mat:
        raise HTTPException(status_code=404, detail="Matrícula no encontrada")

    # Si es docente, verificar que sea tutor de la sección de este alumno
    if current_user.get("rol") == "DOCENTE":
        secciones_tutor = _obtener_secciones_tutor(db, current_user, mat.id_anio_escolar)
        if not secciones_tutor or mat.id_seccion not in secciones_tutor:
            raise HTTPException(
                status_code=403,
                detail="Solo el docente tutor de la sección puede modificar las notas de conducta de sus alumnos"
            )

    # Calcular puntos y nota esperada para validar
    ae = db.query(AnioEscolar).filter(AnioEscolar.id_anio_escolar == mat.id_anio_escolar).first()
    tipo_anio = ((getattr(ae, "tipo", None) or "REGULAR")).strip().upper()

    # En verano solo hay un periodo: se normaliza antes de guardar para que la
    # nota no quede archivada en un bimestre que ese año no tiene y luego no
    # aparezca al consultarla (`nota_conducta` es única por matrícula+bimestre).
    if tipo_anio == "VERANO":
        datos.bimestre = bimestres_util.BIMESTRE_UNICO_VERANO

    rango_bim = bimestres_util.rango(
        db, mat.id_anio_escolar, datos.bimestre,
        getattr(ae, "fecha_inicio", None), getattr(ae, "fecha_fin", None),
        tipo=tipo_anio,
    )
    if rango_bim:
        desde, hasta = rango_bim
    else:
        desde, hasta = date(int(mat.id_anio_escolar or 2026), 1, 1), date(int(mat.id_anio_escolar or 2026), 12, 31)

    puntos_perdidos = db.query(func.coalesce(func.sum(models.NivelConducta.puntos), 0)).select_from(
        models.ReporteConducta
    ).join(models.NivelConducta).filter(
        models.ReporteConducta.id_alumno == mat.id_alumno,
        func.date(models.ReporteConducta.fecha_reporte) >= desde,
        func.date(models.ReporteConducta.fecha_reporte) <= hasta,
    ).scalar() or 0

    nota_calc = calcular_puntaje(int(puntos_perdidos))

    # Guardar en base de datos
    registro = (
        db.query(models.NotaConducta)
        .filter(
            models.NotaConducta.id_matricula == datos.id_matricula,
            models.NotaConducta.bimestre == datos.bimestre,
        )
        .first()
    )

    if registro:
        registro.valor = datos.nota
        registro.origen = "MANUAL"
        registro.fecha_registro = datetime.now()
    else:
        registro = models.NotaConducta(
            id_matricula=datos.id_matricula,
            bimestre=datos.bimestre,
            valor=datos.nota,
            origen="MANUAL",
        )
        db.add(registro)

    db.commit()
    db.refresh(registro)

    return {
        "mensaje": "Nota de conducta guardada con éxito",
        "id_matricula": datos.id_matricula,
        "bimestre": datos.bimestre,
        "nota_guardada": float(registro.valor),
        "nota_calculada": nota_calc,
        "puntos_descontados": int(puntos_perdidos),
        "coincide": (round(float(registro.valor)) == nota_calc),
    }


@router.delete("/nota/{id_matricula}/{bimestre}")
def restablecer_nota_conducta(
    id_matricula: int,
    bimestre: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Elimina la nota manual de conducta para que vuelva al cálculo automático."""
    if current_user.get("rol") not in ["AUXILIAR", "ADMIN", "DOCENTE"]:
        raise HTTPException(status_code=403, detail="No tienes permisos para modificar notas de conducta")

    from app.modules.enrollment.models import Matricula
    mat = db.query(Matricula).filter(Matricula.id_matricula == id_matricula).first()
    if not mat:
        raise HTTPException(status_code=404, detail="Matrícula no encontrada")

    # Si es docente, verificar que sea tutor de la sección de este alumno
    if current_user.get("rol") == "DOCENTE":
        secciones_tutor = _obtener_secciones_tutor(db, current_user, mat.id_anio_escolar)
        if not secciones_tutor or mat.id_seccion not in secciones_tutor:
            raise HTTPException(
                status_code=403,
                detail="Solo el docente tutor de la sección puede modificar las notas de conducta de sus alumnos"
            )

    registro = (
        db.query(models.NotaConducta)
        .filter(
            models.NotaConducta.id_matricula == id_matricula,
            models.NotaConducta.bimestre == bimestre,
        )
        .first()
    )

    if registro:
        db.delete(registro)
        db.commit()

    return {"mensaje": "Nota de conducta restablecida al cálculo automático"}
