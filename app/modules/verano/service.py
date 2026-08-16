"""
Lógica de negocio del año académico de verano:
- Evaluación de fin de año (cursos desaprobados, promoción / nivelación / repitencia).
- Generación del pago fijo de verano y admisión al pagar.
- Utilidades para la renovación de matrícula (condicionada / repite).

Reglas:
- Nota mínima aprobatoria configurable (default 11): promedio_final < nota_minima => desaprobado.
- Primaria (2do-6to): se evalúa por año (sin acumular). 1ro de primaria nunca repite.
- Secundaria (1ro-5to): los desaprobados se acumulan mientras no se nivelen.
- <=3 desaprobados => REQUIERE_NIVELACION ; >=4 => REPITE ; 0 => PROMOVIDO.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session, joinedload

from app.modules.academic import models as ac_models
from app.modules.enrollment import models as en_models
from app.modules.management import models as mn_models
from app.modules.finance import models as fi_models
from app.modules.pagina_principal import models as cfg_models
from app.modules.users.alumno import models as al_models
from app.modules.users.alumno import estados as estados_alumno
from app.modules.users.relacion_familiar import models as rel_models
from app.modules.users import models as usuario_models
from app.core.util.password import get_password_hash
from app.core.util.usuarios import generar_username


NOTA_MINIMA_DEFAULT = Decimal("11")


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
def get_nota_minima(db: Session) -> Decimal:
    fila = db.query(cfg_models.PaginaConfiguracion).filter(
        cfg_models.PaginaConfiguracion.clave == "nota_minima_aprobatoria"
    ).first()
    if fila and fila.valor:
        try:
            return Decimal(str(fila.valor).strip())
        except Exception:
            return NOTA_MINIMA_DEFAULT
    return NOTA_MINIMA_DEFAULT


def nivel_de_grado(grado: ac_models.Grado) -> str:
    """Devuelve PRIMARIA / SECUNDARIA / OTRO a partir del nivel del grado."""
    if grado is None or grado.nivel is None:
        return "OTRO"
    nombre = (grado.nivel.nombre or "").lower()
    if "primaria" in nombre:
        return "PRIMARIA"
    if "secundaria" in nombre:
        return "SECUNDARIA"
    return "OTRO"


# ---------------------------------------------------------------------------
# Grupos / aulas de verano
# ---------------------------------------------------------------------------
GRUPOS_VERANO = {
    "PRIM_1_2": "1ro y 2do de Primaria",
    "PRIM_3_4": "3ro y 4to de Primaria",
    "PRIM_5_6": "5to y 6to de Primaria",
    "SEC_1": "1ro de Secundaria",
    "SEC_2": "2do de Secundaria",
    "SEC_3": "3ro de Secundaria",
    "PRE_ACADEMIA": "Pre Academia",
}


def _siguiente_grado(db: Session, grado: ac_models.Grado):
    """Siguiente grado (destino) — misma lógica que enrollment._calcular_siguiente_grado."""
    if grado is None:
        return None
    siguiente = db.query(ac_models.Grado).filter(
        ac_models.Grado.id_nivel == grado.id_nivel,
        ac_models.Grado.orden == grado.orden + 1,
    ).first()
    if siguiente:
        return siguiente
    nivel = db.query(ac_models.Nivel).filter(ac_models.Nivel.id_nivel == grado.id_nivel).first()
    if nivel and "primaria" in (nivel.nombre or "").lower():
        nivel_sec = db.query(ac_models.Nivel).filter(ac_models.Nivel.nombre.ilike("%secundaria%")).first()
        if nivel_sec:
            return db.query(ac_models.Grado).filter(
                ac_models.Grado.id_nivel == nivel_sec.id_nivel,
                ac_models.Grado.orden == 1,
            ).first()
    return None


def aula_grado(db: Session, grado_actual: ac_models.Grado):
    """Grado del aula de verano = grado al que pasa el alumno (destino).
    Si no hay destino (p. ej. 5º de secundaria egresa), usa el grado actual."""
    if grado_actual is None:
        return None
    return _siguiente_grado(db, grado_actual) or grado_actual


def grupo_por_grado(grado: ac_models.Grado):
    """Clave y etiqueta del grupo/aula de verano a partir del grado-aula (destino)."""
    if grado is None:
        return None, None
    nivel = nivel_de_grado(grado)
    o = grado.orden
    if nivel == "PRIMARIA":
        if o <= 2:
            clave = "PRIM_1_2"
        elif o <= 4:
            clave = "PRIM_3_4"
        else:
            clave = "PRIM_5_6"
    elif nivel == "SECUNDARIA":
        if o <= 3:
            clave = f"SEC_{o}"
        else:
            clave = "PRE_ACADEMIA"
    else:
        return None, None
    return clave, GRUPOS_VERANO.get(clave)


def grupo_de_alumno(db: Session, grado_actual: ac_models.Grado):
    """Devuelve (grado_aula, clave, etiqueta) para el grado actual de un alumno."""
    aula = aula_grado(db, grado_actual)
    clave, etiqueta = grupo_por_grado(aula)
    return aula, clave, etiqueta


# ---------------------------------------------------------------------------
# Evaluación de fin de año
# ---------------------------------------------------------------------------
def _correos_apoderados(db: Session, id_alumno: int):
    """Emails de los apoderados de un alumno."""
    rels = db.query(rel_models.RelacionFamiliar).options(
        joinedload(rel_models.RelacionFamiliar.familiar)
    ).filter(rel_models.RelacionFamiliar.id_alumno == id_alumno).all()
    correos = []
    for r in rels:
        if r.familiar and r.familiar.email and "@" in r.familiar.email:
            correos.append(r.familiar.email)
    return list(dict.fromkeys(correos))  # sin duplicados


def _html_correo_desaprobados(alumno, cursos_nombres, resultado, nota_minima):
    lista = "".join(f"<li>{c}</li>" for c in cursos_nombres)
    if resultado == "REPITE":
        detalle = (
            "<p>Al haber desaprobado <strong>4 o más cursos</strong>, según el reglamento su hijo(a) "
            "<strong>repetirá el año académico</strong>. Esta condición se reflejará al momento de renovar la matrícula.</p>"
        )
    else:
        detalle = (
            "<p>Su hijo(a) tiene la opción de <strong>recuperar estos cursos en el año académico de verano</strong> "
            "para nivelarse. Puede realizar la inscripción desde el campus, en el apartado de Matrícula.</p>"
            "<p>Si no se nivela pero renueva la matrícula, pasará de año con <strong>matrícula condicionada</strong> "
            "(apoyo académico adicional).</p>"
        )
    return f"""
    <div style="font-family:Arial,sans-serif;color:#333;max-width:600px;margin:auto">
      <h2 style="color:#701C32">Colegio Amancio Varona</h2>
      <p>Estimado apoderado de <strong>{alumno.nombres} {alumno.apellidos}</strong>,</p>
      <p>Le informamos que su hijo(a) ha desaprobado los siguientes cursos
      (nota mínima aprobatoria: {nota_minima}):</p>
      <ul>{lista}</ul>
      {detalle}
      <p style="margin-top:20px;color:#777;font-size:13px">Este es un mensaje automático, por favor no responda a este correo.</p>
    </div>
    """


def evaluar_cierre_anio(db: Session, id_anio: str) -> dict:
    """
    Evalúa el cierre de un año escolar.
    - Si el año es REGULAR: calcula desaprobados por alumno, clasifica el resultado,
      registra curso_desaprobado + evaluacion_final y prepara correos a los padres.
    - Si el año es VERANO: marca como recuperados los cursos que el alumno aprobó
      en verano (nivelación).
    Devuelve un resumen y la lista de correos a enviar (para BackgroundTask).
    """
    anio = db.query(ac_models.AnioEscolar).filter(
        ac_models.AnioEscolar.id_anio_escolar == id_anio
    ).first()
    if not anio:
        return {"error": "Año no encontrado", "correos": []}

    nota_minima = get_nota_minima(db)

    if (anio.tipo or "REGULAR").upper() == "VERANO":
        return _evaluar_cierre_verano(db, anio, nota_minima)

    return _evaluar_cierre_regular(db, anio, nota_minima)


def _evaluar_cierre_regular(db: Session, anio, nota_minima: Decimal) -> dict:
    matriculas = db.query(en_models.Matricula).options(
        joinedload(en_models.Matricula.grado).joinedload(ac_models.Grado.nivel),
        joinedload(en_models.Matricula.alumno),
    ).filter(
        en_models.Matricula.id_anio_escolar == anio.id_anio_escolar,
        en_models.Matricula.estado == "MATRICULADO",
    ).all()

    resumen = {"promovidos": 0, "requieren_nivelacion": 0, "repiten": 0, "evaluados": 0}
    correos = []

    for mat in matriculas:
        grado = mat.grado
        nivel = nivel_de_grado(grado)
        orden = grado.orden if grado else None

        # Cursos con promedio final por debajo de la nota mínima
        resumenes = db.query(mn_models.ResumenNota).filter(
            mn_models.ResumenNota.id_matricula == mat.id_matricula
        ).all()

        desaprobados = []
        for rn in resumenes:
            if rn.promedio_final is None:
                continue
            if rn.promedio_final < nota_minima:
                rn.estado_curso = "DESAPROBADO"
                desaprobados.append(rn)
            else:
                rn.estado_curso = "APROBADO"

        # Registrar curso_desaprobado (sin duplicar) — importado localmente para evitar ciclos
        from . import models as vr_models
        for rn in desaprobados:
            existe = db.query(vr_models.CursoDesaprobado).filter(
                vr_models.CursoDesaprobado.id_alumno == mat.id_alumno,
                vr_models.CursoDesaprobado.id_curso == rn.id_curso,
                vr_models.CursoDesaprobado.id_anio_escolar == anio.id_anio_escolar,
            ).first()
            if not existe:
                db.add(vr_models.CursoDesaprobado(
                    id_alumno=mat.id_alumno,
                    id_curso=rn.id_curso,
                    id_anio_escolar=anio.id_anio_escolar,
                    nivel=nivel,
                    promedio=rn.promedio_final,
                    recuperado=False,
                ))
        db.flush()

        total_anio = len(desaprobados)

        # Acumulado (solo secundaria) = desaprobados no recuperados del nivel
        acumulado = total_anio
        if nivel == "SECUNDARIA":
            acumulado = db.query(vr_models.CursoDesaprobado).filter(
                vr_models.CursoDesaprobado.id_alumno == mat.id_alumno,
                vr_models.CursoDesaprobado.nivel == "SECUNDARIA",
                vr_models.CursoDesaprobado.recuperado == False,  # noqa: E712
            ).count()

        # Clasificación
        if nivel == "PRIMARIA" and orden == 1:
            resultado = "PROMOVIDO"  # 1ro de primaria nunca repite
        elif nivel == "SECUNDARIA":
            if acumulado >= 4:
                resultado = "REPITE"
            elif total_anio >= 1:
                resultado = "REQUIERE_NIVELACION"
            else:
                resultado = "PROMOVIDO"
        else:  # PRIMARIA 2do-6to (u OTRO)
            if total_anio >= 4:
                resultado = "REPITE"
            elif total_anio >= 1:
                resultado = "REQUIERE_NIVELACION"
            else:
                resultado = "PROMOVIDO"

        # Guardar / actualizar evaluación final
        eval_row = db.query(vr_models.EvaluacionFinal).filter(
            vr_models.EvaluacionFinal.id_alumno == mat.id_alumno,
            vr_models.EvaluacionFinal.id_anio_escolar == anio.id_anio_escolar,
        ).first()
        if not eval_row:
            eval_row = vr_models.EvaluacionFinal(
                id_alumno=mat.id_alumno,
                id_anio_escolar=anio.id_anio_escolar,
            )
            db.add(eval_row)
        eval_row.id_matricula = mat.id_matricula
        eval_row.nivel = nivel
        eval_row.id_grado = mat.id_grado
        eval_row.total_desaprobados = total_anio
        eval_row.acumulado_desaprobados = acumulado
        eval_row.resultado = resultado

        resumen["evaluados"] += 1
        if resultado == "PROMOVIDO":
            resumen["promovidos"] += 1
        elif resultado == "REQUIERE_NIVELACION":
            resumen["requieren_nivelacion"] += 1
        else:
            resumen["repiten"] += 1

        # Preparar correo si hay desaprobados
        if total_anio >= 1 and not eval_row.correo_enviado:
            nombres_cursos = []
            for rn in desaprobados:
                curso = db.query(ac_models.Curso).filter(
                    ac_models.Curso.id_curso == rn.id_curso
                ).first()
                nombres_cursos.append(curso.nombre if curso else f"Curso {rn.id_curso}")
            for email in _correos_apoderados(db, mat.id_alumno):
                correos.append({
                    "destinatario": email,
                    "asunto": f"Situación académica de {mat.alumno.nombres} {mat.alumno.apellidos}",
                    "html": _html_correo_desaprobados(mat.alumno, nombres_cursos, resultado, nota_minima),
                })
            eval_row.correo_enviado = True

    db.commit()
    resumen["correos_encolados"] = len(correos)
    return {"resumen": resumen, "correos": correos}


def _evaluar_cierre_verano(db: Session, anio, nota_minima: Decimal) -> dict:
    """Al cerrar el verano, marca como recuperados los cursos aprobados en verano."""
    from . import models as vr_models
    recuperados = 0

    matriculas = db.query(en_models.Matricula).filter(
        en_models.Matricula.id_anio_escolar == anio.id_anio_escolar,
        en_models.Matricula.estado == "MATRICULADO",
    ).all()

    for mat in matriculas:
        resumenes = db.query(mn_models.ResumenNota).filter(
            mn_models.ResumenNota.id_matricula == mat.id_matricula
        ).all()
        aprobados_ids = {
            rn.id_curso for rn in resumenes
            if rn.promedio_final is not None and rn.promedio_final >= nota_minima
        }
        if not aprobados_ids:
            continue
        pendientes = db.query(vr_models.CursoDesaprobado).filter(
            vr_models.CursoDesaprobado.id_alumno == mat.id_alumno,
            vr_models.CursoDesaprobado.recuperado == False,  # noqa: E712
            vr_models.CursoDesaprobado.id_curso.in_(aprobados_ids),
        ).all()
        for cd in pendientes:
            cd.recuperado = True
            cd.id_anio_recuperado = anio.id_anio_escolar
            recuperados += 1

    db.commit()
    return {"resumen": {"cursos_recuperados": recuperados}, "correos": []}


# ---------------------------------------------------------------------------
# Utilidades para renovación de matrícula
# ---------------------------------------------------------------------------
def ultima_evaluacion(db: Session, id_alumno: int, id_anio_origen: str = None):
    from . import models as vr_models
    q = db.query(vr_models.EvaluacionFinal).filter(
        vr_models.EvaluacionFinal.id_alumno == id_alumno
    )
    if id_anio_origen:
        e = q.filter(vr_models.EvaluacionFinal.id_anio_escolar == id_anio_origen).first()
        if e:
            return e
    return q.order_by(vr_models.EvaluacionFinal.fecha.desc()).first()


def tiene_desaprobados_pendientes(db: Session, id_alumno: int) -> bool:
    from . import models as vr_models
    return db.query(vr_models.CursoDesaprobado).filter(
        vr_models.CursoDesaprobado.id_alumno == id_alumno,
        vr_models.CursoDesaprobado.recuperado == False,  # noqa: E712
    ).count() > 0


def cursos_desaprobados_pendientes(db: Session, id_alumno: int):
    from . import models as vr_models
    return db.query(vr_models.CursoDesaprobado).filter(
        vr_models.CursoDesaprobado.id_alumno == id_alumno,
        vr_models.CursoDesaprobado.recuperado == False,  # noqa: E712
    ).all()


# ---------------------------------------------------------------------------
# Pago fijo de verano y admisión al pagar
# ---------------------------------------------------------------------------
def seleccionar_tipo_pago_verano(db: Session):
    """Tipo de pago fijo del verano: un TipoPago activo marcado como VERANO
    (o AMBOS), que no sea VACANTE ni MATRÍCULA."""
    tipos = db.query(fi_models.TipoPago).filter(
        fi_models.TipoPago.activo == True,  # noqa: E712
        fi_models.TipoPago.periodo_academico.in_([
            fi_models.PeriodoAcademico.VERANO, fi_models.PeriodoAcademico.AMBOS
        ]),
    ).all()
    # Preferimos los que NO son vacante/matrícula (el pago de verano es único).
    preferidos = [t for t in tipos if t.categoria not in ("VACANTE", "MATRICULA")]
    if preferidos:
        return preferidos[0]
    return tipos[0] if tipos else None


def crear_pago_verano(db: Session, alumno, anio_verano):
    """Crea el pago fijo de verano (PENDIENTE) para un alumno. Devuelve el Pago."""
    tipo = seleccionar_tipo_pago_verano(db)
    if not tipo:
        raise ValueError(
            "No hay un tipo de pago de verano configurado. Cree un tipo de pago con periodo "
            "'Vacacional / Verano' en Trámites y Finanzas."
        )
    # Fecha de vencimiento: fin de inscripción del verano o +15 días
    if anio_verano.fin_inscripcion:
        fecha_venc = anio_verano.fin_inscripcion
    else:
        fecha_venc = date.today() + timedelta(days=15)

    pago = fi_models.Pago(
        id_usuario=alumno.id_usuario,
        id_alumno=alumno.id_alumno,
        id_tipo_pago=tipo.id_tipo_pago,
        concepto=f"{tipo.nombre} - {alumno.nombres} {alumno.apellidos}",
        monto=tipo.costo,
        mora=0,
        monto_total=tipo.costo,
        estado="PENDIENTE",
        fecha_vencimiento=fecha_venc,
    )
    db.add(pago)
    db.flush()
    return pago


def procesar_pago_verano(db: Session, pago) -> bool:
    """Si el pago corresponde a una inscripción de verano y quedó PAGADO,
    admite al alumno y crea su matrícula de verano. Devuelve True si actuó.
    (No hace commit; el caller comita.)"""
    from . import models as vr_models
    solicitud = db.query(vr_models.SolicitudVerano).filter(
        vr_models.SolicitudVerano.id_pago == pago.id_pago
    ).first()
    if not solicitud or solicitud.estado == "ADMITIDO":
        return False

    alumno = db.query(al_models.Alumno).filter(
        al_models.Alumno.id_alumno == solicitud.id_alumno
    ).first()
    if not alumno:
        return False

    # Crear usuario si no tiene o reactivarlo si estaba inactivo (login = dni)
    if alumno.id_usuario:
        usr = db.query(usuario_models.Usuario).filter(
            usuario_models.Usuario.id_usuario == alumno.id_usuario
        ).first()
        if usr:
            usr.activo = True
    else:
        username_alumno = generar_username(alumno.dni, "ALUMNO")
        user_existente = db.query(usuario_models.Usuario).filter(
            usuario_models.Usuario.username == username_alumno
        ).first()
        if user_existente:
            user_existente.activo = True
            alumno.id_usuario = user_existente.id_usuario
        else:
            nuevo = usuario_models.Usuario(
                username=username_alumno,
                password_hash=get_password_hash(alumno.dni),
                rol="ALUMNO",
                activo=True,
            )
            db.add(nuevo)
            db.flush()
            alumno.id_usuario = nuevo.id_usuario
    alumno.estado_ingreso = estados_alumno.ESTUDIANTE

    # Crear matrícula de verano (si no existe)
    matricula = db.query(en_models.Matricula).filter(
        en_models.Matricula.id_alumno == alumno.id_alumno,
        en_models.Matricula.id_anio_escolar == solicitud.id_anio_escolar,
    ).first()
    if not matricula:
        matricula = en_models.Matricula(
            id_anio_escolar=solicitud.id_anio_escolar,
            id_alumno=alumno.id_alumno,
            id_seccion=None,
            id_grado=solicitud.id_grado,
            estado="MATRICULADO",
            tipo_matricula="VERANO",
            condicion="NORMAL",
        )
        db.add(matricula)
        db.flush()

    solicitud.estado = "ADMITIDO"
    solicitud.id_matricula = matricula.id_matricula
    return True
