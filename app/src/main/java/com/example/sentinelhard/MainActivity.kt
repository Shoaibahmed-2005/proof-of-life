package com.example.sentinelhard

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.RectF
import android.os.Bundle
import android.provider.Settings
import android.util.Base64
import android.util.Log
import android.util.Size as AndroidSize
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.annotation.OptIn
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.Camera
import androidx.camera.core.CameraSelector
import androidx.camera.core.ExperimentalGetImage
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size as ComposeSize
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.lifecycleScope
import com.example.sentinelhard.camera.CameraTuning
import com.example.sentinelhard.camera.QrCodeAnalyzer
import com.example.sentinelhard.models.BiometricPayload
import com.example.sentinelhard.models.ScanDiagnosticsPayload
import com.example.sentinelhard.models.VerifyRequest
import com.example.sentinelhard.network.ApiClient
import com.example.sentinelhard.network.QrPayload
import com.example.sentinelhard.face.FaceCapture
import com.example.sentinelhard.face.FaceEmbedder
import com.example.sentinelhard.face.FaceNative
import com.example.sentinelhard.rppg.FaceRois
import com.example.sentinelhard.rppg.GateSettings
import com.example.sentinelhard.rppg.RppgConfig
import com.example.sentinelhard.rppg.RppgNative
import com.example.sentinelhard.rppg.RppgResult
import com.example.sentinelhard.rppg.ScanDiagnostics
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.face.FaceDetection
import com.google.mlkit.vision.face.FaceDetectorOptions
import com.google.mlkit.vision.face.FaceLandmark
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import org.opencv.android.OpenCVLoader
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/** App flow: Home → Scan QR → (connect) → Measuring → Submitting → Result. */
sealed class ScanState {
    object Home : ScanState()
    object ScanQr : ScanState()
    data class Connecting(val qr: QrPayload) : ScanState()
    data class Measuring(val qr: QrPayload, val baseUrl: String) : ScanState()
    object Submitting : ScanState()
    data class Result(val success: Boolean, val title: String, val message: String?) : ScanState()
}

private enum class CameraMode { QR, FACE }

class MainActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "SentinelHard"
        private const val TAG_DSP = "SentinelDSP"
        private const val TAG_TELEMETRY = "SentinelTelemetry"
        private val GREEN = Color(0xFF00FF66)
        private val AMBER = Color(0xFFFFC107)
    }

    // ── UI state (Compose) ──────────────────────────────────────────────
    private val scanState = mutableStateOf<ScanState>(ScanState.Home)
    private val rppgState = mutableStateOf(RppgResult.EMPTY)
    private val faceVisibleState = mutableStateOf(false)
    private val roiOverlayState = mutableStateOf<List<RectF>>(emptyList())
    private val overlayImageSize = mutableStateOf(AndroidSize(0, 0))  // upright analysis image size
    private val showDiagnostics = mutableStateOf(false)                  // off by default for the demo
    private val diagSnapshotState = mutableStateOf<ScanDiagnostics.Snapshot?>(null)
    private val guidanceState = mutableStateOf<String?>(null)
    private val faceBoxState = mutableStateOf<RectF?>(null)              // whole face, upright coords
    private val faceFramesState = mutableIntStateOf(0)                   // good embedding frames so far

    // ── Measurement state (camera thread + ML Kit callbacks) ────────────
    @Volatile private var currentRois: IntArray? = null
    @Volatile private var lastFaceSeenSec = 0.0
    @Volatile private var firstFaceSec: Double? = null
    @Volatile private var isDetectingFace = false
    private val submitted = AtomicBoolean(false)
    private var frameCounter = 0
    private val diagnostics = ScanDiagnostics()
    @Volatile private var gates = GateSettings(RppgConfig.DEFAULT_MIN_SNR_DB, RppgConfig.WINDOW_SEC,
        RppgConfig.STABLE_COUNT, RppgConfig.STABLE_TOLERANCE_BPM, RppgConfig.SCAN_TIMEOUT_SEC)
    @Volatile private var boundCamera: Camera? = null
    @Volatile private var aeLockRequested = false
    @Volatile private var faceWidthFraction = 1.0
    @Volatile private var faceMoving = false
    private var lastFaceCenter: Pair<Float, Float>? = null

    // Face embeddings (Milestone 3)
    @Volatile private var faceEmbedder: FaceEmbedder? = null
    private val embedExecutor = Executors.newSingleThreadExecutor()
    private val faceCapture = FaceCapture()
    @Volatile private var embedBusy = false
    @Volatile private var trackedFaceId: Int? = null
    private var detectionCount = 0

    private val cryptoManager = CryptoManager()
    private val cameraExecutor = Executors.newSingleThreadExecutor()
    private val telemetryStreamer = TelemetryStreamer()

    private val detector = FaceDetection.getClient(
        FaceDetectorOptions.Builder()
            .setPerformanceMode(FaceDetectorOptions.PERFORMANCE_MODE_FAST)
            .setLandmarkMode(FaceDetectorOptions.LANDMARK_MODE_ALL)          // eye positions for alignment
            .setClassificationMode(FaceDetectorOptions.CLASSIFICATION_MODE_ALL) // eyes-open (blink challenge)
            .setContourMode(FaceDetectorOptions.CONTOUR_MODE_NONE)
            .setMinFaceSize(0.15f)
            .enableTracking()                                                // same face throughout the scan
            .build()
    )

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        if (isGranted) {
            scanState.value = ScanState.ScanQr
        } else {
            Log.e(TAG, "Camera permission denied")
            scanState.value = ScanState.Result(false, "Camera permission needed",
                "Allow camera access to scan the QR code and measure your pulse.")
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        if (OpenCVLoader.initLocal()) {
            Log.i(TAG, "OpenCV loaded successfully!")
        }

        // Face model: load once, off the UI thread.
        lifecycleScope.launch(Dispatchers.Default) {
            try {
                faceEmbedder = FaceEmbedder(this@MainActivity)
            } catch (e: Exception) {
                Log.e(FaceEmbedder.TAG, "Could not load the face model", e)
            }
        }

        // StrongBox key generation can take a few seconds on first launch: keep it off the UI thread.
        lifecycleScope.launch(Dispatchers.Default) {
            try {
                cryptoManager.generateHardwareKey()
            } catch (e: Exception) {
                Log.e(TAG, "Key generation failed", e)
            }
        }

        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize(), color = Color(0xFF0A0A0A)) {
                    val state by scanState
                    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        when (val s = state) {
                            is ScanState.Home -> HomeScreen(onScan = { startQrScan() })
                            is ScanState.ScanQr -> {
                                key(CameraMode.QR) { CameraPreview(CameraMode.QR) }
                                BannerText("Point the camera at the QR code on the portal")
                            }
                            is ScanState.Connecting -> BusyScreen("Connecting to the portal…")
                            is ScanState.Measuring -> {
                                key(CameraMode.FACE) { CameraPreview(CameraMode.FACE) }
                                RoiOverlay()
                                MeasuringHud()
                            }
                            is ScanState.Submitting -> BusyScreen("Sending signed result…")
                            is ScanState.Result -> ResultScreen(s)
                        }
                    }
                }
            }
        }
    }

    // ── Flow ────────────────────────────────────────────────────────────

    private fun startQrScan() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            scanState.value = ScanState.ScanQr
        } else {
            requestPermissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    /** Called on the main thread when a QR code is decoded. */
    private fun onQrScanned(raw: String) {
        if (scanState.value !is ScanState.ScanQr) return
        val qr = QrPayload.parse(raw)
        if (qr == null) {
            Log.w(TAG, "Not a session QR code: $raw")
            scanState.value = ScanState.Result(false, "Not a portal QR code",
                "Please scan the QR code shown on the Jeevan Suraksha portal.")
            return
        }
        Log.i(TAG, "QR scanned: session=${qr.sessionId} purpose=${qr.purpose} base_url=${qr.baseUrl} " +
            "min_snr_db=${qr.minSnrDb}")
        if (!qr.isAuth) {
            scanState.value = ScanState.Result(false, "App update needed",
                "This QR code is for ${qr.purpose.replace('_', ' ').lowercase()}. " +
                    "Face registration and life certificates arrive in the next app update.")
            return
        }
        scanState.value = ScanState.Connecting(qr)
        lifecycleScope.launch {
            val probe = ApiClient.resolveReachableBaseUrl(qr.baseUrl)
            val baseUrl = probe.baseUrl
            if (baseUrl == null) {
                scanState.value = ScanState.Result(false, "Can't reach the laptop",
                    probe.describeFailure() + "\n\nPhone and laptop must be on the same Wi-Fi, with port 8000 " +
                        "allowed in Windows Firewall. Over USB: adb reverse tcp:8000 tcp:8000")
            } else {
                startMeasuring(qr, baseUrl)
            }
        }
    }

    private fun startMeasuring(qr: QrPayload, baseUrl: String) {
        resetMeasurement()
        gates = GateSettings.from(qr)
        Log.i(ScanDiagnostics.TAG, "Gates: min_snr=${gates.minSnrDb} dB window=${gates.windowSec}s " +
            "stable=${gates.stableCount} within +/-${gates.stableToleranceBpm} BPM timeout=${gates.timeoutSec}s")
        RppgNative.nativeConfigure(gates.minSnrDb, gates.windowSec, gates.stableCount, gates.stableToleranceBpm)
        telemetryStreamer.connect(baseUrl, qr.sessionId, qr.nonce)
        telemetryStreamer.send("scan_started")
        scanState.value = ScanState.Measuring(qr, baseUrl)
    }

    /** Clears everything from a previous scan so each scan starts from zero. */
    private fun resetMeasurement() {
        RppgNative.nativeReset()
        currentRois = null
        lastFaceSeenSec = 0.0
        firstFaceSec = null
        frameCounter = 0
        submitted.set(false)
        rppgState.value = RppgResult.EMPTY
        faceVisibleState.value = false
        roiOverlayState.value = emptyList()
        diagnostics.reset()
        diagSnapshotState.value = null
        guidanceState.value = null
        aeLockRequested = false
        faceWidthFraction = 1.0
        faceMoving = false
        lastFaceCenter = null
        faceCapture.reset()
        faceFramesState.intValue = 0
        faceBoxState.value = null
        trackedFaceId = null
        detectionCount = 0
    }

    private fun finishScan(result: ScanState.Result) {
        telemetryStreamer.disconnect()
        currentRois = null
        scanState.value = result  // leaving Measuring disposes the camera preview and unbinds the camera
    }

    // ── Camera ──────────────────────────────────────────────────────────

    @Composable
    private fun CameraPreview(mode: CameraMode) {
        val context = LocalContext.current
        val lifecycleOwner = LocalLifecycleOwner.current
        val providerFuture = remember { ProcessCameraProvider.getInstance(context) }

        AndroidView(
            factory = { ctx ->
                val previewView = PreviewView(ctx)
                providerFuture.addListener({
                    val provider = providerFuture.get()
                    when (mode) {
                        CameraMode.QR -> bindQrScanner(provider, previewView, lifecycleOwner)
                        CameraMode.FACE -> bindFaceCamera(provider, previewView, lifecycleOwner)
                    }
                }, ContextCompat.getMainExecutor(ctx))
                previewView
            },
            modifier = Modifier.fillMaxSize(),
        )
        // Release the camera as soon as this screen goes away.
        DisposableEffect(mode) {
            onDispose {
                if (providerFuture.isDone) providerFuture.get().unbindAll()
            }
        }
    }

    private fun bindQrScanner(provider: ProcessCameraProvider, previewView: PreviewView, owner: LifecycleOwner) {
        val preview = Preview.Builder().build().also { it.setSurfaceProvider(previewView.surfaceProvider) }
        val analysis = ImageAnalysis.Builder()
            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
            .setResolutionSelector(resolution(1280, 720))
            .build()
        analysis.setAnalyzer(cameraExecutor, QrCodeAnalyzer { raw -> runOnUiThread { onQrScanned(raw) } })
        try {
            provider.unbindAll()
            provider.bindToLifecycle(owner, CameraSelector.DEFAULT_BACK_CAMERA, preview, analysis)
        } catch (e: Exception) {
            Log.e(TAG, "QR scanner binding failed", e)
        }
    }

    private fun bindFaceCamera(provider: ProcessCameraProvider, previewView: PreviewView, owner: LifecycleOwner) {
        val previewBuilder = Preview.Builder()
        val analysisBuilder = ImageAnalysis.Builder()
            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
            .setResolutionSelector(resolution(640, 480))
        // A steady frame rate matters for rPPG: ask for a fixed 30 fps if the camera offers it.
        val ranges = CameraTuning.frontFpsRanges(this)
        val range = CameraTuning.chooseFpsRange(ranges, RppgConfig.TARGET_FPS)
        diagnostics.supportedFpsRanges = ranges.joinToString(" ") { "[${it.lower},${it.upper}]" }
        diagnostics.fpsRange = range?.let { "[${it.lower},${it.upper}]" } ?: "default"
        if (range != null) {
            CameraTuning.applyFpsRange(previewBuilder, range)
            CameraTuning.applyFpsRange(analysisBuilder, range)
        }
        Log.i(ScanDiagnostics.TAG, "Camera fps ranges: ${diagnostics.supportedFpsRanges} -> using ${diagnostics.fpsRange}")
        val preview = previewBuilder.build().also { it.setSurfaceProvider(previewView.surfaceProvider) }
        val analysis = analysisBuilder.build()
        analysis.setAnalyzer(cameraExecutor) { image -> analyzeFrame(image) }
        try {
            provider.unbindAll()
            boundCamera = provider.bindToLifecycle(owner, CameraSelector.DEFAULT_FRONT_CAMERA, preview, analysis)
        } catch (e: Exception) {
            Log.e(TAG, "Face camera binding failed", e)
        }
    }

    /** Once the face is lit correctly, freeze exposure and white balance, then restart the window. */
    private fun maybeLockExposure(t: Double) {
        val started = firstFaceSec ?: return
        val camera = boundCamera ?: return
        if (aeLockRequested || t - started < RppgConfig.AE_SETTLE_SEC) return
        aeLockRequested = true
        CameraTuning.lockExposure(this, camera) { ok ->
            diagnostics.aeLocked = ok
            Log.i(ScanDiagnostics.TAG, "Exposure/white-balance lock: ${if (ok) "locked" else "not supported"}")
            if (ok && !submitted.get()) {
                // Samples from before the lock contain exposure changes: start the window afresh.
                RppgNative.nativeReset()
                firstFaceSec = lastFaceSeenSec
            }
        }
    }

    /**
     * Every other face detection: align the face straight from the camera planes
     * (C++), then run MobileFaceNet on the embedding thread. Called from the ML Kit
     * success listener, while the image is still open.
     */
    private fun maybeEmbed(imageProxy: ImageProxy, face: com.google.mlkit.vision.face.Face, rotation: Int, width: Int, height: Int) {
        detectionCount++
        val embedder = faceEmbedder ?: return
        if (detectionCount % 2 != 0 || embedBusy) return
        val a = face.getLandmark(FaceLandmark.LEFT_EYE)?.position ?: return
        val b = face.getLandmark(FaceLandmark.RIGHT_EYE)?.position ?: return
        val planes = imageProxy.planes
        val crop = FloatArray(FaceNative.TENSOR_LENGTH)
        val r = FaceNative.nativeAlignFace(
            planes[0].buffer, planes[1].buffer, planes[2].buffer, width, height,
            planes[0].rowStride, planes[0].pixelStride, planes[1].rowStride, planes[1].pixelStride,
            rotation, a.x.toDouble(), a.y.toDouble(), b.x.toDouble(), b.y.toDouble(), crop,
        )
        if (r.size < 4 || r[0] < 0.5) return
        val q = FaceCapture.quality(face.headEulerAngleY, face.headEulerAngleX, face.headEulerAngleZ, r[3], r[2], r[1])
        if (q <= 0f) return
        embedBusy = true
        embedExecutor.execute {
            try {
                val started = System.nanoTime()
                val embedding = embedder.embed(crop)
                faceCapture.add(embedding, q)
                faceFramesState.intValue = faceCapture.goodFrames()
                Log.d(FaceEmbedder.TAG, "embedding #${faceCapture.framesSeen}: q=%.2f sharp=%.0f luma=%.0f eyes=%.0fpx yaw=%.0f pitch=%.0f in %d ms"
                    .format(q, r[1], r[2], r[3], face.headEulerAngleY, face.headEulerAngleX, (System.nanoTime() - started) / 1_000_000))
            } catch (e: Exception) {
                Log.e(FaceEmbedder.TAG, "Embedding failed", e)
            } finally {
                embedBusy = false
            }
        }
    }

    /** More than one face in view: stop the scan and report it (signed), so the portal is told too. */
    private fun onMultipleFaces(state: ScanState.Measuring, count: Int) {
        if (!submitted.compareAndSet(false, true)) return
        Log.w(FaceEmbedder.TAG, "$count faces in view: scan stopped")
        telemetryStreamer.send("multiple_faces", mapOf("message" to "$count faces in view"))
        runOnUiThread { submitResult(state, rppgState.value, livenessPassed = false, abortReason = "MULTIPLE_FACES") }
    }

    /** Plain-language hint when conditions make the pulse hard to measure. */
    private fun guidanceFor(r: RppgResult, faceVisible: Boolean): String? = when {
        !faceVisible -> "Face the camera"
        faceWidthFraction < RppgConfig.FACE_MIN_WIDTH_FRACTION -> "Move closer"
        r.faceSampleValid && r.luma < RppgConfig.LUMA_TOO_DARK -> "Move to brighter light"
        r.faceSampleValid && r.luma > RppgConfig.LUMA_TOO_BRIGHT -> "Too bright: avoid direct light on your face"
        faceMoving -> "Hold still"
        else -> null
    }

    private fun resolution(w: Int, h: Int): ResolutionSelector = ResolutionSelector.Builder()
        .setResolutionStrategy(ResolutionStrategy(AndroidSize(w, h), ResolutionStrategy.FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER))
        .build()

    // ── Per-frame processing (camera thread) ────────────────────────────

    @OptIn(ExperimentalGetImage::class)
    private fun analyzeFrame(imageProxy: ImageProxy) {
        val state = scanState.value
        val mediaImage = imageProxy.image
        if (state !is ScanState.Measuring || submitted.get() || mediaImage == null) {
            imageProxy.close()
            return
        }
        val t = imageProxy.imageInfo.timestamp / 1_000_000_000.0
        diagnostics.onFrame(t)
        val rotation = imageProxy.imageInfo.rotationDegrees
        val width = imageProxy.width
        val height = imageProxy.height

        // 1. rPPG on every frame, using the most recent face ROIs.
        val rois = currentRois
        if (rois != null) {
            if (t - lastFaceSeenSec > RppgConfig.FACE_LOST_RESET_SEC) {
                onFaceLost()
            } else {
                val planes = imageProxy.planes
                val raw = RppgNative.nativeProcessFrame(
                    planes[0].buffer, planes[1].buffer, planes[2].buffer,
                    width, height,
                    planes[0].rowStride, planes[0].pixelStride,
                    planes[1].rowStride, planes[1].pixelStride,
                    rois, t,
                )
                val result = RppgResult.fromArray(raw)
                diagnostics.onResult(result, t, faceVisibleState.value)
                if (result.newEstimate || frameCounter % 5 == 0) {
                    diagSnapshotState.value = diagnostics.snapshot
                    guidanceState.value = guidanceFor(result, faceVisibleState.value)
                }
                onRppgResult(result, t, state)
            }
        }

        // 2. Face detection on every Nth frame (ML Kit keeps the image until it finishes).
        frameCounter++
        if (frameCounter % RppgConfig.FACE_DETECTION_INTERVAL != 0 || isDetectingFace) {
            imageProxy.close()
            return
        }
        isDetectingFace = true
        detector.process(InputImage.fromMediaImage(mediaImage, rotation))
            .addOnSuccessListener { faces ->
                // One face only, at any point of the scan (build-prompt §4.2).
                if (faces.size > 1) {
                    onMultipleFaces(state, faces.size)
                    return@addOnSuccessListener
                }
                val face = faces.firstOrNull()
                // The same tracked face must provide the pulse and the identity: if ML Kit
                // starts tracking a different face, everything measured so far is discarded.
                val id = face?.trackingId
                if (face != null && id != null) {
                    val previous = trackedFaceId
                    if (previous != null && previous != id) {
                        Log.w(FaceEmbedder.TAG, "Tracked face changed ($previous -> $id): restarting the scan")
                        onFaceLost()
                    }
                    trackedFaceId = id
                }
                if (face != null) {
                    faceBoxState.value = RectF(face.boundingBox)
                    maybeEmbed(imageProxy, face, rotation, width, height)
                    currentRois = FaceRois.sensorRois(face.boundingBox, width, height, rotation)
                    lastFaceSeenSec = t
                    if (firstFaceSec == null) firstFaceSec = t
                    faceVisibleState.value = true
                    val uprightWidth = if (rotation == 90 || rotation == 270) height else width
                    val box = face.boundingBox
                    faceWidthFraction = box.width().toDouble() / uprightWidth
                    val center = Pair(box.exactCenterX(), box.exactCenterY())
                    lastFaceCenter?.let { prev ->
                        val jump = Math.hypot((center.first - prev.first).toDouble(), (center.second - prev.second).toDouble())
                        faceMoving = jump / box.width() > RppgConfig.MOTION_MAX_FRACTION
                    }
                    lastFaceCenter = center
                    maybeLockExposure(t)
                    roiOverlayState.value = FaceRois.uprightRois(face.boundingBox)
                    overlayImageSize.value = if (rotation == 90 || rotation == 270) {
                        AndroidSize(height, width)
                    } else {
                        AndroidSize(width, height)
                    }
                } else {
                    faceVisibleState.value = false
                }
            }
            .addOnFailureListener { e -> Log.w(TAG, "Face detection failed: ${e.message}") }
            .addOnCompleteListener {
                isDetectingFace = false
                imageProxy.close()
            }
    }

    private fun onFaceLost() {
        Log.w(TAG_DSP, "Face lost for more than ${RppgConfig.FACE_LOST_RESET_SEC}s: restarting the measurement")
        RppgNative.nativeReset()
        currentRois = null
        firstFaceSec = null  // the no-pulse timeout also restarts
        rppgState.value = RppgResult.EMPTY
        roiOverlayState.value = emptyList()
        faceVisibleState.value = false
        telemetryStreamer.send("face_lost")
        diagnostics.onFaceLost()
        faceCapture.reset()
        faceFramesState.intValue = 0
        faceBoxState.value = null
        guidanceState.value = "Face the camera"
    }

    private fun onRppgResult(result: RppgResult, t: Double, state: ScanState.Measuring) {
        rppgState.value = result
        if (result.newEstimate) {
            Log.i(TAG_TELEMETRY, "estimate #${result.estimateCount}: bpm=%.1f snr=%.1f dB (median %.1f) fill=%.2f stable=%b"
                .format(result.bpm, result.snrDb, result.medianSnrDb, result.windowFill, result.stable))
            telemetryStreamer.send("measuring", mapOf(
                "bpm" to result.bpm, "snr" to result.medianSnrDb,
                "progress" to result.windowFill, "stable" to result.stable,
            ))
        }
        if (result.stable && submitted.compareAndSet(false, true)) {
            Log.i(TAG_DSP, "Stable pulse: %.1f BPM, SNR %.1f dB → submitting".format(result.bpm, result.medianSnrDb))
            telemetryStreamer.send("stable_reading", mapOf("bpm" to result.bpm, "snr" to result.medianSnrDb))
            runOnUiThread { submitResult(state, result, livenessPassed = true) }
            return
        }
        val started = firstFaceSec
        if (started != null && t - started > gates.timeoutSec && submitted.compareAndSet(false, true)) {
            Log.w(TAG_DSP, "No stable pulse within ${gates.timeoutSec}s (last SNR %.1f dB) → reporting no pulse"
                .format(result.medianSnrDb))
            runOnUiThread { submitResult(state, result, livenessPassed = false) }
        }
    }

    // ── Signing and submission ──────────────────────────────────────────

    private fun submitResult(
        state: ScanState.Measuring, result: RppgResult, livenessPassed: Boolean, abortReason: String? = null,
    ) {
        scanState.value = ScanState.Submitting
        lifecycleScope.launch {
            try {
                val diag = diagnostics.summary(abortReason ?: if (livenessPassed) "stable" else "timeout", result)
                val request = withContext(Dispatchers.Default) {
                    buildSignedRequest(state.qr, result, livenessPassed, diag, abortReason)
                }
                val response = ApiClient.service(state.baseUrl).verifyBiometrics(request)
                val body = response.body()
                val outcome = when {
                    response.isSuccessful && body?.status == "ACCESS_GRANTED" ->
                        ScanState.Result(true, "Verified", "Pulse %.0f BPM. The portal has been updated.".format(result.bpm))
                    body != null ->
                        ScanState.Result(false, "Not verified", body.reason ?: "Verification failed")
                    else ->
                        ScanState.Result(false, "Not verified", "Server error ${response.code()}")
                }
                Log.i(TAG, "Verify response: ${response.code()} ${body?.status} ${body?.reasonCode ?: ""}")
                finishScan(outcome)
            } catch (e: Exception) {
                Log.e(TAG, "Submission failed", e)
                finishScan(ScanState.Result(false, "Could not send the result", e.message ?: "Network error"))
            }
        }
    }

    private fun buildSignedRequest(
        qr: QrPayload, result: RppgResult, livenessPassed: Boolean, diag: ScanDiagnosticsPayload,
        abortReason: String? = null,
    ): VerifyRequest {
        // Milestone 3: embeddings are collected on every scan; logged here so the face path
        // can be checked on the phone. Milestone 4 puts them into the signed payload.
        val template = faceCapture.buildTemplate()
        Log.i(FaceEmbedder.TAG, "Face frames: ${faceCapture.goodFrames()} good of ${faceCapture.framesSeen}; " +
            "template ${if (template != null) "built (${template.size} values)" else "not enough good frames"}")
        val timestamp = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply {
            timeZone = TimeZone.getTimeZone("UTC")
        }.format(Date())
        val payload = BiometricPayload(
            sessionId = qr.sessionId,
            purpose = qr.purpose,
            nonce = qr.nonce,
            timestamp = timestamp,
            deviceId = Settings.Secure.getString(contentResolver, Settings.Secure.ANDROID_ID) ?: "unknown",
            bpm = result.bpm,
            snr = result.medianSnrDb,
            livenessPassed = livenessPassed,
            framesUsed = result.samplesInWindow,
            appVersion = BuildConfig.VERSION_NAME,
            diagnostics = diag,
            abortReason = abortReason,
        )
        val payloadJson = Json.encodeToString(BiometricPayload.serializer(), payload)
        if (!cryptoManager.hasKey()) cryptoManager.generateHardwareKey()
        return VerifyRequest(
            payload = Base64.encodeToString(payloadJson.toByteArray(Charsets.UTF_8), Base64.NO_WRAP),
            signature = cryptoManager.signPayload(payloadJson),
            publicKey = cryptoManager.getBase64PublicKey(),
            attestationChain = cryptoManager.getAttestationChain(),
        )
    }

    // ── Screens ─────────────────────────────────────────────────────────

    @Composable
    private fun HomeScreen(onScan: () -> Unit) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
            modifier = Modifier.fillMaxSize().padding(32.dp),
        ) {
            Text("Jeevan Suraksha", color = Color.White, fontSize = 30.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(12.dp))
            Text(
                "Scan the QR code shown on the portal to start.",
                color = Color.White.copy(alpha = 0.8f), fontSize = 20.sp, textAlign = TextAlign.Center,
            )
            Spacer(Modifier.height(40.dp))
            Button(
                onClick = onScan,
                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFE8603C)),
                modifier = Modifier.fillMaxWidth().height(64.dp),
            ) {
                Text("Scan QR code", fontSize = 22.sp, fontWeight = FontWeight.Bold, color = Color.White)
            }
        }
    }

    @Composable
    private fun BannerText(text: String) {
        Box(Modifier.fillMaxSize()) {
            Text(
                text, color = Color.White, fontSize = 20.sp, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center,
                modifier = Modifier.align(Alignment.TopCenter).padding(top = 48.dp, start = 24.dp, end = 24.dp)
                    .background(Color.Black.copy(alpha = 0.5f)).padding(12.dp),
            )
        }
    }

    @Composable
    private fun BusyScreen(message: String) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            CircularProgressIndicator(color = Color(0xFFE8603C), modifier = Modifier.size(64.dp))
            Spacer(Modifier.height(20.dp))
            Text(message, color = Color.White, fontSize = 20.sp)
        }
    }

    @Composable
    private fun ResultScreen(result: ScanState.Result) {
        val color = if (result.success) GREEN else Color(0xFFFF5252)
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.fillMaxSize().padding(32.dp),
            verticalArrangement = Arrangement.Center,
        ) {
            Text(if (result.success) "✓" else "!", color = color, fontSize = 72.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(12.dp))
            Text(result.title, color = color, fontSize = 28.sp, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center)
            result.message?.let {
                Spacer(Modifier.height(12.dp))
                Text(it, color = Color.White, fontSize = 18.sp, textAlign = TextAlign.Center)
            }
            Spacer(Modifier.height(36.dp))
            Button(
                onClick = { scanState.value = ScanState.Home },
                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFE8603C)),
                modifier = Modifier.width(220.dp).height(56.dp),
            ) {
                Text("Done", fontSize = 20.sp, color = Color.White)
            }
        }
    }

    @Composable
    private fun MeasuringHud() {
        val r by rppgState
        val faceVisible by faceVisibleState
        val guidance by guidanceState
        val showDiag by showDiagnostics
        val snap by diagSnapshotState
        val prompt = when {
            r.stable -> "Pulse steady ✓"
            guidance != null -> guidance!!
            !faceVisible && !r.hasEstimate -> "Position your face in the frame"
            r.hasEstimate -> "Measuring… hold still"
            else -> "Measuring…"
        }
        Box(Modifier.fillMaxSize()) {
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                modifier = Modifier.align(Alignment.TopCenter).fillMaxWidth()
                    .background(Color.Black.copy(alpha = 0.55f)).padding(16.dp),
            ) {
                Text(prompt, color = if (r.stable) GREEN else Color.White, fontSize = 24.sp, fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(10.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(
                        progress = r.windowFill.toFloat(),
                        color = if (r.stable) GREEN else AMBER,
                        strokeWidth = 6.dp,
                        modifier = Modifier.size(48.dp),
                    )
                    Spacer(Modifier.width(20.dp))
                    Metric("PULSE", if (r.hasEstimate) "%.0f".format(r.bpm) else "--", "BPM",
                        if (r.stable) GREEN else Color.White.copy(alpha = 0.6f))
                    Spacer(Modifier.width(24.dp))
                    Metric("SIGNAL", if (r.hasEstimate) "%.1f".format(r.medianSnrDb) else "--", "dB",
                        Color(0xFF00CCFF))
                }
            }
            PulseWaveform(r.waveform, Modifier.align(Alignment.BottomCenter).padding(bottom = 48.dp))
            // Small diagnostics toggle (off by default so the demo screen stays clean).
            Text(
                if (showDiag) "Hide diagnostics" else "Diagnostics",
                color = Color.White.copy(alpha = 0.7f), fontSize = 13.sp,
                modifier = Modifier.align(Alignment.BottomEnd).padding(12.dp)
                    .background(Color.Black.copy(alpha = 0.45f))
                    .clickable { showDiagnostics.value = !showDiag }
                    .padding(horizontal = 10.dp, vertical = 6.dp),
            )
            val sn = snap
            if (showDiag && sn != null) {
                Column(
                    modifier = Modifier.align(Alignment.CenterStart).padding(12.dp)
                        .background(Color.Black.copy(alpha = 0.6f)).padding(10.dp),
                ) {
                    DiagLine("time", "%.1f s".format(sn.elapsedSec))
                    DiagLine("camera", "%.1f fps %s".format(sn.fps, sn.fpsRange))
                    DiagLine("pulse", "%.1f BPM (spread %.1f)".format(sn.bpm, sn.spreadBpm))
                    DiagLine("SNR", "%.1f dB (min %.1f)".format(sn.snrDb, sn.minSnrDb))
                    DiagLine("light", "%.0f / 255".format(sn.luma))
                    DiagLine("AE lock", if (sn.aeLocked) "yes" else "no")
                    DiagLine("waiting for", sn.gate.label)
                    DiagLine("face frames", "${faceFramesState.intValue} good")
                }
            }
        }
    }

    @Composable
    private fun DiagLine(label: String, value: String) {
        Row {
            Text("$label: ", color = Color.White.copy(alpha = 0.7f), fontSize = 13.sp)
            Text(value, color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.Bold)
        }
    }

    @Composable
    private fun Metric(label: String, value: String, unit: String, color: Color) {
        Column {
            Text(label, color = color.copy(alpha = 0.8f), fontSize = 12.sp, fontWeight = FontWeight.Bold)
            Row(verticalAlignment = Alignment.Bottom) {
                Text(value, color = color, fontSize = 36.sp, fontWeight = FontWeight.Black)
                Text(" $unit", color = color.copy(alpha = 0.8f), fontSize = 14.sp, modifier = Modifier.padding(bottom = 6.dp))
            }
        }
    }

    @Composable
    private fun PulseWaveform(signal: DoubleArray, modifier: Modifier) {
        Canvas(modifier = modifier.fillMaxWidth().height(140.dp).padding(horizontal = 16.dp)) {
            if (signal.size < 2) return@Canvas
            val path = Path()
            val xStep = size.width / (signal.size - 1)
            val mid = size.height / 2f
            signal.forEachIndexed { i, v ->
                val x = i * xStep
                val y = mid - (v.toFloat() * size.height * 0.42f)  // signal is already scaled to [-1, 1]
                if (i == 0) path.moveTo(x, y) else path.lineTo(x, y)
            }
            drawPath(path, color = GREEN, style = Stroke(width = 5f))
        }
    }

    /** Draws the forehead/cheek ROIs over the (mirrored, FILL_CENTER) front-camera preview. */
    @Composable
    private fun RoiOverlay() {
        val rois by roiOverlayState
        val img by overlayImageSize
        val box by faceBoxState
        Canvas(modifier = Modifier.fillMaxSize()) {
            if (rois.isEmpty() || img.width == 0 || img.height == 0) return@Canvas
            val scale = maxOf(size.width / img.width, size.height / img.height)
            val dx = (size.width - img.width * scale) / 2f
            val dy = (size.height - img.height * scale) / 2f
            box?.let { f ->
                drawRect(
                    color = AMBER,
                    topLeft = Offset(size.width - (dx + f.right * scale), dy + f.top * scale),
                    size = ComposeSize(f.width() * scale, f.height() * scale),
                    style = Stroke(width = 6f),
                )
            }
            rois.forEach { r ->
                val left = size.width - (dx + r.right * scale)  // mirror X for the front camera
                val top = dy + r.top * scale
                drawRect(
                    color = GREEN,
                    topLeft = Offset(left, top),
                    size = ComposeSize(r.width() * scale, r.height() * scale),
                    style = Stroke(width = 4f),
                )
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        telemetryStreamer.shutdown()
        cameraExecutor.shutdown()
        embedExecutor.shutdown()
        faceEmbedder?.close()
        detector.close()
    }
}
