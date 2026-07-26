package com.example.sentinelhard

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.PointF
import android.graphics.RectF
import androidx.appcompat.app.AppCompatActivity
import android.os.Bundle
import android.util.Log
import android.util.Size as AndroidSize
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.annotation.OptIn
import androidx.camera.core.*
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size as ComposeSize
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.face.FaceDetection
import com.google.mlkit.vision.face.FaceDetectorOptions
import com.google.mlkit.vision.face.FaceLandmark
import org.opencv.android.OpenCVLoader
import com.example.sentinelhard.camera.QrCodeAnalyzer
import com.example.sentinelhard.models.BiometricPayload
import com.example.sentinelhard.models.VerifyRequest
import com.example.sentinelhard.network.ApiClient
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.*
import java.util.concurrent.Executors

sealed class AuthState {
    object SelectionMenu : AuthState()
    object ScanQr : AuthState()
    data class MeasureBiometrics(val sessionId: String) : AuthState()
    object LivenessVerified : AuthState()
    object Submitting : AuthState()
    data class Success(val message: String) : AuthState()
    data class Error(val message: String) : AuthState()
}

class MainActivity : AppCompatActivity() {

    private val signalState = mutableStateOf(DoubleArray(0))
    private val bpmState = mutableStateOf(0.0)
    private val snrState = mutableStateOf(0.0)
    
    // 3-Tier Liveness State: 0 = Spoof, 1 = Analyzing, 2 = Human
    private val livenessStatusState = mutableIntStateOf(1)
    
    private val bufferSizeState = mutableStateOf(0.0)
    private val isFaceDetectedState = mutableStateOf(false)
    private val isAnalysisReadyState = mutableStateOf(false)

    // ROI debug overlay state
    private val foreheadRoiState = mutableStateOf<RectF?>(null)
    private val roiImageWidth = mutableIntStateOf(0)
    private val roiImageHeight = mutableIntStateOf(0)

    // QR scanning phase state
    private val authState = mutableStateOf<AuthState>(AuthState.SelectionMenu)
    private val cryptoManager = CryptoManager()

    private val livenessHistory = mutableListOf<Int>()
    private val LIVENESS_SMOOTHING_WINDOW = 15

    // Dwell-Time Filter State
    private var displayedStatus = 1
    private var pendingStatusFrames = 0
    private val MIN_DWELL_FRAMES = 20 // ~0.6s at 30fps

    private val nosePositions = ArrayDeque<PointF>(15)
    private val isMicroMotionLive = mutableStateOf(true)

    // Coasting State
    private var lastGoodYuv: ByteArray? = null
    private var lastGoodRoi: IntArray? = null
    private var lastGoodWidth = 0
    private var lastGoodHeight = 0
    private var coastingFrames: Int = 0
    private val MAX_COASTING_FRAMES = 30 // ~1 second grace period at 30 FPS
    // Replaces the fragile MAX_COASTING_FRAMES+1 sentinel integer with an explicit boolean
    private var hasFaceLost = false

    private val cameraExecutor = Executors.newSingleThreadExecutor()
    private val telemetryStreamer = TelemetryStreamer()
    private var telemetryFrameCounter = 0

    // Thermal optimization: throttle to 20 FPS
    private var lastProcessedTimeMs = 0L
    private val frameIntervalMs = 50L  // 1000 / 20 FPS

    // Decoupled face detection: run ML Kit every 3rd frame, JNI every frame
    private var mlKitFrameCounter = 0
    @Volatile private var isDetectingFace = false
    private val ML_KIT_INTERVAL = 3

    private val detector = FaceDetection.getClient(
        FaceDetectorOptions.Builder()
            .setPerformanceMode(FaceDetectorOptions.PERFORMANCE_MODE_FAST)
            .setLandmarkMode(FaceDetectorOptions.LANDMARK_MODE_ALL)
            // CONTOUR_MODE_NONE: only NOSE_BASE landmark is needed; contours add latency with no benefit here
            .setContourMode(FaceDetectorOptions.CONTOUR_MODE_NONE)
            .build()
    )

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        if (isGranted) {
            // Permission granted
        } else {
            Log.e("SentinelHard", "Camera permission denied")
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        if (OpenCVLoader.initLocal()) {
            Log.i("SentinelHard", "OpenCV loaded successfully!")
        }

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            requestPermissionLauncher.launch(Manifest.permission.CAMERA)
        }

        cryptoManager.generateHardwareKey()

        setContent {
            MaterialTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = Color(0xFF0A0A0A)
                ) {
                    val currentAuthState by authState
                    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        
                        if (currentAuthState != AuthState.SelectionMenu) {
                            CameraPreview(modifier = Modifier.fillMaxSize())
                        }
                        
                        when (val state = currentAuthState) {
                            is AuthState.SelectionMenu -> {
                                SelectionMenuUI(
                                    onPhoneLogin = {
                                        val localSessionId = "phone_session_${System.currentTimeMillis()}"
                                        authState.value = AuthState.MeasureBiometrics(localSessionId)
                                    },
                                    onDesktopLogin = {
                                        authState.value = AuthState.ScanQr
                                    }
                                )
                            }
                            is AuthState.ScanQr -> {
                                Text(
                                    text = "Scanning QR Code...",
                                    color = Color.White,
                                    fontSize = 18.sp,
                                    fontWeight = FontWeight.Bold,
                                    modifier = Modifier.align(Alignment.TopCenter).padding(top = 32.dp)
                                )
                            }
                            is AuthState.MeasureBiometrics -> {
                                ForeheadRoiOverlay()
                                HUDOverlay()
                            }
                            is AuthState.LivenessVerified -> {
                                StatusOverlayUI(
                                    message = "Liveness Verified",
                                    color = Color(0xFF00FF66),
                                    icon = "✓"
                                )
                            }
                            is AuthState.Submitting -> {
                                StatusOverlayUI(
                                    message = "Submitting Biometrics...",
                                    color = Color.Yellow,
                                    showProgress = true
                                )
                            }
                            is AuthState.Success -> {
                                StatusOverlayUI(
                                    message = state.message,
                                    color = Color(0xFF00FF66),
                                    icon = "✓",
                                    showCloseButton = true
                                )
                            }
                            is AuthState.Error -> {
                                StatusOverlayUI(
                                    message = state.message,
                                    color = Color.Red,
                                    icon = "!",
                                    showCloseButton = true
                                )
                            }
                        }
                    }
                }
            }
        }
    }

    @Composable
    fun StatusOverlayUI(
        message: String,
        color: Color,
        icon: String? = null,
        showProgress: Boolean = false,
        showCloseButton: Boolean = false
    ) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(Color.Black.copy(alpha = 0.8f)),
            contentAlignment = Alignment.Center
        ) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                if (showProgress) {
                    CircularProgressIndicator(color = color, modifier = Modifier.size(64.dp))
                } else if (icon != null) {
                    Text(text = icon, color = color, fontSize = 64.sp, fontWeight = FontWeight.Bold)
                }
                
                Spacer(modifier = Modifier.height(16.dp))
                
                Text(
                    text = message,
                    color = color,
                    fontSize = 20.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(horizontal = 32.dp)
                )

                if (showCloseButton) {
                    Spacer(modifier = Modifier.height(32.dp))
                    Button(onClick = { authState.value = AuthState.SelectionMenu }) {
                        Text("Return to Menu")
                    }
                }
            }
        }
    }

    @Composable
    fun CameraPreview(modifier: Modifier = Modifier) {
        val context = LocalContext.current
        val lifecycleOwner = LocalLifecycleOwner.current
        val cameraProviderFuture = remember { ProcessCameraProvider.getInstance(context) }

        AndroidView(
            factory = { ctx ->
                val previewView = PreviewView(ctx)
                cameraProviderFuture.addListener({
                    val cameraProvider = cameraProviderFuture.get()
                    val state = authState.value
                    if (state is AuthState.ScanQr) {
                        bindQrScanner(cameraProvider, previewView, lifecycleOwner)
                    } else if (state is AuthState.MeasureBiometrics) {
                        bindRppgPipeline(cameraProvider, previewView, lifecycleOwner)
                    }
                }, ContextCompat.getMainExecutor(context))
                previewView
            },
            modifier = modifier
        )
    }

    private fun bindQrScanner(
        cameraProvider: ProcessCameraProvider,
        previewView: PreviewView,
        lifecycleOwner: androidx.lifecycle.LifecycleOwner
    ) {
        val preview = Preview.Builder().build().also {
            it.setSurfaceProvider(previewView.surfaceProvider)
        }

        // 720p is plenty for QR code recognition
        val qrResolution = ResolutionSelector.Builder()
            .setResolutionStrategy(
                ResolutionStrategy(
                    AndroidSize(1280, 720),
                    ResolutionStrategy.FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER
                )
            )
            .build()

        val qrAnalysis = ImageAnalysis.Builder()
            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
            .setResolutionSelector(qrResolution)
            .build()

        qrAnalysis.setAnalyzer(cameraExecutor, QrCodeAnalyzer { rawQrString ->
            Log.i("SentinelHard", "QR Scanned: $rawQrString")
            val sessionId = parseSessionId(rawQrString)
            
            runOnUiThread {
                authState.value = AuthState.MeasureBiometrics(sessionId)
            }

            // Transition: unbind QR, bind rPPG pipeline
            cameraProvider.unbindAll()
            bindRppgPipeline(cameraProvider, previewView, lifecycleOwner)
        })

        val cameraSelector = CameraSelector.DEFAULT_BACK_CAMERA
        try {
            cameraProvider.unbindAll()
            cameraProvider.bindToLifecycle(lifecycleOwner, cameraSelector, preview, qrAnalysis)
        } catch (exc: Exception) {
            Log.e("SentinelHard", "QR scanner binding failed", exc)
        }
    }

    private fun bindRppgPipeline(
        cameraProvider: ProcessCameraProvider,
        previewView: PreviewView,
        lifecycleOwner: androidx.lifecycle.LifecycleOwner
    ) {
        val preview = Preview.Builder().build().also {
            it.setSurfaceProvider(previewView.surfaceProvider)
        }

        val resolutionSelector = ResolutionSelector.Builder()
            .setResolutionStrategy(
                ResolutionStrategy(
                    AndroidSize(640, 480),
                    ResolutionStrategy.FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER
                )
            )
            .build()

        val imageAnalysis = ImageAnalysis.Builder()
            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
            .setResolutionSelector(resolutionSelector)
            .build()

        imageAnalysis.setAnalyzer(cameraExecutor) { imageProxy ->
            analyzeFrame(imageProxy)
        }

        val cameraSelector = CameraSelector.DEFAULT_FRONT_CAMERA
        try {
            cameraProvider.unbindAll()
            val camera = cameraProvider.bindToLifecycle(
                lifecycleOwner, cameraSelector, preview, imageAnalysis
            )

            camera.cameraControl.let { control ->
                val exposureState = camera.cameraInfo.exposureState
                if (exposureState.isExposureCompensationSupported) {
                    control.setExposureCompensationIndex(0)
                }
            }
        } catch (exc: Exception) {
            Log.e("SentinelHard", "rPPG pipeline binding failed", exc)
        }
    }

    @Composable
    fun SelectionMenuUI(onPhoneLogin: () -> Unit, onDesktopLogin: () -> Unit) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
            modifier = Modifier.fillMaxSize()
        ) {
            Button(
                onClick = onPhoneLogin,
                modifier = Modifier
                    .width(250.dp)
                    .padding(bottom = 16.dp)
            ) {
                Text("Login Directly on Phone")
            }

            Button(
                onClick = onDesktopLogin,
                modifier = Modifier.width(250.dp)
            ) {
                Text("Scan Desktop QR Code")
            }
        }
    }

    private fun parseSessionId(rawString: String): String {
        return try {
            val json = JSONObject(rawString)
            json.optString("session_id", rawString)
        } catch (e: Exception) {
            rawString
        }
    }

    @Composable
    fun HUDOverlay() {
        val signalData by signalState
        val bpm by bpmState
        val snr by snrState
        val livenessStatus by livenessStatusState
        val trueBufferSize by bufferSizeState
        val isFaceDetected by isFaceDetectedState
        val isAnalysisReady by isAnalysisReadyState

        Box(modifier = Modifier.fillMaxSize()) {
            // --- Title ---
            Text(
                text = "SENTINEL HARD",
                color = Color.White.copy(alpha = 0.9f),
                fontSize = 20.sp,
                fontWeight = FontWeight.Black,
                modifier = Modifier
                    .align(Alignment.TopCenter)
                    .padding(top = 16.dp)
            )

            if (!isFaceDetected) {
                Text(
                    text = "POSITION FACE IN FRAME",
                    color = Color.White,
                    fontSize = 18.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.align(Alignment.Center)
                )
            } else if (!isAnalysisReady) {
                val progress = ((trueBufferSize / 150.0) * 100).toInt()
                Column(
                    modifier = Modifier.align(Alignment.Center),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    CircularProgressIndicator(
                        progress = (trueBufferSize / 150.0).toFloat(),
                        color = Color(0xFF00FF66),
                        strokeWidth = 8.dp,
                        modifier = Modifier.size(80.dp)
                    )
                    Spacer(modifier = Modifier.height(16.dp))
                    Text(
                        text = "ANALYZING BIOMETRICS... $progress%",
                        color = Color.Yellow,
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold
                    )
                }
            } else {
                // --- Metrics Pushed Below Title ---
                Column(
                    modifier = Modifier
                        .align(Alignment.TopStart)
                        .padding(start = 24.dp, top = 80.dp) 
                ) {
                    MetricItem(label = "HEART RATE", value = "%.1f".format(bpm), unit = "BPM", color = Color(0xFF00FF66))
                    Spacer(modifier = Modifier.height(16.dp))
                    MetricItem(label = "SIGNAL SNR", value = "%.1f".format(snr), unit = "dB", color = Color(0xFF00CCFF))
                }

                val statusText = when (livenessStatus) {
                    2 -> "VERIFIED HUMAN"
                    0 -> "SPOOF DETECTED"
                    else -> "ANALYZING SIGNAL..."
                }
                
                val statusColor = when (livenessStatus) {
                    2 -> Color(0xFF00FF66)
                    0 -> Color.Red
                    else -> Color.Yellow
                }

                Box(
                    modifier = Modifier
                        .align(Alignment.TopEnd)
                        .padding(end = 24.dp, top = 80.dp)
                        .clip(RoundedCornerShape(8.dp))
                        .background(statusColor.copy(alpha = 0.2f))
                        .border(1.dp, statusColor, RoundedCornerShape(8.dp))
                        .padding(horizontal = 12.dp, vertical = 6.dp)
                ) {
                    Text(
                        text = statusText,
                        color = statusColor,
                        style = MaterialTheme.typography.labelLarge,
                        fontWeight = FontWeight.Bold
                    )
                }
            }

            Box(
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .padding(bottom = 48.dp)
            ) {
                PulseWaveformView(signalData = signalData)
            }
        }
    }

    @Composable
    fun ForeheadRoiOverlay() {
        val roiRect by foreheadRoiState
        val imgWidth by roiImageWidth
        val imgHeight by roiImageHeight

        Canvas(modifier = Modifier.fillMaxSize()) {
            val rect = roiRect ?: return@Canvas
            if (imgWidth == 0 || imgHeight == 0) return@Canvas

            val scaleX = size.width / imgWidth.toFloat()
            val scaleY = size.height / imgHeight.toFloat()

            // Mirror X-axis for front-facing camera
            val left = size.width - rect.right * scaleX
            val right = size.width - rect.left * scaleX
            val top = rect.top * scaleY
            val bottom = rect.bottom * scaleY

            drawRect(
                color = Color(0xFF00FF66),
                topLeft = Offset(left, top),
                size = ComposeSize(right - left, bottom - top),
                style = Stroke(width = 4f)
            )
        }
    }

    @Composable
    fun MetricItem(label: String, value: String, unit: String, color: Color) {
        Column {
            Text(text = label, color = color.copy(alpha = 0.7f), fontSize = 12.sp, fontWeight = FontWeight.Bold)
            Row(verticalAlignment = Alignment.Bottom) {
                Text(text = value, color = color, fontSize = 42.sp, fontWeight = FontWeight.Black)
                Text(text = " $unit", color = color.copy(alpha = 0.7f), fontSize = 14.sp, modifier = Modifier.padding(bottom = 8.dp))
            }
        }
    }

    @Composable
    fun PulseWaveformView(signalData: DoubleArray) {
        Canvas(
            modifier = Modifier
                .fillMaxWidth()
                .height(180.dp)
                .padding(horizontal = 16.dp)
        ) {
            if (signalData.size < 2) return@Canvas

            val width = size.width
            val height = size.height
            val centerY = height / 2f

            val path = Path()
            val xStep = width / (signalData.size - 1).toFloat()

            val maxVal = signalData.maxOrNull() ?: 1.0
            val minVal = signalData.minOrNull() ?: -1.0
            val range = (maxVal - minVal).coerceAtLeast(0.001)

            signalData.forEachIndexed { index, value ->
                val x = index * xStep
                val normalized = (value - minVal) / range - 0.5
                val y = centerY - (normalized * height * 0.8f).toFloat()

                if (index == 0) {
                    path.moveTo(x, y)
                } else {
                    path.lineTo(x, y)
                }
            }

            drawPath(
                path = path,
                color = Color(0xFF00FF66),
                style = Stroke(width = 4f)
            )
        }
    }

    /**
     * Processes heart metrics from the C++ pipeline and updates all UI/telemetry state.
     * Extracted to avoid duplication between ML Kit and cached-ROI frame paths.
     */
    private fun processMetrics() {
        val metrics = extractHeartMetrics()
        if (metrics.size == 4) {
            bpmState.value = metrics[0]
            snrState.value = metrics[1]

            // Liveness Hysteresis with Tiered Status (0, 1, 2)
            val rawStatus = metrics[2].toInt()

            // Apply Micro-Motion Override
            val finalRawStatus = if (isMicroMotionLive.value) rawStatus else if (rawStatus == 2) 1 else rawStatus

            livenessHistory.add(finalRawStatus)
            if (livenessHistory.size > LIVENESS_SMOOTHING_WINDOW) livenessHistory.removeAt(0)

            // Bug 2 Fix: Gate voting behind warmup window
            val votedStatus = if (livenessHistory.size < LIVENESS_SMOOTHING_WINDOW) {
                1 // Force ANALYZING during warmup
            } else {
                livenessHistory.groupBy { it }.maxByOrNull { it.value.size }?.key ?: 1
            }

            // UX Dwell-Time Filter
            if (votedStatus != displayedStatus) {
                pendingStatusFrames++
                if (pendingStatusFrames >= MIN_DWELL_FRAMES) {
                    displayedStatus = votedStatus
                    pendingStatusFrames = 0
                }
            } else {
                pendingStatusFrames = 0
            }
            livenessStatusState.intValue = displayedStatus

            bufferSizeState.value = metrics[3]
            // One-way latch: lock UI into Metrics view once buffer is primed
            if (!isAnalysisReadyState.value && metrics[3] >= 150.0) {
                isAnalysisReadyState.value = true
            }

            Log.i("SentinelTelemetry",
                "Buffer: ${metrics[3].toInt()}/150 | " +
                "Status: $displayedStatus | " +
                "SNR: ${String.format("%.2f", metrics[1])} dB"
            )

            // Stream telemetry to server (~1 message/sec at 20 FPS)
            telemetryFrameCounter++
            if (telemetryFrameCounter >= 20) {
                telemetryStreamer.sendTelemetry(
                    bpm = metrics[0],
                    snr = metrics[1],
                    livenessStatus = displayedStatus
                )
                telemetryFrameCounter = 0
            }

            // --- Automatic Submission Trigger ---
            val state = authState.value
            if (state is AuthState.MeasureBiometrics && !hasFaceLost) {
                if (displayedStatus == 2 && metrics[3] >= 150.0) {
                    val sessionId = state.sessionId
                    authState.value = AuthState.LivenessVerified
                    
                    lifecycleScope.launch {
                        delay(1200) // Visual handshake delay
                        submitAuthentication(sessionId)
                    }
                }
            }
        }
    }

    private fun submitAuthentication(sessionId: String) {
        authState.value = AuthState.Submitting
        
        lifecycleScope.launch {
            try {
                // 1. Construct BiometricPayload
                val deviceId = android.provider.Settings.Secure.getString(contentResolver, android.provider.Settings.Secure.ANDROID_ID)
                val timestamp = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply {
                    timeZone = TimeZone.getTimeZone("UTC")
                }.format(Date())

                // Calculate combined variance as a proxy for micro-motion liveness
                val varianceX = calculateVariance(nosePositions.map { it.x })
                val varianceY = calculateVariance(nosePositions.map { it.y })
                val totalVariance = (varianceX + varianceY).toDouble()

                val payloadObj = BiometricPayload(
                    sessionId = sessionId,
                    bpm = bpmState.value,
                    timestamp = timestamp,
                    deviceId = deviceId,
                    snr = snrState.value,
                    variance = totalVariance
                )

                val payloadJson = Json.encodeToString(payloadObj)
                
                // 2. Sign with CryptoManager
                if (!cryptoManager.hasKey()) {
                    cryptoManager.generateHardwareKey()
                }
                
                val signature = cryptoManager.signPayload(payloadJson)
                val publicKey = cryptoManager.getBase64PublicKey()
                val attestationChain = cryptoManager.getAttestationChain()

                val verifyRequest = VerifyRequest(
                    payload = android.util.Base64.encodeToString(payloadJson.toByteArray(), android.util.Base64.NO_WRAP),
                    signature = signature,
                    publicKey = publicKey,
                    attestationChain = attestationChain
                )

                // 3. Submit via Retrofit
                val response = ApiClient.apiService.verifyBiometrics(verifyRequest)
                
                if (response.isSuccessful && response.body()?.authenticated == true) {
                    authState.value = AuthState.Success(response.body()?.message ?: "Authenticated Successfully")
                } else {
                    val errorMsg = response.body()?.message ?: "Verification Failed"
                    authState.value = AuthState.Error(errorMsg)
                }
            } catch (e: Exception) {
                Log.e("SentinelHard", "Auth Submission Error", e)
                authState.value = AuthState.Error(e.message ?: "Network Error")
            }
        }
    }

    @OptIn(ExperimentalGetImage::class)
    fun analyzeFrame(imageProxy: ImageProxy) {
        // Temporal downsampling: skip frames beyond 20 FPS to reduce CPU/thermal load
        val currentTimeMs = System.currentTimeMillis()
        if (currentTimeMs - lastProcessedTimeMs < frameIntervalMs) {
            imageProxy.close()
            return
        }
        lastProcessedTimeMs = currentTimeMs

        val mediaImage = imageProxy.image
        if (mediaImage == null) {
            imageProxy.close()
            return
        }
        val rotationDegrees = imageProxy.imageInfo.rotationDegrees
        val timestampSeconds = imageProxy.imageInfo.timestamp / 1_000_000_000.0

        // Copy YUV data while proxy is open (independent of proxy after this)
        val yuvData = yuvToByteArray(imageProxy)
        val imgWidth = imageProxy.width
        val imgHeight = imageProxy.height

        // === JNI Processing: runs EVERY frame with cached ROI ===
        // This gives the C++ POS/FFT pipeline a continuous 20 FPS signal
        // even though ML Kit face detection only runs at ~7 FPS.
        val roi = lastGoodRoi
        if (roi != null && isFaceDetectedState.value && !hasFaceLost) {
            signalState.value = processFrame(
                yuvData, lastGoodWidth, lastGoodHeight,
                roi[0], roi[1], roi[2], roi[3],
                timestampSeconds
            )
            processMetrics()
        }

        // === ML Kit Face Detection: runs every 3rd frame only ===
        // Saves ~66% of ML Kit CPU cost while keeping ROI fresh enough
        mlKitFrameCounter++
        if (mlKitFrameCounter % ML_KIT_INTERVAL == 0 && !isDetectingFace) {
            isDetectingFace = true
            val image = InputImage.fromMediaImage(mediaImage, rotationDegrees)

            detector.process(image)
                .addOnSuccessListener { faces ->
                    if (faces.isNotEmpty()) {
                        coastingFrames = 0
                        hasFaceLost = false
                        // Connect telemetry WebSocket on first face lock-on
                        if (!isFaceDetectedState.value) {
                            telemetryStreamer.connect()
                        }
                        isFaceDetectedState.value = true

                        val face = faces.first()

                        // --- Layer 3: ML Kit Micro-Motion Tracking ---
                        val noseBase = face.getLandmark(FaceLandmark.NOSE_BASE)?.position
                        if (noseBase != null) {
                            if (nosePositions.size == 15) nosePositions.removeFirst()
                            nosePositions.addLast(noseBase)

                            if (nosePositions.size == 15) {
                                val varianceX = calculateVariance(nosePositions.map { it.x })
                                val varianceY = calculateVariance(nosePositions.map { it.y })
                                isMicroMotionLive.value = (varianceX > 0.1f || varianceY > 0.1f)
                            }
                        }

                        // Update cached ROI for JNI processing on subsequent frames
                        val bounds = face.boundingBox
                        val roiWidth = (bounds.width() * 0.45).toInt()
                        val roiLeft = bounds.centerX() - (roiWidth / 2)
                        val roiHeight = (bounds.height() * 0.20).toInt()
                        val roiTop = bounds.top + (bounds.height() * 0.10).toInt()

                        // Debug overlay
                        foreheadRoiState.value = RectF(
                            roiLeft.toFloat(), roiTop.toFloat(),
                            (roiLeft + roiWidth).toFloat(), (roiTop + roiHeight).toFloat()
                        )
                        val effectiveWidth = if (rotationDegrees == 90 || rotationDegrees == 270) imgHeight else imgWidth
                        val effectiveHeight = if (rotationDegrees == 90 || rotationDegrees == 270) imgWidth else imgHeight
                        roiImageWidth.intValue = effectiveWidth
                        roiImageHeight.intValue = effectiveHeight

                        // Cache mapped ROI for use by JNI on every frame
                        val (mappedX, mappedY, mappedW, mappedH) = mapRoiToSensor(
                            roiLeft, roiTop, roiWidth, roiHeight,
                            imgWidth, imgHeight, rotationDegrees
                        )
                        lastGoodRoi = intArrayOf(mappedX, mappedY, mappedW, mappedH)
                        lastGoodWidth = imgWidth
                        lastGoodHeight = imgHeight

                    } else {
                        // Face lost — count coasting (scaled by detection interval)
                        if (!hasFaceLost) {
                            coastingFrames += ML_KIT_INTERVAL
                            if (coastingFrames >= MAX_COASTING_FRAMES) {
                                Log.w("SentinelDSP", "Grace period exceeded. Resetting.")
                                hasFaceLost = true
                                resetBuffers()
                                telemetryStreamer.disconnect()
                                telemetryFrameCounter = 0
                                livenessHistory.clear()
                                nosePositions.clear()
                                isMicroMotionLive.value = true
                                foreheadRoiState.value = null
                                isFaceDetectedState.value = false
                                isAnalysisReadyState.value = false
                                bpmState.value = 0.0
                                snrState.value = 0.0
                                livenessStatusState.intValue = 1
                                displayedStatus = 1
                                pendingStatusFrames = 0
                                bufferSizeState.value = 0.0
                                signalState.value = DoubleArray(0)
                            }
                        }
                    }
                }
                .addOnCompleteListener {
                    isDetectingFace = false
                    imageProxy.close()
                }
        } else {
            imageProxy.close()
        }
    }

    private fun mapRoiToSensor(
        x: Int, y: Int, w: Int, h: Int,
        imgW: Int, imgH: Int, rotation: Int
    ): IntArray {
        return when (rotation) {
            90 -> intArrayOf(y, imgH - x - w, h, w)
            180 -> intArrayOf(imgW - x - w, imgH - y - h, w, h)
            270 -> intArrayOf(imgW - y - h, x, h, w)
            else -> intArrayOf(x, y, w, h)
        }
    }

    private fun yuvToByteArray(image: ImageProxy): ByteArray {
        val yPlane = image.planes[0]
        val uPlane = image.planes[1]
        val vPlane = image.planes[2]
        val width  = image.width
        val height = image.height

        val nv21 = ByteArray(width * height * 3 / 2)

        // --- Y plane: copy row-by-row, respecting rowStride (handles end-of-row padding) ---
        val yRowStride = yPlane.rowStride
        val yBuffer    = yPlane.buffer
        if (yRowStride == width) {
            yBuffer.get(nv21, 0, width * height)
        } else {
            for (row in 0 until height) {
                yBuffer.position(row * yRowStride)
                yBuffer.get(nv21, row * width, width)
            }
        }

        // --- VU interleave into NV21 format (V first, then U) ---
        // Correctly handles both semi-planar (pixelStride=2) and fully-planar (pixelStride=1) sources.
        val uvPixelStride = uPlane.pixelStride
        val uvRowStride   = uPlane.rowStride
        val uBuffer       = uPlane.buffer
        val vBuffer       = vPlane.buffer
        val ySize         = width * height

        for (row in 0 until height / 2) {
            for (col in 0 until width / 2) {
                val srcPos = row * uvRowStride + col * uvPixelStride
                nv21[ySize + row * width + col * 2]     = vBuffer.get(srcPos) // V
                nv21[ySize + row * width + col * 2 + 1] = uBuffer.get(srcPos) // U
            }
        }

        return nv21
    }

    private fun calculateVariance(values: List<Float>): Float {
        if (values.isEmpty()) return 0f
        val mean = values.average().toFloat()
        return values.map { (it - mean) * (it - mean) }.average().toFloat()
    }

    override fun onDestroy() {
        super.onDestroy()
        telemetryStreamer.shutdown()
        cameraExecutor.shutdown()
        detector.close()
    }

    companion object {
        init {
            System.loadLibrary("sentinelhard")
        }
    }

    external fun processFrame(
        yuvData: ByteArray, width: Int, height: Int,
        roiX: Int, roiY: Int, roiW: Int, roiH: Int,
        timestampSeconds: Double
    ): DoubleArray

    external fun extractHeartMetrics(): DoubleArray
    
    external fun resetBuffers()
}
