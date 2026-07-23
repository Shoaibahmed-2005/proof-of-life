package com.example.sentinelhard

import android.annotation.SuppressLint
import androidx.appcompat.app.AppCompatActivity
import android.os.Bundle
import android.util.Log
import androidx.camera.core.ImageProxy
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.face.FaceDetection
import com.google.mlkit.vision.face.FaceDetectorOptions
import org.opencv.android.OpenCVLoader
import java.nio.ByteBuffer

class MainActivity : AppCompatActivity() {

    // 1. Configure ML Kit for fast contour and landmark detection
    private val detector = FaceDetection.getClient(
        FaceDetectorOptions.Builder()
            .setPerformanceMode(FaceDetectorOptions.PERFORMANCE_MODE_FAST)
            .setLandmarkMode(FaceDetectorOptions.LANDMARK_MODE_ALL)
            .setContourMode(FaceDetectorOptions.CONTOUR_MODE_ALL)
            .build()
    )

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Your UI setup code will be here (e.g., setContentView)

        // Initialize OpenCV early in the lifecycle
        if (OpenCVLoader.initLocal()) {
            Log.i("SentinelHard", "OpenCV loaded successfully!")
        } else {
            Log.e("SentinelHard", "OpenCV initialization failed.")
        }
    }

    @SuppressLint("UnsafeOptInUsageError")
    fun analyzeFrame(imageProxy: ImageProxy) {
        val mediaImage = imageProxy.image ?: return
        val rotationDegrees = imageProxy.imageInfo.rotationDegrees
        val image = InputImage.fromMediaImage(mediaImage, rotationDegrees)

        detector.process(image)
            .addOnSuccessListener { faces ->
                if (faces.isNotEmpty()) {
                    val face = faces.first()
                    val bounds = face.boundingBox

                    // 2. Mathematically isolate the forehead from the master bounding box
                    // Take the top 20% of the face, slightly inset to avoid background/hair
                    val foreheadX = bounds.left + (bounds.width() * 0.2).toInt()
                    val foreheadY = bounds.top + (bounds.height() * 0.1).toInt()
                    val foreheadW = (bounds.width() * 0.6).toInt()
                    val foreheadH = (bounds.height() * 0.2).toInt()

                    // 3. Map ROI coordinates back to raw sensor space if rotated
                    // C++ receives raw YUV bytes which are unrotated (landscape)
                    val (mappedX, mappedY, mappedW, mappedH) = mapRoiToSensor(
                        foreheadX, foreheadY, foreheadW, foreheadH,
                        imageProxy.width, imageProxy.height, rotationDegrees
                    )

                    // 4. Convert ImageProxy to raw ByteArray (NV21)
                    val yuvData = yuvToByteArray(imageProxy)

                    // 5. Fire data across JNI bridge
                    val greenChannelMean = processFrame(
                        yuvData, imageProxy.width, imageProxy.height,
                        mappedX, mappedY, mappedW, mappedH
                    )
                    
                    Log.d("SentinelHard", "Green Channel Mean: $greenChannelMean")
                }
            }
            .addOnCompleteListener {
                imageProxy.close() // CRITICAL: Release frame
            }
    }

    private fun mapRoiToSensor(
        x: Int, y: Int, w: Int, h: Int,
        imgW: Int, imgH: Int, rotation: Int
    ): IntArray {
        // ML Kit returns coordinates in the 'upright' frame.
        // If rotation is 90/270, imgW and imgH are swapped relative to sensor.
        return when (rotation) {
            90 -> intArrayOf(y, imgW - x - w, h, w)
            180 -> intArrayOf(imgW - x - w, imgH - y - h, w, h)
            270 -> intArrayOf(imgH - y - h, x, h, w)
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

    // ==========================================
    // KOTLIN JNI CONTRACT
    // ==========================================

    companion object {
        init {
            System.loadLibrary("sentinelhard")
        }
    }

    // Updated JNI signature to receive ROI
    external fun processFrame(
        yuvData: ByteArray, width: Int, height: Int,
        roiX: Int, roiY: Int, roiW: Int, roiH: Int
    ): Double
}
