package com.example.sentinelhard

import com.example.sentinelhard.face.ChallengeVerifier
import com.example.sentinelhard.face.ChallengeVerifier.Status
import org.junit.Assert.assertEquals
import org.junit.Test

/** Runs on the JVM: ./gradlew testDebugUnitTest */
class ChallengeVerifierTest {

    private fun blinkSeq(v: ChallengeVerifier, t0: Double, probs: List<Float>): Double {
        var t = t0
        for (p in probs) {
            v.onFace(t, 0f, p, p)
            t += 0.05
        }
        return t
    }

    @Test
    fun twoBlinksPass() {
        val v = ChallengeVerifier(ChallengeVerifier.BLINK_TWICE, 8.0)
        blinkSeq(v, 0.0, listOf(0.9f, 0.9f, 0.1f, 0.1f, 0.9f, 0.9f, 0.05f, 0.95f))
        assertEquals(2, v.blinks)
        assertEquals(Status.PASSED, v.status)
    }

    @Test
    fun halfClosedEyesDoNotCount() {
        val v = ChallengeVerifier(ChallengeVerifier.BLINK_TWICE, 8.0)
        blinkSeq(v, 0.0, listOf(0.9f, 0.5f, 0.9f, 0.5f, 0.9f, 0.5f, 0.9f))
        assertEquals(0, v.blinks)
        assertEquals(Status.RUNNING, v.status)
    }

    @Test
    fun eyesClosedAtStartIsNotABlink() {
        val v = ChallengeVerifier(ChallengeVerifier.BLINK_TWICE, 8.0)
        blinkSeq(v, 0.0, listOf(0.1f, 0.9f, 0.1f, 0.9f))
        assertEquals(1, v.blinks)
    }

    @Test
    fun oneBlinkTimesOut() {
        val v = ChallengeVerifier(ChallengeVerifier.BLINK_TWICE, 2.0)
        val t = blinkSeq(v, 0.0, listOf(0.9f, 0.1f, 0.9f))
        assertEquals(Status.RUNNING, v.onTick(t))
        assertEquals(Status.FAILED, v.onTick(2.5))
    }

    @Test
    fun turnInRequestedDirectionPasses() {
        val s = ChallengeVerifier.LEFT_YAW_SIGN
        val v = ChallengeVerifier(ChallengeVerifier.TURN_LEFT, 8.0)
        v.onFace(0.0, 0f, null, null)
        v.onFace(0.1, 30f * s, null, null)
        assertEquals(Status.RUNNING, v.status) // needs two detections in a row
        v.onFace(0.2, 32f * s, null, null)
        assertEquals(Status.PASSED, v.status)
    }

    @Test
    fun wrongDirectionOnlyHints() {
        val s = ChallengeVerifier.LEFT_YAW_SIGN
        val v = ChallengeVerifier(ChallengeVerifier.TURN_RIGHT, 8.0)
        v.onFace(0.0, 0f, null, null)
        v.onFace(0.1, 35f * s, null, null) // turned left
        v.onFace(0.2, 35f * s, null, null)
        assertEquals(Status.RUNNING, v.status)
        assertEquals("Other way", v.hint)
        v.onFace(0.3, -30f * s, null, null)
        v.onFace(0.4, -30f * s, null, null)
        assertEquals(Status.PASSED, v.status)
    }

    @Test
    fun alreadyTurnedAtStartMustFaceFrontFirst() {
        val s = ChallengeVerifier.LEFT_YAW_SIGN
        val v = ChallengeVerifier(ChallengeVerifier.TURN_LEFT, 8.0)
        v.onFace(0.0, 40f * s, null, null)
        v.onFace(0.1, 40f * s, null, null)
        v.onFace(0.2, 40f * s, null, null)
        assertEquals(Status.RUNNING, v.status)
        v.onFace(0.3, 0f, null, null)
        v.onFace(0.4, 30f * s, null, null)
        v.onFace(0.5, 30f * s, null, null)
        assertEquals(Status.PASSED, v.status)
    }

    @Test
    fun unknownChallengeFails() {
        val v = ChallengeVerifier("SMILE", 8.0)
        assertEquals(Status.FAILED, v.onFace(0.0, 0f, 0.9f, 0.9f))
    }
}
