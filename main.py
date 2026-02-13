from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text  # Para escribir SQL puro
from app.db.database import get_db # Ajusta la ruta según tu carpeta
from app.modules.users import router as usuario_router 
from app.modules.users.alumno import router as alumno_router
from app.modules.users.familiar import router as familiar_router
from app.modules.users.docente import router as docente_router
from app.modules.chatbot import router as chatbot_router
# Resto de módulos
from app.modules.perfil import router as perfil_router
from app.modules.academic import router as academic_router
from app.modules.enrollment import router as enrollment_router
from app.modules.finance import router as finance_router
from app.modules.management import router as management_router
from app.modules.virtual import router as virtual_router
from app.modules.behavior import router as behavior_router
from app.modules.web import router as web_router
from app.modules.admision import router as admision_router

from app.core.socket_manager import socket_manager


app = FastAPI()

# Lista de URLs permitidas (Frontend)
origins = [
    "http://localhost:3000",    # Tu Next.js local
    "https://tu-colegio.com",   # Tu dominio final en DirectAdmin
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,            # Permite estas webs
    allow_credentials=True,
    allow_methods=["*"],              # Permite todos los métodos (GET, POST, etc.)
    allow_headers=["*"],              # Permite todos los encabezados
)

# Incluir Rutas
app.include_router(usuario_router.router)
app.include_router(alumno_router.router)
app.include_router(familiar_router.router)
app.include_router(docente_router.router)
app.include_router(perfil_router.router)
app.include_router(academic_router.router)
app.include_router(enrollment_router.router)
app.include_router(finance_router.router)
app.include_router(management_router.router)
app.include_router(virtual_router.router)
app.include_router(behavior_router.router)
app.include_router(web_router.router)
app.include_router(chatbot_router.router) 
app.include_router(admision_router.router)


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    # 1. Conectar al usuario
    await socket_manager.connect(user_id, websocket)
    try:
        while True:
            # Mantener la conexión abierta escuchando mensajes (opcional)
            # data = await websocket.receive_text() 
            
            # Recibir JSON si necesitas señales como "está escribiendo" o "leído"
            data = await websocket.receive_json()
            
    except WebSocketDisconnect:
        # 2. Desconectar al usuario si cierra la pestaña o pierde internet
        socket_manager.disconnect(user_id)
    except Exception as e:
        print(f"Error en socket para usuario {user_id}: {e}")
        socket_manager.disconnect(user_id)

@app.get("/")
def check_db_connection(db: Session = Depends(get_db)):
    try:
        # Intentamos ejecutar una consulta simple
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "Conectada correctamente"}
    except Exception as e:
        # Si algo falla (user/pass mal, server apagado), lo veremos aquí
        raise HTTPException(
            status_code=500, 
            detail=f"Error conectando a la base de datos: {str(e)}"
        )