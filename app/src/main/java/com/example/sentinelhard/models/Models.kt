package com.example.sentinelhard.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Signed biometric payload sent to the backend for liveness verification.
 * Matches the FastAPI VerifyRequest schema.
 */
@Serializable
data class VerifyRequest(
    val payload: String,              // Base64-encoded JSON of BiometricPayload
    val signature: String,            // Base64 ECDSA signature of the payload
    @SerialName("public_key")
    val publicKey: String,            // Base64 DER-encoded SubjectPublicKeyInfo
    @SerialName("attestation_chain")
    val attestationChain: List<String> = emptyList()  // X.509 cert chain (leaf → root)
)

/**
 * Biometric result, serialized to JSON then signed inside Titan M2.
 *
 * Optional fields default to null and are left out of the JSON when null
 * (kotlinx.serialization's default Json does not encode default values).
 * Milestones 3–4 add face_embedding / reference_template, challenge fields
 * and key_security_level.
 */
@Serializable
data class BiometricPayload(
    @SerialName("session_id")
    val sessionId: String,
    val purpose: String? = null,
    val nonce: String? = null,
    val timestamp: String,            // ISO-8601 UTC
    @SerialName("device_id")
    val deviceId: String,
    val bpm: Double,
    val snr: Double,                  // rPPG SNR in dB (median of the final estimates)
    @SerialName("liveness_passed")
    val livenessPassed: Boolean? = null,
    @SerialName("frames_used")
    val framesUsed: Int? = null,
    @SerialName("app_version")
    val appVersion: String? = null,
)

/**
 * Backend response after verifying biometric data.
 */
@Serializable
data class VerifyResponse(
    val status: String,
    @SerialName("session_id")
    val sessionId: String,
    val reason: String? = null,
    @SerialName("reason_code")
    val reasonCode: String? = null,
    val outcome: String? = null,
)

/**
 * Session status response for polling endpoint.
 */
@Serializable
data class SessionResponse(
    @SerialName("session_id")
    val sessionId: String,
    val status: String,               // e.g. "PENDING", "GRANTED", "REJECTED"
    @SerialName("created_at")
    val createdAt: String = "",
    @SerialName("expires_at")
    val expiresAt: String = ""
)
