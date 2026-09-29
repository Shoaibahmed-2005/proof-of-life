package com.example.sentinelhard.face

import kotlin.math.abs

/**
 * Verifies the random challenge from the QR code (build-prompt §4.3) with ML Kit's
 * per-face results, one face detection at a time:
 *
 *  - BLINK_TWICE: eyes-open probability (classification mode) must go
 *    open → closed → open twice. Hysteresis (closed below 0.35, open above 0.65)
 *    stops a half-closed eye from counting several times.
 *  - TURN_LEFT / TURN_RIGHT: starting from a frontal pose, the head yaw must pass
 *    TURN_MIN_DEG in the requested direction for TURN_HOLD_DETECTIONS detections
 *    in a row. Turning the wrong way only shows a hint ("other way").
 *
 * The backend chose the challenge when the session was created, so a pre-recorded
 * video cannot know which action to show, or when. Pure Kotlin (no Android types);
 * thread-safe (fed from the camera thread and the ML Kit callback).
 */
class ChallengeVerifier(val type: String, private val timeoutSec: Double) {

    enum class Status { RUNNING, PASSED, FAILED }

    companion object {
        const val BLINK_TWICE = "BLINK_TWICE"
        const val TURN_LEFT = "TURN_LEFT"
        const val TURN_RIGHT = "TURN_RIGHT"
        val SUPPORTED = setOf(BLINK_TWICE, TURN_LEFT, TURN_RIGHT)

        const val DEFAULT_TIMEOUT_SEC = 10.0
        const val EYES_CLOSED_BELOW = 0.35f
        const val EYES_OPEN_ABOVE = 0.65f
        const val BLINKS_NEEDED = 2
        const val FRONTAL_MAX_DEG = 12f
        const val TURN_MIN_DEG = 25f
        const val TURN_HOLD_DETECTIONS = 2

        /**
         * Sign of ML Kit's headEulerAngleY when the person turns their head to their
         * own left, on the front camera. If TURN_LEFT only passes when turning right
         * (TESTING_CHECKLIST.md test 4.6), change this to -1f.
         */
        const val LEFT_YAW_SIGN = 1f
    }

    var status = Status.RUNNING
        private set
    var blinks = 0
        private set
    /** Short hint for the screen while running (e.g. "Other way"), or null. */
    var hint: String? = null
        private set
    /** Why it failed, for the logs and diagnostics. */
    var failDetail: String? = null
        private set
    var lastYaw = 0f
        private set

    private var startedAt: Double? = null
    private var eyesOpenSeen = false
    private var eyesClosed = false
    private var frontalSeen = false
    private var turnHeld = 0

    @Synchronized
    fun start(t: Double) {
        if (startedAt == null) startedAt = t
    }

    @Synchronized
    fun remainingSec(t: Double): Double {
        val s = startedAt ?: return timeoutSec
        return (timeoutSec - (t - s)).coerceAtLeast(0.0)
    }

    /** Call on every frame (also when no face is found) so the time limit is enforced. */
    @Synchronized
    fun onTick(t: Double): Status {
        if (status == Status.RUNNING && remainingSec(t) <= 0.0) {
            status = Status.FAILED
            failDetail = when (type) {
                BLINK_TWICE -> "time limit: $blinks of $BLINKS_NEEDED blinks"
                else -> "time limit: last yaw %.0f°".format(lastYaw)
            }
        }
        return status
    }

    /**
     * One face detection. [leftOpen] / [rightOpen] are ML Kit's eyes-open
     * probabilities (null when it could not classify the frame).
     */
    @Synchronized
    fun onFace(t: Double, yaw: Float, leftOpen: Float?, rightOpen: Float?): Status {
        start(t)
        if (onTick(t) != Status.RUNNING) return status
        lastYaw = yaw
        when (type) {
            BLINK_TWICE -> onBlinkSample(leftOpen, rightOpen)
            TURN_LEFT -> onTurnSample(yaw * LEFT_YAW_SIGN)
            TURN_RIGHT -> onTurnSample(-yaw * LEFT_YAW_SIGN)
            else -> {
                status = Status.FAILED
                failDetail = "unknown challenge $type"
            }
        }
        return status
    }

    private fun onBlinkSample(leftOpen: Float?, rightOpen: Float?) {
        val p = when {
            leftOpen != null && rightOpen != null -> (leftOpen + rightOpen) / 2f
            leftOpen != null -> leftOpen
            rightOpen != null -> rightOpen
            else -> return
        }
        if (p > EYES_OPEN_ABOVE) {
            if (eyesClosed && eyesOpenSeen) {
                blinks++
                if (blinks >= BLINKS_NEEDED) status = Status.PASSED
            }
            eyesOpenSeen = true
            eyesClosed = false
        } else if (p < EYES_CLOSED_BELOW && eyesOpenSeen) {
            eyesClosed = true
        }
    }

    /** [towards] is the yaw in the requested direction (positive = correct way). */
    private fun onTurnSample(towards: Float) {
        if (abs(towards) <= FRONTAL_MAX_DEG) frontalSeen = true
        when {
            !frontalSeen -> {
                hint = "Look straight at the screen first"
                turnHeld = 0
            }
            towards >= TURN_MIN_DEG -> {
                hint = null
                turnHeld++
                if (turnHeld >= TURN_HOLD_DETECTIONS) status = Status.PASSED
            }
            towards <= -TURN_MIN_DEG -> {
                hint = "Other way"
                turnHeld = 0
            }
            else -> {
                hint = null
                turnHeld = 0
            }
        }
    }
}
