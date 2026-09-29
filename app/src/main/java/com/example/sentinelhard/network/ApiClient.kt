package com.example.sentinelhard.network

import android.util.Log
import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import java.util.concurrent.TimeUnit

/**
 * Retrofit client for the backend. The backend address is NOT hard-coded: it
 * comes from the QR code (base_url), so nothing needs rebuilding when the
 * laptop or network changes.
 */
object ApiClient {
    private const val TAG = "SentinelHard"
    private const val API_PATH = "/api/v1/"

    /** Tried when the QR's LAN address is unreachable (USB: `adb reverse tcp:8000 tcp:8000`). */
    private const val DEFAULT_PORT = 8000

    // Lenient JSON parser: ignores unknown fields from server, encodes defaults
    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    private val okHttpClient = OkHttpClient.Builder()
        .addInterceptor(HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BASIC
        })
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .build()

    private val probeClient = OkHttpClient.Builder()
        .connectTimeout(3, TimeUnit.SECONDS)
        .readTimeout(3, TimeUnit.SECONDS)
        .build()

    private val services = mutableMapOf<String, BiometricApiService>()

    /** Retrofit service for a backend base URL such as "http://192.168.1.10:8000". */
    @Synchronized
    fun service(baseUrl: String): BiometricApiService =
        services.getOrPut(baseUrl) {
            Retrofit.Builder()
                .baseUrl(baseUrl.trimEnd('/') + API_PATH)
                .client(okHttpClient)
                .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
                .build()
                .create(BiometricApiService::class.java)
        }

    /** One connection attempt: the address tried and, if it failed, why in plain words. */
    data class ProbeAttempt(val url: String, val ok: Boolean, val reason: String)

    data class ProbeResult(val baseUrl: String?, val attempts: List<ProbeAttempt>) {
        /** Multi-line explanation for the error screen. */
        fun describeFailure(): String = attempts.joinToString("\n") { "• ${it.url}: ${it.reason}" }
    }

    /**
     * Finds a backend address that answers /health: the QR's base_url first,
     * then localhost (works over USB with `adb reverse`). Every attempt is
     * recorded with the reason it failed.
     */
    suspend fun resolveReachableBaseUrl(qrBaseUrl: String?): ProbeResult = withContext(Dispatchers.IO) {
        val port = qrBaseUrl?.let { portOf(it) } ?: DEFAULT_PORT
        val candidates = listOfNotNull(qrBaseUrl, "http://localhost:$port").distinct()
        val attempts = mutableListOf<ProbeAttempt>()
        var chosen: String? = null
        for (url in candidates) {
            val attempt = probe(url)
            attempts.add(attempt)
            Log.i(TAG, "Backend probe ${attempt.url}: ${if (attempt.ok) "OK" else attempt.reason}")
            if (attempt.ok) {
                chosen = url
                break
            }
        }
        ProbeResult(chosen, attempts)
    }

    private fun probe(baseUrl: String): ProbeAttempt = try {
        val request = Request.Builder().url(baseUrl.trimEnd('/') + API_PATH + "health").build()
        probeClient.newCall(request).execute().use { response ->
            if (response.isSuccessful) ProbeAttempt(baseUrl, true, "OK")
            else ProbeAttempt(baseUrl, false, "answered HTTP ${response.code} (is this the Jeevan Suraksha backend?)")
        }
    } catch (e: Exception) {
        ProbeAttempt(baseUrl, false, explain(e, portOf(baseUrl) ?: DEFAULT_PORT))
    }

    /** Turns a network exception into a plain-language cause. */
    private fun explain(e: Exception, port: Int): String {
        // OkHttp wraps the socket error, so look at the whole cause chain.
        val msg = generateSequence(e as Throwable) { it.cause }.take(5)
            .mapNotNull { it.message }.joinToString(" | ")
        return when {
            e is java.net.SocketTimeoutException || msg.contains("timed out", ignoreCase = true) ->
                "timed out: a firewall is blocking port $port on the laptop, the laptop is on a " +
                    "different network, or this Wi-Fi blocks devices from reaching each other"
            e is java.net.UnknownServiceException || msg.contains("CLEARTEXT", ignoreCase = true) ->
                "blocked by Android's plain-HTTP policy"
            e is java.net.ConnectException && msg.contains("ECONNREFUSED") ->
                "connection refused: the backend isn't running on that port, or it only listens on " +
                    "127.0.0.1 (start it with `python run.py`)"
            e is java.net.ConnectException && (msg.contains("EHOSTUNREACH") || msg.contains("ENETUNREACH")) ->
                "network unreachable: the phone and laptop are not on the same network"
            e is java.net.ConnectException -> "could not connect ($msg)"
            e is java.net.UnknownHostException -> "address not found"
            e is javax.net.ssl.SSLException -> "HTTPS/TLS error ($msg)"
            else -> "${e.javaClass.simpleName}: $msg"
        }
    }

    private fun portOf(url: String): Int? =
        Regex("^https?://[^/:]+:(\\d+)").find(url)?.groupValues?.get(1)?.toIntOrNull()
}
