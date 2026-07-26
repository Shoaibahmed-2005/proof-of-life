# IOB Backend — FastAPI Command Center

Biometric authentication backend for the **Internet of Bodies (IOB)** system. Manages WebSocket connections to the React frontend, generates session IDs for QR code rendering, and verifies cryptographically-signed biometric payloads from a Pixel 7 Android device.

## Architecture

```
React Frontend ←──WebSocket──→ FastAPI Backend ←──HTTPS──→ Pixel 7 (Android)
     │                              │
     │  1. POST /sessions           │
     │  2. Render QR code           │
     │  3. WS /ws/{session_id}      │
     │                              │  4. POST /auth/verify
     │                              │     (signed BPM payload)
     │  5. WS push ACCESS_GRANTED   │
     │  6. Animate to Dashboard     │
```

## Project Structure

```text
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                     # App entrypoint, lifespan events
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py               # Settings (session expiry, BPM range)
│   ├── routers/
│   │   ├── __init__.py             # Combines all routers
│   │   ├── health.py               # Health check endpoint
│   │   ├── ws.py                   # WebSocket endpoint
│   │   ├── session.py              # Session CRUD endpoints
│   │   └── auth.py                 # Biometric verification endpoint
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── health.py               # Health response model
│   │   ├── session.py              # Session models + status enum
│   │   └── auth.py                 # BiometricPayload, VerifyRequest/Response
│   ├── services/
│   │   ├── __init__.py
│   │   ├── connection_manager.py   # WebSocket connection manager
│   │   ├── session.py              # Session lifecycle management
│   │   └── crypto.py               # ECDSA signature verification
│   └── db/
│       ├── __init__.py
│       └── session.py              # DB session stub
├── .env.example
├── requirements.txt
└── README.md
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | API overview |
| `GET` | `/api/v1/health` | Health check |
| `POST` | `/api/v1/sessions` | Create a new auth session |
| `GET` | `/api/v1/sessions/{id}` | Get session status |
| `DELETE` | `/api/v1/sessions/{id}` | Expire a session |
| `POST` | `/api/v1/auth/verify` | Verify signed biometric payload |
| `WS` | `/api/v1/ws/{session_id}` | Real-time WebSocket connection |

## WebSocket Events

| Event | Direction | Description |
|-------|-----------|-------------|
| `CONNECTED` | Server → Client | Connection established |
| `ACCESS_GRANTED` | Server → Client | Biometric verification succeeded |
| `STATUS` | Server → Client | Session status update |
| `pong` | Server → Client | Heartbeat response |
| `ping` | Client → Server | Heartbeat request |
| `status` | Client → Server | Request session status |

## Setup & Running Locally

### 1. Prerequisites
- **Python 3.11+**

### 2. Virtual Environment
```bash
cd backend
python -m venv venv

# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# macOS/Linux:
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment
```bash
cp .env.example .env
# Edit .env as needed
```

### 5. Run the Server
```bash
uvicorn app.main:app --reload
```

### 6. Explore the API
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check**: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

## Session Lifecycle

```
PENDING  →  VERIFIED  →  GRANTED
   ↘           ↘
         EXPIRED (timeout / manual)
```

1. **PENDING**: Frontend creates session, renders QR code
2. **VERIFIED**: Pixel 7 scans QR, submits payload (internal state)
3. **GRANTED**: Signature + BPM valid, frontend notified via WebSocket
4. **EXPIRED**: Session timed out or manually expired

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PROJECT_NAME` | `IOB Backend` | Application name |
| `SESSION_EXPIRY_SECONDS` | `300` | Session TTL in seconds |
| `BPM_MIN` | `40` | Minimum valid heart rate |
| `BPM_MAX` | `220` | Maximum valid heart rate |
| `SECRET_KEY` | `change-me` | Application secret key |
| `BACKEND_CORS_ORIGINS` | `localhost:3000,5173` | Allowed CORS origins |
