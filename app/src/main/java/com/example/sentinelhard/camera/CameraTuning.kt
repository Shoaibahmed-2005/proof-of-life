package com.example.sentinelhard.camera

import android.content.Context
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.hardware.camera2.CaptureRequest
import android.util.Log
import android.util.Range
import androidx.annotation.OptIn
import androidx.camera.camera2.interop.Camera2CameraControl
import androidx.camera.camera2.interop.Camera2Interop
import androidx.camera.camera2.interop.CaptureRequestOptions
import androidx.camera.camera2.interop.ExperimentalCamera2Interop
import androidx.camera.core.Camera
import androidx.camera.core.ExtendableBuilder
import androidx.core.content.ContextCompat

/**
 * Camera settings that matter for rPPG:
 *  - a steady frame rate (ideally a fixed 30–30 fps range; variable ranges drop
 *    to ~15 fps indoors), and
 *  - exposure and white balance locked once the face is lit correctly, because
 *    auto-exposure changes the skin colour and adds noise to the pulse signal.
 */
object CameraTuning {
    private const val TAG = "SentinelDiag"

    /** Front camera's supported AE fps ranges, e.g. "[15, 30] [30, 30]". */
    fun frontFpsRanges(context: Context): List<Range<Int>> = try {
        val manager = context.getSystemService(Context.CAMERA_SERVICE) as CameraManager
        val id = manager.cameraIdList.firstOrNull { cid ->
            manager.getCameraCharacteristics(cid).get(CameraCharacteristics.LENS_FACING) ==
                CameraCharacteristics.LENS_FACING_FRONT
        }
        id?.let { manager.getCameraCharacteristics(it).get(CameraCharacteristics.CONTROL_AE_AVAILABLE_TARGET_FPS_RANGES) }
            ?.toList().orEmpty()
    } catch (e: Exception) {
        Log.w(TAG, "Could not read camera fps ranges: ${e.message}")
        emptyList()
    }

    /**
     * Best range for rPPG: exactly [target, target] if offered; otherwise the
     * range with the highest minimum among those reaching the target.
     */
    fun chooseFpsRange(ranges: List<Range<Int>>, target: Int): Range<Int>? {
        ranges.firstOrNull { it.lower == target && it.upper == target }?.let { return it }
        return ranges.filter { it.upper >= target }.maxWithOrNull(compareBy({ it.lower }, { -it.upper }))
            ?: ranges.maxByOrNull { it.upper }
    }

    /** Applies the fps range to a Preview/ImageAnalysis builder before it is built. */
    @OptIn(ExperimentalCamera2Interop::class)
    fun <T> applyFpsRange(builder: ExtendableBuilder<T>, range: Range<Int>) {
        Camera2Interop.Extender(builder).setCaptureRequestOption(CaptureRequest.CONTROL_AE_TARGET_FPS_RANGE, range)
    }

    /** Locks auto-exposure and auto white balance. Calls onDone(success) on the main thread. */
    @OptIn(ExperimentalCamera2Interop::class)
    fun lockExposure(context: Context, camera: Camera, onDone: (Boolean) -> Unit) {
        val options = CaptureRequestOptions.Builder()
            .setCaptureRequestOption(CaptureRequest.CONTROL_AE_LOCK, true)
            .setCaptureRequestOption(CaptureRequest.CONTROL_AWB_LOCK, true)
            .build()
        val future = Camera2CameraControl.from(camera.cameraControl).setCaptureRequestOptions(options)
        future.addListener({
            val ok = try {
                future.get(); true
            } catch (e: Exception) {
                Log.w(TAG, "Exposure lock failed: ${e.message}"); false
            }
            onDone(ok)
        }, ContextCompat.getMainExecutor(context))
    }
}
