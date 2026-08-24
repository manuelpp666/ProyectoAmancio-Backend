# Sistema de puntos de conducta (Reglamento Interno 2026).
#
# El puntaje de conducta ES la nota de conducta de la libreta, y por eso va
# sobre 20 y no sobre 100: el alumno empieza cada bimestre con 20 y cada
# reporte le descuenta los puntos que tenga asignada esa falta en
# `nivel_conducta.puntos`.
#
# Se reinicia CADA BIMESTRE, no cada año: la libreta lleva una nota de
# conducta por bimestre, así que los descuentos de un bimestre no arrastran al
# siguiente. Qué reporte cae en qué bimestre lo decide `bimestres.py` a partir
# de la tabla `bimestre`.
#
# Única fuente de verdad de los umbrales: cualquier cálculo de puntaje o
# semáforo debe pasar por este módulo.

PUNTAJE_MAXIMO = 20
UMBRAL_OBSERVACION = 15  # por debajo: el alumno entra en observación (Amarillo)
UMBRAL_CRITICO = 8       # por debajo: conducta crítica (Rojo)


def calcular_puntaje(puntos_perdidos: int) -> int:
    return max(0, PUNTAJE_MAXIMO - puntos_perdidos)


def estado_visual(puntaje: int, cambio_ie: bool = False) -> str:
    # Una falta que amerita cambio de I.E. es medida extrema: el estado pasa a
    # crítico de inmediato, sin importar el puntaje acumulado.
    if cambio_ie or puntaje < UMBRAL_CRITICO:
        return "Rojo"
    if puntaje < UMBRAL_OBSERVACION:
        return "Amarillo"
    return "Verde"


# Los tres valores que puede devolver `estado_visual`, en orden de gravedad.
# Quien filtre por estado de conducta compara contra esto y no contra
# literales sueltos: un "Rojo " con un espacio o un "rojo" en minúscula no
# deben dejar la pantalla vacía sin explicar por qué.
ESTADOS_CONDUCTA = ("Verde", "Amarillo", "Rojo")


def normalizar_estado(valor):
    """Devuelve el estado canónico ('Verde'), o None si no se reconoce.

    Acepta cualquier combinación de mayúsculas y espacios, para que el valor
    llegue de donde llegue —una URL escrita a mano, un desplegable— se
    interprete igual.
    """
    if not valor:
        return None
    limpio = str(valor).strip().capitalize()
    return limpio if limpio in ESTADOS_CONDUCTA else None
