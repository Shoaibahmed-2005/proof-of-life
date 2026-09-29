package com.example.sentinelhard.face

import android.util.Log

/**
 * Collects face embeddings during a scan, each with a quality score, and
 * builds the result from the best ones (build-prompt §3.1 step 5):
 *   - registration: the best 10–20 frames (frontal, sharp, well lit, large
 *     face) averaged and L2-normalised into the reference template;
 *   - life certificate: the best few frames averaged into the probe.
 * Thread-safe (embeddings arrive from the inference thread).
 */
class FaceCapture {

    companion object {
        const val TAG = "SentinelFace"
        const val MAX_CANDIDATES = 60
        const val ENROLL_K = 15
        const val ENROLL_MIN = 10
        const val PROBE_K = 5
        const val PROBE_MIN = 3

        // Frame acceptance (ML Kit head angles in degrees, alignment metrics).
        const val MAX_YAW = 20f
        const val MAX_PITCH = 20f
        const val MAX_ROLL = 25f
        const val MIN_EYE_DISTANCE = 20.0
        const val MIN_SHARPNESS = 15.0

        /**
         * Quality 0..1 from pose, size, light and sharpness; 0 = don't use.
         * Registration needs "frontal pose, sharp, well lit, large enough face".
         */
        fun quality(yaw: Float, pitch: Float, roll: Float, eyeDistance: Double, luma: Double, sharpness: Double): Float {
            if (kotlin.math.abs(yaw) > MAX_YAW || kotlin.math.abs(pitch) > MAX_PITCH || kotlin.math.abs(roll) > MAX_ROLL) return 0f
            if (eyeDistance < MIN_EYE_DISTANCE || sharpness < MIN_SHARPNESS) return 0f
            val frontal = 1.0 - (kotlin.math.abs(yaw) + kotlin.math.abs(pitch)) / (MAX_YAW + MAX_PITCH)
            val size = minOf(1.0, eyeDistance / 60.0)
            val light = if (luma in 70.0..200.0) 1.0 else 0.5
            val sharp = minOf(1.0, sharpness / 150.0)
            return (frontal * size * light * (0.5 + 0.5 * sharp)).toFloat()
        }
    }

    private data class Candidate(val embedding: FloatArray, val quality: Float)

    private val candidates = ArrayList<Candidate>()

    @Volatile var framesSeen = 0
        private set

    @Synchronized
    fun reset() {
        candidates.clear()
        framesSeen = 0
    }

    @Synchronized
    fun add(embedding: FloatArray, quality: Float) {
        framesSeen++
        if (quality <= 0f) return
        if (candidates.size >= MAX_CANDIDATES) {
            val worst = candidates.indices.minByOrNull { candidates[it].quality } ?: return
            if (candidates[worst].quality >= quality) return
            candidates.removeAt(worst)
        }
        candidates.add(Candidate(embedding, quality))
    }

    @Synchronized
    fun goodFrames(): Int = candidates.size

    /** Registration template, or null if fewer than ENROLL_MIN good frames. */
    fun buildTemplate(): FloatArray? = build(ENROLL_K, ENROLL_MIN)

    /** Life-certificate probe, or null if fewer than PROBE_MIN good frames. */
    fun buildProbe(): FloatArray? = build(PROBE_K, PROBE_MIN)

    @Synchronized
    private fun build(k: Int, minCount: Int): FloatArray? {
        if (candidates.isEmpty()) return null
        val dim = candidates[0].embedding.size
        val flat = FloatArray(candidates.size * dim)
        candidates.forEachIndexed { i, c -> c.embedding.copyInto(flat, i * dim) }
        val q = FloatArray(candidates.size) { candidates[it].quality }
        val result = FaceNative.nativeBuildTemplate(flat, candidates.size, dim, q, k, minCount)
        Log.i(TAG, "Built from best ${minOf(k, candidates.size)} of ${candidates.size} good frames " +
            "(seen $framesSeen): ${if (result.isEmpty()) "not enough" else "ok"}")
        return if (result.isEmpty()) null else result
    }

    /** Number of frames actually averaged (for frames_used in the payload). */
    @Synchronized
    fun framesUsed(k: Int): Int = minOf(k, candidates.size)
}
