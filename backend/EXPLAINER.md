# Internet of Bodies (IoB) Biometric Authentication — System Architecture & Concept Guide

Welcome to the **Internet of Bodies (IoB) Command Center** guide! This document is designed to teach you **what is happening in this project**, **how every piece works together under the hood**, and **the exact concepts and learning resources you need to master it**.

---

## 1. What is Happening? (The Big Picture)

### The Core Problem
Standard two-factor authentication (2FA) or password logins can be phished, intercepted, or stolen.

### The IoB Solution
We are building a **hardware-bound, liveness-verified biometric authentication system**. To log into a web portal (e.g., Netbanking), you cannot just type a password. Instead:
1. The web screen shows a dynamic **QR Code** containing a temporary session ID.
2. An Android device (Pixel 7) scans the QR code.
3. The phone's front camera measures your real-time **pulse (heart rate / BPM)** using micro-fluctuations in skin color (**rPPG**).
4. The phone packages your pulse data with the session ID and **signs it physically inside the Titan M2 hardware security chip** using a private key that *never leaves the chip*.
5. The phone sends this signed payload to our **FastAPI Backend**.
6. The Backend verifies the cryptographic signature, checks that your heart rate is biologically real (e.g., 40–220 BPM), and **instantly unlocks the web session over a WebSocket connection**.

---

## 2. System Architecture & The 4 Roles

The system is split among four specialized components:

```
┌─────────────────────────┐               ┌──────────────────────────┐
│  React Frontend (Web)   │               │   Pixel 7 Android App    │
│  (Frontend Developer)   │               │                          │
│                         │               │  ┌────────────────────┐  │
│  - Displays Login Portal│               │  │  Dev B (rPPG C++)  │  │
│  - Renders QR Code      │               │  │  - CameraX + OpenCV│  │
│  - Real-time Dashboard  │               │  │  - Extracts BPM    │  │
└────────────▲────────────┘               │  └─────────┬──────────┘  │
             │                            │            │ BPM         │
             │ WebSockets                 │  ┌─────────▼──────────┐  │
             │ (Bi-directional)         │  │ Dev A (Kotlin / HW)│  │
             │                            │  │ - Scans QR Code    │  │
             │                            │  │ - Signs via Titan  │  │
             │                            │  │   M2 StrongBox     │  │
             │                            │  └─────────┬──────────┘  │
             │                            └────────────┼─────────────┘
             │                                         │ Signed Payload
             │                                         │ (HTTPS POST)
┌────────────▼─────────────────────────────────────────▼─────────────┐
│                 FastAPI Backend (Command Center)                  │
│                      (Your Role: FastAPI Engineer)                │
│                                                                   │
│  - SessionManager: Generates & manages session life cycle          │
│  - ConnectionManager: Pushes real-time events over WebSockets      │
│  - Crypto Service: Verifies Titan M2 ECDSA-SHA256 signatures      │
└───────────────────────────────────────────────────────────────────┘
```

---

## 3. End-to-End Authentication Flow (Step-by-Step)

Here is the exact sequence of events when a user logs in:

1. **User opens Netbanking Login Page** on React frontend.
2. **React calls `POST /api/v1/sessions`** on FastAPI backend to get a unique `session_id`.
3. **React renders `session_id` as a QR code** on screen and connects to `WS /api/v1/ws/{session_id}`.
4. **Android App (Pixel 7)** scans the QR code (Dev A) to extract `session_id`.
5. **Android App processes face frames** with OpenCV (Dev B) to calculate live pulse/BPM (e.g., 72 BPM).
6. **Titan M2 Chip signs payload** (`{session_id, bpm, timestamp, device_id}`) using physical hardware private key (Dev A).
7. **Android posts signed payload to `POST /api/v1/auth/verify`** on FastAPI backend.
8. **FastAPI Backend runs 6-step verification**:
   - Signature check via ECDSA-SHA256
   - Payload deserialization
   - Session existence & `PENDING` state check
   - BPM biological bounds check ($40 \le \text{BPM} \le 220$)
   - Timestamp freshness check
   - Grants session & triggers WebSocket push (`ACCESS_GRANTED`)
9. **React UI receives WebSocket push** and instantly animates to the secure Account Dashboard.

---

## 4. How the FastAPI Backend Works (Deep-Dive)

As the **FastAPI Engineer**, your code acts as the traffic controller and verifier. Here is how your 3 main modules operate:

### A. Connection Manager (`app/services/connection_manager.py`)
- **What it does**: Holds an active dictionary of open WebSockets (`dict[session_id, WebSocket]`).
- **Why it matters**: WebSockets allow the server to **push** messages to the browser without the browser having to constantly ask ("poll") the server if authentication completed.
- **Key Method**: `send_to_session(session_id, data)` targets a specific user's browser tab to send `"ACCESS_GRANTED"`.

### B. Session Manager (`app/services/session.py`)
- **What it does**: Manages the state machine of a session:
  $$\text{PENDING} \longrightarrow \text{VERIFIED} \longrightarrow \text{GRANTED}$$
  $$\searrow \quad \text{EXPIRED}$$
- **Key Security Feature**: Sessions expire automatically after 300 seconds (5 minutes). A background `asyncio` task purges stale sessions every 60 seconds.

### C. Cryptographic Verifier (`app/services/crypto.py`)
- **What it does**: Verifies the digital signature produced by Google's Titan M2 security chip.
- **How ECDSA Works**:
  1. The Titan M2 chip on the Pixel 7 generated an **Elliptic Curve (EC)** key pair (`secp256r1` / `P-256`).
  2. The **Private Key** lives physically inside the Titan M2 hardware and can never be read by software.
  3. The phone sends the **Public Key**, the **Payload** (`{session_id, bpm, timestamp, device_id}`), and the **Signature**.
  4. The backend uses Python's `cryptography` library to run:
     $$\text{verify}(\text{Signature}, \text{Payload}, \text{Public Key}) \overset{?}{=} \text{True}$$
  5. If anyone altered even a single bit of the BPM or session ID during transit, `verify()` throws an `InvalidSignature` error.

### D. The 6-Step Fail-Fast Pipeline (`app/routers/auth.py`)
When `POST /api/v1/auth/verify` receives data from the Pixel 7, it runs these 6 strict checks:
1. **Signature Verification**: Validates ECDSA-SHA256 signature using `crypto.py`.
2. **Payload Parsing**: Unpacks base64 JSON into a validated `BiometricPayload` object.
3. **Session State Check**: Verifies `session_id` exists in `SessionManager` and is currently in `PENDING` state.
4. **BPM Plausibility Check**: Ensures heart rate is within biological bounds ($40 \le \text{BPM} \le 220$).
5. **Timestamp Freshness**: Rejects payloads older than the session expiry window to prevent **replay attacks**.
6. **State Transition & Push**: Marks session as `GRANTED` and pushes `ACCESS_GRANTED` to the frontend via `ConnectionManager`.

---

## 5. Key Concepts & Resources to Master

To thoroughly understand and speak confidently about this system, here are the key technical concepts and recommended reading resources:

### 1. WebSockets & Real-Time Communication
* **Concept**: Unlike standard HTTP (request-response), WebSockets establish a single long-lived TCP connection for instant bi-directional messaging.
* **Why we use it**: To push the `ACCESS_GRANTED` signal to the web frontend the exact millisecond the phone finishes verification.
* **Recommended Resources**:
  - [MDN WebSockets API Guide](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API)
  - [FastAPI WebSockets Documentation](https://fastapi.tiangolo.com/advanced/websockets/)

### 2. Public-Key Cryptography & ECDSA
* **Concept**: Asymmetric encryption using Elliptic Curve Digital Signature Algorithm (ECDSA). One key signs (Private), another verifies (Public).
* **Why we use it**: Guarantees that the biometric data came from an authentic, untampered physical device.
* **Recommended Resources**:
  - [Computerphile: Elliptic Curves (Video)](https://www.youtube.com/watch?v=NF1pwjL9-DE)
  - [Python `cryptography` Library Documentation](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ec/)

### 3. Hardware Root of Trust (Titan M2 & Android KeyStore)
* **Concept**: A dedicated tamper-resistant microchip (StrongBox) built into the Google Pixel phone that generates and locks cryptographic keys in physical hardware.
* **Why we use it**: Even if malware infects the Android operating system, it cannot steal the private key from Titan M2.
* **Recommended Resources**:
  - [Android Security: Hardware-backed KeyStore](https://developer.android.com/training/articles/keystore)
  - [Google Titan M2 Security Chip Overview](https://security.googleblog.com/2021/10/titan-m2-user-guide.html)

### 4. Remote Photoplethysmography (rPPG)
* **Concept**: Measuring blood volume pulse (BPM) remotely by capturing ambient light reflected off human skin using standard RGB camera sensors.
* **Why we use it**: Proves the person in front of the phone is a live human being with a beating heart, preventing photo/video spoofing.
* **Recommended Resources**:
  - [OpenCV Documentation](https://docs.opencv.org/)
  - [rPPG Principles & Facial ROI Tracking Overview](https://en.wikipedia.org/wiki/Photoplethysmogram)

---

## 6. How to Test Your Command Center

### Step 1: Start the Backend
```bash
cd d:/IOB/backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Step 2: Open Interactive API Docs
Navigate to [http://localhost:8000/docs](http://localhost:8000/docs) in your browser. You can test session creation (`POST /api/v1/sessions`) directly from the UI!
