# TESTING_CHECKLIST.md: Phone Tests (Pixel 7)

This is for the teammate who builds and tests the Android app. Claude writes the code on a laptop **without** an Android toolchain, so the phone tests here are the only real check of the Android side. Please follow them in order and report back using section 7.

Each milestone's section is updated when that milestone is delivered. Thresholds marked _(calibrating)_ are first guesses that your results will tune.

---

## 0. Before every test round

1. **Pull** the latest `master`.
2. **Check your toolchain** against `ANDROID_STUDIO_SETUP.md` §1: JDK 21, platform android-35, build-tools 36.0.0, NDK 28.2.13676358, CMake 3.22.1. From M2 onwards the NDK version is pinned in `app/build.gradle.kts`, so a mismatch shows up as a build error.
3. **Build and install.** In Android Studio: *Build → Clean Project*, then *Run 'app'*. From a terminal:
   ```powershell
   .\gradlew clean :app:installDebug
   ```
   ➜ **If the build fails, stop here** and send the full error (section 7). Build errors are the most likely failure, because the code wasn't compiled before it reached you.
4. **Start the backend** on the laptop:
   ```powershell
   cd backend
   .\venv\Scripts\Activate.ps1
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
5. **Connect the phone to the backend** using one of these:
   - USB (easiest): `adb reverse tcp:8000 tcp:8000`. The phone then reaches the laptop at `localhost:8000`.
   - Same Wi-Fi: the portal puts the laptop's LAN IP in the QR code. Allow port 8000 through Windows Firewall.
6. **Start the portal**: `npm install` (first time only), then `npm run dev`, and open http://localhost:5173.
7. **Start a log capture** before testing (section 7.2) so failures are already recorded.

Test conditions: indoor, even light on the face (no strong window light behind you), phone held about 30–40 cm from the face, stable if possible (resting on a table is best).

---

## 1. Milestone 2: rPPG fixes + QR-carried backend URL

| # | Test | Steps | Expected result |
|---|---|---|---|
| 2.1 | Build | Section 0, step 3 | Builds with no errors and the app installs. |
| 2.2 | QR carries the backend URL | The portal shows a QR code. Scan it with the app. | The app opens the front camera. **No IP was typed or built into the app.** `logcat` shows the parsed `base_url`. |
| 2.3 | "Measuring…" gate | Sit still facing the camera. | The screen says **"Measuring…"** for **at least 10 s**. It must **not** show verified or passed in the first seconds. |
| 2.4 | BPM converges | Keep still. At the same time, count your pulse on your wrist for 30 s and multiply by 2. | The BPM settles and stops climbing. When it passes, it's within about **±5 BPM** of your wrist count. Note both numbers. |
| 2.5 | SNR updates live | Watch the SNR value (now in real dB). | It **changes** over time (not a constant 2.8). It rises as the reading stabilises. Note the value at the moment of passing. |
| 2.6 | Smooth waveform | Watch the waveform. | A **smooth, regular wave** at your pulse rate, not jagged noise. |
| 2.7 | Pass → backend | Complete a scan. | The phone shows success, **and the laptop portal updates at the same moment**. The backend log shows the request accepted. |
| 2.8 | **Printed photo** | Hold a printed photo of a face in front of the camera for 30 s. | It stays on "Measuring…" or fails with "No pulse detected". **It must never pass.** Note the SNR shown. |
| 2.9 | Motion | Shake or turn your head a lot during the scan. | It keeps measuring or asks you to hold still. There's no false pass. |
| 2.10 | Second scan | Finish one scan, return, and scan a **new** QR code straight away. | The new scan starts from zero ("Measuring…" again, at least 10 s). It **doesn't** auto-submit instantly. |
| 2.11 | Camera released | Finish a scan and go to the result screen. | The camera privacy dot/indicator turns off. |
| 2.12 | Wi-Fi path | Repeat 2.2 and 2.7 without `adb reverse`, with the phone on the same Wi-Fi as the laptop. | Works without rebuilding. |

**Send back for M2:** the wrist BPM vs the app BPM for 3 scans, the SNR at pass time, the SNR during the photo test, and one `logcat` capture of a full scan.

---

## 2. Milestone 3: Face detection, same-face box, embeddings

| # | Test | Steps | Expected result |
|---|---|---|---|
| 3.1 | Build | Section 0, step 3 | Builds. The APK is about 10–15 MB larger, because of the face model. |
| 3.2 | Face box | Start a scan. | A box is drawn around the **whole face** and **stays aligned** with it on screen as you move. |
| 3.3 | Skin areas inside the box | Watch the overlay. | The forehead and both cheek areas are drawn **inside** the face box and move with it. |
| 3.4 | Two faces | Have a second person lean into the frame part-way through. | The scan **aborts** with "More than one face detected". |
| 3.5 | Face lost | Leave the frame for about 3 s. | The scan pauses or resets and asks you to face the camera. |
| 3.6 | Embedding runs | Complete a scan with `logcat` running. | `SentinelFace` logs show embeddings being computed every few frames (not every frame) and "template built from N frames" with N between 10 and 20. |
| 3.7 | Performance | Watch during a scan. | The preview stays smooth. The phone doesn't get noticeably hot within 30 s. |
| 3.8 | No images saved | After a scan, check *Files* and the app storage (*Settings → Apps → app → Storage*). | No new images. App data stays small. |

---

## 3. Milestone 4: Random challenge + new app screens + extended payload

| # | Test | Steps | Expected result |
|---|---|---|---|
| 4.1 | Build | Section 0, step 3 | Builds. |
| 4.2 | Four screens | Launch the app. | **Scan QR → Consent → Face Scan → Result**, in orange/white styling with large text. There's no debug menu. |
| 4.3 | Consent | Scan a QR code. | The consent screen appears before the camera starts. Declining returns to Scan QR. |
| 4.4 | Challenge appears | Start a scan. | Part-way through, a big prompt appears: "Blink twice now", "Turn your head left" or "Turn your head right". The portal shows the same challenge. |
| 4.5 | Challenge passed | Do what the prompt says. | It's marked done, and the scan finishes with a pass. |
| 4.6 | Challenge ignored | Don't respond to the prompt. | After the time limit: **"Challenge failed"**, and the result is rejected. |
| 4.7 | Wrong action | For "turn left", turn right instead. | Rejected with "Challenge failed". |
| 4.8 | Challenge is random | Run 5 scans. | You get a mix of challenges. |
| 4.9 | Key type | Run one scan with `logcat` running. | `SentinelHard` logs `key_security_level=STRONGBOX` on the Pixel 7. |
| 4.10 | Result reasons | Trigger a pass, a challenge fail and a photo fail. | The result screen shows approved or rejected **with the reason**, and the portal shows the same thing. |
| 4.11 | Live portal steps | Watch the laptop during a scan. | The portal steps advance live: *Waiting for scan → Measuring pulse → Challenge → Face match → Result*. |

---

## 4. Milestones 5–7 (backend and portal; phone used end to end)
There are no Android code changes in these milestones, so the app doesn't need to be rebuilt unless a note says otherwise. Run section 5 after M7.

---

## 5. The 5 demo scenarios (final acceptance, M8)

Team member **A** is the registered pensioner. Team member **B** is someone else. Do these in order.

| # | Scenario | Steps | Expected result on phone | Expected result on portal |
|---|---|---|---|---|
| S1 | **Register A** | Officer logs in → Register Pensioner → enter A's dummy details → QR code → A scans and completes the face scan → officer clicks **Approve** | "Registration captured" | A appears in Records as **Active** (green badge). A ledger entry is added. |
| S2 | **A submits a life certificate** | Submit Life Certificate → enter A's pension ID → QR code → A scans | "Approved" | Stepper completes, then the **certificate card** shows the score and ledger hash, plus a "Certificate issued for 2026" toast. |
| S3 | **B pretends to be A** | Submit Life Certificate with **A's** pension ID → **B** scans | "Rejected: face does not match" | Red result: **Rejected: face does not match**. It's counted under face mismatch on the Treasury page. |
| S4 | **Photo of A** | Submit with A's ID → hold a **printed photo** of A up to the phone | "Rejected: no pulse detected" | Red result: **Rejected: no pulse detected**. |
| S5 | **Video of A** | Submit with A's ID → play a **video** of A on another phone or laptop screen in front of the camera | "Rejected: challenge failed" (and/or "screen replay detected") | Red result with the same reason. |

After S1–S5, the **Audit Ledger → Verify chain integrity** button shows green. The Treasury page shows 1 certificate issued and 3 rejections split by reason.

Record the score shown for S2 and S3 (for threshold calibration).

---

## 6. Log tags

The app writes to these `logcat` tags:

| Tag | What it logs |
|---|---|
| `SentinelHard` | App flow, QR parsing, network calls, signing, key security level |
| `SentinelHardNative` | C++ rPPG engine: BPM, SNR (dB), window fill |
| `SentinelDSP` | Stability gate and face-lost resets |
| `SentinelTelemetry` | Per-estimate BPM/SNR summary |
| `TelemetryStreamer` | Live telemetry WebSocket |
| `SentinelFace` | Face detection, face count, embeddings, template building (M3+) |
| `SentinelChallenge` | Challenge issued, landmark values, pass or fail (M4+) |

---

## 7. What to send back if something fails

Send all four of the following. A description alone is usually not enough to fix a remote build or device problem.

### 7.1 The exact error text
- **Build error:** copy the **whole** *Build* output from the first `e:` / `error:` / `FAILURE` line to the end. Include the CMake output if the error is in native code. Text, not a screenshot.
- **Crash:** the full stack trace from `logcat` (it starts with `FATAL EXCEPTION`).
- **Wrong result:** the exact message shown on the phone and on the portal, and what you expected instead.

### 7.2 `adb logcat` with the app's tags
Clear the log, start capturing, then reproduce the problem:

```powershell
adb logcat -c
adb logcat -v time SentinelHard:V SentinelHardNative:V SentinelDSP:V SentinelTelemetry:V TelemetryStreamer:V SentinelFace:V SentinelChallenge:V AndroidRuntime:E *:S > phone_log.txt
```

Press Ctrl+C after the problem happens, then send `phone_log.txt`. For a crash, also send the unfiltered log:

```powershell
adb logcat -d -v time > phone_log_full.txt
```

### 7.3 A screen recording
Use the Pixel's built-in *Screen record* (Quick Settings). Start before scanning the QR code and stop after the result. If the portal matters, also record or photograph the laptop screen.

### 7.4 Context
- Which milestone and test number (e.g. "M2 test 2.8").
- Commit hash: `git rev-parse --short HEAD`.
- Backend terminal output around the time of the failure.
- Lighting and position (e.g. "indoor, window behind me, phone in hand").
