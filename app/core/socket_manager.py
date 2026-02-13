from fastapi import WebSocket
from typing import Dict

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