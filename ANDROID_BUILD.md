# ANDROID_BUILD.md: Build, Install and Connect the App

Toolchain versions and first-time setup are in `ANDROID_STUDIO_SETUP.md`. Phone test steps are in `TESTING_CHECKLIST.md`.

## 1. Build and install

**Android Studio:** open the repo root (`sih-iob/`), wait for Gradle sync, then click *Run 'app'* with the Pixel connected.

**Terminal** (repo root):

```powershell
.\gradlew :app:assembleDebug     # → app\build\outputs\apk\debug\app-debug.apk
.\gradlew :app:installDebug      # installs on the connected phone (adb devices must list it)
.\gradlew :app:testDebugUnitTest # JVM unit tests (challenge logic); no phone needed
```

The NDK version is pinned in `app/build.gradle.kts` (`ndkVersion = "28.2.13676358"`). If it isn't installed, run `sdkmanager "ndk;28.2.13676358"`.

To install an APK someone else built: `adb install -r app-debug.apk`.

## 2. Connect the phone to the laptop backend

The app has **no hard-coded address**. The portal's QR code carries the backend URL, the session, the purpose, a single-use nonce, and the minimum pulse-signal quality (`min_snr_db`). After scanning, the app tries the QR's address and then `localhost`, and uses the first one that answers `/api/v1/health`.

Start the backend so other devices can reach it:

```powershell
cd backend
.\venv\Scripts\Activate.ps1
python run.py        # listens on 0.0.0.0:8000 and prints the address phones will use
```

Then pick **one** of these:

| Option | When | How |
|---|---|---|
| **Same Wi-Fi** (default) | Phone and laptop on the same network | Nothing to configure: the QR code carries the laptop's LAN IP. If it can't connect, allow **port 8000** for Python in Windows Firewall (*Allow an app through firewall*, or `netsh advfirewall firewall add rule name="IoB backend" dir=in action=allow protocol=TCP localport=8000`). |
| **USB cable** | Wi-Fi blocks device-to-device traffic (common on venue/guest Wi-Fi) | `adb reverse tcp:8000 tcp:8000`. The app falls back to `localhost:8000`, which now reaches the laptop. Re-run it after each reconnect. |
| **cloudflared tunnel** | Different networks, or a locked-down network | `cloudflared tunnel --url http://localhost:8000`, then set `PUBLIC_BASE_URL=https://<name>.trycloudflare.com` in `backend/.env` and restart the backend. QR codes then carry the tunnel URL. |

Changing networks or laptops needs **no rebuild**: generate a new QR code.

## Wi-Fi setup (any phone, any laptop on the same Wi-Fi)

Do this once per laptop. Then check with a phone that has **never** been connected by USB.

**1. Start both servers so the network can reach them.**
- Backend: `python run.py` (in `backend/`).
  - It listens on **0.0.0.0** (all adapters). Plain `uvicorn app.main:app` only listens on 127.0.0.1: USB works but Wi-Fi phones can't connect, which is the most common cause of "other phones can't connect".
  - At startup it prints the address the QR codes will use, and warns if the laptop has several network adapters (VPN, WSL, VirtualBox, Docker).
  - A second later it logs `LAN self-check OK` (or a loud warning if the Wi-Fi address doesn't answer).
- Portal: `npm run dev`. It runs with `--host` on port 5173, so any device on the Wi-Fi can open `http://<laptop-ip>:5173`.

**2. Check the address the QR codes use.** The QR pages show "The phone will connect to http://…:8000". It must be the laptop's **Wi-Fi** IPv4 address (`ipconfig` → *Wireless LAN adapter Wi-Fi* → *IPv4 Address*). If the startup banner picked a VPN/WSL/VirtualBox address, pin the right one in `backend/.env` and restart:

```ini
PUBLIC_BASE_URL=http://192.168.1.10:8000
```

**3. Allow the ports through Windows Firewall.** Easiest: set the Wi-Fi to **Private** (Settings → Network & internet → Wi-Fi → your network → *Private network*). Then, in an **administrator** PowerShell:

```powershell
netsh advfirewall firewall add rule name="Jeevan Suraksha backend 8000" dir=in action=allow protocol=TCP localport=8000 profile=private,public
netsh advfirewall firewall add rule name="Jeevan Suraksha portal 5173" dir=in action=allow protocol=TCP localport=5173 profile=private,public
```

Remove them after the event: `netsh advfirewall firewall delete rule name="Jeevan Suraksha backend 8000"` (and the same for 5173).

**4. Test from the phone's browser first.** Open `http://<laptop-ip>:8000/api/v1/health` in Chrome on the phone. `{"status":"ok"…}` means the network path works, and any remaining problem is in the app. A spinner then time-out means firewall or Wi-Fi isolation (step 3 or 5).

**5. If the Wi-Fi blocks device-to-device traffic.** College, office, hotel and "guest" networks often isolate clients: the phone gets internet but can't reach the laptop. Use a hotspot instead:
- **Phone hotspot:** turn on the hotspot on one phone and connect the laptop *and* the scanning phone(s) to it. Restart the backend so it picks the new address.
- **Laptop hotspot:** Windows *Settings → Network & internet → Mobile hotspot*. The laptop is usually `192.168.137.1`. Connect the phones to it.
- **Fallback:** USB with `adb reverse tcp:8000 tcp:8000` (one phone at a time).

**6. What the app tells you.** If it can't connect, the error lists every address it tried and why:

| Message | Meaning |
|---|---|
| *timed out* | Firewall (step 3), or Wi-Fi isolation (step 5) |
| *connection refused* | Backend not running, or started without `run.py` (step 1) |
| *network unreachable* | Phone and laptop on different networks |
| *blocked by Android's plain-HTTP policy* | Should not happen: the app allows local HTTP. Report it. |

**7. A second phone.** Any phone on the same Wi-Fi can scan a Practice Scan QR code. For registration and life certificates (Milestones 3–4), each pensioner is bound to the phone used at registration, so register a *new* test pensioner with the second phone rather than reusing one registered on the first. Using another phone for an existing pensioner is correctly rejected as "not the registered device".

## 3. What the app does (version 4.0-challenge)

**Four screens: Scan QR → Consent → Face Scan → Result** (DESIGN.md §7: white screens, orange buttons, green success).

1. **Scan QR:** reads `{base_url, session_id, purpose, nonce, challenge, liveness gate}` from the portal's QR code and checks that the laptop is reachable.
2. **Consent:** plain-language points for the purpose (practice, registration or life certificate). Nothing starts until the pensioner agrees.
3. **Face Scan** (front camera, one tracked face only):
   - **Pulse:** forehead and both cheeks inside the face box. 10 s window, 0.7–4 Hz band-pass, SNR in dB twice a second; stable when 5 estimates in a row agree within ±3 BPM and the SNR reaches the QR's minimum (default 3.0 dB). With no stable pulse within 30 s the result is "no pulse".
   - **Challenge** (registration and life certificate): the backend's random action (blink twice, turn left, turn right), checked with ML Kit landmarks within the QR's time limit (default 8 s).
   - **Face:** MobileFaceNet embeddings every few frames. The best 15 are averaged into the registration template, the best 5 into the life-certificate probe.
   - A second face in view stops the scan (MULTIPLE_FACES). Losing the face restarts it.
4. **Signed result:** the payload (build-prompt §4.4, including the key type StrongBox/TEE) is signed in the phone's key store and posted. **Result** shows approved / under review / rejected with the reason, at the same moment as the portal.

No photos or videos are stored or sent. Practice scans skip the challenge and send no face data.

If the build fails, `TESTING_CHECKLIST.md` section B lists which commit to check first.

## 4. Logs

```powershell
adb logcat -v time SentinelHard:V SentinelHardNative:V SentinelDSP:V SentinelDiag:V SentinelTelemetry:V TelemetryStreamer:V SentinelFace:V SentinelChallenge:V AndroidRuntime:E *:S
```

`SentinelHardNative` prints every estimate (BPM, SNR, window fill, stable, skin fraction), which is what threshold calibration needs.

## 5. Testing the engine without a phone

The C++ rPPG engine (`app/src/main/cpp/rppg_core.cpp`) has no Android dependencies, so it is compiled and tested on a laptop:

```powershell
python -m pip install ziglang numpy scipy
python tools/rppg/run_tests.py
```

This runs:
- C++ unit tests;
- a check of the filters against scipy;
- synthetic scenarios (resting, slow and fast heart rates, a weak pulse, a changing heart rate, head motion, the face lost for 2 s, photos, light flicker);
- a comparison with the Python reference implementation;
- a Monte-Carlo run of pass rates for each `MIN_SNR_DB` value.

It also compiles the JNI layer against a stub `jni.h` to catch type errors.
