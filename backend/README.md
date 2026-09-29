# Jeevan Suraksha Backend (FastAPI)

Backend for the pension life-certificate system built on the IoB liveness engine. It creates QR sessions, verifies payloads signed inside the phone's **Titan M2** (Android StrongBox, ECDSA P-256 / SHA-256), checks liveness, the random challenge and a 1:1 face match, stores pensioner records, runs the officer review queue, writes a hash-chained audit ledger, and pushes live results to the portal over WebSocket.

## Architecture

```
Portal (laptop) ◄──WebSocket── FastAPI backend ◄──HTTP── Phone app (Pixel 7)
   │ 1. POST /sessions → QR {base_url, session_id, purpose, nonce, challenge}
   │ 2. WS /ws/{session_id}                     3. phone scans QR, runs rPPG + challenge + face
   │                                            4. POST /auth/verify (Titan M2-signed payload)
   │ 5. WS push: CERTIFICATE_ISSUED / UNDER_REVIEW / REJECTED / ENROLLMENT_CAPTURED
```

## Project structure

```text
backend/
├── app/
│   ├── main.py                    # App entrypoint: DB init, demo officer seed, maintenance task
│   ├── core/
│   │   ├── config.py              # Settings from .env (thresholds, keys, URLs)
│   │   ├── deps.py                # DB session + officer-auth dependencies
│   │   └── security.py            # Password hashing, officer tokens, Fernet template cipher
│   ├── db/
│   │   ├── database.py            # Engine (SQLite by default), init_db, get_db
│   │   ├── models.py              # Tables: officers, pensioners, biometric_templates, devices,
│   │   │                          #         life_certificates, auth_sessions, audit_ledger
│   │   └── types.py               # UTC datetime column type
│   ├── routers/
│   │   ├── health.py  session.py  auth.py  ws.py
│   │   ├── officers.py            # Demo officer login
│   │   ├── pensioners.py          # Registration details, records, public status lookup
│   │   ├── enroll.py              # Officer approves a captured registration
│   │   └── reviews.py             # Review queue for borderline certificates
│   ├── schemas/                   # auth.py (signed payload), session.py, pensioner.py, health.py
│   └── services/
│       ├── verification.py        # The ordered verification pipeline (§5.2)
│       ├── face_match.py          # Cosine, three-band decision, template update, encryption
│       ├── liveness.py            # BPM / SNR / liveness checks
│       ├── session.py             # DB-backed sessions, QR payload, challenge, base URL
│       ├── pensioners.py          # ACTIVE / FROZEN rules (repeated failures, deadline)
│       ├── ledger.py              # LedgerBackend interface + local hash chain
│       ├── crypto.py              # ECDSA verification, key helpers
│       ├── connection_manager.py  # WebSocket channels (per session + officer events)
│       └── score_log.py           # Face-match scores for threshold calibration
├── scripts/
│   ├── calibrate_thresholds.py    # Label genuine/impostor scores → suggest thresholds
│   ├── simulate_phone.py          # Dev tool: acts as the phone (software key)
│   └── seed_demo.py               # Fictional demo pensioners
├── tests/                         # pytest suite (pipeline, face match, scripts)
├── data/                          # (gitignored) SQLite DB, dev keys, score log
├── .env.example  requirements.txt  requirements-dev.txt
```

## API endpoints

All paths are under `/api/v1`. 🔒 = officer token required (`Authorization: Bearer <token>`).

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` (root) | API overview |
| `GET` | `/health` | Health check |
| `POST` | `/sessions` | Create a session. Body `{purpose, pensioner_id \| ppo_number, consent}`; empty body = legacy AUTH. Returns `qr_payload` (base URL, session, purpose, nonce, challenge). ENROLLMENT is 🔒. |
| `GET` | `/sessions/{id}` | Session status and result (polling fallback) |
| `DELETE` | `/sessions/{id}` | Expire a session |
| `POST` | `/auth/verify` | Verify a signed payload (the full pipeline) |
| `POST` | `/officers/login` | Demo officer login → token |
| `GET` | `/officers/me` 🔒 | Current officer |
| `POST` | `/pensioners` 🔒 | Enter a pensioner's details (starts as `PENDING_ENROLLMENT`) |
| `GET` | `/pensioners` 🔒 | List/search (`q`, `status`) |
| `GET` | `/pensioners/{id}` 🔒 | Detail: device key type, template info, certificate history |
| `GET` | `/pensioners/lookup?ppo_number=` | Public status check by pension ID |
| `POST` | `/enroll/complete` 🔒 | Approve a captured registration → `ACTIVE` |
| `GET` | `/reviews` 🔒 | Certificates under review |
| `POST` | `/reviews/{certificate_id}/decision` 🔒 | `{decision: APPROVE\|REJECT, reason}` |
| `WS` | `/ws/{session_id}` | Portal: live events for one session |
| `WS` | `/ws/events?token=` 🔒 | Officer dashboards: all events |
| `WS` | `/ws/telemetry/{session_id}?nonce=` | Phone → portal scan progress (relayed) |
| `WS` | `/ws/telemetry` | Legacy phone telemetry (log only) |

Ledger, DID, credentials and treasury endpoints arrive in Milestone 6.

## WebSocket events

| Event | Direction | When |
|-------|-----------|------|
| `CONNECTED` | Server → Client | Connection established (includes current status) |
| `SCAN_STARTED`, `MEASURING`, `STABLE_READING` | Phone → Server → Portal | Live scan progress (bpm, snr, progress) |
| `CHALLENGE_ISSUED`, `CHALLENGE_PASSED`, `CHALLENGE_FAILED` | Phone → Server → Portal | Random challenge progress |
| `FACE_LOST`, `MULTIPLE_FACES` | Phone → Server → Portal | Scan problems |
| `ENROLLMENT_CAPTURED` | Server → Portal | Registration scan accepted, awaiting officer approval |
| `ENROLLMENT_APPROVED` | Server → Portal | Officer approved; pensioner is ACTIVE |
| `CERTIFICATE_ISSUED` | Server → Portal | Life certificate issued (score, ledger hash) |
| `UNDER_REVIEW` | Server → Portal | Borderline; sent to the officer review queue |
| `REJECTED` | Server → Portal | Failed, with `reason_code` and `reason` |
| `STATUS_CHANGED` | Server → Portal | Pension frozen after repeated failures |
| `ACCESS_GRANTED` | Server → Portal | Legacy AUTH flow succeeded |
| `STATUS` / `pong` | Server → Client | Replies to `status` / `ping` |

Rejection reason codes: `NO_PULSE`, `CHALLENGE_FAILED`, `CHALLENGE_MISMATCH`, `FACE_MISMATCH`, `DEVICE_MISMATCH`, `DEVICE_NOT_REGISTERED`, `CONSENT_MISSING`, `STALE_PAYLOAD`, `MODEL_MISMATCH`, `INVALID_EMBEDDING`, `INVALID_TEMPLATE`, `ALREADY_REGISTERED`, `SESSION_EXPIRED`, `SESSION_ALREADY_USED`, `NONCE_MISMATCH`, `PURPOSE_MISMATCH`, `INVALID_SIGNATURE`, `INVALID_PAYLOAD`, `INTERNAL_ERROR`.

## Verification pipeline (`POST /auth/verify`)

Fail fast, in this order (details in `app/services/verification.py`):

1. ECDSA-SHA256 signature over the exact payload bytes, P-256 key.
2. Payload parses into the schema.
3. Session exists, purpose matches, nonce matches, not expired, then **claimed atomically** (one use).
4. Device binding: LIFE_CERTIFICATE must use the key registered for that pensioner; ENROLLMENT registers the key (activated when the officer approves).
5. Timestamp freshness (±`TIMESTAMP_MAX_SKEW_SECONDS`) and consent recorded.
6. Liveness: BPM range, SNR ≥ `MIN_SNR_DB`, `liveness_passed`.
7. Challenge matches the one issued and was passed.
8. Face match (LIFE_CERTIFICATE): 1:1 cosine against this pensioner's `current_template` **and** `anchor_template`.
9. Three-band decision → certificate record, pension status, template update, ledger entry, WebSocket push.

**Three bands:** score ≥ `FACE_T_HIGH` (and ≥ `FACE_ANCHOR_MIN` vs the anchor) → issued; `FACE_T_LOW` ≤ score < `FACE_T_HIGH` → review; below `FACE_T_LOW` → rejected. A frozen pension is only released by an officer.

**Template update:** only after an automatic approval ≥ `FACE_T_HIGH`. `current_template` becomes a weighted blend (`TEMPLATE_BLEND_ALPHA`) and is L2-normalised; the result must stay ≥ `FACE_ANCHOR_MIN` from the anchor. `anchor_template` is never overwritten.

The legacy AUTH login flow (original app payload) still works, now accepting a decimal BPM.

## Setup and running

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1          # macOS/Linux: source venv/bin/activate
pip install -r requirements-dev.txt
copy .env.example .env               # then edit as needed
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- Swagger UI: http://localhost:8000/docs
- Demo officer: `officer` / `officer123` (set in `.env`)
- Optional fictional demo data: `python scripts/seed_demo.py`

`--host 0.0.0.0` lets a phone on the same Wi-Fi reach the laptop. The QR code carries the laptop's LAN IP automatically, or `PUBLIC_BASE_URL` if set (e.g. a `cloudflared` tunnel URL). Over USB, `adb reverse tcp:8000 tcp:8000` also works.

## Testing

```powershell
cd backend
.\venv\Scripts\python -m pytest -q
```

The suite simulates the phone (software P-256 key signing the same way the app does) and synthetic face embeddings, and covers every pipeline branch, the three bands, template drift, freezing, the review queue, the ledger and WebSockets.

**Without a phone:** `scripts/simulate_phone.py --qr '<qr json>' --person A` acts as the app (add `--person B`, `--no-pulse`, `--challenge-fail` or `--similarity 0.6` for the other outcomes). It signs with a software key and reports `SOFTWARE`, so it's never mistaken for the real device.

## Calibrating thresholds

The face-match and SNR values in `.env.example` are **placeholders**. Calibrate them on our own scans:

```powershell
python scripts/calibrate_thresholds.py label --last 10 --as genuine   # after 10 genuine scans
python scripts/calibrate_thresholds.py label --last 10 --as impostor  # after 10 impostor scans
python scripts/calibrate_thresholds.py report                         # suggests FACE_T_LOW / FACE_T_HIGH
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | dev value | Signs officer tokens. Change for any shared deployment. |
| `TEMPLATE_KEY` | auto (dev) | Fernet key encrypting face templates at rest |
| `DATABASE_URL` | `sqlite:///data/iob.db` | Any SQLAlchemy URL |
| `PUBLIC_BASE_URL` | auto (LAN IP) | Backend URL put into QR codes |
| `SESSION_EXPIRY_SECONDS` | `300` | QR/session lifetime |
| `TIMESTAMP_MAX_SKEW_SECONDS` | `120` | Allowed phone-clock difference |
| `CHALLENGE_TIMEOUT_SECONDS` | `8` | Time the app allows for the challenge |
| `BPM_MIN` / `BPM_MAX` | `40` / `220` | Plausible heart-rate range |
| `MIN_SNR_DB` | `3.0` (placeholder) | Minimum rPPG SNR |
| `FACE_T_HIGH` / `FACE_T_LOW` | `0.70` / `0.50` (placeholders) | Three-band thresholds |
| `FACE_ANCHOR_MIN` | `0.55` (placeholder) | Minimum similarity to the anchor template |
| `TEMPLATE_BLEND_ALPHA` | `0.10` | Weight of a new scan in the template update |
| `MAX_FAILED_ATTEMPTS` | `3` | Failures before a pension is frozen |
| `CERTIFICATE_DEADLINE` | `11-30` | Yearly deadline (MM-DD) before freezing |
| `BACKEND_CORS_ORIGINS` | `localhost:3000,5173` | Allowed portal origins |

## Privacy

- No face images are stored or accepted. Face templates are Fernet-encrypted at rest.
- No Aadhaar numbers. Only the last 4 digits of the bank account. Demo data is fictional.
- The audit ledger stores hashes only.
- Consent is required when the portal creates a life-certificate session and in every signed payload.

## Known limitations

- rPPG accuracy varies with lighting, skin tone and age; borderline cases fall back to officer review.
- Registration relies on an officer checking physical ID; DigiLocker or the Aadhaar Secure QR code is the production path for ID authenticity.
- The key security level (StrongBox/TEE) is reported by the app; verifying the Android key attestation chain against Google's root is future work.
- The ledger is a local hash chain, designed to be anchored on a real blockchain (Milestone 6).
- Repeated failed attempts freeze a pension by design, so someone who knows a pension ID and has the registered phone could trigger a freeze; an officer can restore it through the review queue.
