# Walkthrough - Face Detection and ROI Signal Extraction

I have integrated ML Kit Face Detection with CameraX to isolate the forehead region and extract biometric signals (green channel mean) via C++.

## Changes Made

### 1. Dependency Updates
- Added ML Kit Face Detection (`play-services-mlkit-face-detection`) and CameraX dependencies to `libs.versions.toml` and `app/build.gradle.kts`.

### 2. Kotlin Implementation (`MainActivity.kt`)
- **Face Detection**: Configured an ML Kit `FaceDetector` for fast processing.
- **ROI Logic**: Implemented `analyzeFrame` to calculate a specific forehead ROI (top 20% of the face).
- **Rotation Correction**: Added `mapRoiToSensor` to translate coordinates from the upright display frame back to the raw landscape sensor space used by OpenCV.
- **Conversion Utility**: Added `yuvToByteArray` to convert `ImageProxy` frames to NV21 format for C++.

### 3. Native Implementation (`native-lib.cpp`)
- **Updated JNI**: Updated `processFrame` to accept ROI coordinates.
- **Safe Cropping**: Implemented a `safeRoi` that intersects with frame boundaries to prevent crashes.
- **Signal Extraction**: Extracts the mean intensity of the **green channel** from the forehead region.
- **Verification Logging**: Added `LOGI` to output frame dimensions and ROI coordinates for debugging alignment.

## Verification Results

### Build Status
- Ran `./gradlew :app:assembleDebug`.
- **Result**: Build finished successfully. All JNI signatures and dependencies are correctly resolved.

### Memory & Performance
- Configured CameraX with `STRATEGY_KEEP_ONLY_LATEST` to prevent frame backpressure and memory overflows.
- Used `GetByteArrayElements` and `ReleaseByteArrayElements` with `JNI_ABORT` for high-performance, no-copy memory access.

> [!TIP]
> Use Logcat with the tag `SentinelHardNative` to verify that your ROI coordinates are correctly mapping within the frame boundaries during live testing.
