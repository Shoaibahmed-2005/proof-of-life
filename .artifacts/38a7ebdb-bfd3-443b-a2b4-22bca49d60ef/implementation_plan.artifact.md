# Face Detection and ROI Signal Extraction (with Rotation Correction)

This plan integrates ML Kit Face Detection and CameraX to isolate the forehead region from camera frames and pass it to the native C++ layer for biometric signal extraction (rPPG). It specifically addresses coordinate mapping issues caused by camera sensor rotation and memory safety using CameraX backpressure strategies.

## Proposed Changes

### Build Configuration

#### [MODIFY] [libs.versions.toml](file:///C:/Users/praji/AndroidStudioProjects/SentinelHard/gradle/libs.versions.toml)
- Add versions for ML Kit and CameraX.
- Add library definitions for `mlkit-face-detection` and CameraX modules (`core`, `camera2`, `lifecycle`, `view`).

#### [MODIFY] [app/build.gradle.kts](file:///C:/Users/praji/AndroidStudioProjects/SentinelHard/app/build.gradle.kts)
- Add dependencies for ML Kit and CameraX.

### Kotlin Layer

#### [MODIFY] [MainActivity.kt](file:///C:/Users/praji/AndroidStudioProjects/SentinelHard/app/src/main/java/com/example/sentinelhard/MainActivity.kt)
- **JNI Signature**: Update `processFrame` to receive ROI coordinates: `yuvData`, `width`, `height`, `roiX`, `roiY`, `roiW`, `roiH`.
- **CameraX Setup**:
    - Configure `ImageAnalysis` with `STRATEGY_KEEP_ONLY_LATEST` to drop intermediate frames and prevent memory overflows.
    - Set output format to `OUTPUT_IMAGE_FORMAT_YUV_420_888`.
- **Face Detection & ROI Calculation**:
    - Use ML Kit `FaceDetector` with `PERFORMANCE_MODE_FAST`.
    - **Rotation Mapping**: Implement logic to map the detected face bounding box from the upright (rotated) coordinate system back to the raw sensor coordinate system (matching the `ByteArray` sent to C++).
    - Mathematically isolate the forehead (top 20% of the face, 60% width).
- **Frame Conversion**: Add `YuvToByteArray` to convert `ImageProxy` (YUV_420_888) to NV21 `ByteArray`.

### Native Layer

#### [MODIFY] [native-lib.cpp](file:///C:/Users/praji/AndroidStudioProjects/SentinelHard/app/src/main/cpp/native-lib.cpp)
- Update `processFrame` JNI implementation:
    - Construct a `safeRoi` using the passed coordinates, intersected with the frame bounds to prevent crashes.
    - Crop the RGB matrix to the forehead ROI.
    - Calculate and return the mean intensity of the **green channel** (`means[1]`).
    - **Logging**: Add `__android_log_print` to verify frame dimensions and ROI alignment during testing.

## Verification Plan

### Automated Tests
- Run `./gradlew :app:assembleDebug` to verify compilation and JNI consistency.

### Manual Verification
- **Device Logs**: Check Logcat for "Frame Dim: ... | ROI: ..." entries to ensure the ROI correctly maps within the frame boundaries, especially in portrait mode.
- **UI Feedback**: (Future step) Use the returned green channel mean to drive a live waveform.

## User Review Required

> [!CAUTION]
> The ROI mapping logic is critical. If the phone is rotated 90 degrees (Portrait), ML Kit coordinates (0,0 at top-left of screen) must be mapped to sensor coordinates (where 0,0 is at the top-left of the physical landscape sensor). I will implement a robust mapping function to handle this.
