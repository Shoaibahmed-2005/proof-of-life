# Phase 17: Multi-Modal Reliability & Tiered UX Stability

This plan addresses the persistent "flip-flop" badge issue by replacing the brittle binary logic with a weighted confidence engine, implementing a real frame coasting injector, and introducing a 3-tier UX with minimum dwell-time filtering.

## Proposed Changes

### Native Layer (`native-lib.cpp`)

#### [MODIFY] [native-lib.cpp](file:///C:/Users/praji/AndroidStudioProjects/SentinelHard/app/src/main/cpp/native-lib.cpp)
- **Implement Robust Pipeline**:
    - Re-inject `applyFIRDetrending` to prevent mathematical lockups.
    - Re-inject `applyKalmanStabilization` with SNR-linked measurement noise ($R \propto 1/SNR^2$).
- **Weighted Confidence Engine**:
    - Replace the binary AND-gate with a continuous confidence score (0.0 to 1.0).
    - **Weights**: Texture (30%), QR (30%), Correlation (20%), HRV (20%).
    - Use a **0.90/0.10 EMA** smoothing factor for the confidence score to ensure graceful transitions.
- **3-Tier Status Output**:
    - Refactor `extractVitals` to return a tiered status code:
        - `2.0`: **HUMAN** (Confidence > 0.65)
        - `1.0`: **ANALYZING** (Confidence 0.45 - 0.65)
        - `0.0`: **SPOOF** (Confidence < 0.45)

### Kotlin Layer (`MainActivity.kt`)

#### [MODIFY] [MainActivity.kt](file:///C:/Users/praji/AndroidStudioProjects/SentinelHard/app/src/main/java/com/example/sentinelhard/MainActivity.kt)
- **Fix ROI Rotation Bug**:
    - Correct `mapRoiToSensor` to use the correct image dimensions when mapping coordinates at 90° and 270°.
- **Real Frame Coasting**:
    - Cache `lastGoodYuv`, `lastGoodRoi`, `lastGoodWidth`, and `lastGoodHeight`.
    - During tracking drops (up to 30 frames), re-invoke `processFrame` using cached data to keep the 150-sample buffer continuous.
- **UX Dwell-Time Filter**:
    - Introduce `displayedStatus` and `pendingStatusFrames`.
    - A state change (e.g., Analyzing -> Human) must be sustained for **20 frames** (~0.6s) before the UI badge updates.
- **HUD Update**:
    - Update `HUDOverlay` to handle 3 states: **Green** (Verified Human), **Amber** (Analyzing Signal...), and **Red** (Spoof Detected).

## Verification Plan

### Automated Tests
- Run `./gradlew :app:assembleDebug` to verify compilation.

### Manual Verification
- **The "Blink" Test**: Confirm the circular analyzer does NOT reset during brief blinks, as the injector keeps the engine warm.
- **Stability Stress Test**: Move the phone under varied lighting. The badge should transition smoothly through Amber or remain solid, never flickering frame-to-frame.
- **Rotation Test**: Verify the ROI remains correctly positioned on the forehead in both Portrait and Landscape.

## User Review Required

> [!IMPORTANT]
> This refactor fixes the "NaN Explosion" and the "Flickering Badge" simultaneously by combining DSP detrending with a decoupled UX dwell-time filter.

> [!TIP]
> Introducing the Amber ("ANALYZING") state makes the app feel more professional and honest, as it acknowledges signal noise instead of snapping between binary results.
