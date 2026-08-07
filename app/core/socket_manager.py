"""
Registro de quién está conectado por WebSocket.

IMPORTANTE PARA EL DESPLIEGUE: este registro vive en la memoria del proceso.
Si el backend se levanta con más de un worker (`uvicorn --workers N`,
`gunicorn -w N`), cada worker tendrá su propia lista y la mensajería fallará
de la peor manera posible: sin error. Un mensaje escrito por alguien atendido
por el worker A no llegará al destinatario si su WebSocket está abierto contra
el worker B; simplemente no aparecerá.

Por eso el backend debe correr con UN SOLO worker. Con 650 usuarios conectados
no es un problema de capacidad: las conexiones son asíncronas y apenas
consumen, y los endpoints síncronos siguen repartiéndose entre varios hilos.

Para poder usar varios workers habría que sacar este registro a un servicio
compartido (Redis con pub/sub es lo habitual).
"""
import os
from typing import Dict

from fastapi import WebSocket


def avisar_si_hay_varios_workers() -> None:
    """Deja constancia en el log si el arranque pide más de un worker."""
    for variable in ("WEB_CONCURRENCY", "UVICORN_WORKERS", "GUNICORN_WORKERS"):
        try:
            n = int((os.getenv(variable) or "1").strip())
        except ValueError:
            continue
        if n > 1:
            print(
                f"[AVISO] {variable}={n}. La mensajería en tiempo real guarda las "
                f"conexiones en memoria del proceso y NO funciona con varios "
                f"workers: los mensajes se perderán sin dar error. "
                f"Arranca con un solo worker."
            )
            return


class ConnectionManager:
    def __init__(self):
        # Diccionario que mapea id_usuario -> WebSocket
        self.active_connections: Dict[int, WebSocket] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: int):
        if user_id in self.active_connections:
            del self.active_connections[user_id]

    async def send_personal_message(self, user_id: int, data: dict):
        """Envía un mensaje JSON a un usuario específico si está online"""
        if user_id in self.active_connections:
            websocket = self.active_connections[user_id]
            await websocket.send_json(data)

# Instancia única para ser importada en otros archivos
socket_manager = ConnectionManager()