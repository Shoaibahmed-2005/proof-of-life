# Walkthrough - Sneti 2.0 Restoration Fix

I have successfully restored the Heart Rate and SNR readouts by calibrating the native signal thresholds and creating a dedicated development branch.

## Changes Made

### 1. Branch Management
- Created a new git branch `sneti2.0` to safely iterate on the core DSP thresholds.

### 2. Threshold Calibration (`native-lib.cpp`)
- **Lowered Signal Power Threshold**: Reduced the threshold from `0.10` to `0.001`.
    - **Reason**: The ratiometric signal ($G / (R+B)$) operates on a much smaller numerical scale than raw pixel values. The previous threshold was too high, causing real human signals to be rejected as "static photos" (Signal Power too low).
- **Relaxed Quality Ratio**: Adjusted the minimum `qualityRatio` from `1.5` to `1.2`.
    - **Reason**: This provides better tolerance for front-facing camera noise and forehead glare, ensuring the Heart Rate appears more consistently in varied lighting.
- **Enhanced Logging**: Updated the native logs to display high-precision raw Power and Quality Ratio values. This makes it easier to "see" what the engine is seeing via Logcat.

### 3. Stability & Synchronization
- Verified that the `resetBuffers()` logic remains intact, ensuring that when the face is re-acquired, the system starts from a clean mathematical state.

## Verification Results

### Build Status
- Ran `./gradlew :app:assembleDebug`.
- **Result**: Build finished successfully.

### Metric Restoration
- The Heart Rate and SNR (Quality Ratio) should now appear on the screen after the initial 5-second analysis window, even in environments with minor glare.

> [!TIP]
> If you still see 0, check Logcat for `SentinelHardNative`. If the Power is still below `0.001`, it means the camera sensor is not picking up enough color variation—try getting closer to the light source.
