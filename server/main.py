"""
SentinelHard Telemetry Server
WebSocket and REST endpoints for real-time rPPG telemetry and biometric verification.

Run with:
    uvicorn main:app --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import json
import base64
from datetime import datetime

app = FastAPI(title="SentinelHard Telemetry Server")

# --- Models ---

class VerifyRequest(BaseModel):
    payload: str              # Base64-encoded JSON of BiometricPayload
    signature: str            # Base64 ECDSA signature
    public_key: str           # Base64 DER-encoded public key
    attestation_chain: Optional[List[str]] = []

class VerifyResponse(BaseModel):
    authenticated: bool
    message: str
    session_id: str
    confidence: float

# --- Connection Management ---

class ConnectionManager:
    """Manages active WebSocket connections."""
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[{datetime.now().isoformat()}] Client connected. Active: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            print(f"[{datetime.now().isoformat()}] Client disconnected. Active: {len(self.active_connections)}")

manager = ConnectionManager()

# --- REST Endpoints ---

@app.post("/api/auth/verify", response_model=VerifyResponse)
async def verify_biometrics(request: VerifyRequest):
    """
    Verifies the hardware-signed biometric payload.
    In production, this would:
    1. Decode the payload.
    2. Verify the ECDSA signature using the public_key.
    3. Validate the attestation_chain against Google's Root CA.
    4. Check liveness metrics (SNR, Variance).
    """
    try:
        # 1. Decode payload
        decoded_payload = base64.b64decode(request.payload).decode('utf-8')
        payload_data = json.loads(decoded_payload)

        session_id = payload_data.get("session_id", "unknown")
        bpm = payload_data.get("bpm", 0.0)
        snr = payload_data.get("snr", 0.0)

        print(f"[{datetime.now().isoformat()}] VERIFY REQ | Session: {session_id} | BPM: {bpm:.1f} | SNR: {snr:.2f}")

        # 2. Logic: For this demo, we "authenticate" if SNR is > 2.0 (good signal)
        is_valid = snr > 2.0

        return VerifyResponse(
            authenticated=is_valid,
            message="Biometrics Verified" if is_valid else "Signal Quality Too Low",
            session_id=session_id,
            confidence=min(1.0, snr / 10.0)
        )
    except Exception as e:
        print(f"[Error] Verification failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "ok", "active_connections": len(manager.active_connections)}

# --- WebSocket Endpoints ---

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

            status_label = {0: "SPOOF", 1: "ANALYZING", 2: "HUMAN"}.get(liveness_status, "UNKNOWN")

            print(
                f"[Telemetry] BPM: {bpm:.1f} | "
                f"SNR: {snr:.2f} | "
                f"Liveness: {status_label} ({liveness_status})"
            )

            await websocket.send_text(json.dumps({
                "ack": True,
                "server_ts": datetime.now().isoformat(),
            }))

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"[Error] WebSocket Exception: {e}")
        manager.disconnect(websocket)
