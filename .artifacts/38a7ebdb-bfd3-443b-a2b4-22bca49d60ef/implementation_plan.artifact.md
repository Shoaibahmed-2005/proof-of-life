# Final Step: Camera Integration & Hardware Deployment

To test the biometric monitor "right now" on a physical device, we need to finalize the CameraX integration. This will pipe live frames from your phone's camera into the face detector and rPPG engine we've built.

## Proposed Changes

### Manifest & Permissions

#### [MODIFY] [AndroidManifest.xml](file:///C:/Users/praji/AndroidStudioProjects/SentinelHard/app/src/main/AndroidManifest.xml)
- Add the `CAMERA` permission and hardware feature requirements.

### Kotlin Layer

#### [MODIFY] [MainActivity.kt](file:///C:/Users/praji/AndroidStudioProjects/SentinelHard/app/src/main/java/com/example/sentinelhard/MainActivity.kt)
- **Permission Request**: Add code to check and request camera permissions at runtime.
- **CameraX Setup**:
    - Initialize `ProcessCameraProvider`.
    - Configure `Preview` use case.
    - Configure `ImageAnalysis` with `STRATEGY_KEEP_ONLY_LATEST` and bind it to our `analyzeFrame` logic.
- **Compose UI Update**:
    - Use `AndroidView` to embed the CameraX `PreviewView`.
    - Layout the `CameraPreview` as the bottom layer, with the `HUDOverlay` on top.

## Verification Plan

### Automated Tests
- Run `./gradlew :app:assembleDebug` to ensure all imports and use cases are correctly configured.

### Manual Verification (The Test)
1. **Deploy**: Plug in a physical Android device and run the app.
2. **Permission**: Grant camera permission when prompted.
3. **Detection**: Point the camera at your face.
    - The green waveform should begin scrolling at the bottom.
    - After ~2 seconds, the **BPM** and **SNR** values should populate.
    - The badge should switch to **VERIFIED HUMAN**.
4. **Spoof Test**: Point the camera at a photo of a face.
    - Observe the **SNR** drop and the badge switch to **SPOOF DETECTED**.

## User Review Required

> [!IMPORTANT]
> A physical device is **strongly recommended** for testing. Emulators often have simulated camera feeds that lack the subtle color fluctuations (photoplethysmogram) required for the C++ engine to calculate an accurate heart rate.
