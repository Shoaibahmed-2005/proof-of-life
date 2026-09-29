# ANALYSIS.md: Current Codebase Record

## ▶ RESUME HERE (for a new agent or chat)

**Status (2026-09-30): all milestones (M2–M8) are built and pushed.** The remaining work is the teammate's phone test round (`TESTING_CHECKLIST.md`, "One combined test run"), then calibrating the thresholds from those measurements, then fixing whatever that round finds. The Android code (commits 82bfbd2, 084af5b, 4089473, 4125eea) has **not been compiled yet**. If the build fails, see `TESTING_CHECKLIST.md` section B.

**Current plan (tick = committed and pushed):**
- [x] **1. Wi-Fi fix.** `backend/run.py` (0.0.0.0), adapter-aware QR address (`app/core/network.py`), startup banner + LAN self-check, LAN CORS, `vite --host`, a network security config, app error reasons, and Wi-Fi setup docs.
- [x] **2. Scan-speed diagnostics.** On-screen diagnostics toggle (off by default), `SentinelDiag` logcat, per-scan summary stored by the backend, 30 fps request, AE/AWB lock, poor-conditions guidance, a scan-speed comparison test. Also: gate parameters come from the backend `.env` via the QR code, and face-loss tolerance is relaxed (it was 1 s, a likely cause of scans never finishing).
- [x] **3. M7 portal**, finished from the uncommitted files in `src/` (Hindi labels to be checked by a native speaker).
- [x] **4. M3:** face box, one-face rule, embeddings (the model download was **approved**: `mobilefacenet.tflite` from hugocornellier/face_detection_tflite, Apache-2.0; LiteRT `com.google.ai.edge.litert:litert:1.4.2`), template averaging.
- [x] **5. M4:** random challenge, extended signed payload, 4 app screens per DESIGN.md.
- [x] **6. M8:** docs, `DEMO_SCRIPT.md`, end-to-end run with the simulator (`backend/scripts/demo_check.py`: all checks pass), and one combined `TESTING_CHECKLIST.md`.

**Final deliverable to the user:** one summary covering what was built, what was verified here, the combined test list, which commit to check first if the Android build fails, and how to read the diagnostics (camera vs lighting vs thresholds). The user said: don't lower `MIN_SNR_DB` without real measurements.

**Read first:**
- `build-prompt.md` (the brief) and `DESIGN.md` (the visual rules). Re-read the relevant sections before each milestone.
- §11 below (the change log: what each milestone built).
- `.graphify/GRAPH_REPORT.md` (backend map, regenerated after M8). It covers `backend/` only.

**Working rules the user set:**
- (Current run) Don't stop between steps. Commit + push per step, and update this section after each commit.
- Commit and push to `origin master` (https://github.com/danishjk2156/SentinelHard.git) after each milestone. The teammate pulls from there.
- **No Android toolchain on this laptop.** Kotlin can't be compiled here. The teammate builds in Android Studio; see `TESTING_CHECKLIST.md`. The C++ engine *is* compiled and tested here with zig (`python tools/rppg/run_tests.py`).
- Ask before deleting files, changing the signing scheme, adding heavy dependencies, or downloading files. (The M3 model download is already approved; see the plan above.)
- Don't hand-edit `.graphify/` or `.engram/`. Regenerate the graph with the graphify skill after backend structure changes.

**How to run and test:**
- **Backend:** `cd backend; .\venv\Scripts\python -m pytest -q` (72 tests). Serve with `python run.py` (0.0.0.0:8000; prints the phone address). The demo officer is `officer` / `officer123`.
- **Without a phone:** `backend/scripts/simulate_phone.py --qr '<qr json>' --person A` (options: `--no-pulse`, `--challenge-fail`, `--multiple-faces`, `--person B`, `--similarity 0.6`). With the backend running, `backend/scripts/demo_check.py` runs all five demo scenarios.
- **Clean demo:** `backend/scripts/reset_demo.py --yes --seed`.
- **Portal:** `npm run dev` (http://localhost:5173) and `npx vite build`.
- **Browser preview:** `.claude/launch.json` has `backend` and `portal` configs.

_Written 2026-09-29 for Step 0 of `build-prompt.md`. This file is the record of the codebase and is updated whenever the structure changes._

Sources read: `.graphify/GRAPH_REPORT.md` and `graph.json` (backend map), every file in `backend/app/`, the whole Android `app/` module (Kotlin, C++, Gradle, manifest, resources), the Vite frontend (`src/`, `index.html`, `vite.config.js`, `package.json`), every `.md` file in the repo (`build-prompt.md`, `DESIGN.md`, `backend/README.md`, `backend/EXPLAINER.md`, the 10 files under `.artifacts/`), and `docs/design-reference.jpeg`.

Sections 0–7 describe the codebase **as it was at Step 0**. Section 11 (the change log) records what each milestone changed, and is the place to look for the current state.

---

## 0. Headline findings (read these first)

1. **On paper, today's phone → backend flow can't reach `ACCESS_GRANTED`.** It fails for two independent reasons:
   - The backend schema declares `bpm: int` ([backend/app/schemas/auth.py:19](backend/app/schemas/auth.py:19)), but the app sends a fractional `Double` from the Kalman filter, such as 72.4. Pydantic v2 rejects that. I reproduced this locally: `Input should be a valid integer, got a number with a fractional part`. The phone therefore gets `ACCESS_DENIED: Invalid payload format`.
   - Even with that fixed, the backend requires `snr ≥ 3.5` ([liveness.py:55](backend/app/services/liveness.py:55)). The app's "SNR" is a linear peak ratio that shows about 2.8 in your recording, so it would be rejected with "Signal quality insufficient".
   - The app also posts to `http://10.0.2.2:8080`, the **Android emulator's** alias for the host. That address doesn't exist on a physical Pixel.

   **Question for you:** have you seen a real `ACCESS_GRANTED` from the phone? If so, the APK on the phone was probably built from a teammate's local copy with a different IP and schema (the `.artifacts/` paths point at `C:/Users/praji/...`), not from this repo. "Don't break the flow that works today" then means **making** it work first, which is part of Milestone 2 below.
2. **The portal's "Simulate Mobile Biometric Approval" button always shows ACCESS GRANTED.** When the backend rejects the mock signature, it falls through to a "standalone fallback" that grants anyway ([src/App.jsx:222-276](src/App.jsx:222)). It must be removed or gated before any judge sees the portal.
3. **The rPPG liveness decision can't tell noise from a pulse.** I simulated the app's own SNR metric: pure white noise scores **3.3 ± 0.9** and a clean 72 BPM sine scores about **9**. The app's "full marks" threshold for that metric is 1.6, and its "HRV" term *rewards* unstable BPM. As a result, noise is very likely scored as "VERIFIED HUMAN". This explains the Known Issues and means a **photo will probably pass today**. Details are in §4.
4. **There's no Android toolchain on this laptop.** No JDK, Android SDK, NDK, CMake or `adb` is installed, and there's no `local.properties`. `./gradlew assembleDebug` can't run here until they're installed. I need your go-ahead to install them (§8, decision D1).
5. **The public key is never bound to anything.** The backend verifies the signature against whatever public key arrives in the same request, and ignores the attestation chain. Anyone with a laptop script and a software key can produce a "valid" payload. Milestone 5 fixes this with per-pensioner device binding.

---

## 1. Repo layout: confirmed and corrected

| Item | What the brief says | What I found |
|---|---|---|
| `backend/` | FastAPI in `backend/app/` with `core/ db/ routers/ schemas/ services/` plus an undocumented `api/` | ✅ Confirmed. **`api/` is dead code.** `main.py` mounts only `app.routers.api_router` ([main.py:15](backend/app/main.py:15)). `api/v1/api.py` is a comment-only file, `api/v1/endpoints/health.py` is a byte-for-byte duplicate of `routers/health.py`, `endpoints/items.py` and `users.py` are "Deprecated stub" one-liners, and `api/deps.py` re-exports the stub `get_db`. **All new endpoints go in `routers/`.** |
| | | Other dead stubs: `routers/items.py`, `routers/users.py`, `schemas/item.py`, `schemas/user.py`, `services/item.py`, `services/user.py`. `db/session.py` is a stub that yields `None`, so **there is no database today**: sessions live in memory and are lost on restart. |
| | | `backend/app/.engram/cache/`: tool metadata, left untouched. |
| Root Gradle project + `app/` | The Android app | ✅ Confirmed. `settings.gradle.kts` includes `:app` and `:opencv` (mapped to `sdk/`). Package and applicationId are `com.example.sentinelhard`. AGP 9.3.1, Gradle 9.6.1, Kotlin 2.2.10 (AGP 9's built-in Kotlin; `app` doesn't apply `kotlin-android`), compile/target SDK 35, min SDK 24, Compose + CameraX 1.4.0 + ML Kit face detection 17.1.0 + ML Kit barcode 17.2.0 + Retrofit/OkHttp. Gradle daemon toolchain is JDK 21. |
| `SentinelHard/` | Unknown | **An empty directory that git records as a gitlink** (mode 160000) with **no `.gitmodules`**. There has never been one in any commit, and there is no `.git/modules/`, so no URL is recorded. The gitlink points to commit **`b9ac98d`**, which is **a commit in this same repo's own history**: "Final verification of flickering fixes on master" (prajit, 2026-07-26), an ancestor of `master`. That commit is an **older** version of this same Android app: Phase 17/18 flicker fixes, with no `CryptoManager`, QR, Retrofit or telemetry. It's 1,173 lines behind today's `app/`. Someone most likely ran `git add` while a clone of the repo sat inside it. **It isn't a separate repo, it isn't built, and it doesn't hold the working app.** See D5 in §8. |
| `sdk/` | Unknown | The **OpenCV 4.12.0 Android SDK** (Java module + native static libs for 4 ABIs, 939 MB). ✅ The app depends on it: `implementation(project(":opencv"))`, and CMake `find_package(OpenCV)` via `-DOpenCV_DIR=${rootDir}/sdk/native/jni`. The C++ uses only `core` + `imgproc` (`cvtColor`, `Laplacian`, `meanStdDev`, `dft`). The Java side calls only `OpenCVLoader.initLocal()`. |
| `src/`, `index.html`, `vite.config.js`, `package.json` | Vite web frontend | ✅ Confirmed. React 18 + Vite 5 + `qrcode.react` + `lucide-react`. It's a single 645-line `App.jsx` themed as **"Sentinel-Hard Bank India"**, a net-banking demo with a dark theme, hard-coded balances and transactions. `node_modules/` isn't installed. |
| `backend.zip` | Backup, don't touch | **Tracked in git but already deleted from the working tree** (`git status` showed ` D backend.zip` before I started). I haven't read, restored or modified it. |
| Others | | `.artifacts/`: planning and walkthrough notes from an earlier AI session (paths like `C:/Users/praji/AndroidStudioProjects/SentinelHard`). `.idea/`: Android Studio config. `.engram/`, `.graphify/`: tool metadata, left untouched. |
| Ports | | **Mismatch.** The README runs `uvicorn` on its default **8000**, and the brief's `adb reverse` uses 8000. The app ([ApiClient.kt:18](app/src/main/java/com/example/sentinelhard/network/ApiClient.kt:18), [TelemetryStreamer.kt:25](app/src/main/java/com/example/sentinelhard/TelemetryStreamer.kt:25)) and the portal ([App.jsx:25](src/App.jsx:25)) hard-code **8080**. I'll standardise on **8000**. |

### Graph vs code
The graph is accurate for what it covers: 158 nodes and 21 communities, with `SessionManager` and `ConnectionManager` as the hubs. The differences:
- **Missing edges.** The graph has no `calls` edges from `routers/auth.verify_biometric` into the services. The code calls `verify_signature` → `session_manager.get_session` → `update_status(VERIFIED)` → `validate_liveness` → `update_status(GRANTED)` → `manager.send_to_session`. The graph only has INFERRED "uses" edges to the exception classes. The same gap exists for `routers/session.py` → `session_manager` and `routers/ws.py` → `manager` and `session_manager`.
- The two "health()" communities (10 and 12 in the report) are the duplicate `api/` and `routers/` files. Communities 13–20 are the dead stubs. The graph doesn't show that `api/` is unmounted; the code does.
- `liveness.py` is in the graph but missing from the README's project tree.

---

## 2. What exists today, component by component

### 2.1 Backend (FastAPI, in-memory)
| Endpoint | Status |
|---|---|
| `GET /` | API overview |
| `GET /api/v1/health` | Works |
| `POST /api/v1/sessions` | Creates a `secrets.token_urlsafe(32)` session (PENDING, 300 s TTL). The body is ignored. It returns only the ID and timestamps: no purpose, nonce, challenge or base URL. |
| `GET` and `DELETE /api/v1/sessions/{id}` | Status poll and manual expire |
| `POST /api/v1/auth/verify` | The verification pipeline (§5.2) |
| `WS /api/v1/ws/{session_id}` | Portal channel. Sends `CONNECTED`, handles `ping`/`status`, and pushes `ACCESS_GRANTED`. **It never pushes a denial.** |
| `WS /api/v1/ws/telemetry` | Phone telemetry. Not tied to any session: it only logs and acks, and nothing is forwarded to the portal. |

- Background task purges expired sessions every 60 s.
- Settings come from `.env` via pydantic-settings: `SESSION_EXPIRY_SECONDS=300`, `BPM_MIN=40`, `BPM_MAX=220`, CORS for `localhost:3000` and `5173`.
- Dependencies: fastapi, uvicorn, pydantic(-settings), cryptography, websockets. There's no ORM and no DB driver.

### 2.2 Android app (`com.example.sentinelhard`)
One `MainActivity` (952 lines of Compose + CameraX) plus:
- `CryptoManager`: Keystore key.
- `QrCodeAnalyzer`: ML Kit barcode.
- `TelemetryStreamer`: OkHttp WebSocket.
- `ApiClient` / `BiometricApiService`: Retrofit.
- `Models`.
- `native-lib.cpp` (504 lines): the rPPG engine.

The screens are a menu ("Login Directly on Phone" / "Scan Desktop QR Code") → QR scan (rear camera) → HUD (front camera, BPM, "SNR dB", status badge, waveform, forehead box) → "Liveness Verified" → "Submitting" → Success or Error.

The theme is the default purple/teal Material template, and `activity_main.xml` is an unused "Hello World" layout.

### 2.3 Web frontend
There are three steps held in React state, with no router:
1. Landing page with an "Initialize Cryptographic Session" button.
2. QR screen: 5-minute countdown, WebSocket with 3 retries, then a "standalone mode" fallback, plus the simulate button.
3. A fake bank dashboard.

The QR encodes **only the raw `session_id` string** ([App.jsx:457](src/App.jsx:457)). All styling is inline and dark themed. None of `DESIGN.md` is applied yet.

---

## 3. The exact current flow (as the code is written)

1. **Laptop:** the user clicks *Initialize* → `POST /sessions` → the portal renders a QR code of the bare `session_id` and opens `ws://localhost:8080/api/v1/ws/{id}`. If the backend is unreachable, the portal invents a fake ID (`SENTINEL-IND-xxxx`) and enters "standalone mode".
2. **Phone:** the user taps *Scan Desktop QR Code* → CameraX binds the **rear** camera with an ML Kit QR analyzer at 1280×720 ([MainActivity.kt:298](app/src/main/java/com/example/sentinelhard/MainActivity.kt:298)). The first QR code found is parsed as JSON `{session_id}`, falling back to the raw string ([MainActivity.kt:414](app/src/main/java/com/example/sentinelhard/MainActivity.kt:414)).
3. **Front camera:** unbind, then bind the **front** camera at 640×480 YUV with `KEEP_ONLY_LATEST` → `analyzeFrame`, throttled to 20 fps.
4. **rPPG:** ML Kit face detection runs on every 3rd processed frame (about 6.7 Hz) and updates a cached forehead ROI. The JNI `processFrame` + `extractHeartMetrics` run on every frame (§4). A liveness status of 0/1/2 goes through a 15-frame majority vote and a 20-frame dwell filter. The telemetry WebSocket sends BPM/SNR about once a second to `10.0.2.2:8080` and fails silently on a real phone.
5. **Auto-submit:** as soon as `displayedStatus == 2 && buffer ≥ 150` ([MainActivity.kt:666-678](app/src/main/java/com/example/sentinelhard/MainActivity.kt:666)), the app shows "Liveness Verified" for 1.2 s, then builds the payload. **There is no BPM-stability or SNR gate on the phone.**
6. **Titan M2 signing:** the payload is JSON-encoded, signed with `SHA256withECDSA` using the Keystore key `rppg_auth_key`, and sent as `{payload: b64(json), signature: b64(DER sig), public_key: b64(SPKI DER), attestation_chain: [b64 certs]}` to `POST http://10.0.2.2:8080/api/v1/auth/verify`.
7. **Backend verifies** (§5.2). On success it sets the session to GRANTED and runs `manager.send_to_session(id, {event: "ACCESS_GRANTED", bpm, device_id, granted_at})`.
8. **Portal** receives `ACCESS_GRANTED` → step 3 (bank dashboard).

The "Login Directly on Phone" path makes up a `phone_session_<ms>` ID the backend has never seen, so it always ends in "Session not found".

---

## 4. The rPPG engine as it is today

**Stack.** C++17 over JNI ([native-lib.cpp](app/src/main/cpp/native-lib.cpp)), OpenCV 4.12 `core` + `imgproc`. Kotlin does capture, face detection (ML Kit, `PERFORMANCE_MODE_FAST`, `LANDMARK_MODE_ALL`), the YUV→NV21 copy and the UI.

**Per frame (20 fps):**
1. Kotlin copies YUV_420_888 into NV21, pixel by pixel through `ByteBuffer.get` (slow; about 150k calls per frame).
2. C++ converts the **whole 640×480 frame** to RGB, then crops the ROI: **forehead only**, at 45% of face-box width and 20% of its height, starting 10% down from the box top. There are no cheeks.
3. Sharpness is the variance of the Laplacian of the ROI. The colour means come from every 2nd pixel, skipping pixels with any channel above 240 and bright desaturated "glare" pixels.
4. Samples are stored with the sensor timestamp. The **window is 5.0 s** ([:127](app/src/main/cpp/native-lib.cpp:127)). It's linearly resampled to 30 Hz, giving about 150 samples.
5. **POS**: each channel is divided by its window mean, `X = G−B`, `Y = G+B−2R`, `S = X + (σX/σY)·Y`. This runs over the **whole 5 s window at once**, not the overlapping 1.6 s sub-windows of the original POS method.
6. **Detrend**: subtract a centred 1 s moving average. This is only a high-pass. **There's no low-pass or band-pass filter**, so everything from about 1 Hz up to 15 Hz passes, which is why the waveform looks jagged. An earlier version (in `.artifacts/.../full_project_code`) had a 0.75–2.5 Hz Butterworth filter; it has since been removed.

**Estimation (also every frame):**
7. Take the last 150 samples → Hamming window → zero-pad to 1024 → `cv::dft` → pick the power peak between 45 and 180 BPM → parabolic interpolation. **The real frequency resolution is 30/150 Hz = 0.2 Hz = 12 BPM.** Zero-padding only interpolates, so a 5 s window can't resolve BPM to better than a few BPM.
8. **"SNR"** = peak power ÷ mean power of all other bins between 45 and 180 BPM. It's a **linear ratio labelled "dB"** in the UI and the backend. With 1024-point padding, the Hamming main lobe is about ±27 bins wide inside a 77-bin band, so the metric is dominated by window shape: **white noise scores about 3.3 and a perfect sine about 9** (my simulation). A steady reading near 2.8 therefore means **no dominant pulse peak**. Consecutive windows share 149 of 150 samples, so the value moves very slowly; I'll confirm with `logcat` that it updates at all.
9. **BPM smoothing**: a 1-D Kalman filter initialised at **75 BPM** ([:109](app/src/main/cpp/native-lib.cpp:109)), updated 20 times a second with measurements that are almost identical, so it becomes overconfident. That explains the "72 → 99.5 climb": the filter walks from its 75 prior toward a raw peak that is itself noise-driven.
10. **Liveness "confidence"** = 0.3·texture + 0.3·QR + 0.2·(1 − R/G correlation) + 0.2·"HRV", then an EMA, then Schmitt thresholds (HUMAN > 0.65, SPOOF < 0.45), then Kotlin voting and dwell.
    - QR score saturates at a ratio of 1.6 ([:32](app/src/main/cpp/native-lib.cpp:32)), below the noise floor of 3.3, so it's **always full**.
    - Texture is full for any normally lit image.
    - "HRV" scores `std(BPM)/0.3` ([:352](app/src/main/cpp/native-lib.cpp:352)), so **jumpy, noisy BPM gets full marks**.
    - **Result: noise, and very likely a photo, reaches "VERIFIED HUMAN" as soon as the 5 s buffer fills.** That matches the "VERIFIED HUMAN in the first second" observation.

**Map to the Known Issues:**

| Symptom | Root cause |
|---|---|
| BPM climbs 72 → 99.5 | Kalman prior of 75, a noise-dominated raw peak, and 12 BPM resolution from the 5 s window |
| "VERIFIED HUMAN" in the first second | QR and HRV terms saturate on noise; there's no stability gate |
| SNR fixed at 2.8 "dB" | A linear ratio at the noise floor; slow to move because 149/150 samples are shared |
| Jagged waveform | No low-pass or band-pass filter; the high-passed raw POS signal is drawn |

**Other engine and app bugs:**
- **Stale state between scans.** `resetBuffers()` is only called after face loss, never at the start of a scan, and the `isAnalysisReady` latch stays `true`. A **second scan after "Return to Menu" can auto-submit almost immediately with the previous BPM.** That matters because the five demo scenarios run back to back.
- **The camera keeps running** after the result screen and after "Return to Menu": the camera provider is never unbound.
- **No multi-face rule**: `faces.first()` ([:795](app/src/main/java/com/example/sentinelhard/MainActivity.kt:795)).
- **The ROI overlay is misaligned**: it ignores PreviewView's `FILL_CENTER` crop. The whole face box isn't drawn.
- **Unsynchronised shared state**: `lastGoodRoi` and the Compose state are written from both the analyzer thread and the main thread (the ML Kit callbacks) without synchronisation.
- **StrongBox key generation runs on the main thread** in `onCreate`. That can take seconds on the first launch.
- **Micro-motion "variance"** is the variance of the nose position in pixels² over 15 detections. The backend rejects anything above 15, and normal head sway at 480p can exceed that.

---

## 5. Signing and verification as they are today

### 5.1 Phone side ([CryptoManager.kt](app/src/main/java/com/example/sentinelhard/CryptoManager.kt))
- **Key:** alias `rppg_auth_key`, EC `secp256r1`, `PURPOSE_SIGN|VERIFY`, SHA-256, no user authentication. It requests `setIsStrongBoxBacked(true)` and falls back to TEE if key generation throws, but **it doesn't record which one was used**.
- **Attestation:** no challenge is ever passed, so the attestation chain carries no freshness.
- **Signature:** `SHA256withECDSA` over the UTF-8 bytes of the JSON string, returning a DER signature. The exact same bytes are Base64-encoded as `payload`, so there's no canonicalisation problem. **I'll keep this scheme.**
- **Payload today:** `{session_id, bpm (Double), timestamp (ISO-8601 UTC, phone clock), device_id (ANDROID_ID), snr, variance}`.

### 5.2 Backend side ([routers/auth.py](backend/app/routers/auth.py))
The checks run in this order:
1. The ECDSA-SHA256 signature is checked against the **public key supplied in the same request**. It isn't compared with anything stored, and the attestation chain is ignored.
2. The payload is Base64-decoded, JSON-parsed and validated against the schema. **This is where fractional BPM fails.**
3. The session must exist, be `PENDING` and not be expired.
4. **The session is set to `VERIFIED` *before* the liveness checks.** If liveness then fails, the session is stuck at VERIFIED: it can't be retried and the portal is never told.
5. `validate_liveness`: `40 ≤ bpm ≤ 220`, `snr ≥ 3.5`, `0.01 < variance ≤ 15`.
6. Timestamp freshness: `|now − ts| ≤ 300 s`. This depends on the phone clock.
7. GRANTED → WebSocket push.

There is no nonce, no purpose, no device binding and no ledger. Replay of a captured request is limited only because the session leaves PENDING after the first attempt.

---

## 6. Connectivity and build

- **How the app finds the backend:** hard-coded `http://10.0.2.2:8080/api/v1/` and `ws://10.0.2.2:8080/...`, the emulator loopback. A physical phone needs a rebuild with the laptop's IP. `usesCleartextTraffic="true"` is set, so plain HTTP works.
- **Portal:** hard-coded `localhost:8080`.
- **Build:** Android Studio, according to `.artifacts/`. The Gradle wrapper is present. CMake 3.22.1 is required. ABIs are `arm64-v8a` and `armeabi-v7a`, with the 16 KB page-size linker flag. The release build has `isMinifyEnabled = true` and references `proguard-rules.pro`, **which doesn't exist**; debug builds aren't affected.
- **This laptop:** Node 24 and Python 3.11 (pydantic 2.12) are present. **There's no JDK, no Android SDK/NDK/CMake and no `adb`.**

---

## 7. Gaps and risks (ranked)

| # | Severity | Issue | Fixed in |
|---|---|---|---|
| 1 | 🔴 | `bpm: int` schema rejects every real payload | M2 (small backend fix) |
| 2 | 🔴 | Liveness decision passes noise (and probably photos): saturated QR term, inverted HRV term, no stability gate | M2 |
| 3 | 🔴 | Portal simulate button always shows ACCESS GRANTED | M2 (removed) |
| 4 | 🔴 | Public key isn't bound to any identity; attestation ignored | M5 (bind at enrollment), M4 (record StrongBox/TEE) |
| 5 | 🔴 | Hard-coded emulator IP and port 8080 | M2 (QR carries `base_url`) |
| 6 | 🟠 | No band-pass filter, 5 s window, fake "dB" SNR, Kalman prior at 75 | M2 |
| 7 | 🟠 | Stale native/UI state on a second scan → instant submit; camera never released | M2 |
| 8 | 🟠 | Session stuck at VERIFIED on a liveness fail; no denial pushed to portal | M2 (push `REJECTED`), M5 (full pipeline) |
| 9 | 🟠 | No multi-face rule; forehead-only ROI; ROI box misaligned | M3 |
| 10 | 🟠 | No face recognition at all | M3 (phone), M5 (backend match) |
| 11 | 🟠 | No anti-video-replay | M4 (random challenge) |
| 12 | 🟡 | No persistence (sessions in memory, no DB) | M5 |
| 13 | 🟡 | Timestamp freshness depends on the phone clock | M4: sign the server's nonce; the timestamp becomes secondary |
| 14 | 🟡 | Telemetry WebSocket not tied to a session; portal can't show "Measuring pulse" | M4/M7 (`/ws/telemetry/{session_id}` relayed to the portal as `MEASURING`) |
| 15 | 🟡 | Slow per-pixel YUV copy; full-frame RGB conversion | M2 (crop in C++) |
| 16 | 🟡 | Dead `api/` package and stubs; empty `SentinelHard/` gitlink; README tree and port out of date | Needs your OK to delete (D4, D5) |
| 17 | 🟡 | StrongBox key generation on the main thread | M4 |

---

## 8. Decisions

### 8.1 Resolved (2026-09-29)
| ID | Outcome |
|---|---|
| D1 | **Changed: no Android toolchain on this laptop.** The teammate builds and tests in Android Studio on his machine and checks his versions against `ANDROID_STUDIO_SETUP.md` (JDK 21, android-35, build-tools 36.0.0, NDK 28.2.13676358, CMake 3.22.1). Consequences:<br>• Android code is written to compile first time: exact pinned versions, the existing Gradle/CMake setup, and imports and APIs double-checked. M2 pins `ndkVersion`.<br>• Everything else is tested here: backend (pytest), portal (Vite build + browser), and the rPPG, face-match and challenge logic, through Python reference implementations fed simulated inputs. The laptop has no C++ compiler, so native code is checked against the Python mirror.<br>• After each Android milestone (M2, M3, M4) I stop so you can push and the teammate can build. Each summary separates "verified here" from "must test on phone".<br>• `TESTING_CHECKLIST.md` holds the phone tests. |
| D2 | Approved: MIT/Apache MobileFaceNet on LiteRT, with `MODEL_INFO.md` recording the source and licence. |
| D3, D9, D10 | Going with the recommendations: ML Kit only, a `monthly_pension_amount` column, and the old flow kept as `purpose = AUTH`. |
| D4 | Approved: delete the unused `backend/app/api/` package and the stubs (done in M2). |
| D5 | **Done.** Confirmed as an accidental old copy. Removed with `git rm --cached SentinelHard` plus the empty folder. The deletion is staged, not committed yet. Findings: there's no `.gitmodules`, and the gitlink points to `b9ac98d`, an older commit of this same repo (see §1). The code that actually runs on the phone isn't there. Git history shows commit `3e6593c` (2026-07-27) once set the app's URL to `http://192.168.1.5:8000/api/`, a physical-device LAN IP. `35a2181` then switched it back to `10.0.2.2:8080/api/v1/`. The Pixel's APK may have been built from around `3e6593c`, or from a teammate's uncommitted copy. |
| D6, D7 | Approved: `sqlmodel` and `react-router-dom`. |
| D8 | Approved. Branch **`legacy-bank-portal`** created at `49c0418` (current `master`) and **pushed to `origin`**. The portal gets replaced on `master` in M7. |
| Port | Standardise on **8000**. |
| Simulate button | **Remove it** (M2) rather than gate it behind a flag. |

**Pending before M2:** the teammate pushes his working code, and you give the go. I then pull, re-check the changes against this file, and start M2. M2 starts from whatever is on `master` at that point, and I'll re-run Step 0 on any changed files.

### 8.2 Original decision list

| ID | Decision | My recommendation |
|---|---|---|
| **D1** | **Install the Android toolchain on this laptop**: Temurin JDK 21, Android command-line tools → platform 35, build-tools, platform-tools (`adb`), NDK, CMake 3.22.1. That's about 3–4 GB. Without it I can write the Android code but **can't compile or install it**. | Install it. The alternative is that a teammate builds each milestone and reports back. |
| **D2** | **Face embedding model and runtime.** This needs `LiteRT` (TensorFlow Lite, ~2–3 MB per ABI) plus a MobileFaceNet `.tflite` (~5 MB, 112×112 input, 128- or 192-d output). InsightFace models are released for **non-commercial research use**; MobileFaceNet ports from `sirius-ai/MobileFaceNet_TF` and similar are MIT/Apache. | LiteRT + an MIT/Apache MobileFaceNet. I'll list the exact file, source and licence for sign-off in M3 before adding it. |
| **D3** | **Face detection library.** ML Kit is already a dependency and gives the box, landmarks, eye-open probability (blink) and head yaw (turn). | Keep ML Kit and don't add MediaPipe. No new dependency is needed for M3/M4 detection or the challenge. |
| **D4** | **Delete the dead backend code**: the `api/` package and the six "Deprecated stub" files. | Delete. After that, regenerate the Graphify graph. |
| **D5** | **Remove the empty `SentinelHard/` gitlink** from the git index (`git rm --cached SentinelHard`). | Remove it. It has no content and confuses tooling. |
| **D6** | **Backend dependencies:** `sqlmodel` (SQLite ORM). Fernet comes from `cryptography`, which is already installed. | Approve. Everything else (did:key, hash chain, officer tokens) uses the standard library plus `cryptography`. |
| **D7** | **Portal dependencies:** `react-router-dom`. Charts will be hand-made SVG, so no chart library. | Approve. |
| **D8** | **Replace the bank-demo UI.** `App.jsx` and `index.css` get rewritten as the Jeevan Suraksha portal. It's the same Vite project, but the banking screens go away. | Approve. The banking theme conflicts with DESIGN.md and the use case. |
| **D9** | **Pension amounts.** The Treasury page needs "amounts released vs frozen", but the brief's `pensioners` table has no amount column. | Add `monthly_pension_amount` (dummy data). |
| **D10** | **Keep the old flow alive.** `POST /sessions` with no body keeps today's behaviour, and the app keeps accepting a bare `session_id` QR code. | Keep both, as `purpose = AUTH`, until M7 replaces the portal. |

---

## 9. Build plan by milestone

Each milestone ends with: a build (or a teammate build if D1 is declined), an end-to-end run, an update to this file, a summary, and a phone test list. Then I wait for "continue". Before each milestone I re-read the relevant sections of `build-prompt.md` and `DESIGN.md`.

### M2: rPPG fixes + terminal build + QR-carried backend URL
**Android: C++**
- Refactor [native-lib.cpp](app/src/main/cpp/native-lib.cpp) into a JNI shim plus a host-testable core: **new** `cpp/rppg_core.{h,cpp}`.
- Crop the ROI in C++ from the Y/UV planes instead of converting the whole frame.
- **10 s window** (300 samples at 30 Hz).
- Proper POS with overlapping 1.6 s sub-windows.
- Detrend, then a **zero-phase Butterworth band-pass at 0.7–4.0 Hz**, run forward and backward over the window.
- Estimate at **2 Hz, not every frame**.
- **SNR in real dB** (de Haan): power within ±0.1 Hz of f₀ and 2f₀ versus the rest of the 0.7–4 Hz band, computed live on every estimate.
- BPM = median of the recent estimates. Remove the 75 BPM Kalman prior and the HRV/QR "confidence" heuristic. Sharpness and correlation stay as logged diagnostics only.
- The waveform returns the band-passed signal, lightly smoothed.

**Android: Kotlin**
- **New** `rppg/StabilityGate.kt`: status is "Measuring…" until ≥ 10 s of signal **and** the last 5 estimates are within ±3 BPM **and** SNR ≥ `MIN_SNR_DB`. Thresholds live in one config object; I'll calibrate `MIN_SNR_DB` from `logcat` runs (a real face versus a photo).
- Reset native and UI state at the start of every scan, and unbind the camera after the result.
- **New** `network/QrPayload.kt`: parse `{v, base_url, session_id, purpose, nonce, challenge}` or a bare ID.
- `ApiClient` and `TelemetryStreamer` build their URLs from `base_url`; the hard-coded IPs are removed.

**Backend**
- `schemas/auth.py`: `bpm: float`.
- `POST /sessions` accepts an optional `{purpose}` and returns `qr_payload` with `base_url`, taken from `PUBLIC_BASE_URL` in `.env` or derived from the request.
- On a liveness failure, set REJECTED (new status) and push `REJECTED` with a reason.
- `.env.example`: `PUBLIC_BASE_URL`, `MIN_SNR_DB`.

**Portal (minimum only)**
- Port 8000 via `VITE_API_BASE`, the QR encodes `qr_payload`, and the simulate button is removed.

**Docs**
- **New** `ANDROID_BUILD.md`: `gradlew assembleDebug` / `installDebug`, `adb reverse tcp:8000 tcp:8000`, LAN IP, `cloudflared`.
- **New** `app/proguard-rules.pro` so release builds work.

**Tests**
- **New** `tools/rppg_sim.py`: a Python reference of the pipeline run on synthetic pulse, noise and still-photo traces, to check BPM convergence and SNR separation before phone testing.

### M3: Face detection, shared box, single-face rule, embeddings, template
- **New** `face/FaceTracker.kt` (ML Kit): whole-face box drawn on the preview with correct `FILL_CENTER` mapping. The rPPG ROIs are the **forehead + both cheeks taken from inside that box** and passed to C++. Any frame with **> 1 face aborts the scan** ("More than one face detected").
- **New** `face/FaceEmbedder.kt`: LiteRT MobileFaceNet (after D2 sign-off). 5-point alignment using the ML Kit eye and nose/mouth landmarks → 112×112. Runs every 3rd detection on a background executor.
- **New** `face/TemplateBuilder.kt`: a quality score from yaw/pitch < 10°, Laplacian sharpness, brightness range and face size. It keeps the **best 10–20** embeddings, averages them and L2-normalises the result.
- Frames live only in memory and are released immediately. No image is written to disk.
- `assets/` gains the model file and a `MODEL_INFO.md` with its source and licence.

### M4: Random challenge + extended signed payload
- **Backend:** the session gets `challenge ∈ {BLINK_TWICE, TURN_LEFT, TURN_RIGHT}`, `challenge_id` and `nonce` from `secrets`, all carried in the QR code. **New** `WS /ws/telemetry/{session_id}` relays `MEASURING` and `CHALLENGE_ISSUED` events to the portal socket.
- **App:** **new** `challenge/ChallengeVerifier.kt`. A blink is detected from eye-open probability dropping below 0.3 and rising above 0.7, twice. A head turn is |yaw| > 20° in the requested direction. There's a time limit (e.g. 5 s), and the prompt appears part-way through the scan.
- **App:** `models/Models.kt` → the full §4.4 payload `{session_id, purpose, nonce, timestamp, device_id, bpm, snr, liveness_passed, challenge_id, challenge_passed, face_embedding | reference_template, frames_used, app_version, key_security_level}`.
- `CryptoManager`: generates the key off the main thread and records StrongBox or TEE using `KeyInfo.securityLevel` (API 31+) or `isInsideSecureHardware`. Still ECDSA P-256 / SHA-256.
- Four new screens (Compose) with DESIGN.md colours: **Scan QR → Consent → Face Scan → Result**. The guide circle is orange while measuring and green when verified, with large prompts and a progress ring. The debug menu and the "Login Directly on Phone" path are removed.

### M5: Data model, verification pipeline, three-band decision, template update, calibration
- **New** `backend/app/db/` using SQLModel + SQLite: `models.py` with pensioners, biometric_templates, devices, life_certificates, officers, sessions (moved out of memory), audit_ledger.
- **New** `core/security.py`: Fernet encryption of templates, key `TEMPLATE_KEY` from `.env`.
- **New** `services/verification.py`: the §5.2 pipeline in order: signature, then key matches the registered device (and for ENROLLMENT, bind the key), then schema, then session/purpose/nonce used once, then freshness, then liveness, then challenge, then face match. `routers/auth.py` becomes a thin wrapper.
- **New** `services/face_match.py`: cosine similarity against `current_template` and `anchor_template`, with a three-band decision on `T_HIGH` and `T_LOW` from `.env`.
- **Template update:** only when the score is ≥ T_HIGH; blend, L2-normalise, and require a minimum anchor similarity.
- **Freeze rule:** after N failures or when the deadline passes, the pensioner becomes FROZEN.
- **New routers:** `enroll.py`, `pensioners.py`, `reviews.py`, `officers.py`, `treasury.py`.
- **New** `scripts/calibrate_thresholds.py`: logs genuine and impostor scores to CSV and suggests `T_LOW` and `T_HIGH`.
- **New** `scripts/seed_demo.py`: dummy officer and pensioners.
- ⚠️ This changes the backend structure, so **please regenerate the Graphify graph** after M5.

### M6: Ledger, DID, credentials
- **New** `services/ledger/` behind an interface, `LedgerBackend` with `append`, `list` and `verify_chain`. The `local_hashchain.py` implementation stores SHA-256 over canonical JSON plus `prev_hash`, and **only stores hashes**.
- **New** `services/did.py`: `did:key` from the device's P-256 public key (multicodec `0x1200`, compressed point, base58btc).
- **New** `services/credentials.py`: a W3C-style Verifiable Credential for each issued certificate, signed with a backend P-256 key kept in `.env`/`data/`.
- The asset rule is that the entitlement is released only if the current year has an issued certificate.
- Endpoints: `GET /ledger`, `GET /ledger/verify`, `GET /treasury/summary`.
- ⚠️ Structure change, so regenerate the graph again.

### M7: Web portal
- Delete the bank UI (D8).
- **New** `src/theme/tokens.css`: every DESIGN.md token (colours, radius, shadow, fonts: Poppins + Noto Sans + Noto Sans Devanagari).
- **New** `src/components/`: shell (utility bar, header, nav, banner, footer, copyright), HeroCarousel, HighlightStrip, FeatureCards, StatusStepper, QrPanel, StatusBadge, StatTiles, DataTable, FormField, CertificateCard, Toast plus an ARIA live region, FAQ accordion.
- **New** `src/pages/`: Home, SubmitLifeCertificate, CheckStatus, OfficerLogin, RegisterPensioner, ReviewQueue, PensionerRecords (+ detail), Treasury, AuditLedger, HowItWorks, Help.
- **New** `src/api/client.js` and `src/api/useSessionSocket.js`.
- The logo is a simple original SVG. Illustrations are unDraw (recoloured) or hand-made SVG. No emblems, no AI images.
- Text-size control (A−/A/A+), keyboard focus rings, 18 px body text on pensioner pages.

### M8: End-to-end demo and docs
- Run all 5 scenarios on the Pixel 7 + laptop and record the results in this file.
- Update `backend/README.md` (endpoints, WebSocket events, port 8000, honest limitations), `backend/EXPLAINER.md` and `ANDROID_BUILD.md`.
- **New** `DEMO_SCRIPT.md`.

---

## 10. What I'd like you to check on the phone now (optional, helps M2)
1. Which build is installed? **Settings → Apps → SentinelHard → App details**: the version and install date. Is it from this repo, or a teammate's copy?
2. If you can, run one scan with the phone connected and send me `adb logcat -s SentinelHardNative SentinelTelemetry`. That lets me confirm the SNR really is frozen, rather than just slow-moving.
3. Hold a printed photo up to the current app. My prediction is that it reaches "VERIFIED HUMAN". If it does, we have a useful before/after for the pitch.

---

## 11. Change log (current state)

**Order changed:** the teammate's Android code hadn't been pushed (`origin/master` was still `49c0418`), so the backend and portal milestones (5 → 6 → 7) go first. M2–M4 follow once his code is in.

### M5: Backend data model and verification pipeline (2026-09-29)

⚠️ **Backend structure changed: please regenerate the Graphify graph** (`.graphify/` still shows the Step 0 backend).

**Removed (D4):** `app/api/` (the whole unused package), the six "Deprecated stub" files in `routers/`, `schemas/` and `services/`, and the `db/session.py` stub.

**Backend layout now** (see `backend/README.md` for the full tree):
- **`db/`**: `database.py` (SQLite engine via SQLModel, `init_db`, `get_db`), `models.py` (officers, pensioners, biometric_templates, devices, life_certificates, auth_sessions, audit_ledger), `types.py` (UTC datetime type).
- **`core/`**: `config.py` gains thresholds and keys, `security.py` is new (PBKDF2 passwords, HMAC officer tokens, Fernet template cipher), `deps.py` is new (DB and officer-auth dependencies).
- **`services/`**:
  - `verification.py` is **new**: the ordered pipeline. `routers/auth.py` is now a thin wrapper around it.
  - `face_match.py` is new: cosine, three bands, blend update, encryption.
  - `session.py` was **rewritten**: DB-backed, with purpose, nonce, challenge, QR payload, LAN base URL and an atomic claim. The in-memory `SessionManager` is gone.
  - `pensioners.py` is new: freeze and restore rules.
  - `ledger.py` is new: `LedgerBackend` interface plus the local hash chain (append/list/verify).
  - `score_log.py` is new.
  - `connection_manager.py` now supports several sockets per channel plus an officer events channel.
  - `liveness.py` accepts a decimal BPM and adds `check_liveness` (dB SNR).
- **`routers/`**:
  - New: `officers.py`, `pensioners.py`, `enroll.py`, `reviews.py`.
  - `session.py` gains purposes and `qr_payload`.
  - `ws.py` gains `/ws/events` and `/ws/telemetry/{session_id}` relays.
- **`schemas/`**: `auth.py` has the §4.4 payload (legacy payload still accepted as `AUTH`); `session.py` has purpose, challenge and QR; `pensioner.py` is new.
- **`scripts/`**: `calibrate_thresholds.py`, `simulate_phone.py` (dev tool, software key), `seed_demo.py` (fictional data).
- **`tests/`**: 47+ pytest tests. `requirements-dev.txt` is new. `data/` is gitignored.

**Fixed from §7:**
- #1: a decimal BPM is now accepted.
- #3: the simulate button still exists in the portal, and **is removed in M7**. The backend side is honest, because the phone simulator reports `SOFTWARE`.
- #4: the device key is bound per pensioner.
- #8: a failed session becomes REJECTED and is pushed to the portal.
- #12: everything is persisted in SQLite.
- #13: timestamp skew is ±120 s, and the session nonce is inside the signed payload.
- #14: the phone → portal telemetry relay exists. The app starts using it in M4.

**Design decisions made in M5 (beyond the brief):**
- **Device binding** is checked right after the session lookup, because the pensioner is only known from the session. For ENROLLMENT the key is stored but **inactive until the officer approves**.
- **Single use:** `PENDING → PROCESSING` is an atomic UPDATE. Checks that happen before it (bad signature, nonce, purpose, expired) do **not** use up the session, so a genuine retry still works.
- **Freeze counting:** only `NO_PULSE`, `CHALLENGE_FAILED` and `FACE_MISMATCH` count toward `MAX_FAILED_ATTEMPTS`. Otherwise a stranger's phone (`DEVICE_MISMATCH`) could freeze anyone's pension. All rejections are still recorded, so they show up in the treasury view.
- **Frozen pensions** are only released by an officer: a strong match on a frozen pension goes to review (`FROZEN_REVIEW`).
- **Anchor check on every decision:** an approval needs `score ≥ T_high` **and** `anchor_score ≥ FACE_ANCHOR_MIN`. Tests show a template *can* drift (it stays ≥ `ANCHOR_MIN` from the anchor), but an impostor's own face is never auto-approved, because it fails the anchor check.
- **Consent** is required twice: `consent: true` when the portal creates a life-certificate session, and `consent: true` inside every signed payload (stored as `consent_at`).
- **Only one live QR** per pensioner and purpose: creating a new one expires the older one.
- **QR `base_url`:** `PUBLIC_BASE_URL`, or else the laptop's LAN IP. The app will fall back to `localhost` for `adb reverse` (M2).
- **Thresholds:** `FACE_T_HIGH=0.70`, `FACE_T_LOW=0.50`, `FACE_ANCHOR_MIN=0.55` and `MIN_SNR_DB=3.0` are **placeholders** until calibrated with `calibrate_thresholds.py` on real scans.
- **Payload additions beyond §4.4:** `model_version`, `key_security_level` and `consent` (all optional for AUTH).

**After M5 (same day):** an officer can lift a freeze from the review queue (`GET /reviews/frozen`, `POST /reviews/frozen/{id}/restore`), and `scripts/reset_demo.py` resets the demo to a clean state (the old data is moved to `data/backups/`, never deleted).

### M2: rPPG fixes, QR-carried backend URL, laptop engine tests (2026-09-30)

**Android native (`app/src/main/cpp/`):**
- **New `rppg_core.{h,cpp}`:** a pure C++17 engine with no JNI/OpenCV, so it runs on a laptop. Per frame, it takes the mean colour of the skin pixels inside the face ROIs, read straight from the YUV planes (YCbCr skin box, glare excluded). Over a **10 s window** it runs: resample to 30 Hz → **POS** (1.6 s overlap-add) → linear detrend → **zero-phase Butterworth band-pass 0.7–4 Hz** → Hann spectrum on a 0.5 BPM grid → peak → **SNR in dB** (de Haan: ±0.2 Hz around f0 and 2·f0 vs the rest), with an estimate every 0.5 s.
- **Stability gate:** window ≥ 95% full, 5 estimates within ±3 BPM of their median, and median SNR ≥ `minSnrDb`. The reported BPM is that median. A timestamp gap over 1 s restarts the scan.
- **Removed:** the Kalman filter with its 75 BPM prior, the texture/QR/correlation/"HRV" confidence heuristic, and full-frame RGB conversion.
- **`native-lib.cpp` rewritten** as a thin JNI layer for `com.example.sentinelhard.rppg.RppgNative`. Planes are read as direct ByteBuffers with no copy, and ROIs are passed as a flat array.
- **`CMakeLists.txt`:** adds `rppg_core.cpp` and C++17. OpenCV stays linked.

**Android Kotlin:**
- **New files:**
  - `rppg/RppgNative.kt` (JNI);
  - `rppg/RppgResult.kt` (output layout);
  - `rppg/RppgConfig.kt` (window, gate, 30 s timeout);
  - `rppg/FaceRois.kt` (forehead + two cheeks inside the ML Kit face box, mapped to sensor coordinates);
  - `network/QrPayload.kt` (parses the v1 QR JSON, or a legacy bare id).
- **`MainActivity` rewritten:**
  - flow Home → Scan QR → Connecting → Measuring → Submitting → Result;
  - state reset at the start of every scan;
  - the camera is released when a screen is left;
  - the signed payload is auto-submitted once the reading is stable;
  - a signed "no pulse" is sent after 30 s;
  - StrongBox keygen runs off the UI thread.
- **Removed:** "Login Directly on Phone", micro-motion variance, voting/dwell/hysteresis, coasting, and the per-pixel YUV copy.
- **`ApiClient`:** one Retrofit client per base URL from the QR; probes `/health` on the QR URL, then on `localhost` (for `adb reverse`). The hard-coded `10.0.2.2:8080` is gone.
- **`TelemetryStreamer`:** `/ws/telemetry/{session_id}?nonce=` with events `scan_started`, `measuring`, `stable_reading` and `face_lost`.
- **`Models`:** the payload adds `purpose`, `nonce`, `liveness_passed`, `frames_used` and `app_version`; `variance` is dropped. SNR is in dB.
- **`build.gradle.kts`:** `ndkVersion = "28.2.13676358"` pinned, `buildConfig = true`, version `2.0-m2` (code 2).
- **New `app/proguard-rules.pro`**, so release builds no longer reference a missing file.

**Backend:**
- The QR payload gains `liveness.min_snr_db` (from `MIN_SNR_DB`).
- AUTH sessions use the dB liveness check when the payload has `liveness_passed`; the original app's payload still gets the legacy check.
- **Bug fixed:** the telemetry relay didn't acknowledge throttled messages. Found in live testing, with a regression test added.
- The simulator acts like the M2 app, including live telemetry (`--legacy` gives the old payload).

**Portal (minimal; the full redesign is M7):**
- Port 8000 via `VITE_API_BASE`.
- The QR encodes `qr_payload`.
- **The always-grant "Simulate" button and the fake "standalone" sessions are removed.** If the backend is down, the portal says so.
- Live `MEASURING` status and `REJECTED` reasons are shown.

**Laptop tests (`tools/rppg/run_tests.py`):**
- zig-compiled C++ unit tests (filter response, zero phase, YUV plane indexing with interleaved and padded layouts, POS rejects brightness-only changes, gaps);
- filters checked against scipy;
- the JNI layer compiled against a `jni.h` stub;
- 10 synthetic scenarios;
- C++ vs the Python reference (agree to 0.0001 BPM / dB);
- Monte-Carlo pass rates (default 3.0 dB: 0% photos pass, 88% genuine).

**Known limits of M2** (by design; later milestones):
- no whole-face box or multi-face rejection (M3);
- no challenge (M4);
- only AUTH QR codes are accepted by the app (M3/M4 add ENROLLMENT and LIFE_CERTIFICATE);
- the dark HUD stays until the M4 screens;
- the ROI overlay assumes the preview and analysis streams have the same aspect ratio.

### M6: Ledger, DID, credentials, treasury (2026-09-30)

⚠️ **Backend structure changed: please regenerate the Graphify graph.**

**New services:**
- `did.py`: `did:key` for P-256 (multicodec 0x1200, compressed point, base58btc), with round-trip decode.
- `credentials.py`: a backend issuer key (`ISSUER_KEY_PEM`, or auto-generated `data/issuer_key.pem`) and W3C-VC-shaped `LifeCertificateCredential` JSON. The subject is the pensioner's DID only. The proof is ECDSA P-256 over canonical JSON, and verification uses the key inside the issuer's did:key.
- `certificates.py`: **one issuance path** (credential → hash → `CERTIFICATE_ISSUED` ledger entry) shared by automatic approvals and officer approvals.
- `entitlement.py`: RELEASED / AWAITING_CERTIFICATE / FROZEN / NOT_REGISTERED, plus the treasury summary.

**New router `ledger.py`:**
- `GET /ledger` (with `head`) and `GET /ledger/verify`;
- `GET /credentials/issuer`, `GET /certificates/{id}/credential` and `POST /credentials/verify` (signature, issuer, validity window, ledger record, certificate status, chain);
- `GET /treasury/summary` (officer).

**Changed:**
- **Registration approval** sets `pensioner.did` from the bound phone key and records the DID in `REGISTRATION_APPROVED`.
- **CERTIFICATE_ISSUED:**
  - ledger records now include `credential_hash`;
  - WebSocket events carry `credential_hash` and `did`;
  - pensioner detail and public lookup include `did` and `entitlement`;
  - `life_certificates` gains `credential_json`.
- **DB migration:** `init_db` adds missing *nullable* columns to existing SQLite tables. `create_all` doesn't; checked on the real dev DB.
- **Seed:** demo pensioners get DIDs and signed credentials.

**Bug found in testing:** the credential validity check compared timestamps as strings, which fails within the same second. It now uses real datetimes.

**Tests:** 61 pass. They cover:
- did:key format and round trip, plus base58 vectors;
- that credentials hold no personal data, verify correctly, and catch tampering and a forged issuer;
- review-approved credentials;
- ledger endpoints and tamper detection;
- treasury counts and amounts through freeze and restore;
- the migration.

### Step 1 (Wi-Fi) and Step 2 (diagnostics), 2026-09-30
See commits `82bfbd2` and `084af5b`, plus the "Wi-Fi setup" and "Scan speed comparison" sections of `TESTING_CHECKLIST.md`.
- **New backend files:** `run.py` (always 0.0.0.0), `app/core/network.py` (adapter-aware QR address, startup banner, LAN self-check), `routers/diagnostics.py`.
- **Changed backend:**
  - the `scan_diagnostics` table;
  - the QR `liveness` block carries every gate setting;
  - CORS allows LAN origins;
  - `calibrate_thresholds.py scans` / `label-scans`.
- **App:**
  - `camera/CameraTuning.kt` (30 fps range, AE/AWB lock) and `rppg/ScanDiagnostics.kt`;
  - `GateSettings` from the QR;
  - diagnostics toggle, guidance prompts, and error reasons in `ApiClient`;
  - `res/xml/network_security_config.xml`;
  - the JNI header grows to 18 values.

### M7: Web portal (2026-09-30)
The banking demo is replaced (it's kept on the `legacy-bank-portal` branch). React 18 + Vite 5 + react-router-dom 6.30, with no UI kit. Everything follows `DESIGN.md`.

**Structure:**
- `src/theme/`: `tokens.css` (all tokens) and `components.css` (shell + component library).
- `src/app/`: `providers.jsx` (auth, toasts + ARIA live region, i18n, text size), `strings.js` (English + Hindi), `useScanFlow.js` (WebSocket events to the stepper, with a polling fallback).
- `src/api/`: `client.js` (backend on the same host, port 8000) and `sockets.js`.
- `src/components/`: `Shell` (utility bar, header, nav, officer nav, banner, footer), `ui` (badge, stepper, QR panel, certificate card, table, field, hash), `sections` (hero, highlight, side info, features, showcase, feeds, icon carousel, links, FAQ), `Art` (original SVGs), `Consent`, `ScanPanel`, `RequireOfficer`.
- `src/pages/`: Home, SubmitCertificate, PracticeScan (AUTH, a device check), CheckStatus, OfficerLogin, OfficerHome (live events), RegisterPensioner, ReviewQueue (borderline + frozen), Records/RecordDetail, Treasury, Ledger (chain verify + credential verifier), and Info (How It Works, Help, Contact, Search, Not found).

**Verified in the browser:**
- the full submit flow (simulator scan: stepper, then certificate card, then ledger verify);
- the officer flows: login redirect, review approve (with the empty-reason guard), restore frozen, and registration with capture, approve, Active + DID;
- the treasury figures;
- no horizontal overflow at 375 px on 15 pages;
- WCAG contrast of every colour pair;
- the Hindi toggle, the text-size control and the skip link.

**Security detail:** the portal never shows the challenge before the scan, so an attacker can't pick a matching video in advance.

### M3: Face detection, one-face rule, embeddings, template (2026-09-30)
- **Model:** `app/src/main/assets/mobilefacenet.tflite`, 5,233,552 bytes, SHA-256 `be4bc7cf…`. See `MODEL_INFO.md` for source, licence, provenance caveat, I/O and pre-processing. The app's `MODEL_VERSION` and the backend's `FACE_MODEL_VERSION` are both `mobilefacenet-192-v1`.
- **Native:**
  - `face_core.{h,cpp}`: alignment straight from the YUV planes (2.5× eye distance, eyes level, 0.15× offset; RGB [-1,1]) plus sharpness and brightness, and `averageTopK` for the template.
  - JNI functions `FaceNative.nativeAlignFace` / `nativeBuildTemplate`; CMake adds `face_core.cpp`.
  - Laptop tests in `tools/rppg/test_face.cpp`: identical crops for rotations 0/90/180/270, tilt removal, centring, eye order, quality measures, top-k averaging.
- **Kotlin:**
  - `face/FaceNative.kt`, `face/FaceEmbedder.kt` (LiteRT `Interpreter`, verifies the model's I/O shapes at load), `face/FaceCapture.kt` (quality from pose, size, light and sharpness; template = best 15 of ≥10, probe = best 5 of ≥3).
  - ML Kit now reports landmarks, classification and tracking. More than one face → the scan stops and a signed `abort_reason=MULTIPLE_FACES` is sent. A change of tracked face → full restart.
  - The whole-face box is drawn; there's a face-frames count in the diagnostics.
  - Embeddings are only *logged* in M3; M4 puts them into the payload.
- **Dependency:** `com.google.ai.edge.litert:litert:1.4.2` (checked: `Interpreter(ByteBuffer, Options)`, `run`, `get{Input,Output}Tensor`, arm64/armv7 native libraries).
- **Backend:** `abort_reason` (Literal `MULTIPLE_FACES`) → reason `MULTIPLE_FACES`, which doesn't count toward freezing. The portal maps it to the "Measuring pulse" step with advice.

### M4: Random challenge, extended signed payload, four app screens (2026-09-30)
- **Challenge** (`face/ChallengeVerifier.kt`, pure Kotlin, JVM tests in `app/src/test/.../ChallengeVerifierTest.kt`):
  - BLINK_TWICE uses ML Kit eyes-open probability with hysteresis (closed < 0.35, open > 0.65).
  - TURN_LEFT/RIGHT uses head yaw: frontal first, then ≥ 25° in the requested direction for 2 detections in a row. The wrong way only shows the hint "Other way".
  - The time limit comes from the QR `challenge.timeout_s`.
  - `LEFT_YAW_SIGN` is the one constant to flip if a phone reports yaw the other way (test 4.6).
- **Scan phases** (MainActivity): PULSE (stable gate as before) → CHALLENGE (face detection on every frame) → CAPTURE (wait ≤ 6 s for ENROLL_MIN / PROBE_MIN clear face frames) → submit.
  - Practice (AUTH) scans have no challenge and submit on the stable pulse, as before.
  - Losing the face or a change of tracked face during the challenge sends the scan back to PULSE.
  - Telemetry sends `challenge_issued/passed/failed` (the portal stepper already handled them).
- **Signed payload** (build-prompt §4.4) adds:
  - `challenge_id`, `challenge_passed`;
  - `face_embedding` (life certificate, best 5 frames) or `reference_template` (registration, best 15);
  - `frames_used` (face frames averaged), `model_version`, `consent`;
  - `key_security_level` from `KeyInfo` (Android 12+ exact; older versions report StrongBox as TEE, never overstated).
  - Error responses (non-2xx) are parsed too.
- **Screens** (`ui/Theme.kt`, `ui/Screens.kt`, DESIGN.md §7): Scan QR (welcome + camera with an orange frame) → Consent (purpose-specific plain-language points) → Face Scan (dark camera, guide circle orange→green, progress ring, big prompt, pulse + waveform card, diagnostics toggle) → Result (big icon, outcome, reason).
  - Fonts: system sans-serif, not Poppins/Inter. Downloadable fonts would need another dependency; left out on purpose.
- **Backend:**
  - `abort_reason` also accepts `FACE_NOT_CAPTURED` (not counted toward freezing).
  - The schema no longer requires face data when the app aborted or when the pulse or challenge failed, so those attempts are reported with their real reason (before this, a MULTIPLE_FACES abort on a life-certificate QR would have failed validation).
  - New test (73 total).
  - The portal maps FACE_NOT_CAPTURED to the Face step.
- App version 4.0-challenge (versionCode 5).

### M8: Docs, demo script, end-to-end run (2026-09-30)
- **`DEMO_SCRIPT.md`** (new): the 10-minute presentation. It covers:
  - the cast and props, and why everything uses one phone;
  - a 30-minute pre-flight checklist;
  - word-for-word talking points for S1–S5, the freeze/restore finale, the ledger and treasury;
  - a "what to do if…" table (including falling back to the simulator via "Show QR data");
  - likely judge questions.
- **`backend/scripts/demo_check.py`** (new): runs against a live backend and checks each result.
  - It covers S1–S5, the freeze after 3 failures, Review Queue → restore, ledger verification, the treasury and a MULTIPLE_FACES abort.
  - It uses a fresh test pensioner and a fresh simulated device.
  - Run on this laptop: **all checks pass**.
  - The portal was also checked live with the simulator: the stepper went through Measuring → Challenge ("Turn your head left") → Face match → Result, and the certificate card appeared.
- **`simulate_phone.py`** now behaves like the M4 app: stable_reading, challenge_issued, then challenge_passed/failed telemetry; `--multiple-faces`; frames_used 15/5.
- **Docs:**
  - `backend/EXPLAINER.md` rewritten for the pension system (it still described the old netbanking login), including an honest "what it does not do" section.
  - `backend/README.md`: structure (network, diagnostics, run.py, demo_check), the app-abort step, new reason codes, more limitations.
  - `ANDROID_BUILD.md`: the app's four screens and flow, log tags, unit-test command.
  - `TESTING_CHECKLIST.md`:
    - a **combined run order** at the top (setup → Wi-Fi → M2 → scan-speed comparison → M3 → M4 → demo scenarios);
    - new **section B** (which commit to check if the Android build fails);
    - demo expectations updated to the new app's wording.
- The Graphify backend map was regenerated (639 nodes, 28 communities) and copied to `.graphify/`.
- The dev DB was reset with seed data (the old data is in `backend/data/backups/`).
