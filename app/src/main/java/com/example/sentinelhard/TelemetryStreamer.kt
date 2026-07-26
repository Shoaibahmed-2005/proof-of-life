package com.example.sentinelhard

import android.util.Log
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * Streams rPPG telemetry (BPM, SNR, liveness status) to the FastAPI backend
 * over a persistent WebSocket connection.
 *
 * Thread-safety: OkHttp's WebSocket.send() is thread-safe and non-blocking,
 * so this class can be called directly from the CameraX analyzer thread.
 */
class TelemetryStreamer {

    companion object {
        private const val TAG = "TelemetryStreamer"
        // Default: Android emulator loopback to host machine.
        // Replace with your machine's local IP for physical device testing.
        private const val DEFAULT_URL = "ws://10.0.2.2:8080/api/v1/ws/telemetry"
    }

    private var webSocket: WebSocket? = null
    @Volatile
    private var isConnected = false

    private val client = OkHttpClient.Builder()
        .readTimeout(3, TimeUnit.SECONDS)
        .retryOnConnectionFailure(true)
        .build()

    /**
     * Opens a WebSocket connection to the telemetry server.
     * Safe to call multiple times — will no-op if already connected.
     */
    fun connect(serverUrl: String = DEFAULT_URL) {
        if (isConnected) return

        val request = Request.Builder().url(serverUrl).build()

        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(ws: WebSocket, response: Response) {
                isConnected = true
                Log.i(TAG, "WebSocket connected to $serverUrl")
            }

            override fun onMessage(ws: WebSocket, text: String) {
                Log.d(TAG, "Server: $text")
            }

            override fun onClosing(ws: WebSocket, code: Int, reason: String) {
                Log.i(TAG, "WebSocket closing: $code / $reason")
                ws.close(code, reason)
                isConnected = false
            }

            override fun onFailure(ws: WebSocket, t: Throwable, response: Response?) {
                Log.e(TAG, "WebSocket error: ${t.message}")
                isConnected = false
            }
        })
    }

    /**
     * Sends a telemetry payload to the server.
     * No-ops silently if the WebSocket is not connected.
     *
     * @param bpm        Kalman-smoothed heart rate
     * @param snr        Signal-to-noise ratio from FFT analysis
     * @param livenessStatus  Liveness tier: 0 = Spoof, 1 = Analyzing, 2 = Human
     */
    fun sendTelemetry(bpm: Double, snr: Double, livenessStatus: Int) {
        if (!isConnected) return

        val payload = JSONObject().apply {
            put("bpm", bpm)
            put("snr", snr)
            put("liveness_status", livenessStatus)
            put("timestamp", System.currentTimeMillis())
        }

        webSocket?.send(payload.toString())
    }

    /**
     * Gracefully closes the WebSocket connection.
     */
    fun disconnect() {
        webSocket?.close(1000, "Session ended")
        webSocket = null
        isConnected = false
    }

    /**
     * Shuts down the OkHttp client entirely. Call in Activity.onDestroy().
     */
    fun shutdown() {
        disconnect()
        client.dispatcher.executorService.shutdown()
    }
}
