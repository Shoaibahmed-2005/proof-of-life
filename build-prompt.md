# Build Prompt: Pension Life-Certificate System on the IoB Liveness Engine

You are working on an existing project. Read everything below before touching any code.

---

## STEP 0: Analyse first, build nothing yet

Before writing or changing any code:

1. **Start with the Graphify knowledge graph of the backend.** It's in the **`.graphify/` folder at the repo root** (`sih-iob/.graphify/`). Read `GRAPH_REPORT.md` first, then use `graph.json` to map the backend's modules, how they connect, and the main call paths before reading the code.
   - The graph covers **only the `backend/` folder** (the existing engine logic). It's a map, not a replacement: still read the backend code to confirm details.
   - The Android app and the frontend have no graph, so read their code in full.
   - If the graph and the code disagree, trust the code and note the difference in `ANALYSIS.md`.
   - Don't edit anything inside `.graphify/` or any `.engram/` folder (including `backend/app/.engram/cache/`); those are tool metadata.

   **Repo layout** (confirm each item and correct it in `ANALYSIS.md` if I'm wrong):
   - `backend/`: FastAPI backend (the Graphify graph covers this). Code is in `backend/app/` with `core/`, `db/`, `routers/`, `schemas/` and `services/` as described in the README, plus an **`api/` folder that the README doesn't mention**. Check whether `api/` duplicates `routers/` or is an older version, and state which one the running app actually uses before adding endpoints.
   - Root Gradle project (`build.gradle.kts`, `settings.gradle.kts`, `gradlew`) with the **`app/`** module: the Android app.
   - `SentinelHard/`: check what this is (another Android module, the app itself, or an old copy) and which one is actually built and installed on the phone.
   - `sdk/`: check what it contains and whether the app depends on it.
   - `src/`, `index.html`, `vite.config.js`, `package.json` at the root: the Vite web frontend.
   - `backend.zip`: a backup. Don't read, modify or build from it.
2. Read the **entire codebase**: the FastAPI backend, the Android app (the "SentinelHard" Android Studio / Gradle project), and any web frontend.
3. Read **every `.md` file** in the repo (README, EXPLAINER, **DESIGN.md** and any others), and look at `docs/design-reference.jpeg`.
4. Write `ANALYSIS.md` in the repo root covering:
   - What exists and works today, component by component (backend, Android app, frontend).
   - The exact current flow: laptop shows a QR code → phone app scans it with the rear camera → front camera opens → rPPG pulse check → Titan M2 signs the payload → backend verifies → WebSocket pushes `ACCESS_GRANTED`.
   - How the rPPG engine works (language, libraries, signal processing, window size, filtering, how BPM and SNR are computed).
   - How the payload is built and signed (fields, key alias, StrongBox usage) and how the backend verifies it.
   - How the app finds the backend (hard-coded IP / localhost?) and how it is built and installed.
   - Gaps, bugs and risks you notice, especially in the rPPG signal pipeline (see Known Issues below).
   - A step-by-step build plan mapped to the milestones in this prompt, with the files you will create or change.
5. **Stop and wait for my approval of `ANALYSIS.md` before building anything.**

Whenever you change the backend's structure, tell me so I can regenerate the Graphify graph. Don't rely on an outdated graph for later milestones.

Rules for the whole task:
- Do not break the flow that works today. Extend it.
- Work milestone by milestone. After each one, make sure it runs end to end and summarise what changed.
- Ask me before deleting files, changing the signing scheme, or adding heavy dependencies.

---

## 1. Context

- **Hackathon:** Smart India Hackathon 2026, problem statement **SIH26125**, Bharat Electronics Limited: *Blockchain-Based Secure Platform for Identity, Access Control, and Digital Asset Management* (theme: Blockchain & Cybersecurity).
- **Existing engine:** hardware-bound, liveness-verified authentication. The phone measures pulse from the face with the camera (rPPG), and the payload is signed inside the Pixel 7's **Titan M2** chip (Android StrongBox, ECDSA P-256 / SHA-256). The FastAPI backend verifies the signature, checks BPM plausibility, timestamp freshness and session state, then pushes `ACCESS_GRANTED` to the browser over a WebSocket.
- **Use case we are building:** **annual life certificates for pensioners**, framed for **defence pensioners**. Every pensioner must prove each year that they are alive so their pension continues. Fraud happens when a pension keeps being paid after death using photos or videos of the pensioner. Our system proves (a) the person is **alive** (heartbeat), (b) they are **the registered pensioner** (face match), and (c) the proof came from **a real, genuine device** (hardware signature).

---

## 2. Architecture (final decision)

Keep all three parts, with these responsibilities:

| Part | Role |
|---|---|
| **Web portal (laptop)** | The professional government-style portal. Almost all UI lives here. Shows QR codes and live status. Does no biometric processing. |
| **Android app (phone)** | A thin, clean scanner app: scan QR → consent → guided face scan → result. All biometric processing and signing happen here, natively. |
| **FastAPI backend** | Sessions, verification, pensioner records, face-match decision, review queue, pension status, audit ledger, WebSocket push. |

Do **not** move rPPG or face matching into the browser. Native processing is needed for camera control, rPPG accuracy, and Titan M2 signing.

---

## 3. User flows

### 3.1 Officer-assisted registration (once per pensioner)
There is **no ID-card photo matching**. Identity is anchored by an officer, like HR supervising face registration in an office attendance system.

1. The officer logs into the portal and opens **Register Pensioner**.
2. The officer enters the pensioner's details (name, pension ID / PPO number, service number, bank account last 4 digits, etc.) after checking their physical ID in person. Use **dummy data** for the demo; never collect or store Aadhaar numbers.
3. The portal creates a session with `purpose = ENROLLMENT` and shows a QR code.
4. The pensioner scans it with the app. The front-camera scan runs **liveness + face embedding on the same tracked face**.
5. On a live pass, the app builds the **reference template**: take the best 10–20 frames from the scan window (frontal pose, sharp, well lit, large enough face), average their embeddings, and L2-normalise. It sends this template in the signed payload.
6. The backend stores the template (encrypted) together with the device's **public key**, which binds the pensioner to that hardware key. The officer clicks **Approve** to complete registration.
7. The portal shows the new pensioner as **Active**.

### 3.2 Annual life certificate (at home)
1. The pensioner opens the portal (or an assisted kiosk page), enters their pension ID and clicks **Submit Life Certificate**.
2. The portal creates a session with `purpose = LIFE_CERTIFICATE` and shows a QR code.
3. The pensioner scans it. The app runs the continuous scan: rPPG + random challenge + face embedding, all on the same tracked face.
4. The signed payload goes to the backend. It runs the verification pipeline (section 5.2) and does a **1:1 comparison** against *that pensioner's* stored template only. Never search the whole database.
5. Three outcomes:
   - **Strong match + live:** certificate issued, pension stays **Active**, and the stored template is updated (section 5.4).
   - **Borderline score:** goes to the officer **Review Queue**, e.g. for ageing, lighting or pose issues.
   - **Clear mismatch or failed liveness:** rejected. After repeated failures, or no certificate by the deadline, the pension status becomes **Frozen**. It is frozen, never cancelled, until resolved.
6. The portal updates live over the WebSocket, e.g. "Life certificate issued for 2026". Judges watch the laptop screen, so the portal must react clearly.

### 3.3 Demo scenarios (must all work)
1. Team member A registers through the officer screen → **Active**.
2. A submits a life certificate → **Approved**, certificate issued.
3. Team member B tries to submit as A → **Rejected: face does not match**.
4. Someone holds up a **photo** of A → **Rejected: no pulse detected**.
5. Someone plays a **video** of A on another screen → **Rejected: challenge failed** (it can't respond to the random prompt) and/or screen replay detected.

---

## 4. Android app changes

### 4.1 Known issues in the current rPPG engine (fix these)
From a screen recording of the current app:
- While sitting still, BPM climbs 72 → 95 → 98 → 99 → 99.5 over about 4 seconds. The estimate has not converged.
- "VERIFIED HUMAN" is shown in the first second, before any stable reading exists.
- The SNR shows exactly **2.8 dB in every frame**, so it is either not updating or computed once. 2.8 dB is also low.
- The waveform looks jagged, like noise, rather than a smooth pulse.

Required fixes:
- Band-pass filter the signal to the physiological range, about **0.7–4 Hz (42–240 BPM)**, and detrend before estimating.
- Use an analysis window of about **8–10 seconds**.
- Show **"Measuring…"** until the BPM is stable (e.g. varies by less than ±3 BPM over the last few estimates), then decide.
- Compute SNR live on every estimate, and require a **minimum SNR** to pass. Make the threshold configurable and calibrate it.
- Show the smoothed, filtered waveform.

### 4.2 Face detection, matching and the "same face" rule
- Add face detection with **MediaPipe Face Detection/Face Mesh or ML Kit**. Draw a box around the **whole face**.
- Take the rPPG skin area (forehead / cheeks) from **inside that same tracked face box**, so pulse and identity always come from the same face.
- **Reject the attempt if more than one face** appears in the frame at any point.
- Add face embeddings with a **MobileFaceNet or ArcFace-family model in TensorFlow Lite** (e.g. an InsightFace mobile model). Compute an embedding every few frames, not every frame.
- Use the same model for registration and verification. Embeddings from different models are not comparable.
- Do **not** use face-api.js.

### 4.3 Anti-replay: random challenge
rPPG alone stops photos, but a video of the real person on another screen can still carry a pulse. Add:
- **Random challenge:** partway through the scan, prompt a randomly chosen action (blink twice, turn head left, or turn head right) and verify it with face landmarks within a time limit. The backend generates the challenge and includes it in the session/QR, so it can't be predicted. Include the challenge ID and result in the signed payload.
- **Optional, if time allows:** screen-replay detection (moiré patterns, screen borders, glare).

### 4.4 Signed payload
Extend the payload signed inside Titan M2 (StrongBox) to:

```
{ session_id, purpose, nonce, timestamp, device_id,
  bpm, snr, liveness_passed, challenge_id, challenge_passed,
  face_embedding (or reference template for ENROLLMENT),
  frames_used, app_version }
```

- Keep ECDSA P-256 / SHA-256. If StrongBox is unavailable on a device, fall back to a TEE-backed key and record which one was used in the payload.
- Delete raw frames right after processing. Never save or upload face images.

### 4.5 QR code and connectivity
- The QR code must contain the **backend base URL**, the `session_id`, the `purpose`, the challenge and a nonce. The app reads the backend address from the QR, so **nothing is hard-coded and no rebuild is needed** when the network or laptop changes.
- Document how to reach the laptop backend: `adb reverse tcp:8000 tcp:8000` over USB, the laptop's LAN IP, or a `cloudflared` tunnel.

### 4.6 App UI (clean, simple, elderly-friendly)
Only four screens: **Scan QR → Consent → Face Scan → Result**.
- Large text, high contrast, a clear guide circle around the face, a progress indicator, and plain-language prompts ("Hold still", "Blink twice now").
- Show live BPM and waveform, but only mark success after the stable reading plus challenge.
- The result screen shows approved, under review or rejected, with the reason.

### 4.7 Build without Android Studio
- Make the app buildable and installable from the terminal: `./gradlew assembleDebug` and `./gradlew installDebug`.
- Add a short `ANDROID_BUILD.md` covering building, installing the APK, and connecting to the backend.

---

## 5. Backend (FastAPI) changes

### 5.1 Data model
Use SQLite with SQLModel/SQLAlchemy (swappable later). Tables:
- **pensioners:** id, name, pension ID / PPO number, service number, bank account last 4 digits, status (`ACTIVE` / `FROZEN` / `PENDING_ENROLLMENT`), registered_by (officer), created_at.
- **biometric_templates:** pensioner_id, `anchor_template` (encrypted, from registration, never overwritten), `current_template` (encrypted, updated over time), model_version, updated_at.
- **devices:** pensioner_id, public key (PEM), key type (StrongBox / TEE), registered_at.
- **life_certificates:** pensioner_id, year, status (`ISSUED` / `UNDER_REVIEW` / `REJECTED`), match score, BPM, SNR, challenge result, timestamp, reviewer, reason.
- **officers:** simple login for the demo.
- **audit_ledger:** see section 5.5.

Encrypt templates at rest (e.g. Fernet with a key from `.env`). Store no face images and no Aadhaar data.

### 5.2 Verification pipeline (`POST /api/v1/auth/verify`)
Fail fast, in this order:
1. The signature is valid (ECDSA-SHA256) and the public key matches the device registered for that pensioner. For `ENROLLMENT`, the key is registered at this step.
2. The payload parses into the schema.
3. The session exists, is `PENDING`, has the right purpose, is not expired, and has the matching nonce. Each nonce and session can be used **only once** (replay protection).
4. Timestamp freshness.
5. Liveness: BPM in the plausible range, SNR above the minimum, `liveness_passed` true.
6. Challenge: matches the one issued for this session and was passed.
7. Face match (`LIFE_CERTIFICATE` only): cosine similarity against the pensioner's `current_template`, and also check against `anchor_template`.
8. Decide, update state, write the ledger entry, and push the result over the WebSocket.

### 5.3 Three-band decision
- `score ≥ T_high` → **approve**
- `T_low ≤ score < T_high` → **review queue**
- `score < T_low` → **reject**

Thresholds must be **configurable in `.env` and calibrated on our own test scans**. Do not copy numbers from the internet. Add a small calibration script that logs scores from genuine and impostor attempts, so we can pick the thresholds.

### 5.4 Template update (handles ageing)
- Only after an approval **above `T_high`**, update `current_template` as a weighted blend of the old template and the new scan's embedding, then L2-normalise.
- Never update after a borderline or reviewed pass.
- Never overwrite `anchor_template`. Also require a minimum similarity to the anchor, so the template can't be slowly shifted to another person over several years.

### 5.5 Blockchain / ledger layer (for SIH26125)
Keep this lightweight and behind a clean interface so it can be swapped for a real chain.
- **Decentralized identity:** derive a `did:key` identifier from each pensioner's device public key.
- **Verifiable credential:** each issued life certificate becomes a signed credential (backend-signed JSON) tied to the pensioner's DID.
- **Ledger:** record only **hashes** of credentials, registrations and status changes, never personal data. Start with a local **append-only hash-chained ledger** in the database (each entry includes the previous entry's hash), with a `verify_chain` endpoint. Make it easy to later anchor these hashes on Hyperledger Fabric or a Polygon testnet.
- **Asset / access control:** treat the pension entitlement as an asset owned by the pensioner's DID. It is released only if a valid life certificate exists for the current year, and otherwise frozen.

### 5.6 Endpoints to add
- `POST /api/v1/sessions`: add `purpose`, `pensioner_id`, challenge and nonce; return the full QR payload including the backend URL.
- `POST /api/v1/enroll/complete`: officer approves a registration.
- `GET /api/v1/pensioners`, `GET /api/v1/pensioners/{id}`
- `GET /api/v1/reviews`, `POST /api/v1/reviews/{id}/decision`
- `GET /api/v1/treasury/summary`: counts and amounts released vs frozen.
- `GET /api/v1/ledger`, `GET /api/v1/ledger/verify`
- `POST /api/v1/officers/login`: simple demo auth.
- WebSocket events: add `MEASURING`, `CHALLENGE_ISSUED`, `CERTIFICATE_ISSUED`, `UNDER_REVIEW`, `REJECTED` (with reason), `ENROLLMENT_CAPTURED`.

Keep existing endpoints working, and update the README tables.

---

## 6. Web portal (laptop)

Build a **professional, government-style portal**. Use the existing React frontend if there is one; otherwise React + Vite.

**Follow `DESIGN.md` (repo root) for all visual design**: colours, fonts, page shell, component library and page layouts. It applies to **every page** and to the Android app's screens, not just the landing page. The reference image it mentions is at `docs/design-reference.jpeg`; use it for style only and never copy its logos, text or images. Build the theme and shared components first, then the pages.

- **Branding:** use a **fictional portal name and logo** (e.g. "Jeevan Suraksha – Pension Life Certificate Portal"). **Do not use real government emblems, the State Emblem of India, or official logos**, because their use is legally restricted. It must work on a laptop screen at a distance for judges.
- **Pages:**
  1. **Home:** what the system does, with two entry points: Pensioner and Officer.
  2. **Pensioner – Submit Life Certificate:** enter pension ID → QR code → live status steps (Waiting for scan → Measuring pulse → Challenge → Face match → Result) driven by WebSocket events → certificate view with the ledger hash.
  3. **Officer – Register Pensioner:** details form → QR code → live capture status → Approve.
  4. **Officer – Review Queue:** borderline cases with score, BPM, SNR and challenge result, plus Approve/Reject with a reason.
  5. **Pensioner Records:** list and detail view with status and certificate history.
  6. **Treasury Dashboard:** pensions released vs frozen, certificates this year, and rejected attempts by reason (no pulse, face mismatch, challenge failed).
  7. **Audit Ledger:** hash-chained entries with a "Verify chain integrity" button.
- **Language:** English first. Add Hindi labels if time allows.
- **Accessibility:** large type, good contrast, keyboard navigable.
- **Privacy:** show a consent notice before any scan starts.

---

## 7. Privacy, safety and honesty

- Store only encrypted face templates. No images, no Aadhaar numbers. Use dummy pensioner data.
- Record consent for each scan.
- In the README and pitch notes, state the known limitations honestly:
  - rPPG accuracy varies with lighting, skin tone and age; there is a review fallback.
  - Registration relies on officer verification; DigiLocker or the Aadhaar Secure QR code are the production path for ID authenticity.
  - The ledger is a local hash chain that can be anchored on a real blockchain.

---

## 8. Milestones (in order)

1. `ANALYSIS.md`, then **wait for approval**.
2. rPPG fixes (filtering, window, stability gate, live SNR) + terminal build + QR-carried backend URL.
3. Face detection + shared face box + single-face rule + embeddings + template averaging.
4. Random challenge + extended signed payload.
5. Backend data model, verification pipeline, three-band decision, template update, calibration script.
6. Ledger / DID / credential layer.
7. Web portal (all pages) wired to the backend and WebSocket.
8. Run all five demo scenarios end to end; update README, EXPLAINER and ANDROID_BUILD.md; write `DEMO_SCRIPT.md` with the exact steps to present.

After each milestone, report what works, what doesn't, and anything I need to test on the phone.
