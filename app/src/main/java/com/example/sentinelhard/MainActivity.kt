package com.example.sentinelhard

import androidx.appcompat.app.AppCompatActivity
import android.os.Bundle
import android.util.Log
import org.opencv.android.OpenCVLoader
// ... any other generated imports ...

class MainActivity : AppCompatActivity() {

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

    // ==========================================
    // KOTLIN JNI CONTRACT
    // ==========================================

    companion object {
        init {
            // Loads the C++ library compiled via CMake
            System.loadLibrary("sentinelhard")
        }
    }

    // The external function declaration (Biometric processing entry point)
    external fun processFrame(yuvData: ByteArray, width: Int, height: Int): Double
}