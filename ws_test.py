import asyncio
import websockets

async def handler(websocket):
    print("Клиент подключился!")
    async for message in websocket:
        print(f"Получено: {message}")
        await websocket.send(f"Сервер Uniqueizer ответил: {message}")

async def main():
    async with websockets.serve(handler, "localhost", 8765):
        print("Локальный сервер запущен на ws://localhost:8765")
        await asyncio.Future()  # Работает вечно

if __name__ == "__main__":
    asyncio.run(main())