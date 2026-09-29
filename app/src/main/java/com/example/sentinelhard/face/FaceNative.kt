package com.example.sentinelhard.face

import java.nio.ByteBuffer

/**
 * JNI bridge to face_core.cpp (alignment and template averaging).
 * Same native library as the rPPG engine.
 */
object FaceNative {

    init {
        System.loadLibrary("sentinelhard")
    }

    const val SIZE = 112
    const val TENSOR_LENGTH = SIZE * SIZE * 3

    /**
     * Writes the aligned 112×112 RGB face crop (values in [-1, 1], NHWC) into
     * [out] (length TENSOR_LENGTH) straight from the camera planes. Eye
     * positions are in upright image coordinates (as ML Kit reports them).
     * Returns [ok (0/1), sharpness, luma, eye distance px].
     * The buffers must still be open (call before ImageProxy.close()).
     */
    external fun nativeAlignFace(
        yBuffer: ByteBuffer,
        uBuffer: ByteBuffer,
        vBuffer: ByteBuffer,
        width: Int,
        height: Int,
        yRowStride: Int,
        yPixelStride: Int,
        uvRowStride: Int,
        uvPixelStride: Int,
        rotation: Int,
        eyeAx: Double,
        eyeAy: Double,
        eyeBx: Double,
        eyeBy: Double,
        out: FloatArray,
    ): DoubleArray

    /**
     * Average of the [k] best embeddings (by [quality]), L2-normalised; empty
     * if fewer than [minCount] were given. [embeddings] is count × dim, flat.
     */
    external fun nativeBuildTemplate(
        embeddings: FloatArray,
        count: Int,
        dim: Int,
        quality: FloatArray,
        k: Int,
        minCount: Int,
    ): FloatArray
}
