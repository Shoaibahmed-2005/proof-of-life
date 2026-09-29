# ANDROID_STUDIO_SETUP.md: Toolchain Setup (Windows)

Follow these steps so that every team machine builds the app the same way, from the terminal with `gradlew`. Android Studio is optional (section 7).

Versions are taken from the project files (`gradle/libs.versions.toml`, `gradle/wrapper/gradle-wrapper.properties`, `gradle/gradle-daemon-jvm.properties`, `app/build.gradle.kts`) and the official AGP 9.3 compatibility table (checked 2026-09-29).

## 1. Exact versions

| Component | Version | Why |
|---|---|---|
| **JDK** | **Eclipse Temurin 21** (LTS) | AGP 9.3 needs JDK 17 or newer. The project's Gradle daemon is pinned to JDK 21 (`gradle-daemon-jvm.properties`). |
| Gradle | 9.6.1 | Downloaded automatically by `gradlew`. Don't install it separately. |
| Android Gradle Plugin | 9.3.1 | Set in `libs.versions.toml`. Downloaded automatically. |
| Android SDK Command-line Tools | latest (`commandlinetools-win-15859902_latest.zip`) | Provides `sdkmanager` |
| SDK Platform | **android-35** | `compileSdk = 35` |
| SDK Build-Tools | **36.0.0** | AGP 9.3 default |
| SDK Platform-Tools | latest | Provides `adb` |
| **NDK** | **28.2.13676358** | AGP 9.3 default. The app compiles C++ (`native-lib.cpp`). |
| **CMake** | **3.22.1** | Pinned in `app/build.gradle.kts` |
| Google USB Driver | latest | Lets Windows `adb` talk to the Pixel 7 over USB |
| Python | 3.11+ | Backend |
| Node.js | 20 LTS or newer (24 works) | Web portal |

The disk space needed is about 4 GB for the SDK + NDK, plus about 1 GB of Gradle cache after the first build.

## 2. Install the JDK

In PowerShell:

```powershell
winget install --id EclipseAdoptium.Temurin.21.JDK -e
```

Open a **new** terminal, then check:

```powershell
java -version        # should print: openjdk version "21.x"
echo $env:JAVA_HOME  # should point to the Temurin 21 folder
```

If `JAVA_HOME` is empty, set it (adjust the folder name to what was installed):

```powershell
setx JAVA_HOME "C:\Program Files\Eclipse Adoptium\jdk-21.0.x-hotspot"
```

## 3. Install the Android SDK command-line tools

1. Download `commandlinetools-win-15859902_latest.zip` from https://developer.android.com/studio#command-tools (the "Command line tools only" section).
2. Create the SDK folder and unzip the tools into the **`cmdline-tools\latest`** subfolder. The exact path matters.

```powershell
$sdk = "$env:LOCALAPPDATA\Android\Sdk"
New-Item -ItemType Directory -Force "$sdk\cmdline-tools" | Out-Null
Expand-Archive "$HOME\Downloads\commandlinetools-win-15859902_latest.zip" "$sdk\cmdline-tools\tmp"
Move-Item "$sdk\cmdline-tools\tmp\cmdline-tools" "$sdk\cmdline-tools\latest"
Remove-Item "$sdk\cmdline-tools\tmp"
```

3. Set the environment variables:

```powershell
setx ANDROID_HOME "$env:LOCALAPPDATA\Android\Sdk"
setx PATH "$env:PATH;$env:LOCALAPPDATA\Android\Sdk\cmdline-tools\latest\bin;$env:LOCALAPPDATA\Android\Sdk\platform-tools"
```

Close the terminal and open a new one before continuing.

## 4. Install the SDK packages

```powershell
sdkmanager --licenses
sdkmanager "platform-tools" "platforms;android-35" "build-tools;36.0.0" "ndk;28.2.13676358" "cmake;3.22.1" "extras;google;usb_driver"
```

Answer `y` to every licence prompt. Then check:

```powershell
sdkmanager --list_installed
adb version
```

**Pixel USB driver:** open Device Manager, plug in the phone, right-click the Pixel → *Update driver* → *Browse my computer* → select `%LOCALAPPDATA%\Android\Sdk\extras\google\usb_driver`.

## 5. Point the project at the SDK

`ANDROID_HOME` is usually enough. If Gradle says "SDK location not found", create `local.properties` in the repo root (it's in `.gitignore`, so each machine has its own):

```properties
sdk.dir=C\:\\Users\\<you>\\AppData\\Local\\Android\\Sdk
```

## 6. Build and install from the terminal

In the repo root:

```powershell
.\gradlew --version            # first run downloads Gradle 9.6.1
.\gradlew :app:assembleDebug   # APK → app\build\outputs\apk\debug\app-debug.apk
```

To install on the phone:
1. On the Pixel, enable *Settings → About phone → tap Build number 7 times*, then *Developer options → USB debugging*.
2. Plug the phone in and accept the "Allow USB debugging" prompt.
3. Then run:

```powershell
adb devices                    # the phone should be listed as "device"
.\gradlew :app:installDebug
```

The first build downloads Gradle, AGP and all the libraries, and compiles OpenCV bindings, so it can take 5–10 minutes. Later builds are much faster.

How the app connects to the backend is covered in `ANDROID_BUILD.md`, which is added in Milestone 2.

## 7. Optional: Android Studio instead

Install **Android Studio Quail 4 (2026.1.4)** from https://developer.android.com/studio. Then:
1. Open *SDK Manager* and tick the same packages as in section 4: Android 15 (API 35), Build-Tools 36.0.0, NDK 28.2.13676358 ("Show Package Details"), CMake 3.22.1, Platform-Tools and the Google USB Driver.
2. Set *Settings → Build → Gradle → Gradle JDK* to Temurin 21.
3. Open the **repo root** (`sih-iob/`), not the empty `SentinelHard/` folder.

`gradlew` in the terminal still works exactly as in section 6.

## 8. Backend and portal (same machine)

```powershell
# Backend (port 8000)
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py        # listens on 0.0.0.0:8000 (reachable from phones on the Wi-Fi)

# Portal (in a second terminal, from the repo root)
npm install
npm run dev
```

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `JAVA_HOME is not set` / `java not found` | Redo section 2 and open a new terminal. |
| `SDK location not found` | Set `ANDROID_HOME` or create `local.properties` (section 5). |
| `NDK not configured` / wrong NDK version | Run `sdkmanager "ndk;28.2.13676358"`. |
| `CMake '3.22.1' was not found` | Run `sdkmanager "cmake;3.22.1"`. |
| `adb devices` shows `unauthorized` | Unlock the phone and accept the USB debugging prompt. |
| `adb devices` shows nothing | Install the Google USB Driver (section 4), try another cable, and set USB mode to "File transfer". |
