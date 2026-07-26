"""
SentinelHard Telemetry Server
WebSocket endpoint for receiving real-time rPPG telemetry from the Android client.

Run with:
    uvicorn server.main:app --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import json
from datetime import datetime

app = FastAPI(title="SentinelHard Telemetry Server")


class ConnectionManager:
    """Manages active WebSocket connections."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[{datetime.now().isoformat()}] Client connected. Active: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        print(f"[{datetime.now().isoformat()}] Client disconnected. Active: {len(self.active_connections)}")


manager = ConnectionManager()


@app.websocket("/ws/telemetry")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            telemetry = json.loads(data)

            bpm = telemetry.get("bpm", 0.0)
            snr = telemetry.get("snr", 0.0)
            liveness_status = telemetry.get("liveness_status", 1)
            timestamp = telemetry.get("timestamp", 0)

            status_label = {0: "SPOOF", 1: "ANALYZING", 2: "HUMAN"}.get(liveness_status, "UNKNOWN")

            print(
                f"[Telemetry] BPM: {bpm:.1f} | "
                f"SNR: {snr:.2f} | "
                f"Liveness: {status_label} ({liveness_status}) | "
                f"Client-ts: {timestamp}"
            )

            # TODO: Server-side validation rules
            # e.g., if liveness_status == 2 sustained for 3+ seconds -> Authenticated
            # For now, echo an acknowledgment back to the client
            await websocket.send_text(json.dumps({
                "ack": True,
                "server_ts": datetime.now().isoformat(),
            }))

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"[Error] {e}")
        manager.disconnect(websocket)


@app.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {
        "status": "ok",
        "active_connections": len(manager.active_connections),
    }
