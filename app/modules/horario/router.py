from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import ProgrammingError
from typing import List, Optional
from datetime import time, datetime, date, timedelta
from app.db.database import get_db
from app.modules.horario.models import (
    HorarioEscolar, HoraLectiva, ConfiguracionHorario, RecesoHorario,
    AMBITOS_REGULAR, AMBITOS_VERANO,
)
from app.modules.management.models import CargaAcademica
from app.modules.horario.schemas import (
    HorarioCreate, HorarioResponse, HoraLectivaResponse, MateriaDisponibleResponse,
    ConfiguracionResponse, ConfiguracionUpdate, RecesoBase, BloqueResponse,
)
from app.modules.academic.models import Seccion, Grado, Nivel, AnioEscolar
from app.modules.enrollment.models import Matricula
from app.modules.users.alumno.models import Alumno
from app.modules.users.models import Usuario
from app.modules.users.docente.models import Docente
from app.core.util.security import get_current_user

router = APIRouter(prefix="/horarios", tags=["Horarios"])


# ===========================================================================
# CÁLCULO DE LA REJILLA
#
# Una sola función construye las filas del horario, y todo el sistema la usa:
# el constructor del panel, el horario del docente, el del alumno y el PDF.
# Antes cada pantalla las generaba por su cuenta con los valores escritos a
# mano, y bastaba tocar una para que dejaran de coincidir.
# ===========================================================================

DEFECTOS = {
    ("PRIMARIA", "REGULAR"): dict(duracion=45, inicio=time(7, 30), fin=time(13, 30),
                                  recesos=[("Recreo", time(10, 0), 30)]),
    ("SECUNDARIA", "REGULAR"): dict(duracion=45, inicio=time(7, 30), fin=time(14, 15),
                                    recesos=[("Recreo", time(10, 15), 30)]),
    ("PRIMARIA", "VERANO"): dict(duracion=45, inicio=time(8, 0), fin=time(12, 0),
                                 recesos=[("Recreo", time(10, 0), 20)]),
    ("SECUNDARIA", "VERANO"): dict(duracion=45, inicio=time(8, 0), fin=time(12, 45),
                                   recesos=[("Recreo", time(10, 15), 20)]),
    ("PRE_ACADEMIA", "VERANO"): dict(duracion=60, inicio=time(8, 0), fin=time(13, 0),
                                     recesos=[("Recreo", time(10, 0), 20)]),
}


def _a_minutos(t: time) -> int:
    return t.hour * 60 + t.minute


def _a_texto(minutos: int) -> str:
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def calcular_bloques(config: ConfiguracionHorario) -> List[dict]:
    """Construye las filas de la rejilla a partir de la configuración.

    Recorre la jornada de principio a fin. Cuando toca un receso lo inserta
    entero; el resto del tiempo lo parte en bloques de la duración indicada.
    Un bloque que chocaría con el inicio de un receso o con el fin de la
    jornada se recorta, para que nunca se solapen ni se salgan del horario.
    """
    inicio = _a_minutos(config.hora_inicio)
    fin = _a_minutos(config.hora_fin)
    duracion = max(int(config.duracion_bloque or 0), 1)

    # Los recesos, ordenados y sin salirse de la jornada
    recesos = sorted(
        (
            {
                "inicio": _a_minutos(r.hora_inicio),
                "fin": _a_minutos(r.hora_inicio) + int(r.duracion),
                "nombre": r.nombre or "Recreo",
            }
            for r in config.recesos
        ),
        key=lambda r: r["inicio"],
    )
    recesos = [r for r in recesos if r["inicio"] >= inicio and r["inicio"] < fin]

    bloques: List[dict] = []
    actual = inicio
    # El tope evita un bucle infinito si llegara una configuración imposible
    for _ in range(1000):
        if actual >= fin:
            break

        receso = next((r for r in recesos if r["inicio"] == actual), None)
        if receso:
            cierre = min(receso["fin"], fin)
            bloques.append({
                "hora_inicio": _a_texto(actual),
                "hora_fin": _a_texto(cierre),
                "tipo": "receso",
                "duracion": cierre - actual,
                "nombre": receso["nombre"],
            })
            actual = cierre
            continue

        siguiente = actual + duracion
        # ¿Se cruza con un receso que empieza más adelante?
        cruce = next((r["inicio"] for r in recesos
                      if actual < r["inicio"] < siguiente), None)
        if cruce is not None:
            siguiente = cruce
        siguiente = min(siguiente, fin)
        if siguiente <= actual:
            break

        bloques.append({
            "hora_inicio": _a_texto(actual),
            "hora_fin": _a_texto(siguiente),
            "tipo": "clase",
            "duracion": siguiente - actual,
            "nombre": None,
        })
        actual = siguiente

    return bloques


def obtener_config(db: Session, ambito: str, modalidad: str) -> ConfiguracionHorario:
    """Devuelve la configuración pedida, creándola con valores por defecto
    la primera vez. Así el módulo funciona sin que nadie tenga que sembrar
    nada a mano."""
    ambito = (ambito or "").upper()
    modalidad = (modalidad or "REGULAR").upper()

    permitidos = AMBITOS_VERANO if modalidad == "VERANO" else AMBITOS_REGULAR
    if ambito not in permitidos:
        raise HTTPException(
            status_code=400,
            detail=f"El ámbito '{ambito}' no existe en la modalidad {modalidad}. "
                   f"Válidos: {', '.join(permitidos)}",
        )

    try:
        config = db.query(ConfiguracionHorario).filter(
            ConfiguracionHorario.ambito == ambito,
            ConfiguracionHorario.modalidad == modalidad,
        ).first()
    except ProgrammingError:
        # Las tablas de configuración se crean con 08_configuracion_horario.sql.
        # Si el código está subido pero el script todavía no se ejecutó, mejor
        # decirlo con todas las letras que devolver un 500 sin explicación.
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Falta preparar la base de datos: ejecuta el script "
                   "08_configuracion_horario.sql para crear las tablas de "
                   "configuración del horario.",
        )

    if config:
        return config

    base = DEFECTOS.get((ambito, modalidad),
                        dict(duracion=45, inicio=time(7, 30), fin=time(13, 30), recesos=[]))
    config = ConfiguracionHorario(
        ambito=ambito, modalidad=modalidad,
        duracion_bloque=base["duracion"],
        hora_inicio=base["inicio"], hora_fin=base["fin"],
    )
    db.add(config)
    db.flush()
    for nombre, hora, dur in base["recesos"]:
        db.add(RecesoHorario(id_configuracion=config.id_configuracion,
                             nombre=nombre, hora_inicio=hora, duracion=dur))
    db.commit()
    db.refresh(config)
    return config


def _config_a_dict(config: ConfiguracionHorario) -> dict:
    return {
        "id_configuracion": config.id_configuracion,
        "ambito": config.ambito,
        "modalidad": config.modalidad,
        "duracion_bloque": config.duracion_bloque,
        "hora_inicio": config.hora_inicio.strftime("%H:%M"),
        "hora_fin": config.hora_fin.strftime("%H:%M"),
        "recesos": [
            {
                "id_receso": r.id_receso,
                "nombre": r.nombre,
                "hora_inicio": r.hora_inicio.strftime("%H:%M"),
                "duracion": r.duracion,
            }
            for r in sorted(config.recesos, key=lambda x: x.hora_inicio)
        ],
        "bloques": calcular_bloques(config),
    }


def ambito_de_seccion(db: Session, id_seccion: int) -> tuple:
    """(ámbito, modalidad) que le corresponde a una sección."""
    fila = db.query(Nivel.nombre, AnioEscolar.tipo).select_from(Seccion).join(
        Grado, Grado.id_grado == Seccion.id_grado
    ).join(Nivel, Nivel.id_nivel == Grado.id_nivel).join(
        AnioEscolar, AnioEscolar.id_anio_escolar == Seccion.id_anio_escolar
    ).filter(Seccion.id_seccion == id_seccion).first()

    if not fila:
        raise HTTPException(status_code=404, detail="La sección no existe")

    nivel, tipo_anio = fila
    modalidad = "VERANO" if (tipo_anio or "REGULAR").upper() == "VERANO" else "REGULAR"
    return (nivel or "").upper(), modalidad


# ===========================================================================
# BLOQUES YA COLOCADOS
#
# Cambiar la rejilla después de haber armado horarios es lo que rompía el
# módulo: las clases quedaban en horas que ya no existen y desaparecían de
# la pantalla sin que nadie las hubiera borrado. Las funciones de aquí abajo
# permiten mirar qué hay puesto antes de tocar la configuración.
# ===========================================================================

class _RejillaSimulada:
    """Configuración de mentira, solo para calcular cómo quedaría la rejilla.

    `calcular_bloques` únicamente lee cuatro atributos, así que basta con
    esto para probar un cambio sin escribirlo en la base de datos.
    """

    def __init__(self, duracion_bloque, hora_inicio, hora_fin, recesos):
        self.duracion_bloque = duracion_bloque
        self.hora_inicio = hora_inicio
        self.hora_fin = hora_fin
        self.recesos = recesos


def horarios_del_ambito(db: Session, ambito: str, modalidad: str) -> List[HorarioEscolar]:
    """Bloques de clase ya colocados en las secciones que usan esta rejilla.

    PRE_ACADEMIA no es un nivel de la tabla `nivel`, solo un ámbito de
    configuración, así que aquí devuelve lista vacía: no hay secciones suyas
    a las que afectar.
    """
    consulta = (
        db.query(HorarioEscolar)
        .join(CargaAcademica,
              CargaAcademica.id_carga_academica == HorarioEscolar.id_carga_academica)
        .join(Seccion, Seccion.id_seccion == CargaAcademica.id_seccion)
        .join(Grado, Grado.id_grado == Seccion.id_grado)
        .join(Nivel, Nivel.id_nivel == Grado.id_nivel)
        .join(AnioEscolar, AnioEscolar.id_anio_escolar == Seccion.id_anio_escolar)
        .filter(Nivel.nombre == (ambito or "").upper())
    )
    if (modalidad or "").upper() == "VERANO":
        consulta = consulta.filter(AnioEscolar.tipo == "VERANO")
    else:
        consulta = consulta.filter(
            (AnioEscolar.tipo != "VERANO") | (AnioEscolar.tipo.is_(None))
        )
    return consulta.all()


def _datos_bloque(h: HorarioEscolar) -> tuple:
    """(curso, sección, día) de un bloque, tolerando datos incompletos."""
    dia = h.dia_semana.value if hasattr(h.dia_semana, "value") else h.dia_semana
    try:
        curso = h.carga.curso.nombre
        seccion = f"{h.carga.seccion.grado.nombre} {h.carga.seccion.nombre}"
    except AttributeError:
        curso, seccion = "una clase", "una sección"
    return curso, seccion, dia


def _describir_bloque(h: HorarioEscolar) -> str:
    """'Matemática de 1ero Amarillo, Lunes 10:00-10:45', para los avisos."""
    curso, seccion, dia = _datos_bloque(h)
    return (f"{curso} de {seccion}, {dia} "
            f"{h.hora_inicio.strftime('%H:%M')}-{h.hora_fin.strftime('%H:%M')}")


def _listar_pocos(bloques: List[HorarioEscolar], cuantos: int = 3) -> str:
    muestra = "; ".join(_describir_bloque(h) for h in bloques[:cuantos])
    if len(bloques) > cuantos:
        muestra += f"; y {len(bloques) - cuantos} más"
    return muestra


def _listar_cursos(bloques: List[HorarioEscolar], cuantos: int = 6) -> str:
    """Los cursos con los que se choca, agrupados por curso y sección.

    Listar bloque a bloque no sirve de nada cuando el receso pisa la misma
    hora en veinte secciones: salen veinte líneas casi iguales y no se ve con
    qué curso es el problema. Aquí cada curso y sección aparece una sola vez,
    con los días en los que choca.
    """
    agrupados: dict = {}
    for h in bloques:
        curso, seccion, dia = _datos_bloque(h)
        entrada = agrupados.setdefault((curso, seccion), {"dias": [], "hora": None})
        if dia not in entrada["dias"]:
            entrada["dias"].append(dia)
        if entrada["hora"] is None:
            entrada["hora"] = (f"{h.hora_inicio.strftime('%H:%M')}"
                               f"-{h.hora_fin.strftime('%H:%M')}")

    partes = [
        f"{curso} de {seccion} ({', '.join(datos['dias'])} {datos['hora']})"
        for (curso, seccion), datos in list(agrupados.items())[:cuantos]
    ]
    texto = "; ".join(partes)
    if len(agrupados) > cuantos:
        texto += f"; y {len(agrupados) - cuantos} clases más"
    return texto


def bloques_que_se_romperian(db: Session, ambito: str, modalidad: str,
                             rejilla: List[dict]) -> tuple:
    """(todos los asignados, los que no encajarían en `rejilla`).

    Un bloque encaja si en la rejilla nueva existe un hueco de clase con
    exactamente esas horas. Si no, la clase quedaría en una hora que ya no
    existe: es justo lo que hay que avisar antes de guardar.
    """
    huecos = {(b["hora_inicio"], b["hora_fin"])
              for b in rejilla if b["tipo"] == "clase"}
    asignados = horarios_del_ambito(db, ambito, modalidad)
    rotos = [
        h for h in asignados
        if (h.hora_inicio.strftime("%H:%M"), h.hora_fin.strftime("%H:%M")) not in huecos
    ]
    return asignados, rotos


def _exigir_confirmacion(asignados: List[HorarioEscolar], rotos: List[HorarioEscolar],
                         ambito: str, que_cambia: str):
    """Corta con un 409 para que el panel pueda preguntar antes de romper nada."""
    etiqueta = (ambito or "").replace("_", " ").capitalize()
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "requiere_confirmacion": True,
            "bloques_asignados": len(asignados),
            "bloques_afectados": len(rotos),
            "mensaje": (
                f"{etiqueta} ya tiene {len(asignados)} "
                f"{'clase colocada' if len(asignados) == 1 else 'clases colocadas'} "
                f"en el horario, y {len(rotos)} "
                f"{'quedaría' if len(rotos) == 1 else 'quedarían'} en una hora que "
                f"deja de existir al {que_cambia}. Si continúas se borrará el horario "
                f"completo de {etiqueta} y habrá que armarlo de nuevo."
            ),
            "ejemplos": _listar_pocos(rotos),
        },
    )


def _borrar_horarios(db: Session, asignados: List[HorarioEscolar]) -> None:
    for h in asignados:
        db.delete(h)


# --- CONFIGURACIÓN DE LA REJILLA -------------------------------------------
@router.get("/configuracion", response_model=List[ConfiguracionResponse])
def listar_configuraciones(db: Session = Depends(get_db),
                           current_user: dict = Depends(get_current_user)):
    """Las cinco configuraciones: primaria y secundaria en regular y verano,
    más la Pre Academia, que solo existe en verano."""
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes ver esta información")

    salida = []
    for modalidad, ambitos in (("REGULAR", AMBITOS_REGULAR), ("VERANO", AMBITOS_VERANO)):
        for ambito in ambitos:
            salida.append(_config_a_dict(obtener_config(db, ambito, modalidad)))
    return salida


@router.put("/configuracion/{ambito}/{modalidad}", response_model=ConfiguracionResponse)
def actualizar_configuracion(ambito: str, modalidad: str, datos: ConfiguracionUpdate,
                             db: Session = Depends(get_db),
                             current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información")

    config = obtener_config(db, ambito, modalidad)
    nuevo_inicio = datetime.strptime(datos.hora_inicio, "%H:%M").time()
    nuevo_fin = datetime.strptime(datos.hora_fin, "%H:%M").time()

    cambia_la_rejilla = (
        config.duracion_bloque != datos.duracion_bloque
        or config.hora_inicio != nuevo_inicio
        or config.hora_fin != nuevo_fin
    )

    # Cambiar los minutos por bloque o la jornada recoloca todas las filas del
    # horario. Antes esto se guardaba sin más y las clases ya asignadas se
    # quedaban en horas inexistentes. Ahora se avisa y se pide confirmación,
    # y solo si el administrador acepta se borra el horario del nivel.
    if cambia_la_rejilla:
        rejilla_nueva = calcular_bloques(_RejillaSimulada(
            datos.duracion_bloque, nuevo_inicio, nuevo_fin, config.recesos))
        asignados, rotos = bloques_que_se_romperian(db, ambito, modalidad, rejilla_nueva)

        if rotos and not datos.confirmar:
            _exigir_confirmacion(asignados, rotos, ambito, "cambiar la jornada o el bloque")
        if rotos:
            _borrar_horarios(db, asignados)

    config.duracion_bloque = datos.duracion_bloque
    config.hora_inicio = nuevo_inicio
    config.hora_fin = nuevo_fin
    db.commit()
    db.refresh(config)
    return _config_a_dict(config)


@router.post("/configuracion/{ambito}/{modalidad}/recesos",
             response_model=ConfiguracionResponse, status_code=status.HTTP_201_CREATED)
def agregar_receso(ambito: str, modalidad: str, datos: RecesoBase,
                   db: Session = Depends(get_db),
                   current_user: dict = Depends(get_current_user)):
    """Añade un receso en la hora que se indique. Puede haber varios."""
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información")

    config = obtener_config(db, ambito, modalidad)
    inicio = datetime.strptime(datos.hora_inicio, "%H:%M").time()
    nuevo_ini = _a_minutos(inicio)
    nuevo_fin = nuevo_ini + datos.duracion

    if nuevo_ini < _a_minutos(config.hora_inicio) or nuevo_fin > _a_minutos(config.hora_fin):
        raise HTTPException(
            status_code=400,
            detail=f"El receso se sale de la jornada "
                   f"({config.hora_inicio.strftime('%H:%M')} a {config.hora_fin.strftime('%H:%M')})",
        )

    for r in config.recesos:
        otro_ini = _a_minutos(r.hora_inicio)
        if nuevo_ini < otro_ini + r.duracion and nuevo_fin > otro_ini:
            raise HTTPException(
                status_code=400,
                detail=f"Se cruza con '{r.nombre}' de {r.hora_inicio.strftime('%H:%M')}",
            )

    # Un receso encima de clases ya colocadas no se acepta: esas clases se
    # quedarían pisadas por el recreo y desaparecerían del horario. Se rechaza
    # y se dice con cuáles choca, para poder moverlas o elegir otra hora.
    choques = [
        h for h in horarios_del_ambito(db, ambito, modalidad)
        if _a_minutos(h.hora_inicio) < nuevo_fin and _a_minutos(h.hora_fin) > nuevo_ini
    ]
    if choques:
        cursos = len({_datos_bloque(h)[:2] for h in choques})
        raise HTTPException(
            status_code=400,
            detail=(
                f"'{datos.nombre or 'El receso'}' de {datos.hora_inicio} a "
                f"{_a_texto(nuevo_fin)} choca con "
                f"{'este curso' if cursos == 1 else f'estos {cursos} cursos'} "
                f"que ya {'tiene' if cursos == 1 else 'tienen'} clase a esa hora: "
                f"{_listar_cursos(choques)}. "
                f"Quita {'esa clase' if len(choques) == 1 else 'esas clases'} del "
                f"horario o elige otra hora para el receso."
            ),
        )

    db.add(RecesoHorario(id_configuracion=config.id_configuracion,
                         nombre=datos.nombre, hora_inicio=inicio, duracion=datos.duracion))
    db.commit()
    db.refresh(config)
    return _config_a_dict(config)


@router.delete("/recesos/{id_receso}", response_model=ConfiguracionResponse)
def eliminar_receso(id_receso: int, confirmar: bool = False,
                    db: Session = Depends(get_db),
                    current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes modificar esta información")

    receso = db.query(RecesoHorario).filter(RecesoHorario.id_receso == id_receso).first()
    if not receso:
        raise HTTPException(status_code=404, detail="Ese receso no existe")

    config = receso.configuracion

    # Quitar un receso corre hacia arriba todo lo que venía después, así que
    # invalida bloques igual que cambiar la duración. Se avisa por lo mismo.
    quedan = [r for r in config.recesos if r.id_receso != id_receso]
    rejilla_nueva = calcular_bloques(_RejillaSimulada(
        config.duracion_bloque, config.hora_inicio, config.hora_fin, quedan))
    asignados, rotos = bloques_que_se_romperian(
        db, config.ambito, config.modalidad, rejilla_nueva)

    if rotos and not confirmar:
        _exigir_confirmacion(asignados, rotos, config.ambito,
                             f"quitar '{receso.nombre or 'el receso'}'")
    if rotos:
        _borrar_horarios(db, asignados)

    db.delete(receso)
    db.commit()
    db.refresh(config)
    return _config_a_dict(config)


# --- REJILLA YA CALCULADA, PARA PINTARLA -----------------------------------
@router.get("/bloques/seccion/{id_seccion}", response_model=List[BloqueResponse])
def bloques_de_seccion(id_seccion: int, db: Session = Depends(get_db),
                       current_user: dict = Depends(get_current_user)):
    ambito, modalidad = ambito_de_seccion(db, id_seccion)
    return calcular_bloques(obtener_config(db, ambito, modalidad))


@router.get("/bloques/usuario/{id_usuario}", response_model=List[BloqueResponse])
def bloques_de_usuario(id_usuario: int, id_anio_escolar: str,
                       db: Session = Depends(get_db),
                       current_user: dict = Depends(get_current_user)):
    """Rejilla que le toca a un docente o a un alumno.

    Un docente puede dictar en primaria y en secundaria a la vez, así que se
    mezclan las rejillas de los ámbitos donde tenga clase: se toman todos los
    cortes de ambas y se parte la jornada por ahí. Así ninguna clase se queda
    sin fila donde pintarse.
    """
    if current_user.get("id") != id_usuario and current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes ver esta información")

    usuario = db.query(Usuario).filter(Usuario.id_usuario == id_usuario).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    rol = (usuario.rol or "").upper()
    secciones: List[int] = []

    if rol == "ALUMNO":
        alumno = db.query(Alumno).filter(Alumno.id_usuario == id_usuario).first()
        if alumno:
            matricula = db.query(Matricula).join(Seccion).filter(
                Matricula.id_alumno == alumno.id_alumno,
                Seccion.id_anio_escolar == id_anio_escolar,
            ).first()
            if matricula:
                secciones = [matricula.id_seccion]
    elif rol == "DOCENTE":
        docente = db.query(Docente).filter(Docente.id_usuario == id_usuario).first()
        if docente:
            secciones = [
                s for (s,) in db.query(CargaAcademica.id_seccion).join(
                    Seccion, Seccion.id_seccion == CargaAcademica.id_seccion
                ).filter(
                    CargaAcademica.id_docente == docente.id_docente,
                    Seccion.id_anio_escolar == id_anio_escolar,
                ).distinct().all()
            ]

    ambitos = set()
    for id_sec in secciones:
        try:
            ambitos.add(ambito_de_seccion(db, id_sec))
        except HTTPException:
            continue

    if not ambitos:
        # Sin clases todavía: se enseña la rejilla de primaria regular como base
        return calcular_bloques(obtener_config(db, "PRIMARIA", "REGULAR"))

    rejillas = [calcular_bloques(obtener_config(db, a, m)) for a, m in sorted(ambitos)]
    if len(rejillas) == 1:
        return rejillas[0]

    # Mezcla: se juntan todos los cortes y se reconstruyen los tramos
    cortes, recesos = set(), []
    for rejilla in rejillas:
        for b in rejilla:
            cortes.add(b["hora_inicio"])
            cortes.add(b["hora_fin"])
            if b["tipo"] == "receso":
                recesos.append((b["hora_inicio"], b["hora_fin"], b["nombre"]))
    ordenados = sorted(cortes)

    mezcla = []
    for ini, fin in zip(ordenados, ordenados[1:]):
        # Es receso solo si lo es en TODAS las rejillas que lo cubren
        cubren = [r for r in rejillas
                  if r and r[0]["hora_inicio"] <= ini and r[-1]["hora_fin"] >= fin]
        def es_receso(rejilla):
            return any(b["tipo"] == "receso" and b["hora_inicio"] <= ini and b["hora_fin"] >= fin
                       for b in rejilla)
        receso = bool(cubren) and all(es_receso(r) for r in cubren)
        nombre = next((n for i, f, n in recesos if i <= ini and f >= fin), None) if receso else None
        mezcla.append({
            "hora_inicio": ini, "hora_fin": fin,
            "tipo": "receso" if receso else "clase",
            "duracion": _a_minutos(datetime.strptime(fin, "%H:%M").time())
                        - _a_minutos(datetime.strptime(ini, "%H:%M").time()),
            "nombre": nombre,
        })
    return mezcla


# --- CONFIGURACIÓN DE HORAS ---
@router.get("/horas", response_model=List[HoraLectivaResponse])
def obtener_horas_lectivas(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Retorna los bloques de tiempo (filas del schedule)"""
    return db.query(HoraLectiva).order_by(HoraLectiva.hora_inicio).all()

# --- HORARIO POR SECCIÓN ---
@router.get("/seccion/{id_seccion}", response_model=List[HorarioResponse])
def obtener_horario_seccion(id_seccion: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    # Join explícito para evitar el error de Mapper
    horarios = db.query(HorarioEscolar).join(
        CargaAcademica, HorarioEscolar.id_carga_academica == CargaAcademica.id_carga_academica
    ).filter(CargaAcademica.id_seccion == id_seccion).all()
    
    resultado = []
    for h in horarios:
        # Importante: Manejar si dia_semana es un Enum o String
        dia = h.dia_semana.value if hasattr(h.dia_semana, 'value') else h.dia_semana
        
        resultado.append({
            "id_horario": h.id_horario,
            "dia_semana": dia,
            "id_carga_academica": h.id_carga_academica,
            "hora_inicio": h.hora_inicio.strftime("%H:%M"), # NUEVO: Horas dinámicas
            "hora_fin": h.hora_fin.strftime("%H:%M"),       # NUEVO: Horas dinámicas
            "curso_nombre": h.carga.curso.nombre,
            "docente_nombre": f"{h.carga.docente.nombres} {h.carga.docente.apellidos}",
            "seccion_nombre": h.carga.seccion.nombre
        })
    return resultado

# --- GUARDAR / ACTUALIZAR BLOQUE ---
@router.post("/", status_code=status.HTTP_201_CREATED)
def asignar_bloque_horario(horario_in: HorarioCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN" :
        raise HTTPException(status_code=403, detail="No puedes ver modificar esta información")
    # 1. Convertir strings del frontend a objetos time reales para operar en BD
    t_inicio = datetime.strptime(horario_in.hora_inicio, "%H:%M").time()
    t_fin = datetime.strptime(horario_in.hora_fin, "%H:%M").time()

    # 3. Obtener carga académica
    carga_actual = db.query(CargaAcademica).filter(
        CargaAcademica.id_carga_academica == horario_in.id_carga_academica
    ).first()
    
    if not carga_actual:
        raise HTTPException(status_code=404, detail="La carga académica no existe")

    # 3.b El bloque tiene que existir en la rejilla configurada y ser de clase.
    #     Sin esto se podría colar una clase encima de un receso, o en una hora
    #     que ya no existe si alguien cambió la duración del bloque.
    ambito, modalidad = ambito_de_seccion(db, carga_actual.id_seccion)
    rejilla = calcular_bloques(obtener_config(db, ambito, modalidad))
    hueco = next((b for b in rejilla
                  if b["hora_inicio"] == horario_in.hora_inicio[:5]
                  and b["hora_fin"] == horario_in.hora_fin[:5]), None)

    if hueco is None:
        raise HTTPException(
            status_code=400,
            detail="Ese bloque ya no existe en el horario configurado. "
                   "Vuelve a cargar la página para ver la rejilla actual.",
        )
    if hueco["tipo"] == "receso":
        raise HTTPException(
            status_code=400,
            detail=f"No se puede poner clase en '{hueco.get('nombre') or 'el receso'}'",
        )

    # 4. VALIDACIÓN DE CONFLICTO DOCENTE (Join explícito - Adaptado a horas en vez de ID)
    #    Solo se compara contra el MISMO NIVEL. Primaria y secundaria tienen
    #    jornadas y bloques distintos, así que sus horas se pisan sobre el papel
    #    aunque en la práctica no sean el mismo tramo; comparándolas entre sí,
    #    un docente que dicta en los dos niveles se bloqueaba a sí mismo.
    conflicto = db.query(HorarioEscolar).join(
        CargaAcademica, HorarioEscolar.id_carga_academica == CargaAcademica.id_carga_academica
    ).join(
        Seccion, Seccion.id_seccion == CargaAcademica.id_seccion
    ).join(
        Grado, Grado.id_grado == Seccion.id_grado
    ).join(
        Nivel, Nivel.id_nivel == Grado.id_nivel
    ).filter(
        Nivel.nombre == ambito,           # el nivel de la sección a la que se asigna
        CargaAcademica.id_docente == carga_actual.id_docente,
        HorarioEscolar.dia_semana == horario_in.dia_semana,
        HorarioEscolar.hora_inicio < t_fin,   # Lógica de solapamiento de tiempo
        HorarioEscolar.hora_fin > t_inicio
    ).first()

    if conflicto:
        raise HTTPException(
            status_code=400,
            detail=f"Conflicto: El docente ya dicta clases en {conflicto.carga.seccion.nombre} en este horario."
        )

    # 5. Evitar aula ocupada (Faltaba el join explícito aquí - Adaptado a horas)
    aula_ocupada = db.query(HorarioEscolar).join(
        CargaAcademica, HorarioEscolar.id_carga_academica == CargaAcademica.id_carga_academica
    ).filter(
        CargaAcademica.id_seccion == carga_actual.id_seccion,
        HorarioEscolar.dia_semana == horario_in.dia_semana,
        HorarioEscolar.hora_inicio < t_fin,
        HorarioEscolar.hora_fin > t_inicio
    ).first()

    if aula_ocupada:
        raise HTTPException(status_code=400, detail="Esta sección ya tiene una materia asignada en este bloque")

    # 6. Guardar (Asegúrate de que los nombres de campos coincidan con tu Model)
    nuevo_horario = HorarioEscolar(
        id_carga_academica=horario_in.id_carga_academica,
        dia_semana=horario_in.dia_semana,
        hora_inicio=t_inicio,
        hora_fin=t_fin
    )
    db.add(nuevo_horario)
    db.commit()
    return {"message": "Horario asignado correctamente"}


@router.delete("/{id_horario}")
def eliminar_bloque_horario(id_horario: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes ver modificar esta información")
    db_horario = db.query(HorarioEscolar).filter(HorarioEscolar.id_horario == id_horario).first()
    if not db_horario:
        raise HTTPException(status_code=404, detail="No se encontró el bloque")
    db.delete(db_horario)
    db.commit()
    return {"message": "Bloque eliminado"}


@router.get("/materias-disponibles/{id_seccion}", response_model=List[MateriaDisponibleResponse])
def obtener_materias_disponibles(id_seccion: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    # Buscamos la carga académica de esa sección
    materias = db.query(CargaAcademica).filter(CargaAcademica.id_seccion == id_seccion).all()
    
    resultado = []
    for m in materias:
        # Calcular los minutos que ya se han asignado en el horario
        horarios = db.query(HorarioEscolar).filter(HorarioEscolar.id_carga_academica == m.id_carga_academica).all()
        min_asignados = 0
        for h in horarios:
            diff = datetime.combine(date.min, h.hora_fin) - datetime.combine(date.min, h.hora_inicio)
            min_asignados += diff.total_seconds() / 60

        resultado.append({
            "id_carga_academica": m.id_carga_academica,
            "curso_nombre": m.curso.nombre,
            "docente_nombre": f"{m.docente.nombres} {m.docente.apellidos}",
            "minutos_semanales": m.curso.minutos_semanales,
            "minutos_asignados": int(min_asignados)
        })
    return resultado

@router.get("/usuario/{id_usuario}", response_model=List[HorarioResponse])
def obtener_horario_por_usuario(
    id_usuario: int, 
    id_anio_escolar: str, 
    db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    if  current_user.get("id") != id_usuario:
        raise HTTPException(status_code=403, detail="No puedes ver esta información")
    """
    Obtiene el horario basado en el rol definido en la tabla Usuario.
    """
    # 1. Obtenemos el usuario para saber su rol
    usuario = db.query(Usuario).filter(Usuario.id_usuario == id_usuario).first()
    
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    horarios = []
    rol = usuario.rol.upper()  # Aseguramos consistencia

    # 2. Lógica según el rol del usuario
    if rol == "ALUMNO":
        alumno = db.query(Alumno).filter(Alumno.id_usuario == id_usuario).first()

        if not alumno:
            raise HTTPException(
                status_code=404, 
                detail="No se encontró un alumno asociado a este usuario"
            )

        # 2. Buscamos la matrícula usando el id_alumno encontrado
        matricula = db.query(Matricula).join(Seccion).filter(
            Matricula.id_alumno == alumno.id_alumno,
            Seccion.id_anio_escolar == id_anio_escolar
        ).first()

        if not matricula:
            raise HTTPException(
                status_code=404, 
                detail="El alumno no tiene una matrícula registrada para el año escolar seleccionado"
            )

        # 3. Lógica para obtener los horarios (se mantiene igual)
        id_seccion = matricula.id_seccion
        
        horarios = db.query(HorarioEscolar).join(
            CargaAcademica, HorarioEscolar.id_carga_academica == CargaAcademica.id_carga_academica
        ).filter(CargaAcademica.id_seccion == id_seccion).all()
    elif rol == "DOCENTE":
        docente = db.query(Docente).filter(Docente.id_usuario == id_usuario).first()
        if not docente:
            raise HTTPException(status_code=404, detail="Docente no vinculado a este usuario")

        # Filtramos horarios donde el docente tiene carga en el año escolar dado
        horarios = db.query(HorarioEscolar).join(CargaAcademica).join(Seccion).filter(
            CargaAcademica.id_docente == docente.id_docente,
            Seccion.id_anio_escolar == id_anio_escolar
        ).all()
    
    else:
        raise HTTPException(status_code=400, detail=f"Rol '{rol}' no soportado para consulta de horarios")

    # 3. Mapeo común a la respuesta
    resultado = []
    for h in horarios:
        dia = h.dia_semana.value if hasattr(h.dia_semana, 'value') else h.dia_semana
        resultado.append({
            "id_horario": h.id_horario,
            "dia_semana": dia,
            "id_carga_academica": h.id_carga_academica,
            "hora_inicio": h.hora_inicio.strftime("%H:%M"), # NUEVO: Se formatea la hora para el frontend
            "hora_fin": h.hora_fin.strftime("%H:%M"),       # NUEVO: Se formatea la hora para el frontend
            "curso_nombre": h.carga.curso.nombre,
            "docente_nombre": f"{h.carga.docente.nombres} {h.carga.docente.apellidos}",
            "seccion_nombre": h.carga.seccion.nombre
        })
    
    return resultado