import os
import re
import asyncio
import aiohttp
import logging
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError, PhoneNumberInvalidError, PhoneCodeInvalidError
from aiohttp import web
import socketio

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Variables de entorno
API_ID = int(os.environ.get("API_ID", 34381011))
API_HASH = os.environ.get("API_HASH", "9fa719ab3184445d8de8548da9f3bb4b")
CANAL_ID = int(os.environ.get("CANAL_ID", -1002766995952))
SESSION_NAME = os.environ.get("SESSION_NAME", "session")

# Intentar usar el archivo de sesión local (si existe)
session_path = f"{SESSION_NAME}.session"
if not os.path.exists(session_path):
    logger.warning(f"El archivo de sesión {session_path} no existe. Se creará uno nuevo, pero puede que se requiera autenticación interactiva (no disponible en Render).")

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

# Socket.IO server con CORS abierto
sio = socketio.AsyncServer(cors_allowed_origins='*')
app = web.Application()
sio.attach(app)

signals = []
opportunities = []
gales = []

# ===== Middleware CORS =====
@web.middleware
async def cors_middleware(request, handler):
    response = await handler(request)
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

app.middlewares.append(cors_middleware)

# ===== Funciones de parsing (igual que antes) =====
def parse_signal(text):
    result = {"type": None, "game": None, "entry": None, "bet_on": None, "result": None, "raw": text}
    if "GREEN" in text.upper():
        result["type"] = "green"
        match = re.search(r"RESULTADO:\s*COLOR\s*(.*?)(?:\n|$)", text, re.IGNORECASE)
        if match:
            result["result"] = match.group(1).strip()
    elif "ENTRADA CONFIRMADA" in text:
        result["type"] = "señal"
        match = re.search(r"Juego:\s*(.*?)(?:\n|$)", text)
        if match:
            result["game"] = match.group(1).strip()
        match = re.search(r"INGRESAR DESPUÉS:\s*(.*?)(?:\n|$)", text)
        if match:
            result["entry"] = match.group(1).strip()
        match = re.search(r"APUESTA EN:\s*(.*?)(?:\n|$)", text)
        if match:
            result["bet_on"] = match.group(1).strip()
    return result

def parse_opportunity(text):
    if "DETECTANDO POSIBLE OPORTUNIDAD" in text.upper():
        info = {"type": "oportunidad", "game": None, "raw": text}
        match = re.search(r"Juego:\s*(.*?)(?:\n|$)", text)
        if match:
            info["game"] = match.group(1).strip()
        return info
    return None

def parse_gale(text):
    text_lower = text.lower()
    if "1° gale" in text_lower or "1ª gale" in text_lower or "1 gale" in text_lower:
        return {"type": "gale_1", "raw": text}
    if "2° gale" in text_lower or "2ª gale" in text_lower or "2 gale" in text_lower:
        return {"type": "gale_2", "raw": text}
    gale_match = re.search(r"(\d+)[°ª]?\s*gale", text_lower)
    if gale_match:
        return {"type": f"gale_{gale_match.group(1)}", "raw": text}
    return None

# ===== Manejador de mensajes =====
@client.on(events.NewMessage)
async def handler(event):
    if event.chat_id != CANAL_ID:
        return
    text = event.message.text
    if not text:
        return

    logger.info(f"Mensaje recibido:\n{text}")

    signal = parse_signal(text)
    if signal["type"]:
        signal["timestamp"] = event.message.date.isoformat()
        signals.append(signal)
        if len(signals) > 100:
            signals.pop(0)
        await sio.emit('new_signal', signal)
        logger.info(f"✅ Señal guardada: {signal['type']}")
        return

    opp = parse_opportunity(text)
    if opp:
        opp["timestamp"] = event.message.date.isoformat()
        opportunities.append(opp)
        if len(opportunities) > 100:
            opportunities.pop(0)
        await sio.emit('new_opportunity', opp)
        logger.info("⚠️ Oportunidad guardada")
        return

    gale = parse_gale(text)
    if gale:
        gale["timestamp"] = event.message.date.isoformat()
        gales.append(gale)
        if len(gales) > 100:
            gales.pop(0)
        await sio.emit('new_gale', gale)
        logger.info(f"🔄 Gale guardado: {gale['type']}")
        return

    logger.info("Mensaje no relevante, ignorado.")

# ===== Rutas HTTP =====
async def health(request):
    return web.json_response({"status": "ok"})

async def signals_api(request):
    return web.json_response(signals[-20:])

async def opportunities_api(request):
    return web.json_response(opportunities[-20:])

async def gales_api(request):
    return web.json_response(gales[-20:])

async def test_emit(request):
    # Para pruebas manuales
    await sio.emit('new_signal', {
        "type": "señal",
        "game": "Prueba manual",
        "entry": "🔥",
        "bet_on": "🟢",
        "timestamp": "2025-04-01T12:00:00"
    })
    return web.json_response({"ok": True})

app.router.add_get('/health', health)
app.router.add_get('/signals', signals_api)
app.router.add_get('/opportunities', opportunities_api)
app.router.add_get('/gales', gales_api)
app.router.add_get('/test', test_emit)

# ===== Auto‑ping cada 5 minutos =====
async def self_ping():
    port = int(os.environ.get("PORT", 5000))
    url = f"http://localhost:{port}/health"
    while True:
        await asyncio.sleep(300)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5) as resp:
                    if resp.status == 200:
                        logger.info("[PING] Auto‑ping exitoso")
                    else:
                        logger.warning(f"[PING] Auto‑ping falló con código {resp.status}")
        except Exception as e:
            logger.error(f"[PING] Error: {e}")

# ===== Inicio de Telethon con manejo de errores =====
async def start_telethon():
    try:
        await client.start()
        logger.info("✅ Cliente de Telegram iniciado. Escuchando mensajes...")
        await client.run_until_disconnected()
    except Exception as e:
        logger.error(f"❌ Error al iniciar Telethon: {e}")

# ===== Main =====
async def main():
    # Tareas
    telethon_task = asyncio.create_task(start_telethon())
    ping_task = asyncio.create_task(self_ping())

    # Servidor web
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 5000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"🌐 Servidor web y WebSocket en http://0.0.0.0:{port}")

    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
