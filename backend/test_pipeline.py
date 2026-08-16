import asyncio, glob
import cv2
import websockets

async def main():
    images = glob.glob("../assets/*.jpg")
    print(f"Testing with {len(images)} images...\n")

    async with websockets.connect("ws://localhost:8000/ws/stream") as ws:
        for path in images:
            frame = cv2.imread(path)
            _, jpg = cv2.imencode(".jpg", frame)
            await ws.send(jpg.tobytes())
            msg = await ws.recv()
            import json
            data = json.loads(msg)
            print(f"{path.split(chr(92))[-1]}")
            print(f"   detections: {[(d['cls'], round(d['conf'],2)) for d in data['detections']]}")
            if data["violations"]:
                print(f"   >>> VIOLATIONS: {[v['type'] for v in data['violations']]}")
            print()

asyncio.run(main())