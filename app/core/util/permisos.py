"""
Permisos del panel de administración (lado servidor).

EL CATÁLOGO
    Es el espejo de ProyectoAmancio/src/config/permisos.ts: la misma estructura
    de apartado → pestaña → subpestaña. Si se añade una pestaña en el panel hay
    que añadirla en los dos sitios. Hasta septiembre de 2026 esta copia se había
    quedado atrás (le faltaban «Catálogo de Faltas» y «Reporte de Asistencia»),
    y como al guardar se pasa todo por `normalizar`, desmarcar esas casillas no
    se guardaba nunca: la clave desaparecía y la pantalla la daba por permitida.

    Una pestaña con acciones no es un booleano sino un diccionario:
        {"ver": True, "agregar": True, "editar": True, "eliminar": True}
    `ver` es la casilla de siempre (entrar a la pestaña). Las acciones solo
    aparecen en las pestañas que de verdad las tienen: «Notas Finales» solo lee,
    así que sigue siendo un booleano.

LO QUE SE COMPRUEBA AQUÍ
    Las ESCRITURAS. `requiere_permiso` va en el decorador de cada ruta que
    crea, cambia o borra algo desde el panel, y rechaza con 403 al
    administrador que no tenga esa acción marcada.

    Las lecturas no: el mismo GET (niveles, grados, secciones...) lo usan
    muchas pantallas a la vez, y cerrarlo por pestaña rompería las demás. Que
    una pestaña no se vea sigue siendo cosa de la pantalla, como hasta ahora.

    Solo se mira al rol ADMIN. Un auxiliar o un docente que use una ruta
    compartida (asistencia, conducta) sigue igual: su acceso lo decide la
    propia ruta, como siempre.
"""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.util.security import get_current_user
from app.db.database import get_db

ACCIONES = ("agregar", "editar", "eliminar")


def _pestana(*acciones: str):
    """Pestaña con las acciones indicadas; sin acciones es un simple booleano."""
    if not acciones:
        return True
    return {"ver": True, **{a: True for a in acciones}}


# Cada entrada es una clave; si tiene hijos, es un diccionario anidado.
CATALOGO = {
    "panel_control": True,
    "gestion_estudiantes": {
        "estudiantes": _pestana("agregar", "editar", "eliminar"),
        "postulantes": _pestana("editar"),
        "renovaciones": _pestana("editar"),
        "verano": _pestana("editar"),
        "notas": _pestana(),
        "asistencia": _pestana(),
        "faltas": _pestana("agregar", "editar", "eliminar"),
    },
    "gestion_personal": {
        "admin": _pestana(*ACCIONES),
        "docente": _pestana(*ACCIONES),
        "auxiliar": _pestana(*ACCIONES),
        "psicologo": _pestana(*ACCIONES),
    },
    "tramites_finanzas": {
        "config": _pestana("agregar", "editar"),
        "solicitudes": _pestana("editar"),
        "tipos_pagos": _pestana(*ACCIONES),
        "recaudacion": _pestana(*ACCIONES),
        "conciliacion": _pestana("agregar", "editar"),
    },
    "academico": {
        "estructura": _pestana(*ACCIONES),
        "horarios": _pestana(*ACCIONES),
        "docentes": _pestana(*ACCIONES),
        "estudiantes": _pestana("editar"),
        "cursos": _pestana(*ACCIONES),
    },
    "contenido_web": {
        # Las secciones del Editor Web ya son, cada una, el permiso de
        # editarla: no llevan acciones aparte.
        "info_general": {
            "inicio": True,
            "login": True,
            "nosotros": True,
            "docentes": True,
            "calendario": True,
            "noticias": True,
            "admision": True,
            "footer": True,
        },
        "noticias": _pestana(*ACCIONES),
        "calendario": _pestana(*ACCIONES),
    },
    "chatbot": _pestana("agregar", "eliminar"),
    "mensajeria": True,
    "seguridad": _pestana("editar"),
}

# Nombres para los mensajes de error: lo que el administrador ve en pantalla.
ETIQUETAS = {
    "panel_control": "Dashboard",
    "gestion_estudiantes": "Gestión de Estudiantes",
    "gestion_estudiantes.estudiantes": "Estudiantes",
    "gestion_estudiantes.postulantes": "Solicitudes de Admisión",
    "gestion_estudiantes.renovaciones": "Renovaciones de Matrícula",
    "gestion_estudiantes.verano": "Inscripciones de Verano",
    "gestion_estudiantes.notas": "Notas Finales",
    "gestion_estudiantes.asistencia": "Reporte de Asistencia",
    "gestion_estudiantes.faltas": "Catálogo de Faltas",
    "gestion_personal": "Gestión de Personal",
    "gestion_personal.admin": "Administradores",
    "gestion_personal.docente": "Docentes",
    "gestion_personal.auxiliar": "Auxiliares",
    "gestion_personal.psicologo": "Psicólogos",
    "tramites_finanzas": "Trámites y Finanzas",
    "tramites_finanzas.config": "Tarifario / Trámites",
    "tramites_finanzas.solicitudes": "Atención de Solicitudes",
    "tramites_finanzas.tipos_pagos": "Tipos de Pagos",
    "tramites_finanzas.recaudacion": "Caja y Recaudación",
    "tramites_finanzas.conciliacion": "Conciliación BCP",
    "academico": "Cursos y Materias",
    "academico.estructura": "Estructura Escolar",
    "academico.horarios": "Gestión de Horarios",
    "academico.docentes": "Asignación de Docentes",
    "academico.estudiantes": "Asignación de Estudiantes",
    "academico.cursos": "Gestión de Cursos",
    "contenido_web": "Contenido Web",
    "contenido_web.info_general": "Editor Web",
    "contenido_web.noticias": "Gestión de Noticias",
    "contenido_web.calendario": "Calendario Anual",
    "chatbot": "Gestionar Chatbot",
    "mensajeria": "Mensajería",
    "seguridad": "Seguridad",
}

VERBOS = {"agregar": "agregar", "editar": "editar", "eliminar": "eliminar", "ver": "entrar"}


def _copiar(plantilla, valor: bool):
    """Reproduce la forma del catálogo con todas sus hojas en `valor`."""
    if isinstance(plantilla, dict):
        return {k: _copiar(v, valor) for k, v in plantilla.items()}
    return valor


def permisos_completos() -> dict:
    """Todo activado: lo que recibe un administrador recién creado."""
    return _copiar(CATALOGO, True)


def normalizar(permisos, plantilla=None) -> dict:
    """
    Completa unos permisos guardados con el catálogo actual.

    Lo ya decidido se respeta; lo que nunca se configuró se da por activado,
    para que una pestaña nueva no deje fuera a quien tenía permisos de antes.
    Una rama guardada como booleano se propaga a todos sus hijos: así un
    administrador que tenía «Noticias» marcada de antes de existir las
    acciones conserva agregar, editar y eliminar.
    """
    plantilla = CATALOGO if plantilla is None else plantilla
    guardado = permisos if isinstance(permisos, dict) else {}
    todo = guardado.get("all") is True

    salida = {}
    for clave, sub in plantilla.items():
        valor = True if todo else guardado.get(clave)

        if not isinstance(sub, dict):
            salida[clave] = True if valor is None else bool(valor)
            continue

        if valor is None or valor is True:
            salida[clave] = _copiar(sub, True)
        elif valor is False:
            salida[clave] = _copiar(sub, False)
        else:
            salida[clave] = normalizar(valor, sub)

    # Sin «ver» no hay acciones: una acción marcada en una pestaña cerrada no
    # vale nada, y así no queda un permiso escondido que nadie ve en pantalla.
    for clave, valor in salida.items():
        if isinstance(valor, dict) and valor.get("ver") is False:
            for accion in ACCIONES:
                if accion in valor:
                    valor[accion] = False
    return salida


def _alguno(valor) -> bool:
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, dict):
        return any(_alguno(v) for v in valor.values())
    return False


def tiene_permiso(permisos, *ruta: str) -> bool:
    """
    ¿Estos permisos dejan hacer esto?

        tiene_permiso(p, "gestion_estudiantes", "faltas", "agregar")
        tiene_permiso(p, "contenido_web", "info_general", "inicio")

    A diferencia de la pantalla, aquí una ruta que no existe en el catálogo es
    un NO: si alguien se equivoca al escribirla, mejor que falle cerrado.
    """
    actual = normalizar(permisos)
    for clave in ruta:
        if isinstance(actual, bool):
            return actual
        if not isinstance(actual, dict) or clave not in actual:
            return False
        # Una acción exige también poder entrar a la pestaña.
        if clave in ACCIONES and actual.get("ver") is False:
            return False
        actual = actual[clave]

    if isinstance(actual, dict):
        if "ver" in actual:
            return actual["ver"] is True
        return _alguno(actual)
    return actual is True


def _mensaje(ruta) -> str:
    accion = ruta[-1] if ruta and ruta[-1] in ACCIONES else None
    lugar = ruta[:-1] if accion else ruta
    etiqueta = None
    for i in range(len(lugar), 0, -1):
        etiqueta = ETIQUETAS.get(".".join(lugar[:i]))
        if etiqueta:
            break
    etiqueta = etiqueta or "este apartado"
    if accion:
        return (f"No tienes permiso para {VERBOS[accion]} en «{etiqueta}». "
                "Pídeselo a quien administra los permisos del panel.")
    return (f"No tienes permiso para modificar «{etiqueta}». "
            "Pídeselo a quien administra los permisos del panel.")


def exigir_permiso(db: Session, current_user: dict, *ruta: str) -> None:
    """Lanza 403 si el ADMIN de la sesión no tiene ese permiso.

    A los demás roles no los toca. La cuenta ADMIN sin ficha de administrador
    no tiene permisos (la pantalla ya no le enseñaba nada), así que tampoco
    puede escribir.
    """
    if current_user.get("rol") != "ADMIN":
        return
    # Import aquí para no crear una dependencia circular entre módulos.
    from app.modules.personal.models import Administrador

    admin = db.query(Administrador).filter(
        Administrador.id_usuario == current_user.get("id")
    ).first()
    if not admin or not tiene_permiso(admin.permisos, *ruta):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_mensaje(ruta))


def requiere_permiso(*ruta: str):
    """
    Dependencia para el decorador de una ruta de escritura:

        @router.post("/faltas", dependencies=[Depends(requiere_permiso(
            "gestion_estudiantes", "faltas", "agregar"))])
    """
    def checker(current_user: dict = Depends(get_current_user),
                db: Session = Depends(get_db)) -> dict:
        exigir_permiso(db, current_user, *ruta)
        return current_user
    return checker


# --- Rutas cuyo permiso depende de un dato de la propia petición -----------

TIPOS_PERSONAL = ("admin", "docente", "auxiliar", "psicologo")

ROL_A_PESTANA = {
    "ADMIN": ("gestion_personal", "admin"),
    "DOCENTE": ("gestion_personal", "docente"),
    "AUXILIAR": ("gestion_personal", "auxiliar"),
    "PSICOLOGO": ("gestion_personal", "psicologo"),
    "ALUMNO": ("gestion_estudiantes", "estudiantes"),
}


def requiere_permiso_personal(accion: str):
    """Para /personal/{tipo}...: la pestaña la dice el `tipo` de la URL."""
    def checker(request: Request,
                current_user: dict = Depends(get_current_user),
                db: Session = Depends(get_db)) -> dict:
        tipo = request.path_params.get("tipo")
        if current_user.get("rol") == "ADMIN" and tipo not in TIPOS_PERSONAL:
            raise HTTPException(status_code=400, detail="Tipo de personal no válido")
        exigir_permiso(db, current_user, "gestion_personal", tipo, accion)
        return current_user
    return checker


def requiere_permiso_sobre_usuario(accion: str):
    """Para rutas por id_usuario: la pestaña sale del rol de esa cuenta."""
    def checker(request: Request,
                current_user: dict = Depends(get_current_user),
                db: Session = Depends(get_db)) -> dict:
        if current_user.get("rol") != "ADMIN":
            return current_user
        from app.modules.users.models import Usuario

        try:
            id_usuario = int(request.path_params.get("id_usuario"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Usuario no válido")
        usuario = db.query(Usuario).filter(Usuario.id_usuario == id_usuario).first()
        if not usuario:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        pestana = ROL_A_PESTANA.get(usuario.rol)
        if not pestana:
            raise HTTPException(status_code=403, detail="No puedes modificar esta cuenta")
        exigir_permiso(db, current_user, *pestana, accion)
        return current_user
    return checker


# Sección de `pagina_configuracion` → permiso que hace falta para cambiarla.
SECCIONES_EDITOR_WEB = tuple(CATALOGO["contenido_web"]["info_general"].keys())
PERMISO_DE_SECCION = {
    "seguridad": ("seguridad", "editar"),
    "academico": ("academico", "estructura", "editar"),
}


def ruta_de_seccion(seccion: str):
    if seccion in SECCIONES_EDITOR_WEB:
        return ("contenido_web", "info_general", seccion)
    return PERMISO_DE_SECCION.get(seccion)


def requiere_permiso_configuracion():
    """Para PUT /configuracion/{clave}: el permiso depende de la sección.

    Manda la sección GUARDADA de la clave, no la que llega en la URL: si no,
    bastaría con mandar ?seccion=inicio para cambiar una clave de seguridad
    con el permiso del Editor Web.
    """
    def checker(request: Request,
                current_user: dict = Depends(get_current_user),
                db: Session = Depends(get_db)) -> dict:
        if current_user.get("rol") != "ADMIN":
            return current_user
        from app.modules.pagina_principal.models import PaginaConfiguracion

        clave = request.path_params.get("clave")
        fila = db.query(PaginaConfiguracion).filter(PaginaConfiguracion.clave == clave).first()
        seccion = fila.seccion if fila else request.query_params.get("seccion")
        ruta = ruta_de_seccion(seccion or "")
        if not ruta:
            raise HTTPException(status_code=403,
                                detail="No se puede modificar una sección de configuración desconocida")
        exigir_permiso(db, current_user, *ruta)
        return current_user
    return checker
