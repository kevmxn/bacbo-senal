from telethon import TelegramClient

api_id = 34381011
api_hash = '9fa719ab3184445d8de8548da9f3bb4b'

client = TelegramClient('session', api_id, api_hash)

async def main():
    await client.start()
    print("✅ Sesión creada. Ahora puedes detener el script (Ctrl+C).")

with client:
    client.loop.run_until_complete(main())
