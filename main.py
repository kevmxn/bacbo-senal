import os
import asyncio
import aiohttp
import logging
from telethon import TelegramClient, events
from aiohttp import web
import socketio

# ============================================
# CONFIGURACIÓN
# ============================================
API_ID = int(os.environ.get("API_ID", 34381011))
API_HASH = os.environ.get("API_HASH", "9fa719ab3184445d8de8548da9f3bb4b")
CANAL_ID = int(os.environ.get("CANAL_ID", -1002766995952))
SESSION_NAME = os.environ.get("SESSION_NAME", "session")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Variables globales (para guardar últimos mensajes si se desea)
messages_history = []   # opcional, para tener los últimos 100 mensajes

# ============================================
# MANEJADOR DE MENSAJES (TODOS)
# ============================================
def create_handler(client, sio):
    @client.on(events.NewMessage)
    async def handler(event):
        if event.chat_id != CANAL_ID:
            return
        text = event.message.text
        if not text:
            return

        logger.info(f"Mensaje recibido:\n{text}")

        # Crear objeto con todos los datos relevantes
        message_data = {
            'text': text,
            'timestamp': event.message.date.isoformat(),
            'message_id': event.message.id,
            'sender_id': event.sender_id,
            'chat_id': event.chat_id
        }

        # Guardar en memoria (opcional, últimos 100)
        messages_history.append(message_data)
        if len(messages_history) > 100:
            messages_history.pop(0)

        # Emitir a todos los clientes conectados
        await sio.emit('new_message', message_data)
        logger.info("📨 Mensaje emitido a todos los clientes")

    return handler

# ============================================
# BUCLE DE RECONEXIÓN DE TELEGRAM
# ============================================
async def run_telethon(client):
    while True:
        try:
            logger.info("Conectando a Telegram...")
            await client.start()
            logger.info("✅ Cliente de Telegram iniciado. Escuchando mensajes...")
            await client.run_until_disconnected()
        except Exception as e:
            logger.error(f"Error en conexión de Telegram: {e}")
            logger.info("Reconectando en 5 segundos...")
            await asyncio.sleep(5)

# ============================================
# ENDPOINTS HTTP (opcionales)
# ============================================
async def health(request):
    return web.json_response({"status": "ok"})

async def last_messages(request):
    return web.json_response(messages_history[-20:])

# ============================================
# AUTO‑PING CADA 5 MINUTOS
# ============================================
async def self_ping(port):
    url = f"http://localhost:{port}/health"
    while True:
        await asyncio.sleep(300)  # 5 minutos
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5) as resp:
                    if resp.status == 200:
                        logger.info("[PING] Auto‑ping exitoso, servicio activo")
                    else:
                        logger.warning(f"[PING] Auto‑ping falló con código {resp.status}")
        except Exception as e:
            logger.error(f"[PING] Error en auto‑ping: {e}")

# ============================================
# MIDDLEWARE CORS
# ============================================
@web.middleware
async def cors_middleware(request, handler):
    resp = await handler(request)
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return resp

# ============================================
# MAIN
# ============================================
async def main():
    # Servidor web + Socket.IO
    sio = socketio.AsyncServer(cors_allowed_origins='*')
    app = web.Application(middlewares=[cors_middleware])
    sio.attach(app)

    app.router.add_get('/health', health)
    app.router.add_get('/messages', last_messages)   # endpoint para ver últimos mensajes

    # Iniciar servidor web
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get('PORT', 5000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"🌐 Servidor web y WebSocket en http://0.0.0.0:{port}")

    # Crear cliente de Telegram con la sesión
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

    # Agregar manejador de mensajes
    handler = create_handler(client, sio)
    client.add_event_handler(handler)

    # Lanzar tareas
    asyncio.create_task(run_telethon(client))
    asyncio.create_task(self_ping(port))

    # Mantener la aplicación corriendo
    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
