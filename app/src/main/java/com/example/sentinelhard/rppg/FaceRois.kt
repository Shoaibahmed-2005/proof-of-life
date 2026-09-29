package com.example.sentinelhard.rppg

import android.graphics.Rect
import android.graphics.RectF

/**
 * Skin regions for rPPG, taken from INSIDE the detected face box so the pulse
 * always comes from the same face: the forehead and both cheeks (fractions of
 * the ML Kit bounding box; eyes, brows, nose and mouth are avoided).
 */
object FaceRois {

    // (left, top, right, bottom) as fractions of the face box, in upright image coordinates.
    private val REGIONS = listOf(
        floatArrayOf(0.30f, 0.08f, 0.70f, 0.24f),  // forehead
        floatArrayOf(0.16f, 0.50f, 0.38f, 0.72f),  // cheek (image left)
        floatArrayOf(0.62f, 0.50f, 0.84f, 0.72f),  // cheek (image right)
    )

    /** ROIs in upright image coordinates (for drawing the overlay). */
    fun uprightRois(face: Rect): List<RectF> = REGIONS.map { f ->
        RectF(
            face.left + f[0] * face.width(),
            face.top + f[1] * face.height(),
            face.left + f[2] * face.width(),
            face.top + f[3] * face.height(),
        )
    }

    /**
     * ROIs as a flat [x, y, w, h, ...] array in sensor (unrotated) coordinates,
     * which is how the camera's YUV planes are laid out.
     */
    fun sensorRois(face: Rect, sensorWidth: Int, sensorHeight: Int, rotationDegrees: Int): IntArray {
        val out = IntArray(REGIONS.size * 4)
        uprightRois(face).forEachIndexed { i, r ->
            val m = mapToSensor(
                r.left.toInt(), r.top.toInt(), r.width().toInt(), r.height().toInt(),
                sensorWidth, sensorHeight, rotationDegrees,
            )
            m.copyInto(out, i * 4)
        }
        return out
    }

    /**
     * Maps a rectangle from the upright (rotated) image back to sensor
     * coordinates. imgW/imgH are the sensor image size.
     */
    fun mapToSensor(x: Int, y: Int, w: Int, h: Int, imgW: Int, imgH: Int, rotation: Int): IntArray =
        when (rotation) {
            90 -> intArrayOf(y, imgH - x - w, h, w)
            180 -> intArrayOf(imgW - x - w, imgH - y - h, w, h)
            270 -> intArrayOf(imgW - y - h, x, h, w)
            else -> intArrayOf(x, y, w, h)
        }
}
