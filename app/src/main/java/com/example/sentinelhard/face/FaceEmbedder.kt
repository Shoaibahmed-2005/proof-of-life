package com.example.sentinelhard.face

import android.content.Context
import android.util.Log
import org.tensorflow.lite.Interpreter
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * MobileFaceNet (assets/mobilefacenet.tflite, see MODEL_INFO.md) on LiteRT.
 * Input: 1×112×112×3 float RGB in [-1, 1] (from FaceNative.nativeAlignFace).
 * Output: 192-dim embedding, L2-normalised by the model.
 *
 * The same model must be used for registration and verification: embeddings
 * from different models are not comparable, so MODEL_VERSION goes into every
 * signed payload and the backend refuses mismatches.
 */
class FaceEmbedder(context: Context) : AutoCloseable {

    companion object {
        const val TAG = "SentinelFace"
        const val MODEL_FILE = "mobilefacenet.tflite"
        /** Sent in the payload; the backend stores it with the template. */
        const val MODEL_VERSION = "mobilefacenet-192-v1"
        const val EMBEDDING_DIM = 192
    }

    private val interpreter: Interpreter
    private val input: ByteBuffer = ByteBuffer.allocateDirect(FaceNative.TENSOR_LENGTH * 4).order(ByteOrder.nativeOrder())
    private val output = Array(1) { FloatArray(EMBEDDING_DIM) }

    init {
        val bytes = context.assets.open(MODEL_FILE).use { it.readBytes() }
        val model = ByteBuffer.allocateDirect(bytes.size).order(ByteOrder.nativeOrder())
        model.put(bytes)
        model.rewind()
        val options = Interpreter.Options()
        options.setNumThreads(2)
        interpreter = Interpreter(model, options)
        val inShape = interpreter.getInputTensor(0).shape()
        val outShape = interpreter.getOutputTensor(0).shape()
        Log.i(TAG, "Loaded $MODEL_FILE (${bytes.size} bytes): input ${inShape.contentToString()} output ${outShape.contentToString()}")
        require(inShape.contentEquals(intArrayOf(1, FaceNative.SIZE, FaceNative.SIZE, 3))) { "Unexpected model input ${inShape.contentToString()}" }
        require(outShape.contentEquals(intArrayOf(1, EMBEDDING_DIM))) { "Unexpected model output ${outShape.contentToString()}" }
    }

    /** Embedding for one aligned crop (TENSOR_LENGTH floats). Not thread-safe: call from one thread. */
    fun embed(crop: FloatArray): FloatArray {
        input.rewind()
        input.asFloatBuffer().put(crop)
        input.rewind()
        interpreter.run(input, output)
        return output[0].copyOf()
    }

    override fun close() {
        interpreter.close()
    }
}
