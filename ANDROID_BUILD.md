# ANDROID_BUILD.md: Build, Install and Connect the App

Toolchain versions and first-time setup are in `ANDROID_STUDIO_SETUP.md`. Phone test steps are in `TESTING_CHECKLIST.md`.

## 1. Build and install

**Android Studio:** open the repo root (`sih-iob/`), wait for Gradle sync, then click *Run 'app'* with the Pixel connected.

**Terminal** (repo root):

```powershell
.\gradlew :app:assembleDebug     # → app\build\outputs\apk\debug\app-debug.apk
.\gradlew :app:installDebug      # installs on the connected phone (adb devices must list it)
```

The NDK version is pinned in `app/build.gradle.kts` (`ndkVersion = "28.2.13676358"`). If it isn't installed, run `sdkmanager "ndk;28.2.13676358"`.

To install an APK someone else built: `adb install -r app-debug.apk`.

## 2. Connect the phone to the laptop backend

The app has **no hard-coded address**. The portal's QR code carries the backend URL, the session, the purpose, a single-use nonce, and the minimum pulse-signal quality (`min_snr_db`). After scanning, the app tries the QR's address and then `localhost`, and uses the first one that answers `/api/v1/health`.

Start the backend so other devices can reach it:

```powershell
cd backend
.\venv\Scripts\Activate.ps1
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then pick **one** of these:

| Option | When | How |
|---|---|---|
| **Same Wi-Fi** (default) | Phone and laptop on the same network | Nothing to configure: the QR code carries the laptop's LAN IP. If it can't connect, allow **port 8000** for Python in Windows Firewall (*Allow an app through firewall*, or `netsh advfirewall firewall add rule name="IoB backend" dir=in action=allow protocol=TCP localport=8000`). |
| **USB cable** | Wi-Fi blocks device-to-device traffic (common on venue/guest Wi-Fi) | `adb reverse tcp:8000 tcp:8000`. The app falls back to `localhost:8000`, which now reaches the laptop. Re-run it after each reconnect. |
| **cloudflared tunnel** | Different networks, or a locked-down network | `cloudflared tunnel --url http://localhost:8000`, then set `PUBLIC_BASE_URL=https://<name>.trycloudflare.com` in `backend/.env` and restart the backend. QR codes then carry the tunnel URL. |

Changing networks or laptops needs **no rebuild**: generate a new QR code.

## 3. What the app does (Milestone 2)

**Scan QR → connect → measure pulse → send signed result → show result.**

- The pulse is measured from the forehead and both cheeks inside the detected face box.
- The rPPG engine uses a 10 s window, a 0.7–4 Hz band-pass filter, and an SNR in dB that is updated twice a second. It shows "Measuring…" until 5 estimates in a row agree within ±3 BPM and the SNR reaches the minimum from the QR code (default 3.0 dB).
- The stable result is signed in Titan M2 (StrongBox) and posted to the backend. The portal updates live.
- With no stable pulse within 30 s of seeing a face (e.g. a photo), the app sends a signed "no pulse" result. Both the phone and the portal then show "No pulse detected".
- Face registration and life-certificate QR codes need the Milestone 3–4 app. This version says so instead of failing silently.

## 4. Logs

```powershell
adb logcat -v time SentinelHard:V SentinelHardNative:V SentinelDSP:V SentinelTelemetry:V TelemetryStreamer:V AndroidRuntime:E *:S
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
