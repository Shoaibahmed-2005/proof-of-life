package com.example.sentinelhard.rppg

/**
 * One frame's output from the C++ engine. Mirrors the array layout written by
 * native-lib.cpp (keep HEADER_SIZE in sync with kHeaderSize there).
 */
data class RppgResult(
    val bpm: Double,            // median of recent estimates (0 = none yet)
    val latestBpm: Double,
    val snrDb: Double,          // latest estimate
    val medianSnrDb: Double,
    val windowFill: Double,     // 0..1 of the analysis window
    val stable: Boolean,        // window full + estimates agree + SNR ≥ minimum
    val newEstimate: Boolean,
    val estimateCount: Int,
    val samplesInWindow: Int,
    val faceSampleValid: Boolean,
    val skinFraction: Double,
    val pixels: Int,
    val waveform: DoubleArray,
) {
    val hasEstimate: Boolean get() = estimateCount > 0 && bpm > 0.0

    companion object {
        const val HEADER_SIZE = 12

        val EMPTY = RppgResult(0.0, 0.0, -99.0, -99.0, 0.0, false, false, 0, 0, false, 0.0, 0, DoubleArray(0))

        fun fromArray(a: DoubleArray): RppgResult {
            if (a.size < HEADER_SIZE) return EMPTY
            return RppgResult(
                bpm = a[0],
                latestBpm = a[1],
                snrDb = a[2],
                medianSnrDb = a[3],
                windowFill = a[4],
                stable = a[5] >= 0.5,
                newEstimate = a[6] >= 0.5,
                estimateCount = a[7].toInt(),
                samplesInWindow = a[8].toInt(),
                faceSampleValid = a[9] >= 0.5,
                skinFraction = a[10],
                pixels = a[11].toInt(),
                waveform = a.copyOfRange(HEADER_SIZE, a.size),
            )
        }
    }

    // DoubleArray needs content-based equality for Compose state comparisons.
    override fun equals(other: Any?): Boolean =
        other is RppgResult && bpm == other.bpm && snrDb == other.snrDb &&
            estimateCount == other.estimateCount && stable == other.stable &&
            windowFill == other.windowFill && waveform.contentEquals(other.waveform)

    override fun hashCode(): Int = 31 * estimateCount + waveform.contentHashCode()
}
