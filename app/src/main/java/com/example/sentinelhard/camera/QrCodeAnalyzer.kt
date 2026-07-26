package com.example.sentinelhard.camera

import android.annotation.SuppressLint
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage

/**
 * CameraX ImageAnalysis.Analyzer that scans for QR codes using ML Kit.
 *
 * Restricted to QR_CODE format only to minimize processing overhead.
 * Once a valid code is scanned, the scanner closes itself to save battery.
 * The caller should unbind this analyzer and transition to the rPPG pipeline.
 */
class QrCodeAnalyzer(
    private val onQrCodeScanned: (String) -> Unit
) : ImageAnalysis.Analyzer {

    private val options = BarcodeScannerOptions.Builder()
        .setBarcodeFormats(Barcode.FORMAT_QR_CODE)
        .build()

    private val scanner = BarcodeScanning.getClient(options)

    @Volatile
    private var hasScanned = false

    @SuppressLint("UnsafeOptInUsageError")
    override fun analyze(imageProxy: ImageProxy) {
        if (hasScanned) {
            imageProxy.close()
            return
        }

        val mediaImage = imageProxy.image
        if (mediaImage == null) {
            imageProxy.close()
            return
        }

        val image = InputImage.fromMediaImage(mediaImage, imageProxy.imageInfo.rotationDegrees)

        scanner.process(image)
            .addOnSuccessListener { barcodes ->
                for (barcode in barcodes) {
                    val rawValue = barcode.rawValue
                    if (rawValue != null && !hasScanned) {
                        hasScanned = true
                        onQrCodeScanned(rawValue)
                        scanner.close()
                        break
                    }
                }
            }
            .addOnFailureListener {
                // Silently continue — next frame will retry
            }
            .addOnCompleteListener {
                imageProxy.close()
            }
    }
}
