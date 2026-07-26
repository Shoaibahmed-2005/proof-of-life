package com.example.sentinelhard

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.PrivateKey
import java.security.Signature
import java.security.spec.ECGenParameterSpec

/**
 * Hardware-backed ECDSA cryptographic manager for SentinelHard.
 *
 * Uses the Android Keystore (backed by Titan M2 / StrongBox on supported devices)
 * to generate, store, and use an ECDSA P-256 key pair. The private key never leaves
 * the secure hardware — all signing operations are delegated to the HSM.
 *
 * Outputs Base64-encoded signatures and public keys matching the backend's
 * VerifyRequest schema.
 */
class CryptoManager {

    companion object {
        private const val KEY_ALIAS = "rppg_auth_key"
        private const val KEYSTORE_PROVIDER = "AndroidKeyStore"
    }

    private val keyStore: KeyStore = KeyStore.getInstance(KEYSTORE_PROVIDER).apply { load(null) }

    /**
     * Generates a hardware-backed ECDSA P-256 key pair in the Android Keystore.
     * If a key with [KEY_ALIAS] already exists, this is a no-op.
     *
     * The key is configured for:
     * - SIGN/VERIFY purpose only (cannot be used for encryption)
     * - SHA-256 digest
     * - StrongBox backing (Titan M2) when available, falls back to TEE
     * - Key attestation with challenge for hardware provenance proof
     */
    fun generateHardwareKey(attestationChallenge: ByteArray? = null) {
        if (keyStore.containsAlias(KEY_ALIAS)) return

        val specBuilder = KeyGenParameterSpec.Builder(
            KEY_ALIAS,
            KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY
        )
            .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
            .setDigests(KeyProperties.DIGEST_SHA256)
            .setUserAuthenticationRequired(false)

        // Request StrongBox (Titan M2) backing if available
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.P) {
            specBuilder.setIsStrongBoxBacked(true)
        }

        // Attach attestation challenge if provided
        if (attestationChallenge != null && android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.N) {
            specBuilder.setAttestationChallenge(attestationChallenge)
        }

        try {
            val keyPairGenerator = KeyPairGenerator.getInstance(
                KeyProperties.KEY_ALGORITHM_EC, KEYSTORE_PROVIDER
            )
            keyPairGenerator.initialize(specBuilder.build())
            keyPairGenerator.generateKeyPair()
        } catch (e: Exception) {
            // StrongBox may not be available — retry without it
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.P) {
                specBuilder.setIsStrongBoxBacked(false)
                val keyPairGenerator = KeyPairGenerator.getInstance(
                    KeyProperties.KEY_ALGORITHM_EC, KEYSTORE_PROVIDER
                )
                keyPairGenerator.initialize(specBuilder.build())
                keyPairGenerator.generateKeyPair()
            } else {
                throw e
            }
        }
    }

    /**
     * Signs the raw JSON string using the hardware-backed ECDSA private key.
     * Returns a Base64 (NO_WRAP) encoded signature string.
     */
    fun signPayload(jsonPayload: String): String {
        val privateKey = keyStore.getKey(KEY_ALIAS, null) as? PrivateKey
            ?: throw IllegalStateException("Hardware key not found. Call generateHardwareKey() first.")

        val signature = Signature.getInstance("SHA256withECDSA").apply {
            initSign(privateKey)
            update(jsonPayload.toByteArray(Charsets.UTF_8))
        }

        val signatureBytes = signature.sign()
        return Base64.encodeToString(signatureBytes, Base64.NO_WRAP)
    }

    /**
     * Extracts the SubjectPublicKeyInfo (DER format) from the Keystore
     * and encodes it as a Base64 string for the backend.
     */
    fun getBase64PublicKey(): String {
        val certificate = keyStore.getCertificate(KEY_ALIAS)
            ?: throw IllegalStateException("Certificate not found.")

        val publicKey = certificate.publicKey
        return Base64.encodeToString(publicKey.encoded, Base64.NO_WRAP)
    }

    /**
     * Extracts the Key Attestation certificate chain to prove to the backend
     * that the key was generated inside a physical Titan M2 / StrongBox chip.
     *
     * Returns a list of Base64-encoded X.509 certificates (leaf → root).
     */
    fun getAttestationChain(): List<String> {
        val certChain = keyStore.getCertificateChain(KEY_ALIAS) ?: return emptyList()
        return certChain.map { cert ->
            Base64.encodeToString(cert.encoded, Base64.NO_WRAP)
        }
    }

    /**
     * Checks whether a hardware-backed key already exists.
     */
    fun hasKey(): Boolean = keyStore.containsAlias(KEY_ALIAS)

    /**
     * Deletes the key pair. Useful for key rotation or testing.
     */
    fun deleteKey() {
        if (keyStore.containsAlias(KEY_ALIAS)) {
            keyStore.deleteEntry(KEY_ALIAS)
        }
    }
}
