package com.example.sentinelhard.rppg

/**
 * rPPG thresholds. MIN_SNR_DB is normally supplied by the backend in the QR
 * code (backend .env MIN_SNR_DB), so it can be calibrated without rebuilding
 * the app; the default here is used only if the QR code doesn't carry one.
 *
 * Default 3.0 dB: in laptop simulations (tools/rppg/run_tests.py) no photo
 * passed at this level while ~90% of genuine scans did. Calibrate on the phone
 * (TESTING_CHECKLIST.md, M2 tests 2.5 and 2.8).
 */
object RppgConfig {
    const val DEFAULT_MIN_SNR_DB = 3.0
    const val WINDOW_SEC = 10.0
    const val STABLE_COUNT = 5
    const val STABLE_TOLERANCE_BPM = 3.0

    /** Give up and report "no pulse" if no stable reading within this time of seeing a face. */
    const val SCAN_TIMEOUT_SEC = 30.0

    /** Run ML Kit face detection on every Nth frame; ROIs are reused in between. */
    const val FACE_DETECTION_INTERVAL = 3

    /** Restart the measurement if the face is missing for this long. */
    const val FACE_LOST_RESET_SEC = 1.0
}
