# TESTING_CHECKLIST.md: Phone Tests (Pixel 7)

This is for the teammate who builds and tests the Android app. Claude writes the code on a laptop **without** an Android toolchain, so the phone tests here are the only real check of the Android side. Please follow them in order and report back using section 7.

Each milestone's section is updated when that milestone is delivered. Thresholds marked _(calibrating)_ are first guesses that your results will tune.

## ▶ One combined test run (everything, in this order)

All milestones are delivered (app version **4.0-challenge**). Do one full round in this order; each step assumes the ones before it passed.

| Order | Section | What it covers | Time |
|---|---|---|---|
| 1 | **0** Before every test round | Pull, toolchain, build + install, backend, portal, log capture | 15 min |
| 2 | **B** If the Android build fails | Only if step 1's build fails: which commit to look at | – |
| 3 | **W** Wi-Fi setup (W.1–W.7) | Phone and a second phone reach the laptop over Wi-Fi | 10 min |
| 4 | **1** Milestone 2 (2.1–2.16) | rPPG engine, stability gate, QR-carried URL (already passed once; quick re-run of 2.1–2.6 is enough) | 10 min |
| 5 | **D** Scan speed comparison (D.1–D.5) | Your phone vs your friend's: camera, lighting or thresholds? Send the numbers | 20 min |
| 6 | **2** Milestone 3 (3.1–3.11) | Face box, one-face rule, embeddings | 10 min |
| 7 | **3** Milestone 4 (4.1–4.17) | Four screens, consent, random challenge, registration and life certificate from the phone | 20 min |
| 8 | **5** The 5 demo scenarios (S1–S5 + finale) | The presentation, end to end, with two people | 15 min |

Send the results with section 7 (logs, recordings, the diagnostics numbers from D).

---

## B. If the Android build fails: where to look

The code was written without compiling it. The last build that was **confirmed on the phone** is `c05c79f` (Milestone 2). The later commits that change the Android app, from most to least likely to break the build:

| Look here first | Commit | What it added | Typical error |
|---|---|---|---|
| 1 | `4089473` (M3) | LiteRT 1.4.2 dependency, `mobilefacenet.tflite` asset, new C++ `face_core.cpp` + JNI functions (`FaceNative`), CMake change | Dependency resolution (`litert`), duplicate `org.tensorflow.lite` classes, C++ compile errors, `UnsatisfiedLinkError` at runtime (JNI name mismatch) |
| 2 | `4125eea` (M4) | New Compose screens (`ui/Screens.kt`, `ui/Theme.kt`), `ChallengeVerifier`, `KeyInfo` key level, rewritten `MainActivity` | Kotlin compile errors (an API not in Compose BOM 2023.08.00 / Material3 1.1.1), unresolved reference |
| 3 | `084af5b` (Step 2) | `CameraTuning.kt` (Camera2Interop fps range, AE/AWB lock), `ScanDiagnostics.kt` | Opt-in or Camera2Interop API errors |
| 4 | `82bfbd2` (Wi-Fi) | Manifest `networkSecurityConfig`, `res/xml/network_security_config.xml`, `ApiClient` probing | Resource/manifest merge errors |

To pin it down: `git checkout <commit>` and build each of these in turn, oldest first (`82bfbd2` → `084af5b` → `4089473` → `4125eea`); the first one that fails is the culprit. Then `git checkout master` again. Send the error text (section 7.1) and the commit that first fails.

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
   python run.py
   ```
5. **Connect the phone to the backend** using one of these:
   - USB (easiest): `adb reverse tcp:8000 tcp:8000`. The phone then reaches the laptop at `localhost:8000`.
   - Same Wi-Fi: the portal puts the laptop's LAN IP in the QR code. Allow port 8000 through Windows Firewall.
6. **Start the portal**: `npm install` (first time only), then `npm run dev`, and open http://localhost:5173.
7. **Start a log capture** before testing (section 7.2) so failures are already recorded.

Test conditions: indoor, even light on the face (no strong window light behind you), phone held about 30–40 cm from the face, stable if possible (resting on a table is best).

---

## W. Wi-Fi setup (do this before any other test)

Full instructions: `ANDROID_BUILD.md`, section "Wi-Fi setup". In short:
1. Start the backend with `python run.py` (**not** plain `uvicorn`) and the portal with `npm run dev`.
2. Set the laptop's Wi-Fi to *Private* and add the two firewall rules (ports 8000 and 5173).
3. Check the address the portal's QR page shows.

| # | Test | Steps | Expected result |
|---|---|---|---|
| W.1 | Backend banner | Start the backend. | It prints "QR codes use http://<laptop Wi-Fi IP>:8000" and, a second later, `LAN self-check OK`. Note any "network adapters found" warning and the list it prints. |
| W.2 | Phone browser | On a phone that has **never** used USB/adb, open `http://<laptop-ip>:8000/api/v1/health` in Chrome. | `{"status":"ok",…}`. If it times out: firewall or Wi-Fi isolation (ANDROID_BUILD.md steps 3 and 5). |
| W.3 | Portal from another device | On a second device, open `http://<laptop-ip>:5173`. | The portal loads, and creating a QR code works (no "cannot reach the server" message). |
| W.4 | App over Wi-Fi | **Unplug USB** (no `adb reverse`). Scan a QR code. | The camera opens (no "Can't reach the laptop"). |
| W.5 | Error is explained | Stop the backend, then scan a QR code. | "Can't reach the laptop", listing each address tried with a reason (e.g. "connection refused…"). Send a photo of this screen if W.4 failed. |
| W.6 | Second phone | Repeat W.2 and W.4 with another phone (e.g. your father's) on the same Wi-Fi. | Same results as the first phone. |
| W.7 | Hotspot fallback (only if W.2 fails on the venue Wi-Fi) | Connect the laptop and phones to one phone's hotspot, restart the backend, and repeat W.1–W.4. | Works over the hotspot. |

---

## 1. Milestone 2: rPPG fixes + QR-carried backend URL

**What changed in the app:**
- The home screen has one button, "Scan QR code". The old "Login Directly on Phone" option is gone.
- The rPPG engine is rewritten: a 10 s window, a 0.7–4 Hz band-pass filter, and an SNR in dB updated twice a second.
- The pulse is taken from the forehead and both cheeks (three green boxes on screen).
- The scan passes only when 5 estimates in a row agree within ±3 BPM and the SNR is at least the minimum. The minimum comes from the QR code (backend `.env` `MIN_SNR_DB`, default 3.0 dB).
- Without a stable pulse within 30 s, the app reports "No pulse detected".
- The backend address comes from the QR code.

The laptop portal is the new Jeevan Suraksha portal (Milestone 7). It shows the phone's live progress and results.

**Before the first scan:** open the portal (`http://<laptop-ip>:5173`), go to **Help & FAQs → Practice scan** (or `/practice`), tick the consent box, click **Start practice scan**, and scan the QR code on screen.

**With the Milestone 4 app** (4.0-challenge): after scanning, a **consent screen** appears; tap **I agree, start the scan**. The three green skin boxes are shown only with **Diagnostics** on (bottom right of the white card), and "Verified" is now **Practice scan passed**. Everything else in this section is unchanged.

| # | Test | Steps | Expected result |
|---|---|---|---|
| 2.1 | Build | Section 0, step 3 | Builds with no errors and the app installs. |
| 2.2 | QR carries the backend URL | The portal shows a QR code. Scan it with the app. | "Connecting to the portal…", then the front camera opens. **No IP was typed or built into the app.** `logcat` (tag `SentinelHard`) shows `QR scanned: … base_url=http://<laptop IP>:8000 min_snr_db=3.0` and `Backend candidates … → using …`. |
| 2.3 | "Measuring…" gate | Sit still facing the camera. | The screen says **"Measuring…"**, and the progress ring fills over about 10 s. It must **not** show "Pulse steady" before about 9.5 s. The BPM number stays grey until steady. |
| 2.4 | BPM converges | Keep still. At the same time, count your pulse on your wrist for 30 s and multiply by 2. | The BPM settles and stops climbing. When it passes, it's within about **±5 BPM** of your wrist count. Note both numbers. |
| 2.5 | SNR updates live | Watch the SNR value (now in real dB). | It **changes** over time (not a constant 2.8). It rises as the reading stabilises. Note the value at the moment of passing. |
| 2.6 | Smooth waveform | Watch the waveform. | A **smooth, regular wave** at your pulse rate, not jagged noise. |
| 2.7 | Pass → backend | Complete a scan. | The phone shows success, **and the laptop portal updates at the same moment**. The backend log shows the request accepted. |
| 2.8 | **Printed photo** | Hold a printed photo of a face in front of the camera for 30 s. | It stays on "Measuring…" or fails with "No pulse detected". **It must never pass.** Note the SNR shown. |
| 2.9 | Motion | Shake or turn your head a lot during the scan. | It keeps measuring or asks you to hold still. There's no false pass. |
| 2.10 | Second scan | Finish one scan, return, and scan a **new** QR code straight away. | The new scan starts from zero ("Measuring…" again, at least 10 s). It **doesn't** auto-submit instantly. |
| 2.11 | Camera released | Finish a scan and go to the result screen. | The camera privacy dot/indicator turns off. |
| 2.12 | Wi-Fi path | Repeat 2.2 and 2.7 without `adb reverse`, with the phone on the same Wi-Fi as the laptop. | Works without rebuilding. |
| 2.13 | Live progress on the portal | Watch the laptop during a scan. | The portal shows "Measuring pulse… NN BPM · signal X dB · NN%", updating about every half second. |
| 2.14 | Photo → rejection on both screens | Test 2.8 until it times out (30 s). | Phone: "Not verified: No pulse detected…". Portal: red **Rejected** box with the same reason and a *Try again* button. |
| 2.15 | Face lost | During a scan, move out of view for 2 s, then come back. | The boxes disappear and the measurement restarts from zero ("Measuring…", ring empty). It still passes about 10 s after you return. |
| 2.16 | Wrong QR | Scan any other QR code (e.g. a URL). | "Not a portal QR code". No crash. |

**Send back for M2:**
- the wrist BPM vs the app BPM for 3 scans;
- the SNR at pass time for each scan (`SentinelTelemetry` log lines);
- the highest SNR shown during the photo test;
- one full `logcat` capture of a passing scan and one of the photo test.

These set `MIN_SNR_DB` in `backend/.env`, with no rebuild needed. It should sit between the photo's highest SNR and the genuine scans' pass-time SNR.

---

## D. Scan speed comparison (camera vs lighting vs thresholds)

**Goal:** find out with data why a scan is slow or never verifies. Is it the phone's camera, the lighting, or our thresholds (10 s window, 5 readings within ±3 BPM, `MIN_SNR_DB` 3.0)? **Don't change any threshold before doing this.**

**Setup:**
- Same person, same room, same chair, same lighting. Phone about 30–40 cm from the face, at eye level, resting on something if possible.
- On the scan screen, tap **Diagnostics** (bottom-right) to show the live readout. It's off by default for the demo.
- Keep a logcat capture running (section 7.2 includes the `SentinelDiag` tag).

| # | Test | Steps | Record |
|---|---|---|---|
| D.1 | Phone A, 5 scans | Practice Scan on the portal → scan the QR code → sit still. Count your wrist pulse for 30 s during each scan. | For each scan: **time to verify** (the `SCAN SUMMARY … time=` line, or the stopwatch), app BPM vs wrist BPM, **SNR** at pass, **fps**, and the `waiting for` value if it was slow. |
| D.2 | Phone B (e.g. your father's), 5 scans | The same, with the other phone, same person and same spot. | Same values. |
| D.3 | Bright light | Phone A, face lit by a lamp or window in front of you (not behind). | Same values. |
| D.4 | Dim light | Phone A, main light off. | Same values. |
| D.5 | Photo check | Phone A: hold a printed photo of the same person for 30 s. | The highest SNR it reached. It must **not** pass. |

**After testing, on the laptop:**

```powershell
cd backend
python scripts/calibrate_thresholds.py label-scans --last 1 --as photo      # right after D.5
python scripts/calibrate_thresholds.py scans                                 # per-phone report + diagnosis
```

Label the genuine scans too (`label-scans --last N --as genuine`, right after each batch). The report then prints a table of which `MIN_SNR_DB` values would pass the genuine scans while rejecting the photo. Send the `scans` output, or `http://<laptop>:8000/api/v1/diagnostics.csv` (officer login needed), plus the logcat files.

### How to read the diagnostics

The readout (and each `SentinelDiag` line) shows: time, camera fps and range, pulse and spread, SNR (and minimum), light (0–255), AE lock, and **waiting for**. "Waiting for" names the gate that's still blocking:

| You see | It means | So the cause is |
|---|---|---|
| `camera: ~15 fps` (or `avg_fps` under 20), range not `[30,30]` | The camera delivers too few frames. | **Camera/phone.** Try brighter light (many cameras drop to 15 fps in dim light). If it stays low in good light, that phone's camera is the limit. |
| `light:` under ~60, prompt "Move to brighter light" | The face is too dark; the pulse signal is buried in sensor noise. | **Lighting.** |
| `waiting for: window filling` for ~10 s, then passes | Normal: the first 10 s always fill the window. | Nothing wrong (it's the minimum time by design). |
| `waiting for: readings not yet stable` for a long time, `spread` 3–6 BPM, SNR above minimum | The heart-rate readings are close but not within ±3 BPM. | **Threshold** may be tight (`RPPG_STABLE_TOLERANCE_BPM`). Only if this repeats with good light and ~30 fps. |
| `waiting for: readings not yet stable`, `spread` large (10+ BPM) | The readings jump around: noise. | **Motion, lighting or camera**, not the threshold. |
| `waiting for: SNR below minimum`, SNR within ~1 dB of the minimum | The signal is almost strong enough. | Possibly the **threshold**, but only lower `MIN_SNR_DB` if the photo test (D.5) stays well below the new value. |
| `waiting for: SNR below minimum`, SNR far below the minimum | The pulse is too weak. | **Camera or lighting.** |
| `waiting for: face lost`, or "face lost" counted often | Face detection keeps losing the face. | **Positioning** (distance, angle, glasses glare) or a weak camera. |
| `AE lock: no` | This phone can't lock exposure; brightness changes add noise. | **Camera** limitation (still usable). |

**Rule of thumb:**
- Phone B much slower than phone A in the same conditions, with lower fps → **camera**.
- Both slow in dim light but fine in bright light → **lighting**.
- Both phones at ~30 fps, bright light, blocked on "readings not yet stable" with a small spread, or SNR just under the minimum → **thresholds**. Change them in `backend/.env` (no app rebuild needed) using the `scans` report, never below what the photo reached.

---

## 2. Milestone 3: Face detection, same-face box, embeddings

Use **Practice scan** on the portal. Registration and life certificates also need the Milestone 4 challenge, so they are tested in section 3.

| # | Test | Steps | Expected result |
|---|---|---|---|
| 3.1 | Build | Section 0, step 3 | Builds. The APK is about **8–10 MB larger** (face model ~5 MB + LiteRT runtime). On app start, `SentinelFace` logs `Loaded mobilefacenet.tflite (5233552 bytes): input [1, 112, 112, 3] output [1, 192]`. |
| 3.2 | Face box | Start a scan. | A thin **white box around the whole face** stays aligned with the face on screen as you move. |
| 3.3 | Skin areas inside the box | Tap **Diagnostics** (bottom right of the white card). | The three green boxes (forehead, both cheeks) appear **inside** the white face box and move with it. |
| 3.4 | Two faces | A second person leans into the frame part-way through. | The scan **stops at once**. Phone: "Not accepted: More than one face was in view…". Portal: red **Rejected** with the same reason. |
| 3.5 | Face swap | Person A starts the scan, then moves away while person B moves in within 2 s. | The measurement restarts ("Measuring…" and an empty ring again). `SentinelFace`: `Tracked face changed`. |
| 3.6 | Face lost | Leave the frame for about 3 s. | Guidance "Face the camera"; the measurement restarts when you return. |
| 3.7 | Embeddings run | Complete a scan with `logcat` running (section 7.2, tag `SentinelFace`). | Lines `embedding #n: q=… sharp=… luma=… eyes=…px yaw=… pitch=… in N ms`, a few per second (not every frame). At the end: `Face frames: N good of M; sending no face data (practice scan)` with **N ≥ 10** (registrations and life certificates send the template or embedding: tests 4.10–4.11). Note the typical `in N ms` value. |
| 3.8 | Diagnostics readout | Tap Diagnostics during a scan. | The `face frames: N good` count rises during the scan. |
| 3.9 | Poor pose | Scan while looking clearly sideways, or with the phone far below your face. | Fewer good face frames (the quality filter rejects them). Guidance "Move closer" if the face is small. |
| 3.10 | Performance | Watch during a scan. | The preview stays smooth, and the diagnostics fps doesn't drop by more than a few frames compared with before. The phone doesn't get hot within 30 s. |
| 3.11 | No images saved | After a scan, check *Files* / *Photos* and *Settings → Apps → Jeevan Suraksha (SentinelHard) → Storage*. | No new images. App data stays small. |

---

## 3. Milestone 4: Random challenge + new app screens + extended payload

The app now accepts all three QR codes: **Practice scan** (no challenge), **Register Pensioner** (officer) and **Submit Life Certificate**. Keep `adb logcat` running with the tags in section 7.2 (`SentinelChallenge` is new).

| # | Test | Steps | Expected result |
|---|---|---|---|
| 4.1 | Build + unit tests | Section 0, step 3, then `./gradlew testDebugUnitTest` | Builds; the unit tests pass, including the 8 `ChallengeVerifierTest` tests (blink counting, turn direction, time limit). The app shows version **4.0-challenge**. |
| 4.2 | Four screens | Launch the app and do a practice scan. | **Scan QR** (white page, orange "Scan QR code" button, then the camera with an orange frame) → **Consent** (white page, large text, "I agree, start the scan") → **Face Scan** (dark camera view, big face-guide circle and progress ring, prompt at the top, pulse and waveform in a white card) → **Result** (big icon, one-line outcome, reason, "Done"). |
| 4.3 | Consent | Scan a QR code, then tap **Cancel** on the consent screen. | Back to the start; the camera never turned on. Scan again and agree: the face scan starts. |
| 4.4 | Guide circle colour | Watch the circle during a life-certificate scan. | **Orange** while measuring and during the challenge; **green** only after the pulse is steady **and** the challenge is passed. |
| 4.5 | Challenge appears | Portal: Submit Life Certificate (registered pensioner) → scan. | After the pulse is steady (about 10–15 s), a big prompt appears: "Blink twice now", "← Turn your head to your left" or "Turn your head to your right →", with seconds left. The portal's **Challenge** step shows the same action at the same moment. `SentinelChallenge`: `Challenge issued: …`. |
| 4.6 | Turn direction | Get a **Turn left** challenge (repeat until you get one) and turn your head to **your own** left. | It passes within a second. **If it only passes when you turn right**, the sign is reversed on this phone: set `LEFT_YAW_SIGN = -1f` in `face/ChallengeVerifier.kt`, rebuild, and report it. Turn the other way to see the "Other way" hint. |
| 4.7 | Blink | Get a **Blink twice** challenge and blink twice, normally. | The detail line counts "1 of 2", "2 of 2", then it passes. Half-closing your eyes doesn't count. |
| 4.8 | Challenge ignored | Don't respond to the prompt. | After the time limit (QR `challenge.timeout_s`, default 8 s): phone **Not accepted: Challenge failed…**; portal red **Rejected** at the Challenge step. `SentinelChallenge`: `Challenge failed: … (time limit: …)`. |
| 4.9 | Challenge is random | Run 5 life-certificate or registration QR codes. | A mix of the three actions (chosen by the backend, not the phone). |
| 4.10 | Registration | Officer: Register Pensioner → QR → scan with the consent, pulse and challenge. | Phone: **Face registered** ("The officer will now approve…"). Portal: **Face captured**, then the officer clicks **Approve** → Active. `SentinelFace`: `sending reference template (192 values, best 15 frames)`. |
| 4.11 | Life certificate | Submit Life Certificate with the registered person. | Phone: **Life certificate issued**. Portal: certificate card with score. `SentinelFace`: `sending probe embedding (192 values, best 5 frames)`. |
| 4.12 | Key type in the payload | Look at `SentinelHard` at app start. | `Signing key: STRONGBOX` on the Pixel 7 (TEE on phones without StrongBox; on Android 11 and older a StrongBox key shows as TEE). The portal's Records → pensioner → device shows the same key type. |
| 4.13 | Face lost during the challenge | During the challenge, move out of the frame for 3 s. | The scan goes back to measuring the pulse (ring restarts), then asks for the challenge again. |
| 4.14 | Face not captured | Hard to trigger on purpose. If it happens (very dark, or the face always turned away): | Phone: **Not accepted: The face could not be captured clearly…**; not counted toward freezing. |
| 4.15 | Result reasons | Trigger a pass, a challenge fail and a photo (no pulse). | Each result screen shows the outcome **and the reason**, and the portal shows the same at the same time. |
| 4.16 | Live portal steps | Watch the laptop during a life-certificate scan. | *Waiting for scan → Measuring pulse → Challenge → Face match → Result* advance live. |
| 4.17 | Timing | Note the time from "I agree" to the result screen for 3 good scans. | Pulse phase as in section D, plus a few seconds for the challenge. Report the times. |

## 4. Milestones 5–7 (backend and portal)
No phone tests of their own: the backend and portal are tested on the laptop (`pytest`, 73 tests; `scripts/demo_check.py` runs the five scenarios with a simulated phone). The phone exercises them in sections 3 and 5.

---

## 5. The 5 demo scenarios (final acceptance, M8)

Team member **A** is the registered pensioner. Team member **B** is someone else. Do these in order.

**Use the same Pixel 7 for every scenario.** The backend binds A's pension to the phone used in S1. If B scans with a different phone, the result is "Rejected: this phone is not the device registered for this pensioner", not the face mismatch that S3 is meant to show.

| # | Scenario | Steps | Expected result on phone | Expected result on portal |
|---|---|---|---|---|
| S1 | **Register A** | Officer logs in → Register Pensioner → enter A's dummy details → QR code → A scans, agrees on the consent screen, completes the face scan and the challenge → officer clicks **Approve** | "Face registered" | A appears in Records as **Active** (green badge). A ledger entry is added. |
| S2 | **A submits a life certificate** | Submit Life Certificate → enter A's pension ID → QR code → A scans | "Life certificate issued" | Stepper completes, then the **certificate card** shows the score and ledger hash, plus a "Certificate issued for 2026" toast. |
| S3 | **B pretends to be A** | Submit Life Certificate with **A's** pension ID → **B** scans | "Not accepted" + face does not match | Red result: **Rejected: face does not match**. It's counted under face mismatch on the Treasury page. |
| S4 | **Photo of A** | Submit with A's ID → hold a **printed photo** of A up to the phone | "Not accepted" + no pulse (after about 30 s) | Red result: **Rejected: no pulse detected**. |
| S5 | **Video of A** | Submit with A's ID → play a **video** of A on another phone or laptop screen in front of the camera | "Not accepted" + challenge failed (or no pulse, if the screen shows no clear pulse) | Red result with the same reason. |

After S1–S5, the **Audit Ledger → Verify chain integrity** button shows green. The Treasury page shows 1 certificate issued and 3 rejections split by reason.

**A's pension is frozen after S5.** With `MAX_FAILED_ATTEMPTS=3` (backend `.env`), the three failed attempts in S3–S5 freeze it, and the portal shows **Frozen**. This is the finale: "three attacks, and the pension is frozen until an officer reviews it". The officer then opens **Review Queue → Frozen pensions → Restore** and gives a reason, and A is Active again.

**Rehearsing from a clean state:** stop the backend, then run `python scripts/reset_demo.py --yes --seed` in `backend/`, and start it again. The old data is moved to `backend/data/backups/`, not deleted.

**Rehearsing without the phone:** `python scripts/demo_check.py` (in `backend/`, backend running) runs S1–S5, the freeze and the restore with a simulated phone and prints ok/FAIL for each; `simulate_phone.py` does single scans (see `backend/README.md`). The presentation itself is in `DEMO_SCRIPT.md`.

Record the score shown for S2 and S3 (for threshold calibration).

---

## 6. Log tags

The app writes to these `logcat` tags:

| Tag | What it logs |
|---|---|
| `SentinelHard` | App flow, QR parsing, network calls, signing, key security level |
| `SentinelHardNative` | C++ rPPG engine: every estimate (BPM, SNR dB, median SNR, window fill, stable, skin fraction, pixels) |
| `SentinelDSP` | Stable-pulse decision, 30 s no-pulse timeout, face-lost restarts |
| `SentinelTelemetry` | Per-estimate BPM/SNR summary (one line every 0.5 s) |
| `SentinelDiag` | Scan diagnostics: camera fps ranges, exposure lock, per-estimate fps/BPM/SNR/spread/gate/light, and one `SCAN SUMMARY` line per scan |
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
adb logcat -v time SentinelHard:V SentinelHardNative:V SentinelDSP:V SentinelDiag:V SentinelTelemetry:V TelemetryStreamer:V SentinelFace:V SentinelChallenge:V AndroidRuntime:E *:S > phone_log.txt
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
