package com.example.sentinelhard

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.PointF
import androidx.appcompat.app.AppCompatActivity
import android.os.Bundle
import android.util.Log
import android.util.Size
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
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.face.FaceDetection
import com.google.mlkit.vision.face.FaceDetectorOptions
import com.google.mlkit.vision.face.FaceLandmark
import org.opencv.android.OpenCVLoader
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity() {

    private val signalState = mutableStateOf(DoubleArray(0))
    private val bpmState = mutableStateOf(0.0)
    private val snrState = mutableStateOf(0.0)
    
    // 3-Tier Liveness State: 0 = Spoof, 1 = Analyzing, 2 = Human
    private val livenessStatusState = mutableIntStateOf(1)
    
    private val bufferSizeState = mutableStateOf(0.0)
    private val isFaceDetectedState = mutableStateOf(false)
    private val isAnalysisReadyState = mutableStateOf(false)

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

    private val cameraExecutor = Executors.newSingleThreadExecutor()

    private val detector = FaceDetection.getClient(
        FaceDetectorOptions.Builder()
            .setPerformanceMode(FaceDetectorOptions.PERFORMANCE_MODE_FAST)
            .setLandmarkMode(FaceDetectorOptions.LANDMARK_MODE_ALL)
            .setContourMode(FaceDetectorOptions.CONTOUR_MODE_ALL)
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

        setContent {
            MaterialTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = Color(0xFF0A0A0A)
                ) {
                    Box(modifier = Modifier.fillMaxSize()) {
                        CameraPreview(modifier = Modifier.fillMaxSize())
                        HUDOverlay()
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
                    val preview = Preview.Builder().build().also {
                        it.setSurfaceProvider(previewView.surfaceProvider)
                    }

                    val resolutionSelector = ResolutionSelector.Builder()
                        .setResolutionStrategy(
                            ResolutionStrategy(
                                Size(640, 480),
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
                        Log.e("SentinelHard", "Use case binding failed", exc)
                    }
                }, ContextCompat.getMainExecutor(context))
                previewView
            },
            modifier = modifier
        )
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
                // Bug 1 Fix: Latch to Metrics view once ready
                if (trueBufferSize >= 150.0) isAnalysisReadyState.value = true
                
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

    @OptIn(ExperimentalGetImage::class)
    fun analyzeFrame(imageProxy: ImageProxy) {
        val mediaImage = imageProxy.image ?: return
        val rotationDegrees = imageProxy.imageInfo.rotationDegrees
        val image = InputImage.fromMediaImage(mediaImage, rotationDegrees)
        val timestampSeconds = imageProxy.imageInfo.timestamp / 1_000_000_000.0

        detector.process(image)
            .addOnSuccessListener { faces ->
                if (faces.isNotEmpty()) {
                    coastingFrames = 0
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

                    val bounds = face.boundingBox
                    val roiWidth = (bounds.width() * 0.45).toInt()
                    val roiLeft = bounds.centerX() - (roiWidth / 2)
                    val roiHeight = (bounds.height() * 0.20).toInt()
                    val roiTop = bounds.top + (bounds.height() * 0.10).toInt()

                    val (mappedX, mappedY, mappedW, mappedH) = mapRoiToSensor(
                        roiLeft, roiTop, roiWidth, roiHeight,
                        imageProxy.width, imageProxy.height, rotationDegrees
                    )

                    val yuvData = yuvToByteArray(imageProxy)
                    
                    // Cache valid frame data for coasting
                    lastGoodYuv = yuvData
                    lastGoodRoi = intArrayOf(mappedX, mappedY, mappedW, mappedH)
                    lastGoodWidth = imageProxy.width
                    lastGoodHeight = imageProxy.height
                    
                    // Normal Frame Processing
                    signalState.value = processFrame(
                        yuvData, imageProxy.width, imageProxy.height,
                        mappedX, mappedY, mappedW, mappedH,
                        timestampSeconds
                    )

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

                        Log.i("SentinelTelemetry", 
                            "Buffer: ${metrics[3].toInt()}/150 | " +
                            "Coasting: false | " +
                            "Status: $displayedStatus | " +
                            "SNR: ${String.format("%.2f", metrics[1])} dB"
                        )
                    }
                } else {
                    // Face Lost: Coasting Logic
                    val yuv = lastGoodYuv
                    val roi = lastGoodRoi
                    if (coastingFrames < MAX_COASTING_FRAMES && yuv != null && roi != null) {
                        coastingFrames++
                        
                        // Inject last known good data to keep buffer continuous
                        signalState.value = processFrame(
                            yuv, lastGoodWidth, lastGoodHeight,
                            roi[0], roi[1], roi[2], roi[3],
                            timestampSeconds
                        )
                        
                        Log.d("SentinelDSP", "Coasting frame $coastingFrames / $MAX_COASTING_FRAMES | Injecting Duplicate Data")
                    } else if (coastingFrames >= MAX_COASTING_FRAMES) {
                        if (isFaceDetectedState.value) {
                            Log.w("SentinelDSP", "Grace period exceeded. Resetting.")
                            resetBuffers()
                            livenessHistory.clear()
                            nosePositions.clear()
                            isMicroMotionLive.value = true
                            isFaceDetectedState.value = false
                            isAnalysisReadyState.value = false // Reset latch
                            bpmState.value = 0.0
                            snrState.value = 0.0
                            livenessStatusState.intValue = 1
                            displayedStatus = 1
                            pendingStatusFrames = 0
                            bufferSizeState.value = 0.0
                            signalState.value = DoubleArray(0)
                            coastingFrames = MAX_COASTING_FRAMES + 1 // Sentinel: don't re-enter
                        }
                    }
                }
            }
            .addOnCompleteListener {
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
        val yBuffer = image.planes[0].buffer
        val uBuffer = image.planes[1].buffer
        val vBuffer = image.planes[2].buffer

        val ySize = yBuffer.remaining()
        val uSize = uBuffer.remaining()
        val vSize = vBuffer.remaining()

        val nv21 = ByteArray(ySize + uSize + vSize)

        yBuffer.get(nv21, 0, ySize)
        vBuffer.get(nv21, ySize, vSize)
        uBuffer.get(nv21, ySize + vSize, uSize)

        return nv21
    }

    private fun calculateVariance(values: List<Float>): Float {
        if (values.isEmpty()) return 0f
        val mean = values.average().toFloat()
        return values.map { (it - mean) * (it - mean) }.average().toFloat()
    }

    override fun onDestroy() {
        super.onDestroy()
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
