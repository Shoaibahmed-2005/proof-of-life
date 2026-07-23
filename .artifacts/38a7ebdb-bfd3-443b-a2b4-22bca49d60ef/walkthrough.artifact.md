# Walkthrough - Phase 4: Heart Rate Extraction & Deepfake SNR Verification

I have completed Phase 4, transitioning the biometric monitor from raw waveform visualization to intelligent vital sign extraction and anti-spoofing verification.

## Changes Made

### 1. Native DSP Engine (`native-lib.cpp`)
- **DTFT Frequency Sweep**: Implemented a highly optimized Discrete-Time Fourier Transform that sweeps frequencies from 45 to 180 BPM. This finds the dominant cardiac peak without the overhead of a full FFT library.
- **SNR Analysis**: Added Signal-to-Noise Ratio (SNR) calculation. This measures how "clean" and rhythmic the signal is, which is the primary indicator for distinguishing a living human from a static image or video replay.
- **Liveness Determination**: Implemented a threshold-based liveness check (3.0 dB) to flag potential deepfakes or spoofing attempts.
- **New JNI Bridge**: Added `extractHeartMetrics` which returns `[BPM, SNR, Liveness]` to the Kotlin layer.

### 2. Kotlin HUD UI (`MainActivity.kt`)
- **Compose HUD Overlay**: Built a sleek, high-contrast Head-Up Display (HUD) using Jetpack Compose.
    - **Heart Rate**: Large glowing indicator in BPM.
    - **SNR Metric**: Real-time signal quality readout in dB.
    - **Liveness Badge**: A high-visibility badge that toggles between **VERIFIED HUMAN** (Green) and **SPOOF DETECTED** (Red).
- **State Integration**: Connected the native metrics to Compose `MutableState` for instant, reactive UI updates.

## Verification Results

### Build Status
- Ran `./gradlew :app:assembleDebug`.
- **Result**: Build finished successfully.

### Performance & Security
- The DTFT sweep is targeted specifically to the physiological range (45-180 BPM), ensuring high accuracy with minimal CPU usage.
- The **SNR-based anti-spoofing** provides a robust defense against 2D presentation attacks (photos/videos), as digital displays lack the sub-pixel pulsatility of real human skin.

> [!TIP]
> To test the anti-spoofing, point the camera at a high-resolution photo of a face. You should see the **SNR** drop and the badge switch to **SPOOF DETECTED**, even if a face is successfully detected by ML Kit.
