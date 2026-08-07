"""
Caché en memoria para datos que se consultan constantemente y casi nunca
cambian.

El caso que la motiva es el año escolar activo: se pide en diez sitios del
backend y en algunos de ellos varias veces por petición, pero cambia dos veces
al año. Con 650 usuarios conectados eso son decenas de consultas por segundo
para leer siempre la misma fila.

Es una caché de proceso, no compartida: si algún día se levantan varios workers
cada uno tendrá la suya. No es un problema porque todo lo que se guarda aquí
caduca solo, y además se invalida a mano cuando se escribe.
"""
import threading
import time
from typing import Any, Callable, Optional

_lock = threading.Lock()
_entradas: dict[str, tuple[float, Any]] = {}


def obtener(clave: str, calcular: Callable[[], Any], segundos: float = 300) -> Any:
    """
    Devuelve el valor guardado para `clave`; si no está o caducó, lo recalcula.

    `calcular` puede ejecutarse más de una vez si varias peticiones coinciden
    justo cuando caduca. Se acepta a propósito: bloquear mientras se consulta la
    base sería peor que repetir una consulta barata de vez en cuando.
    """
    ahora = time.monotonic()
    with _lock:
        entrada = _entradas.get(clave)
        if entrada and entrada[0] > ahora:
            return entrada[1]

    valor = calcular()

    with _lock:
        _entradas[clave] = (ahora + segundos, valor)
    return valor


def invalidar(clave: Optional[str] = None) -> None:
    """Olvida una clave, o toda la caché si no se indica ninguna."""
    with _lock:
        if clave is None:
            _entradas.clear()
        else:
            _entradas.pop(clave, None)
