package com.example.sentinelhard

import android.util.Log
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.net.URLEncoder
import java.util.concurrent.TimeUnit

/**
 * Streams scan progress to the backend, which relays it to the portal page
 * showing the QR code (WS /api/v1/ws/telemetry/{session_id}?nonce=...).
 *
 * Message types understood by the backend (routers/ws.py TELEMETRY_EVENTS):
 * scan_started, measuring, stable_reading, challenge_issued, challenge_passed,
 * challenge_failed, face_lost, multiple_faces.
 *
 * Telemetry is best effort: if the socket is down the scan still completes;
 * the signed result is always sent over HTTP.
 * Thread-safety: OkHttp's WebSocket.send() is thread-safe and non-blocking,
 * so this class can be called directly from the CameraX analyzer thread.
 */
class TelemetryStreamer {

    companion object {
        private const val TAG = "TelemetryStreamer"
    }

    private var webSocket: WebSocket? = null
    @Volatile
    private var isConnected = false

    private val client = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MILLISECONDS)  // long-lived socket
        .retryOnConnectionFailure(true)
        .build()

    /** Opens the session's telemetry socket. Safe to call again; reconnects to the new session. */
    fun connect(baseUrl: String, sessionId: String, nonce: String?) {
        disconnect()
        val wsBase = baseUrl.trimEnd('/').replaceFirst(Regex("^http"), "ws")
        val url = "$wsBase/api/v1/ws/telemetry/$sessionId?nonce=" + URLEncoder.encode(nonce ?: "", "UTF-8")
        val request = Request.Builder().url(url).build()

        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(ws: WebSocket, response: Response) {
                isConnected = true
                Log.i(TAG, "Telemetry connected for session $sessionId")
            }

            override fun onClosing(ws: WebSocket, code: Int, reason: String) {
                Log.i(TAG, "Telemetry closing: $code / $reason")
                ws.close(code, reason)
                isConnected = false
            }

            override fun onFailure(ws: WebSocket, t: Throwable, response: Response?) {
                Log.w(TAG, "Telemetry socket error: ${t.message}")
                isConnected = false
            }
        })
    }

    /** Sends one event. OkHttp queues it until the socket opens; dropped if the socket failed. */
    fun send(type: String, fields: Map<String, Any?> = emptyMap()) {
        val ws = webSocket ?: return
        val payload = JSONObject().apply {
            put("type", type)
            fields.forEach { (k, v) -> if (v != null) put(k, v) }
        }
        ws.send(payload.toString())
    }

    /** Gracefully closes the WebSocket connection. */
    fun disconnect() {
        webSocket?.close(1000, "Scan finished")
        webSocket = null
        isConnected = false
    }

    /** Shuts down the OkHttp client entirely. Call in Activity.onDestroy(). */
    fun shutdown() {
        disconnect()
        client.dispatcher.executorService.shutdown()
    }
}
