# Phase 18: UX Decoupling & Stability Latch

This plan implements the final consensus on high-trust biometric UX. We will decouple the "raw math" from the UI by introducing a **Dwell-Time Latch** and a **Hysteresis Dead-Band** to eliminate any remaining layout flickers and badge flip-flops.

## Proposed Changes

### Kotlin Layer (`MainActivity.kt`)

#### [MODIFY] [MainActivity.kt](file:///C:/Users/praji/AndroidStudioProjects/SentinelHard/app/src/main/java/com/example/sentinelhard/MainActivity.kt)
- **Implement Analysis Latch (Bug 1 Fix)**:
    - Add `private var isAnalysisReady = false` (one-way latch).
    - In `HUDOverlay`, once `trueBufferSize >= 150`, set `isAnalysisReady = true`.
    - Use `isAnalysisReady` to lock the UI into the Metrics layout, preventing the "Spinner/Metrics" flicker.
- **Warmup-Gated Voting (Bug 2 Fix)**:
    - Modify the `votedStatus` calculation.
    - If `livenessHistory.size < LIVENESS_SMOOTHING_WINDOW`, force status to `1` (ANALYZING).
- **UX Dwell-Time Filter (Final Consensus)**:
    - Add `displayedStatus`, `pendingStatusFrames`, and `MIN_DWELL_FRAMES = 20`.
    - Only update `livenessStatusState` if the new status is sustained for 20 frames (~0.6s).
- **Coasting Reset Fix (Bug 3 Fix)**:
    - Use a sentinel value (`MAX_COASTING_FRAMES + 1`) to ensure the reset block is only entered once per face loss.

### Native Layer (`native-lib.cpp`)

#### [MODIFY] [native-lib.cpp](file:///C:/Users/praji/AndroidStudioProjects/SentinelHard/app/src/main/cpp/native-lib.cpp)
- **Hysteresis Dead-Band (Bug 4 Fix)**:
    - Implement different thresholds for entering vs. leaving the **HUMAN** (2.0) and **SPOOF** (0.0) states.
    - Human: Enter at > 0.65, Leave at < 0.60.
    - Spoof: Enter at < 0.45, Leave at > 0.50.
- **Confidence Deceleration**:
    - Adjust the EMA factor to **0.90/0.10** for the most graceful transitions.

## Verification Plan

### Automated Tests
- Run `./gradlew :app:assembleDebug` to verify compilation.

### Manual Verification
- **Flicker Stress Test**: Rapidly change lighting or move the camera. The HUD should stay locked in the Metrics layout, and the badge should transition smoothly without "jittering."
- **Reset Test**: Briefly hide/show the face. Confirm there is no single-frame "POSITION FACE" flash.
- **Dwell Test**: Cover the camera; the Human badge should persist for ~0.6s before changing, showing the dwell filter in action.
