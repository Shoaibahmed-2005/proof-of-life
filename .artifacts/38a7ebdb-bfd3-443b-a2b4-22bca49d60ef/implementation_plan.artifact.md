# Phase 12: Final Optimizations & Bug Fixes

This plan implements critical refactorings to fix ROI rotation bugs, prevent memory leaks, correct Gradle DSL syntax, and stabilize the native signal processing engine for the IOB Cybernova hackathon.

## Proposed Changes

### Build Configuration

#### [MODIFY] [app/build.gradle.kts](file:///C:/Users/praji/AndroidStudioProjects/SentinelHard/app/build.gradle.kts)
- Correct invalid DSL syntax for `compileSdk` and `buildTypes`.
- Change `compileSdk { version = release(35) }` to `compileSdk = 35`.
- Change `optimization { enable = false }` to `isMinifyEnabled = false`.

### Kotlin Layer (`MainActivity.kt`)

#### [MODIFY] [MainActivity.kt](file:///C:/Users/praji/AndroidStudioProjects/SentinelHard/app/src/main/java/com/example/sentinelhard/MainActivity.kt)
- **Fix Rotation Bug**: Update `mapRoiToSensor` for 90° and 270° cases.
    - 90°: `intArrayOf(y, imgH - x - w, h, w)`
    - 270°: `intArrayOf(imgW - y - h, x, h, w)`
- **Memory Management**: Add `onDestroy()` lifecycle method to shut down `cameraExecutor` and close the ML Kit `detector`.
- **API Modernization**:
    - Replace deprecated `setTargetResolution` with `ResolutionSelector`.
    - Replace `@SuppressLint("UnsafeOptInUsageError")` with `@OptIn(ExperimentalGetImage::class)`.

### Native Layer (`native-lib.cpp`)

#### [MODIFY] [native-lib.cpp](file:///C:/Users/praji/AndroidStudioProjects/SentinelHard/app/src/main/cpp/native-lib.cpp)
- **Fix Resampling Drift**: Update `resampleToUniform` to use an integer-based sample-count loop instead of a floating-point increment loop to prevent cumulative rounding errors.
- **Strict Liveness Logic**:
    - Port exact RMS Signal Power check from web logic (`signalPower < 0.10`).
    - Port Peak-to-Noise Ratio (Quality Ratio) check from web logic (`qualityRatio < 1.5`).
    - Ensure all spoof detections log specific failure reasons to Logcat.

## Verification Plan

### Automated Tests
- Run `./gradlew :app:assembleDebug` to verify compilation and DSL correctness.

### Manual Verification
- **Rotation Test**: Verify that the forehead ROI tracks correctly in both Portrait and Landscape orientations.
- **Leak Test**: Open and close the app multiple times to ensure no camera or detector memory leaks occur.
- **Spoof Integrity**: Confirm binary "Verified" vs "Spoof" decisions align with the strict web thresholds.
