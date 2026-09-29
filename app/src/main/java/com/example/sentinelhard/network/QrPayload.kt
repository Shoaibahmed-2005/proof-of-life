package com.example.sentinelhard.network

import org.json.JSONException
import org.json.JSONObject

/**
 * What the portal's QR code carries (backend services/session.py build_qr_payload):
 *
 *   {"v":1, "base_url":"http://192.168.1.10:8000", "session_id":"...",
 *    "purpose":"AUTH|ENROLLMENT|LIFE_CERTIFICATE", "nonce":"...",
 *    "challenge":{"id":"...","type":"BLINK_TWICE","timeout_s":8},
 *    "liveness":{"min_snr_db":3.0}}
 *
 * Older portals put only the bare session id (or {"session_id": ...}) in the
 * QR; those are accepted as purpose AUTH with no base URL.
 */
data class QrPayload(
    val sessionId: String,
    val purpose: String,
    val baseUrl: String?,
    val nonce: String?,
    val challengeId: String?,
    val challengeType: String?,
    val challengeTimeoutSec: Int?,
    val minSnrDb: Double?,
) {
    val isAuth: Boolean get() = purpose == PURPOSE_AUTH

    companion object {
        const val PURPOSE_AUTH = "AUTH"
        const val PURPOSE_ENROLLMENT = "ENROLLMENT"
        const val PURPOSE_LIFE_CERTIFICATE = "LIFE_CERTIFICATE"

        /** Returns null if the text is not a session QR code. */
        fun parse(raw: String): QrPayload? {
            val text = raw.trim()
            if (text.isEmpty()) return null
            if (!text.startsWith("{")) {
                // Legacy: the QR is just the session id.
                return if (text.length in 16..128 && text.none { it.isWhitespace() }) {
                    QrPayload(text, PURPOSE_AUTH, null, null, null, null, null, null)
                } else null
            }
            return try {
                val json = JSONObject(text)
                val sessionId = json.optString("session_id").takeIf { it.isNotBlank() } ?: return null
                val challenge = json.optJSONObject("challenge")
                val liveness = json.optJSONObject("liveness")
                QrPayload(
                    sessionId = sessionId,
                    purpose = json.optString("purpose", PURPOSE_AUTH).ifBlank { PURPOSE_AUTH },
                    baseUrl = json.optString("base_url").takeIf { it.startsWith("http") }?.trimEnd('/'),
                    nonce = json.optString("nonce").takeIf { it.isNotBlank() },
                    challengeId = challenge?.optString("id")?.takeIf { it.isNotBlank() },
                    challengeType = challenge?.optString("type")?.takeIf { it.isNotBlank() },
                    challengeTimeoutSec = challenge?.optInt("timeout_s", 0)?.takeIf { it > 0 },
                    minSnrDb = liveness?.optDouble("min_snr_db")?.takeIf { !it.isNaN() },
                )
            } catch (e: JSONException) {
                null
            }
        }
    }
}
