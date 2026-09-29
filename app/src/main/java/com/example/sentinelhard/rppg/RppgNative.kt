package com.example.sentinelhard.rppg

import java.nio.ByteBuffer

/**
 * JNI bridge to the C++ rPPG engine (app/src/main/cpp/native-lib.cpp → rppg_core.cpp).
 *
 * The engine keeps its state between calls: call [nativeReset] at the start of
 * every scan, then [nativeProcessFrame] once per camera frame. All calls come
 * from the camera thread except configure/reset, which the C++ side guards
 * with a mutex.
 */
object RppgNative {

    init {
        System.loadLibrary("sentinelhard")
    }

    /** Sets thresholds and clears all state. */
    external fun nativeConfigure(
        minSnrDb: Double,
        windowSec: Double,
        stableCount: Int,
        stableToleranceBpm: Double,
    )

    /** Clears all samples and estimates (new scan). */
    external fun nativeReset()

    /**
     * Adds one frame. The Y/U/V buffers must be the camera's direct plane
     * buffers and must stay valid for the duration of the call (i.e. call
     * before ImageProxy.close()). [rois] is a flat [x, y, w, h, ...] array in
     * sensor (unrotated) coordinates. Returns the layout described in [RppgResult].
     */
    external fun nativeProcessFrame(
        yBuffer: ByteBuffer,
        uBuffer: ByteBuffer,
        vBuffer: ByteBuffer,
        width: Int,
        height: Int,
        yRowStride: Int,
        yPixelStride: Int,
        uvRowStride: Int,
        uvPixelStride: Int,
        rois: IntArray,
        timestampSeconds: Double,
    ): DoubleArray
}
