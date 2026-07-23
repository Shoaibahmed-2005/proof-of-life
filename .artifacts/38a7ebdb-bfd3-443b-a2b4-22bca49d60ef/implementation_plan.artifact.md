# Phase 4: Heart Rate Extraction & Deepfake SNR Verification

This plan implements the frequency-domain analysis required to extract Beats Per Minute (BPM) and verify liveness via Signal-to-Noise Ratio (SNR) directly in the native C++ layer.

## Proposed Changes

### Native Layer

#### [MODIFY] [native-lib.cpp](file:///C:/Users/praji/AndroidStudioProjects/SentinelHard/app/src/main/cpp/native-lib.cpp)
- **Implement `extractVitals`**: Add a DSP function that performs a targeted Discrete-Time Fourier Transform (DTFT) sweep (45-180 BPM) over the 150-sample filtered signal buffer.
- **Calculate SNR**: Implement logic to calculate SNR by comparing power around the peak frequency (+/- 3 BPM) vs. the rest of the physiological spectrum.
- **Liveness Check**: Add a threshold (3.0 dB) to determine if the signal is biological or likely a spoof.
- **New JNI Function**: Implement `Java_com_example_sentinelhard_MainActivity_extractHeartMetrics` to return `[BPM, SNR, Liveness]` as a `jdoubleArray`.

### Kotlin Layer

#### [MODIFY] [MainActivity.kt](file:///C:/Users/praji/AndroidStudioProjects/SentinelHard/app/src/main/java/com/example/sentinelhard/MainActivity.kt)
- **JNI Declaration**: Add `external fun extractHeartMetrics(): DoubleArray`.
- **UI State**: Add `currentBpm`, `currentSnr`, and `isLive` as observable state variables.
- **Analyze Integration**: Update `analyzeFrame` to call `extractHeartMetrics()` after `processFrame()` and update the new state variables.
- **Compose UI Update**: Update the layout to display the BPM, SNR, and a liveness indicator (e.g., "LIVE" vs "SPOOF") prominently on the screen.

## Verification Plan

### Automated Tests
- Run `./gradlew :app:assembleDebug` to verify JNI and C++ compilation.

### Manual Verification
- **Liveness Test**: Test with a real face (expect SNR > 3.0) vs. a high-res photo or video of a face (expect low SNR and "SPOOF" status).
- **BPM Accuracy**: Compare the displayed BPM with a known pulse (e.g., a smart watch or manual count).
- **Logcat**: Monitor `SentinelHardNative` for calculation logs.

## User Review Required

> [!IMPORTANT]
> The DTFT sweep is computationally efficient for 150 samples but will run every frame. If performance issues arise, we can consider running the metrics extraction every 10-15 frames instead of every single frame.
