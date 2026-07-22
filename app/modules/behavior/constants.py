# Sistema de puntos de conducta (Reglamento Interno 2026).
# Todo alumno inicia el año escolar con PUNTAJE_MAXIMO; cada reporte descuenta
# los puntos de la falta. Única fuente de verdad de los umbrales: cualquier
# cálculo de puntaje o semáforo debe pasar por este módulo.

PUNTAJE_MAXIMO = 100
UMBRAL_OBSERVACION = 75  # por debajo: el alumno entra en observación (Amarillo)
UMBRAL_CRITICO = 40      # por debajo: conducta crítica (Rojo)


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
