import asyncio
import json
import random

import websockets


class FaceWSServer:
    def __init__(self):
        self.server = None
        self.port = 8765

    async def handler(self, websocket):
        print("[OK] Face client connected")

        try:
            while True:
                data = {
                    "student_id": random.randint(1, 5),
                    "student_name": "Test Student",
                    "confidence": round(random.uniform(0.7, 0.95), 2),
                    "period_id": 1,
                    "class_section": "10-A",
                    "status": "present",
                }

                await websocket.send(json.dumps(data))
                print("[SEND] Sent:", data)

                await asyncio.sleep(5)

        except websockets.exceptions.ConnectionClosed:
            print("[ERROR] Face client disconnected")

    async def start(self):
        try:
            print("[STARTING] ENTERING WS START")

            self.server = await websockets.serve(self.handler, "127.0.0.1", self.port)

            print(f"[RUNNING] Face WS running on ws://127.0.0.1:{self.port}")

        except Exception as e:
            print("[FAILED] WS START FAILED:", e)

    async def stop(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()


if __name__ == "__main__":
    async def main():
        server = FaceWSServer()
        await server.start()
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            await server.stop()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
