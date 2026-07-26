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
 * Raw biometric telemetry data, serialized to JSON then signed.
 */
@Serializable
data class BiometricPayload(
    @SerialName("session_id")
    val sessionId: String,
    val bpm: Double,
    val timestamp: String,            // ISO-8601
    @SerialName("device_id")
    val deviceId: String,
    val snr: Double,
    val variance: Double
)

/**
 * Backend response after verifying biometric data.
 */
@Serializable
data class VerifyResponse(
    val status: String,
    @SerialName("session_id")
    val sessionId: String,
    val reason: String? = null
)

/**
 * Session status response for polling endpoint.
 */
@Serializable
data class SessionResponse(
    @SerialName("session_id")
    val sessionId: String,
    val status: String,               // e.g. "pending", "authenticated", "rejected"
    @SerialName("created_at")
    val createdAt: String = "",
    @SerialName("expires_at")
    val expiresAt: String = ""
)
