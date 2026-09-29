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
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.lifecycleScope
import com.example.sentinelhard.camera.CameraTuning
import com.example.sentinelhard.camera.QrCodeAnalyzer
import com.example.sentinelhard.face.ChallengeVerifier
import com.example.sentinelhard.face.FaceCapture
import com.example.sentinelhard.face.FaceEmbedder
import com.example.sentinelhard.face.FaceNative
import com.example.sentinelhard.models.BiometricPayload
import com.example.sentinelhard.models.ScanDiagnosticsPayload
import com.example.sentinelhard.models.VerifyRequest
import com.example.sentinelhard.models.VerifyResponse
import com.example.sentinelhard.network.ApiClient
import com.example.sentinelhard.network.QrPayload
import com.example.sentinelhard.rppg.FaceRois
import com.example.sentinelhard.rppg.GateSettings
import com.example.sentinelhard.rppg.RppgConfig
import com.example.sentinelhard.rppg.RppgNative
import com.example.sentinelhard.rppg.RppgResult
import com.example.sentinelhard.rppg.ScanDiagnostics
import com.example.sentinelhard.ui.BusyScreen
import com.example.sentinelhard.ui.ConsentScreen
import com.example.sentinelhard.ui.FaceScanHud
import com.example.sentinelhard.ui.Jst
import com.example.sentinelhard.ui.QrScannerOverlay
import com.example.sentinelhard.ui.ResultKind
import com.example.sentinelhard.ui.ResultScreen
import com.example.sentinelhard.ui.WelcomeScreen
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.face.Face
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
import kotlin.math.ceil

/**
 * The app's four screens (build-prompt §4.6): Scan QR → Consent → Face Scan → Result.
 * Welcome/Connecting/Submitting are the start and the waits of those screens.
 */
sealed class ScanState {
    object Welcome : ScanState()
    object ScanQr : ScanState()
    data class Connecting(val qr: QrPayload) : ScanState()
    data class Consent(val qr: QrPayload, val baseUrl: String) : ScanState()
    data class Measuring(val qr: QrPayload, val baseUrl: String) : ScanState()
    object Submitting : ScanState()
    data class Result(val kind: ResultKind, val title: String, val message: String?) : ScanState()
}

/**
 * Steps inside the face scan: stable pulse first, then the random challenge,
 * then (if needed) a moment more to collect enough clear face frames.
 * Practice scans (AUTH) have no challenge and submit on the stable pulse.
 */
enum class ScanPhase { PULSE, CHALLENGE, CAPTURE, DONE }

private enum class CameraMode { QR, FACE }

/** What the phone concluded; the backend makes the decision. */
private data class Verdict(val livenessPassed: Boolean, val challengePassed: Boolean?, val abortReason: String? = null)

/** Challenge progress for the screen. */
private data class ChallengeUi(val type: String, val secondsLeft: Int, val blinks: Int, val hint: String?, val yaw: Float)

class MainActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "SentinelHard"
        private const val TAG_DSP = "SentinelDSP"
        private const val TAG_TELEMETRY = "SentinelTelemetry"
        private const val TAG_CHALLENGE = "SentinelChallenge"
        private val ROI_GREEN = Color(0xFF00FF66)

        /** After the challenge, wait at most this long for enough clear face frames. */
        private const val CAPTURE_TIMEOUT_SEC = 6.0
    }

    // ── UI state (Compose) ──────────────────────────────────────────────
    private val scanState = mutableStateOf<ScanState>(ScanState.Welcome)
    private val rppgState = mutableStateOf(RppgResult.EMPTY)
    private val faceVisibleState = mutableStateOf(false)
    private val roiOverlayState = mutableStateOf<List<RectF>>(emptyList())
    private val overlayImageSize = mutableStateOf(AndroidSize(0, 0))  // upright analysis image size
    private val showDiagnostics = mutableStateOf(false)                  // off by default for the demo
    private val diagSnapshotState = mutableStateOf<ScanDiagnostics.Snapshot?>(null)
    private val guidanceState = mutableStateOf<String?>(null)
    private val faceBoxState = mutableStateOf<RectF?>(null)              // whole face, upright coords
    private val faceFramesState = mutableIntStateOf(0)                   // good embedding frames so far
    private val phaseState = mutableStateOf(ScanPhase.PULSE)
    private val challengeUiState = mutableStateOf<ChallengeUi?>(null)
    private val verifiedState = mutableStateOf(false)                    // pulse + challenge passed

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

    // Challenge and phases (Milestone 4)
    private val phaseLock = Any()
    @Volatile private var phase = ScanPhase.PULSE
    @Volatile private var activeQr: QrPayload? = null
    @Volatile private var challenge: ChallengeVerifier? = null
    @Volatile private var stableResult: RppgResult? = null
    @Volatile private var captureStartedSec = 0.0

    private val cryptoManager = CryptoManager()
    private val cameraExecutor = Executors.newSingleThreadExecutor()
    private val telemetryStreamer = TelemetryStreamer()
    private val lenientJson = Json { ignoreUnknownKeys = true }

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
            scanState.value = ScanState.Result(ResultKind.FAILURE, "Camera permission needed",
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
                Log.i(TAG, "Signing key: ${cryptoManager.keySecurityLevel()}")
            } catch (e: Exception) {
                Log.e(TAG, "Key generation failed", e)
            }
        }

        setContent {
            MaterialTheme {
                val state by scanState
                val dark = state is ScanState.ScanQr || state is ScanState.Measuring
                Box(Modifier.fillMaxSize().background(if (dark) Color.Black else Jst.Surface)) {
                    when (val s = state) {
                        is ScanState.Welcome -> WelcomeScreen(onScan = { startQrScan() })
                        is ScanState.ScanQr -> {
                            key(CameraMode.QR) { CameraPreview(CameraMode.QR) }
                            QrScannerOverlay(onCancel = { scanState.value = ScanState.Welcome })
                        }
                        is ScanState.Connecting -> BusyScreen("Connecting to the portal…")
                        is ScanState.Consent -> ConsentScreen(
                            title = consentTitle(s.qr), points = consentPoints(s.qr),
                            onAgree = { onConsentAgreed(s) },
                            onCancel = { scanState.value = ScanState.Welcome },
                        )
                        is ScanState.Measuring -> {
                            key(CameraMode.FACE) { CameraPreview(CameraMode.FACE) }
                            FaceScanScreen(s.qr)
                        }
                        is ScanState.Submitting -> BusyScreen("Sending your signed result…")
                        is ScanState.Result -> ResultScreen(s.kind, s.title, s.message,
                            onDone = { scanState.value = ScanState.Welcome })
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
            scanState.value = ScanState.Result(ResultKind.FAILURE, "Not a portal QR code",
                "Please scan the QR code shown on the Jeevan Suraksha portal.")
            return
        }
        Log.i(TAG, "QR scanned: session=${qr.sessionId} purpose=${qr.purpose} base_url=${qr.baseUrl} " +
            "challenge=${qr.challengeType} (${qr.challengeTimeoutSec}s) min_snr_db=${qr.minSnrDb}")
        val problem = unsupportedReason(qr)
        if (problem != null) {
            scanState.value = ScanState.Result(ResultKind.FAILURE, "App update needed", problem)
            return
        }
        scanState.value = ScanState.Connecting(qr)
        lifecycleScope.launch {
            val probe = ApiClient.resolveReachableBaseUrl(qr.baseUrl)
            val baseUrl = probe.baseUrl
            if (baseUrl == null) {
                scanState.value = ScanState.Result(ResultKind.FAILURE, "Can't reach the laptop",
                    probe.describeFailure() + "\n\nPhone and laptop must be on the same Wi-Fi, with port 8000 " +
                        "allowed in Windows Firewall. Over USB: adb reverse tcp:8000 tcp:8000")
            } else {
                scanState.value = ScanState.Consent(qr, baseUrl)
            }
        }
    }

    private fun unsupportedReason(qr: QrPayload): String? {
        val known = setOf(QrPayload.PURPOSE_AUTH, QrPayload.PURPOSE_ENROLLMENT, QrPayload.PURPOSE_LIFE_CERTIFICATE)
        return when {
            qr.purpose !in known ->
                "This QR code is for \"${qr.purpose}\", which this app version does not support."
            !qr.isAuth && qr.challengeId == null ->
                "This QR code has no challenge. Please refresh the QR code on the portal and scan again."
            !qr.isAuth && !ChallengeVerifier.SUPPORTED.contains(qr.challengeType ?: "") ->
                "The portal asked for an action (${qr.challengeType}) this app does not know. Please update the app."
            else -> null
        }
    }

    private fun consentTitle(qr: QrPayload): String = when (qr.purpose) {
        QrPayload.PURPOSE_ENROLLMENT -> "Register your face"
        QrPayload.PURPOSE_LIFE_CERTIFICATE -> "Submit your life certificate"
        else -> "Practice scan"
    }

    private fun consentPoints(qr: QrPayload): List<String> = buildList {
        add("The camera measures your pulse from tiny colour changes in your face, to check that a real person is present.")
        when (qr.purpose) {
            QrPayload.PURPOSE_ENROLLMENT -> add("Your face is turned into a code of numbers (not a photo). " +
                "The pension office keeps it encrypted, to recognise you next year.")
            QrPayload.PURPOSE_LIFE_CERTIFICATE -> add("Your face is turned into a code of numbers (not a photo) " +
                "and compared only with your own registered code.")
            else -> add("This is only a practice. Nothing is kept.")
        }
        if (!qr.isAuth) add("You will be asked to do one simple action, such as blinking twice.")
        add("No photos or videos are saved or sent. Camera frames are deleted straight after they are measured.")
        add("The result is signed by this phone's security chip and sent to the portal.")
    }

    private fun onConsentAgreed(s: ScanState.Consent) {
        if (!s.qr.isAuth && faceEmbedder == null) {
            scanState.value = ScanState.Result(ResultKind.FAILURE, "Face model not ready",
                "The face-recognition model could not be loaded. Close and reopen the app, then scan the QR code again.")
            return
        }
        startMeasuring(s.qr, s.baseUrl)
    }

    private fun startMeasuring(qr: QrPayload, baseUrl: String) {
        resetMeasurement()
        activeQr = qr
        challenge = newChallenge(qr)
        gates = GateSettings.from(qr)
        Log.i(ScanDiagnostics.TAG, "Gates: min_snr=${gates.minSnrDb} dB window=${gates.windowSec}s " +
            "stable=${gates.stableCount} within +/-${gates.stableToleranceBpm} BPM timeout=${gates.timeoutSec}s")
        RppgNative.nativeConfigure(gates.minSnrDb, gates.windowSec, gates.stableCount, gates.stableToleranceBpm)
        telemetryStreamer.connect(baseUrl, qr.sessionId, qr.nonce)
        telemetryStreamer.send("scan_started")
        scanState.value = ScanState.Measuring(qr, baseUrl)
    }

    private fun newChallenge(qr: QrPayload?): ChallengeVerifier? {
        if (qr == null || qr.isAuth) return null
        val type = qr.challengeType ?: return null
        return ChallengeVerifier(type, qr.challengeTimeoutSec?.toDouble() ?: ChallengeVerifier.DEFAULT_TIMEOUT_SEC)
    }

    private fun setPhase(p: ScanPhase) {
        phase = p
        phaseState.value = p
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
        setPhase(ScanPhase.PULSE)
        challengeUiState.value = null
        verifiedState.value = false
        stableResult = null
        captureStartedSec = 0.0
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
            if (ok && !submitted.get() && phase == ScanPhase.PULSE) {
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
    private fun maybeEmbed(imageProxy: ImageProxy, face: Face, rotation: Int, width: Int, height: Int) {
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
        if (submitted.get()) return
        Log.w(FaceEmbedder.TAG, "$count faces in view: scan stopped")
        telemetryStreamer.send("multiple_faces", mapOf("message" to "$count faces in view"))
        submit(state, rppgState.value, Verdict(false, challenge?.let { false }, "MULTIPLE_FACES"))
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

        // 0. Time limits of the challenge and the face capture (also when no face is found).
        when (phase) {
            ScanPhase.CHALLENGE -> challenge?.let { c ->
                if (c.onTick(t) == ChallengeVerifier.Status.FAILED) onChallengeFailed(state, c) else publishChallengeUi(c, t)
            }
            ScanPhase.CAPTURE -> maybeFinishCapture(state, t)
            else -> {}
        }

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

        // 2. Face detection on every Nth frame (every frame during the challenge, so a
        //    blink is not missed). ML Kit keeps the image until it finishes.
        frameCounter++
        val interval = if (phase == ScanPhase.CHALLENGE) 1 else RppgConfig.FACE_DETECTION_INTERVAL
        if (frameCounter % interval != 0 || isDetectingFace) {
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
                // The same tracked face must provide the pulse, the challenge and the identity:
                // if ML Kit starts tracking a different face, everything measured so far is discarded.
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
                    if (phase == ScanPhase.CHALLENGE) onChallengeSample(state, face, t)
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
        // The pulse, the challenge and the face frames must all come from one face:
        // losing it during the challenge starts the whole scan again.
        synchronized(phaseLock) {
            if (phase == ScanPhase.CHALLENGE || phase == ScanPhase.CAPTURE) {
                Log.w(TAG_CHALLENGE, "Face lost during the ${phase.name.lowercase()} step: back to measuring the pulse")
                setPhase(ScanPhase.PULSE)
                challenge = newChallenge(activeQr)
                stableResult = null
                challengeUiState.value = null
                verifiedState.value = false
            }
        }
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
        if (phase != ScanPhase.PULSE || submitted.get()) return
        if (result.stable) {
            onPulseStable(result, t, state)
            return
        }
        val started = firstFaceSec
        if (started != null && t - started > gates.timeoutSec) {
            Log.w(TAG_DSP, "No stable pulse within ${gates.timeoutSec}s (last SNR %.1f dB) → reporting no pulse"
                .format(result.medianSnrDb))
            submit(state, result, Verdict(false, challenge?.let { false }))
        }
    }

    // ── Challenge and face capture (Milestone 4) ────────────────────────

    /** Stable pulse: practice scans submit now; the others get the random challenge. */
    private fun onPulseStable(result: RppgResult, t: Double, state: ScanState.Measuring) {
        Log.i(TAG_DSP, "Stable pulse: %.1f BPM, SNR %.1f dB".format(result.bpm, result.medianSnrDb))
        stableResult = result
        telemetryStreamer.send("stable_reading", mapOf("bpm" to result.bpm, "snr" to result.medianSnrDb))
        val c = challenge
        if (c == null) {
            verifiedState.value = true
            submit(state, result, Verdict(true, null))
            return
        }
        synchronized(phaseLock) {
            if (phase != ScanPhase.PULSE) return
            setPhase(ScanPhase.CHALLENGE)
        }
        c.start(t)
        Log.i(TAG_CHALLENGE, "Challenge issued: ${c.type} (time limit ${state.qr.challengeTimeoutSec ?: ChallengeVerifier.DEFAULT_TIMEOUT_SEC.toInt()} s)")
        telemetryStreamer.send("challenge_issued", mapOf("challenge_type" to c.type))
        publishChallengeUi(c, t)
    }

    private fun onChallengeSample(state: ScanState.Measuring, face: Face, t: Double) {
        val c = challenge ?: return
        when (c.onFace(t, face.headEulerAngleY, face.leftEyeOpenProbability, face.rightEyeOpenProbability)) {
            ChallengeVerifier.Status.PASSED -> onChallengePassed(state, c, t)
            ChallengeVerifier.Status.FAILED -> onChallengeFailed(state, c)
            ChallengeVerifier.Status.RUNNING -> publishChallengeUi(c, t)
        }
    }

    private fun publishChallengeUi(c: ChallengeVerifier, t: Double) {
        challengeUiState.value = ChallengeUi(c.type, ceil(c.remainingSec(t)).toInt(), c.blinks, c.hint, c.lastYaw)
    }

    private fun onChallengePassed(state: ScanState.Measuring, c: ChallengeVerifier, t: Double) {
        synchronized(phaseLock) {
            if (phase != ScanPhase.CHALLENGE) return
            setPhase(ScanPhase.CAPTURE)
            captureStartedSec = t
        }
        Log.i(TAG_CHALLENGE, "Challenge passed: ${c.type} (blinks=${c.blinks}, yaw=%.0f°)".format(c.lastYaw))
        telemetryStreamer.send("challenge_passed", mapOf("challenge_type" to c.type))
        challengeUiState.value = null
        verifiedState.value = true
        maybeFinishCapture(state, t)
    }

    private fun onChallengeFailed(state: ScanState.Measuring, c: ChallengeVerifier) {
        synchronized(phaseLock) {
            if (phase != ScanPhase.CHALLENGE) return
            setPhase(ScanPhase.DONE)
        }
        Log.w(TAG_CHALLENGE, "Challenge failed: ${c.type} (${c.failDetail})")
        telemetryStreamer.send("challenge_failed", mapOf("challenge_type" to c.type, "message" to (c.failDetail ?: "")))
        submit(state, stableResult ?: rppgState.value, Verdict(true, false))
    }

    /** After the challenge: submit once there are enough clear face frames (usually at once). */
    private fun maybeFinishCapture(state: ScanState.Measuring, t: Double) {
        if (phase != ScanPhase.CAPTURE) return
        val needed = if (state.qr.purpose == QrPayload.PURPOSE_ENROLLMENT) FaceCapture.ENROLL_MIN else FaceCapture.PROBE_MIN
        val result = stableResult ?: rppgState.value
        when {
            faceCapture.goodFrames() >= needed -> submit(state, result, Verdict(true, true))
            t - captureStartedSec > CAPTURE_TIMEOUT_SEC -> {
                Log.w(FaceEmbedder.TAG, "Only ${faceCapture.goodFrames()} clear face frames of $needed needed: face not captured")
                submit(state, result, Verdict(true, true, "FACE_NOT_CAPTURED"))
            }
        }
    }

    /** Ends the scan once (from any thread) and sends the signed result. */
    private fun submit(state: ScanState.Measuring, result: RppgResult, verdict: Verdict) {
        if (!submitted.compareAndSet(false, true)) return
        setPhase(ScanPhase.DONE)
        runOnUiThread { submitResult(state, result, verdict) }
    }

    // ── Signing and submission ──────────────────────────────────────────

    private fun submitResult(state: ScanState.Measuring, result: RppgResult, verdict: Verdict) {
        scanState.value = ScanState.Submitting
        lifecycleScope.launch {
            try {
                val hint = verdict.abortReason?.lowercase() ?: when {
                    !verdict.livenessPassed -> "timeout"
                    verdict.challengePassed == false -> "challenge_failed"
                    else -> "stable"
                }
                val diag = diagnostics.summary(hint, result)
                val request = withContext(Dispatchers.Default) { buildSignedRequest(state.qr, result, verdict, diag) }
                val response = ApiClient.service(state.baseUrl).verifyBiometrics(request)
                val body = response.body() ?: parseErrorBody(response.errorBody()?.string())
                Log.i(TAG, "Verify response: ${response.code()} ${body?.status} ${body?.outcome ?: ""} ${body?.reasonCode ?: ""}")
                finishScan(resultFor(body, response.code(), result))
            } catch (e: Exception) {
                Log.e(TAG, "Submission failed", e)
                finishScan(ScanState.Result(ResultKind.FAILURE, "Could not send the result",
                    (e.message ?: "Network error") + "\n\nCheck the Wi-Fi and scan a new QR code."))
            }
        }
    }

    private fun parseErrorBody(text: String?): VerifyResponse? = try {
        text?.let { lenientJson.decodeFromString(VerifyResponse.serializer(), it) }
    } catch (e: Exception) {
        null
    }

    /** Result screen text (build-prompt §4.6: approved, under review or rejected, with the reason). */
    private fun resultFor(body: VerifyResponse?, code: Int, result: RppgResult): ScanState.Result = when {
        body == null -> ScanState.Result(ResultKind.FAILURE, "Something went wrong",
            "The server answered with error $code. Please scan a new QR code and try again.")
        body.outcome == "ISSUED" -> ScanState.Result(ResultKind.SUCCESS, "Life certificate issued",
            "Your pension continues. The portal on the laptop now shows your certificate.")
        body.outcome == "UNDER_REVIEW" -> ScanState.Result(ResultKind.REVIEW, "Sent for officer review",
            (body.reason ?: "An officer will check your scan.") + "\n\nYou don't need to do anything now.")
        body.outcome == "CAPTURED" -> ScanState.Result(ResultKind.SUCCESS, "Face registered",
            "The officer will now approve your registration on the portal.")
        body.status == "ACCESS_GRANTED" -> ScanState.Result(ResultKind.SUCCESS, "Practice scan passed",
            "Pulse %.0f BPM. Your phone is ready for the real scan.".format(result.bpm))
        else -> ScanState.Result(ResultKind.FAILURE, "Not accepted", body.reason ?: "Verification failed")
    }

    private fun finite(v: Double, fallback: Double) = if (v.isFinite()) v else fallback

    private fun buildSignedRequest(
        qr: QrPayload, result: RppgResult, verdict: Verdict, diag: ScanDiagnosticsPayload,
    ): VerifyRequest {
        val enrollment = qr.purpose == QrPayload.PURPOSE_ENROLLMENT
        val lifeCertificate = qr.purpose == QrPayload.PURPOSE_LIFE_CERTIFICATE
        var abortReason = verdict.abortReason
        var template: FloatArray? = null
        var probe: FloatArray? = null
        if (abortReason == null) {
            if (enrollment) template = faceCapture.buildTemplate()
            if (lifeCertificate) probe = faceCapture.buildProbe()
            val passed = verdict.livenessPassed && verdict.challengePassed == true
            if (passed && ((enrollment && template == null) || (lifeCertificate && probe == null))) {
                abortReason = "FACE_NOT_CAPTURED"
            }
        }
        val framesUsed = when {
            enrollment -> faceCapture.framesUsed(FaceCapture.ENROLL_K)
            lifeCertificate -> faceCapture.framesUsed(FaceCapture.PROBE_K)
            else -> result.samplesInWindow
        }
        Log.i(FaceEmbedder.TAG, "Face frames: ${faceCapture.goodFrames()} good of ${faceCapture.framesSeen}; sending " +
            when {
                template != null -> "reference template (${template.size} values, best $framesUsed frames)"
                probe != null -> "probe embedding (${probe.size} values, best $framesUsed frames)"
                qr.isAuth -> "no face data (practice scan)"
                else -> "no face data"
            })
        if (!cryptoManager.hasKey()) cryptoManager.generateHardwareKey()
        val timestamp = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply {
            timeZone = TimeZone.getTimeZone("UTC")
        }.format(Date())
        val payload = BiometricPayload(
            sessionId = qr.sessionId,
            purpose = qr.purpose,
            nonce = qr.nonce,
            timestamp = timestamp,
            deviceId = Settings.Secure.getString(contentResolver, Settings.Secure.ANDROID_ID) ?: "unknown",
            bpm = finite(result.bpm, 0.0),
            snr = finite(result.medianSnrDb, -99.0),
            livenessPassed = verdict.livenessPassed,
            challengeId = qr.challengeId,
            challengePassed = if (qr.challengeId != null) (verdict.challengePassed ?: false) else null,
            faceEmbedding = probe?.toList(),
            referenceTemplate = template?.toList(),
            modelVersion = if (qr.isAuth) null else FaceEmbedder.MODEL_VERSION,
            keySecurityLevel = cryptoManager.keySecurityLevel(),
            consent = true,
            framesUsed = framesUsed,
            appVersion = BuildConfig.VERSION_NAME,
            diagnostics = diag,
            abortReason = abortReason,
        )
        val payloadJson = Json.encodeToString(BiometricPayload.serializer(), payload)
        return VerifyRequest(
            payload = Base64.encodeToString(payloadJson.toByteArray(Charsets.UTF_8), Base64.NO_WRAP),
            signature = cryptoManager.signPayload(payloadJson),
            publicKey = cryptoManager.getBase64PublicKey(),
            attestationChain = cryptoManager.getAttestationChain(),
        )
    }

    // ── Face scan screen ────────────────────────────────────────────────

    @Composable
    private fun FaceScanScreen(qr: QrPayload) {
        val r by rppgState
        val currentPhase by phaseState
        val ch by challengeUiState
        val guidance by guidanceState
        val faceVisible by faceVisibleState
        val verified by verifiedState
        val showDiag by showDiagnostics
        val frames = faceFramesState.intValue
        val needed = if (qr.purpose == QrPayload.PURPOSE_ENROLLMENT) FaceCapture.ENROLL_MIN else FaceCapture.PROBE_MIN

        val (prompt, detail) = when (currentPhase) {
            ScanPhase.PULSE -> Pair(
                guidance ?: if (faceVisible) "Hold still" else "Look at the screen",
                if (r.hasEstimate) "Measuring your pulse…" else "Keep your face inside the circle",
            )
            ScanPhase.CHALLENGE -> challengePrompt(ch)
            ScanPhase.CAPTURE -> Pair("Hold still", "Look straight at the screen")
            ScanPhase.DONE -> Pair(if (verified) "Done ✓" else "Done", "Sending your result…")
        }
        val progress = when (currentPhase) {
            ScanPhase.PULSE -> (r.windowFill * 0.6).toFloat()
            ScanPhase.CHALLENGE -> 0.7f
            ScanPhase.CAPTURE -> 0.8f + 0.2f * (frames.toFloat() / needed).coerceAtMost(1f)
            ScanPhase.DONE -> 1f
        }

        Box(Modifier.fillMaxSize()) {
            FaceOverlay(showDiag)
            FaceScanHud(
                prompt = prompt,
                detail = detail,
                progress = progress,
                verified = verified,
                bpm = if (r.hasEstimate) "%.0f".format(r.bpm) else "--",
                snr = if (r.hasEstimate) "%.1f".format(r.medianSnrDb) else "--",
                waveform = r.waveform,
                diagnosticsOn = showDiag,
                onToggleDiagnostics = { showDiagnostics.value = !showDiag },
            )
            if (showDiag) DiagnosticsPanel(Modifier.align(Alignment.CenterStart), currentPhase, ch, frames)
        }
    }

    private fun challengePrompt(c: ChallengeUi?): Pair<String, String?> {
        if (c == null) return Pair("Get ready", null)
        val title = when (c.type) {
            ChallengeVerifier.BLINK_TWICE -> "Blink twice now"
            ChallengeVerifier.TURN_LEFT -> "← Turn your head to your left"
            ChallengeVerifier.TURN_RIGHT -> "Turn your head to your right →"
            else -> c.type
        }
        val detail = c.hint ?: when (c.type) {
            ChallengeVerifier.BLINK_TWICE -> "${c.blinks} of ${ChallengeVerifier.BLINKS_NEEDED} · ${c.secondsLeft} s left"
            else -> "Then look back at the screen · ${c.secondsLeft} s left"
        }
        return Pair(title, detail)
    }

    @Composable
    private fun DiagnosticsPanel(modifier: Modifier, currentPhase: ScanPhase, ch: ChallengeUi?, frames: Int) {
        val snap by diagSnapshotState
        val sn = snap ?: return
        Column(
            modifier = modifier.padding(12.dp)
                .background(Color.Black.copy(alpha = 0.7f), RoundedCornerShape(8.dp)).padding(10.dp),
        ) {
            DiagLine("time", "%.1f s".format(sn.elapsedSec))
            DiagLine("camera", "%.1f fps %s".format(sn.fps, sn.fpsRange))
            DiagLine("pulse", "%.1f BPM (spread %.1f)".format(sn.bpm, sn.spreadBpm))
            DiagLine("SNR", "%.1f dB (min %.1f)".format(sn.snrDb, sn.minSnrDb))
            DiagLine("light", "%.0f / 255".format(sn.luma))
            DiagLine("AE lock", if (sn.aeLocked) "yes" else "no")
            DiagLine("waiting for", sn.gate.label)
            DiagLine("step", currentPhase.name.lowercase())
            if (ch != null) DiagLine("challenge", "${ch.type} yaw %.0f° blinks ${ch.blinks}".format(ch.yaw))
            DiagLine("face frames", "$frames good")
        }
    }

    @Composable
    private fun DiagLine(label: String, value: String) {
        Row {
            Text("$label: ", color = Color.White.copy(alpha = 0.75f), fontSize = 13.sp)
            Text(value, color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.Bold)
        }
    }

    /**
     * The whole-face box (build-prompt §4.2) over the mirrored, FILL_CENTER
     * front-camera preview, plus the forehead/cheek ROIs when diagnostics are on.
     */
    @Composable
    private fun FaceOverlay(showRois: Boolean) {
        val rois by roiOverlayState
        val img by overlayImageSize
        val box by faceBoxState
        Canvas(modifier = Modifier.fillMaxSize()) {
            if (img.width == 0 || img.height == 0) return@Canvas
            val scale = maxOf(size.width / img.width, size.height / img.height)
            val dx = (size.width - img.width * scale) / 2f
            val dy = (size.height - img.height * scale) / 2f
            box?.let { f ->
                drawRect(
                    color = Color.White.copy(alpha = 0.8f),
                    topLeft = Offset(size.width - (dx + f.right * scale), dy + f.top * scale),
                    size = ComposeSize(f.width() * scale, f.height() * scale),
                    style = Stroke(width = 4f),
                )
            }
            if (!showRois) return@Canvas
            rois.forEach { r ->
                val left = size.width - (dx + r.right * scale)  // mirror X for the front camera
                val top = dy + r.top * scale
                drawRect(
                    color = ROI_GREEN,
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
