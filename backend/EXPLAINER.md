# Proof of Life: How the System Works (Concept Guide)

This guide explains **what the system does, how the pieces fit together, and the concepts behind it**, so that anyone on the team can present it. It covers the whole project: the Android app, this FastAPI backend and the web portal. For setup and API details see `README.md`; for the demo see `../DEMO_SCRIPT.md`.

---

## 1. The problem and the idea

Every year, each pensioner must prove they are alive (a **life certificate**) or the pension stops. Travelling to an office is hard for elderly and disabled pensioners, and remote checks can be fooled with a photo or a video.

Proof of Life lets the pensioner do it **at home with their own phone**, and makes three independent checks:

| Check | Question it answers | How |
|---|---|---|
| **Liveness (rPPG)** | Is a living person in front of the camera? | The phone measures the pulse from tiny colour changes in the face skin. A photo has no pulse. |
| **Random challenge** | Is it happening now, not a recording? | The backend picks an action (blink twice, turn left, turn right) when the session is created. A pre-recorded video can't know which one, or when it will be asked. |
| **1:1 face match** | Is it the registered pensioner? | The face is turned into 192 numbers (MobileFaceNet) and compared only with *that* pensioner's registered template. |

The result is **signed inside the phone's security chip** (Titan M2 / StrongBox on a Pixel), so the backend knows it came from the registered phone and wasn't altered.

---

## 2. The parts

```
 Web portal (laptop, React)            Android app (Pixel 7, Kotlin + C++)
 - officer: register, review,          - Scan QR → Consent → Face Scan → Result
   records, treasury, ledger           - rPPG engine in C++ (POS, band-pass, SNR, stability gate)
 - pensioner: submit, practice,        - ML Kit face detection + tracking (one face only)
   check status                        - MobileFaceNet embeddings (LiteRT)
        ▲  WebSocket (live steps)      - challenge check from ML Kit landmarks
        │                              - ECDSA P-256 signature in StrongBox / TEE
        │                                         │  HTTP POST (signed payload)
 ┌──────┴─────────────────────────────────────────▼──────┐
 │ FastAPI backend                                        │
 │ sessions + QR · signature check · device binding ·     │
 │ liveness + challenge rules · 1:1 face match (3 bands) · │
 │ templates (encrypted) · freeze rules · review queue ·  │
 │ hash-chained audit ledger · did:key · signed credential │
 └────────────────────────────────────────────────────────┘
```

---

## 3. The two flows

### Registration (once, officer-assisted)
1. The officer checks the pensioner's physical ID in person, then enters their details in **Register Pensioner** (dummy data for the demo; never Aadhaar numbers).
2. The portal shows a QR code: `{base_url, session_id, purpose: ENROLLMENT, nonce, challenge, liveness gate settings}`.
3. The pensioner scans it with the app, agrees to the consent screen, and does the face scan: stable pulse → the random challenge → face frames.
4. The app averages its **best 15 face embeddings** into a reference template, signs `{session, nonce, pulse, challenge result, template, model version, key type, consent}` and posts it.
5. The backend stores the template **encrypted** and binds the phone's **public key** to the pensioner. The officer clicks **Approve** and the pension is **Active**.

### Annual life certificate (at home)
1. The pensioner enters their pension ID on the portal and gets a QR code (`purpose: LIFE_CERTIFICATE`).
2. Same scan on the same phone; this time the app sends a **probe embedding** (average of the best 5 frames).
3. The backend runs the pipeline (section 4) and decides:
   - **strong match + live + challenge passed** → certificate issued, the template is gently updated (ageing);
   - **borderline match** → officer **Review Queue**;
   - **mismatch / no pulse / challenge failed** → rejected. Three such failures **freeze** the pension (never cancel it) until an officer restores it.
4. The portal updates live over the WebSocket: *Waiting for scan → Measuring pulse → Challenge → Face match → Result*.

---

## 4. The verification pipeline (backend)

`app/services/verification.py`, fail fast, in this order:

1. **Signature**: ECDSA-SHA256 over the exact payload bytes (P-256).
2. **Schema**: the payload parses; face data is required only when the pulse and challenge passed.
3. **Session**: exists, right purpose, right nonce, not expired, then **claimed atomically** (single use, so a replay of the same payload fails).
4. **Device binding**: a life certificate must be signed by the key registered for that pensioner.
5. **Freshness and consent**.
6. **App abort**: if the app stopped the scan (`MULTIPLE_FACES`, `FACE_NOT_CAPTURED`), it is rejected with that reason.
7. **Liveness**: BPM in 40–220, SNR ≥ `MIN_SNR_DB`, and the phone's stability verdict.
8. **Challenge**: same challenge id as issued, and passed.
9. **Face match**: cosine similarity to the pensioner's current template **and** the original anchor template → three bands.
10. **Record**: certificate, pension status, template update, ledger entry, signed credential, WebSocket events.

Only `NO_PULSE`, `CHALLENGE_FAILED` and `FACE_MISMATCH` count toward freezing. Problems like "wrong phone" or "someone walked into the frame" don't, so a stranger can't freeze a pension by accident.

---

## 5. Key concepts

### rPPG (remote photoplethysmography)
Each heartbeat pushes blood into the face and changes skin colour very slightly. The app averages the skin pixels of the forehead and cheeks in every frame, and turns the colour signal into a pulse with the **POS** method (Wang et al., "Algorithmic principles of remote PPG", IEEE TBME 2017). It then band-pass filters 0.7–4 Hz (42–240 BPM), finds the strongest frequency in a 10 s window, and measures the **SNR** (how much the pulse stands out from noise). A result counts only when 5 estimates in a row agree within ±3 BPM and the SNR is above the minimum: that is the "stable reading".

### Face embeddings
A neural network (MobileFaceNet) turns an aligned 112×112 face crop into 192 numbers. Two photos of the same person give similar numbers (high **cosine similarity**), different people give lower values. We store numbers, not pictures, and they are encrypted at rest. Scores from one model can't be compared with another's, so the model version is part of every payload.

### Public-key signatures (ECDSA P-256)
The phone has a private key that signs, and the backend has the matching public key that verifies. Changing a single byte of the payload breaks the signature.

### Hardware-backed keys (StrongBox / Titan M2, TEE)
On a Pixel the private key is created inside the Titan M2 chip and never leaves it, even if the phone's software is compromised. The app reports where its key lives (StrongBox, TEE or software), and the portal shows it.

### Hash-chained ledger, DIDs, credentials
Each event (registration, certificate, freeze, restore) is added to an **append-only log** in which every entry includes the hash of the previous one. Changing any old entry breaks the chain, and **Verify chain integrity** on the portal detects it. Pensioners get a `did:key` identifier derived from their device key, and each certificate is issued as a **signed credential** (W3C Verifiable Credential shape) that anyone can check. The ledger is local, and designed to be anchored on a public blockchain later.

### WebSockets
A long-lived connection lets the backend push each step to the portal the moment it happens, which is why the laptop updates live while the phone scans.

**Further reading:**
- [MDN WebSockets API](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API)
- [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/)
- [Android Keystore](https://developer.android.com/training/articles/keystore)
- [Python `cryptography`: elliptic curves](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ec/)
- [Photoplethysmogram (overview)](https://en.wikipedia.org/wiki/Photoplethysmogram)

---

## 6. What it does not do (be honest in the presentation)

- **Screen-replay detection** (moiré, screen borders) is not implemented. A video is stopped by the random challenge, but a *live* deepfake that follows the prompt and carries a pulse-like colour signal is out of scope.
- **The thresholds are placeholders** until calibrated on our own scans: `MIN_SNR_DB`, and the face bands `FACE_T_HIGH`/`FACE_T_LOW`/`FACE_ANCHOR_MIN`. Use `scripts/calibrate_thresholds.py`. Don't lower `MIN_SNR_DB` without measurements: it also makes photos easier to pass.
- **rPPG depends on light, camera and skin tone.** Poor conditions lead to "no pulse" or officer review, not to a false pass.
- **The key type is reported by the app.** Checking the Android key-attestation chain against Google's root is future work.
- **Identity at registration** rests on the officer's in-person ID check. DigiLocker or the Aadhaar Secure QR code is the production path.
- **The face model's training data** is not documented by its source (see `../MODEL_INFO.md`). Confirm it, or retrain, before any production use.

---

## 7. Try it

```powershell
cd backend
.\venv\Scripts\Activate.ps1
python run.py                    # 0.0.0.0:8000; prints the address the phone will use
python scripts/demo_check.py     # runs the five demo scenarios end to end (simulated phone)
```

Open http://localhost:8000/docs for the interactive API, and the portal (`npm run dev` in the repo root) at http://localhost:5173.
