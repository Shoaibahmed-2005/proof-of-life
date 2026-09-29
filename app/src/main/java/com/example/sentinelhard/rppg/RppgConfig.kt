package com.example.sentinelhard.rppg

import com.example.sentinelhard.network.QrPayload

/**
 * rPPG gate settings. The backend sends them in the QR code (backend .env:
 * MIN_SNR_DB, RPPG_WINDOW_SEC, RPPG_STABLE_COUNT, RPPG_STABLE_TOLERANCE_BPM,
 * RPPG_SCAN_TIMEOUT_SEC), so they can be tuned from measured data without
 * rebuilding the app. The defaults here are used only if the QR has none.
 *
 * MIN_SNR_DB default 3.0 dB: in laptop simulations (tools/rppg/run_tests.py)
 * no photo passed at this level while ~90% of genuine scans did. Only change
 * it from real measurements (TESTING_CHECKLIST.md, scan speed comparison).
 */
data class GateSettings(
    val minSnrDb: Double,
    val windowSec: Double,
    val stableCount: Int,
    val stableToleranceBpm: Double,
    val timeoutSec: Double,
) {
    companion object {
        fun from(qr: QrPayload) = GateSettings(
            minSnrDb = qr.minSnrDb ?: RppgConfig.DEFAULT_MIN_SNR_DB,
            windowSec = qr.windowSec ?: RppgConfig.WINDOW_SEC,
            stableCount = qr.stableCount ?: RppgConfig.STABLE_COUNT,
            stableToleranceBpm = qr.stableToleranceBpm ?: RppgConfig.STABLE_TOLERANCE_BPM,
            timeoutSec = qr.timeoutSec ?: RppgConfig.SCAN_TIMEOUT_SEC,
        )
    }
}

object RppgConfig {
    const val DEFAULT_MIN_SNR_DB = 3.0
    const val WINDOW_SEC = 10.0
    const val STABLE_COUNT = 5
    const val STABLE_TOLERANCE_BPM = 3.0

    /** Give up and report "no pulse" if no stable reading within this time of seeing a face. */
    const val SCAN_TIMEOUT_SEC = 30.0

    /** Run ML Kit face detection on every Nth frame; ROIs are reused in between. */
    const val FACE_DETECTION_INTERVAL = 3

    /**
     * Restart the measurement if the face is missing for this long. Was 1.0 s:
     * on weaker cameras or dim light, face detection misses a few frames in a
     * row, and a 1 s limit could restart the 10 s window again and again.
     */
    const val FACE_LOST_RESET_SEC = 2.0

    /** Let auto-exposure settle on the face for this long, then lock exposure and white balance. */
    const val AE_SETTLE_SEC = 1.0

    /** Frame rate we ask the camera for (steady, not variable). */
    const val TARGET_FPS = 30

    // Guidance thresholds (face brightness is the mean luma 0..255 of the skin pixels).
    const val LUMA_TOO_DARK = 60.0
    const val LUMA_TOO_BRIGHT = 215.0
    const val FACE_MIN_WIDTH_FRACTION = 0.28   // face box width / image width
    const val MOTION_MAX_FRACTION = 0.06       // face-centre jump between detections / face width
}
