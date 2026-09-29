package com.example.sentinelhard.rppg

import android.os.Build
import android.util.Log
import com.example.sentinelhard.models.ScanDiagnosticsPayload
import java.util.ArrayDeque

/**
 * Per-scan diagnostics: tells a slow camera apart from poor lighting or tight
 * thresholds. Fed from the camera thread; read by the UI (snapshot) and sent
 * with the signed result (summary).
 *
 * Gate order (what is still holding the reading back):
 *   FACE_LOST → WINDOW_FILLING → READINGS_NOT_STABLE → SNR_BELOW_MIN → READY
 */
class ScanDiagnostics {

    enum class Gate(val label: String) {
        FACE_LOST("face lost"),
        WINDOW_FILLING("window filling"),
        READINGS_NOT_STABLE("readings not yet stable"),
        SNR_BELOW_MIN("SNR below minimum"),
        READY("all gates passed"),
    }

    /** What the on-screen readout shows. */
    data class Snapshot(
        val elapsedSec: Double,
        val fps: Double,
        val bpm: Double,
        val snrDb: Double,
        val minSnrDb: Double,
        val spreadBpm: Double,
        val luma: Double,
        val gate: Gate,
        val aeLocked: Boolean,
        val fpsRange: String,
    )

    companion object {
        const val TAG = "SentinelDiag"
        private const val FPS_WINDOW_SEC = 2.0
    }

    private val frameTimes = ArrayDeque<Double>()
    private var startSec: Double? = null
    private var lastFrameSec: Double? = null
    private var frames = 0
    private var fpsSum = 0.0
    private var fpsSamples = 0
    private var minFps = Double.MAX_VALUE
    private var faceLostCount = 0
    private var bestSnr = -99.0
    private var lumaSum = 0.0
    private var lumaSamples = 0
    private val gateSeconds = mutableMapOf<Gate, Double>()
    private var lastGate: Gate = Gate.WINDOW_FILLING

    @Volatile var aeLocked = false
    @Volatile var fpsRange = "default"
    @Volatile var supportedFpsRanges = ""
    @Volatile var snapshot: Snapshot? = null
        private set

    @Synchronized
    fun reset() {
        frameTimes.clear(); startSec = null; lastFrameSec = null; frames = 0
        fpsSum = 0.0; fpsSamples = 0; minFps = Double.MAX_VALUE; faceLostCount = 0
        bestSnr = -99.0; lumaSum = 0.0; lumaSamples = 0; gateSeconds.clear()
        lastGate = Gate.WINDOW_FILLING; aeLocked = false; snapshot = null
    }

    /** Every camera frame (whether or not a face was found). */
    @Synchronized
    fun onFrame(tSec: Double) {
        if (startSec == null) startSec = tSec
        frames++
        frameTimes.addLast(tSec)
        while (frameTimes.size > 1 && tSec - frameTimes.first() > FPS_WINDOW_SEC) frameTimes.removeFirst()
        val prev = lastFrameSec
        if (prev != null) gateSeconds[lastGate] = (gateSeconds[lastGate] ?: 0.0) + (tSec - prev)
        lastFrameSec = tSec
    }

    @Synchronized
    fun onFaceLost() { faceLostCount++; lastGate = Gate.FACE_LOST }

    fun currentFps(): Double {
        synchronized(this) {
            if (frameTimes.size < 2) return 0.0
            val span = frameTimes.last() - frameTimes.first()
            return if (span > 0) (frameTimes.size - 1) / span else 0.0
        }
    }

    fun gateOf(r: RppgResult, faceVisible: Boolean): Gate = when {
        !faceVisible -> Gate.FACE_LOST
        !r.windowOk -> Gate.WINDOW_FILLING
        !r.agreeOk -> Gate.READINGS_NOT_STABLE
        !r.snrOk -> Gate.SNR_BELOW_MIN
        else -> Gate.READY
    }

    /** After each processed frame; logs a line on every new estimate. */
    @Synchronized
    fun onResult(r: RppgResult, tSec: Double, faceVisible: Boolean) {
        val gate = gateOf(r, faceVisible)
        lastGate = gate
        if (r.hasEstimate) bestSnr = maxOf(bestSnr, r.medianSnrDb)
        if (r.faceSampleValid) { lumaSum += r.luma; lumaSamples++ }
        val fps = currentFps()
        if (r.newEstimate && fps > 0) {
            fpsSum += fps; fpsSamples++; minFps = minOf(minFps, fps)
            Log.i(TAG, "t=%.1fs fps=%.1f bpm=%.1f snr=%.1f/%.1f dB (min %.1f) spread=%.1f fill=%.2f gate=%s luma=%.0f skin=%.2f ae_lock=%b"
                .format(elapsed(tSec), fps, r.bpm, r.snrDb, r.medianSnrDb, r.minSnrDb, r.spreadBpm,
                    r.windowFill, gate.name, r.luma, r.skinFraction, aeLocked))
        }
        snapshot = Snapshot(elapsed(tSec), fps, r.bpm, r.medianSnrDb, r.minSnrDb, r.spreadBpm, r.luma, gate, aeLocked, fpsRange)
    }

    private fun elapsed(tSec: Double) = tSec - (startSec ?: tSec)

    /** Summary sent with the signed result and logged once per scan. */
    @Synchronized
    fun summary(outcomeHint: String, last: RppgResult): ScanDiagnosticsPayload {
        val elapsed = (lastFrameSec ?: 0.0) - (startSec ?: lastFrameSec ?: 0.0)
        val avgFps = if (fpsSamples > 0) fpsSum / fpsSamples else currentFps()
        val p = ScanDiagnosticsPayload(
            scanSeconds = round1(elapsed),
            avgFps = round1(avgFps),
            minFps = if (minFps == Double.MAX_VALUE) null else round1(minFps),
            frames = frames,
            faceLostCount = faceLostCount,
            bestSnrDb = round1(bestSnr),
            finalSpreadBpm = round1(last.spreadBpm),
            meanLuma = if (lumaSamples > 0) round1(lumaSum / lumaSamples) else null,
            skinFraction = round2(last.skinFraction),
            estimates = last.estimateCount,
            minSnrDb = last.minSnrDb,
            gateSecWindow = round1(gateSeconds[Gate.WINDOW_FILLING] ?: 0.0),
            gateSecStable = round1(gateSeconds[Gate.READINGS_NOT_STABLE] ?: 0.0),
            gateSecSnr = round1(gateSeconds[Gate.SNR_BELOW_MIN] ?: 0.0),
            gateSecFace = round1(gateSeconds[Gate.FACE_LOST] ?: 0.0),
            lastGate = lastGate.name,
            aeLocked = aeLocked,
            fpsRange = fpsRange,
            deviceModel = "${Build.MANUFACTURER} ${Build.MODEL}",
        )
        Log.i(TAG, "SCAN SUMMARY outcome=$outcomeHint time=${p.scanSeconds}s bpm=%.1f snr=%.1f best_snr=${p.bestSnrDb} " .format(last.bpm, last.medianSnrDb) +
            "min_snr=${p.minSnrDb} avg_fps=${p.avgFps} min_fps=${p.minFps} face_lost=${p.faceLostCount} " +
            "gate_s[window=${p.gateSecWindow} stable=${p.gateSecStable} snr=${p.gateSecSnr} face=${p.gateSecFace}] " +
            "last_gate=${p.lastGate} luma=${p.meanLuma} ae_lock=${p.aeLocked} fps_range=${p.fpsRange} " +
            "supported=[$supportedFpsRanges] device=${p.deviceModel}")
        return p
    }

    private fun round1(v: Double) = Math.round(v * 10.0) / 10.0
    private fun round2(v: Double) = Math.round(v * 100.0) / 100.0
}
