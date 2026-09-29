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
import com.example.sentinelhard.camera.QrCodeAnalyzer
import com.example.sentinelhard.models.BiometricPayload
import com.example.sentinelhard.models.VerifyRequest
import com.example.sentinelhard.network.ApiClient
import com.example.sentinelhard.network.QrPayload
import com.example.sentinelhard.rppg.FaceRois
import com.example.sentinelhard.rppg.RppgConfig
import com.example.sentinelhard.rppg.RppgNative
import com.example.sentinelhard.rppg.RppgResult
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.face.FaceDetection
import com.google.mlkit.vision.face.FaceDetectorOptions
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

    // ── Measurement state (camera thread + ML Kit callbacks) ────────────
    @Volatile private var currentRois: IntArray? = null
    @Volatile private var lastFaceSeenSec = 0.0
    @Volatile private var firstFaceSec: Double? = null
    @Volatile private var isDetectingFace = false
    private val submitted = AtomicBoolean(false)
    private var frameCounter = 0

    private val cryptoManager = CryptoManager()
    private val cameraExecutor = Executors.newSingleThreadExecutor()
    private val telemetryStreamer = TelemetryStreamer()

    private val detector = FaceDetection.getClient(
        FaceDetectorOptions.Builder()
            .setPerformanceMode(FaceDetectorOptions.PERFORMANCE_MODE_FAST)
            .setLandmarkMode(FaceDetectorOptions.LANDMARK_MODE_NONE)
            .setContourMode(FaceDetectorOptions.CONTOUR_MODE_NONE)
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
        RppgNative.nativeConfigure(
            qr.minSnrDb ?: RppgConfig.DEFAULT_MIN_SNR_DB,
            RppgConfig.WINDOW_SEC,
            RppgConfig.STABLE_COUNT,
            RppgConfig.STABLE_TOLERANCE_BPM,
        )
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
        val preview = Preview.Builder().build().also { it.setSurfaceProvider(previewView.surfaceProvider) }
        val analysis = ImageAnalysis.Builder()
            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
            .setResolutionSelector(resolution(640, 480))
            .build()
        analysis.setAnalyzer(cameraExecutor) { image -> analyzeFrame(image) }
        try {
            provider.unbindAll()
            provider.bindToLifecycle(owner, CameraSelector.DEFAULT_FRONT_CAMERA, preview, analysis)
        } catch (e: Exception) {
            Log.e(TAG, "Face camera binding failed", e)
        }
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
                onRppgResult(RppgResult.fromArray(raw), t, state)
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
                // Milestone 3 adds the whole-face box and rejects frames with more than one face.
                val face = faces.maxByOrNull { it.boundingBox.width() * it.boundingBox.height() }
                if (face != null) {
                    currentRois = FaceRois.sensorRois(face.boundingBox, width, height, rotation)
                    lastFaceSeenSec = t
                    if (firstFaceSec == null) firstFaceSec = t
                    faceVisibleState.value = true
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
        if (started != null && t - started > RppgConfig.SCAN_TIMEOUT_SEC && submitted.compareAndSet(false, true)) {
            Log.w(TAG_DSP, "No stable pulse within ${RppgConfig.SCAN_TIMEOUT_SEC}s (last SNR %.1f dB) → reporting no pulse"
                .format(result.medianSnrDb))
            runOnUiThread { submitResult(state, result, livenessPassed = false) }
        }
    }

    // ── Signing and submission ──────────────────────────────────────────

    private fun submitResult(state: ScanState.Measuring, result: RppgResult, livenessPassed: Boolean) {
        scanState.value = ScanState.Submitting
        lifecycleScope.launch {
            try {
                val request = withContext(Dispatchers.Default) { buildSignedRequest(state.qr, result, livenessPassed) }
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

    private fun buildSignedRequest(qr: QrPayload, result: RppgResult, livenessPassed: Boolean): VerifyRequest {
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
        val prompt = when {
            !faceVisible && !r.hasEstimate -> "Position your face in the frame"
            r.stable -> "Pulse steady ✓"
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
        Canvas(modifier = Modifier.fillMaxSize()) {
            if (rois.isEmpty() || img.width == 0 || img.height == 0) return@Canvas
            val scale = maxOf(size.width / img.width, size.height / img.height)
            val dx = (size.width - img.width * scale) / 2f
            val dy = (size.height - img.height * scale) / 2f
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
        detector.close()
    }
}
