import os
import re
import asyncio
from telethon import TelegramClient, events
from aiohttp import web
import socketio

# Configuración desde variables de entorno
API_ID = int(os.environ.get("API_ID", 34381011))
API_HASH = os.environ.get("API_HASH", "9fa719ab3184445d8de8548da9f3bb4b")
CANAL_ID = int(os.environ.get("CANAL_ID", -1002766995952))
SESSION_NAME = os.environ.get("SESSION_NAME", "session")

# Cliente de Telegram
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

# Socket.IO server
sio = socketio.AsyncServer(cors_allowed_origins='*')
app = web.Application()
sio.attach(app)

# Almacenamiento en memoria (opcional, para consultas REST)
signals = []
opportunities = []
gales = []

# Funciones de parsing (igual que antes)
def parse_signal(text):
    result = {
        "type": None,
        "game": None,
        "entry": None,
        "bet_on": None,
        "result": None,
        "raw": text
    }
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
        info = {
            "type": "oportunidad",
            "game": None,
            "raw": text
        }
        match = re.search(r"Juego:\s*(.*?)(?:\n|$)", text)
        if match:
            info["game"] = match.group(1).strip()
        return info
    return None

def parse_gale(text):
    text_lower = text.lower()
    gale_match = re.search(r"(\d+)[°ª]?\s*gale", text_lower)
    if gale_match:
        gale_number = gale_match.group(1)
        return {"type": f"gale_{gale_number}", "raw": text}
    if "1° gale" in text_lower or "1ª gale" in text_lower or "1 gale" in text_lower:
        return {"type": "gale_1", "raw": text}
    if "2° gale" in text_lower or "2ª gale" in text_lower or "2 gale" in text_lower:
        return {"type": "gale_2", "raw": text}
    return None

# Evento de Telegram
@client.on(events.NewMessage)
async def handler(event):
    if event.chat_id != CANAL_ID:
        return
    text = event.message.text
    if not text:
        return

    print("Mensaje recibido:\n", text)

    # Señal
    signal = parse_signal(text)
    if signal["type"]:
        signal["timestamp"] = event.message.date.isoformat()
        signals.append(signal)
        if len(signals) > 100:
            signals.pop(0)
        print("✅ Señal guardada:", signal)
        # Emitir por WebSocket a todos los clientes conectados
        await sio.emit('new_signal', signal)
        return

    # Oportunidad
    opp = parse_opportunity(text)
    if opp:
        opp["timestamp"] = event.message.date.isoformat()
        opportunities.append(opp)
        if len(opportunities) > 100:
            opportunities.pop(0)
        print("⚠️ Oportunidad guardada:", opp)
        await sio.emit('new_opportunity', opp)
        return

    # Gale
    gale = parse_gale(text)
    if gale:
        gale["timestamp"] = event.message.date.isoformat()
        gales.append(gale)
        if len(gales) > 100:
            gales.pop(0)
        print("🔄 Gale guardado:", gale)
        await sio.emit('new_gale', gale)
        return

    print("Mensaje no relevante, ignorado.")

# Ruta para servir el archivo HTML
async def index(request):
    return web.FileResponse('./static/index.html')

# Configurar rutas HTTP
app.router.add_get('/', index)
# Opcional: endpoints REST para consultar datos históricos
app.router.add_get('/signals', lambda r: web.json_response(signals[-20:]))
app.router.add_get('/opportunities', lambda r: web.json_response(opportunities[-20:]))
app.router.add_get('/gales', lambda r: web.json_response(gales[-20:]))

# Iniciar servidor aiohttp y Telethon
async def start_telethon():
    await client.start()
    print("✅ Cliente de Telegram iniciado. Escuchando mensajes...")
    await client.run_until_disconnected()

async def main():
    # Ejecutar el cliente de Telegram en segundo plano
    telethon_task = asyncio.create_task(start_telethon())

    # Configurar y ejecutar el servidor web (aiohttp)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 5000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"🌐 Servidor web y WebSocket en http://0.0.0.0:{port}")

    # Mantener el programa corriendo hasta que se interrumpa
    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
