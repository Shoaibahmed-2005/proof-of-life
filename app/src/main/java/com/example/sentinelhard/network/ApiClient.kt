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

    /**
     * Finds a backend address that answers /health: the QR's base_url first,
     * then localhost (works over USB with `adb reverse`). Returns null if none.
     */
    suspend fun resolveReachableBaseUrl(qrBaseUrl: String?): String? = withContext(Dispatchers.IO) {
        val port = qrBaseUrl?.let { portOf(it) } ?: DEFAULT_PORT
        val candidates = listOfNotNull(qrBaseUrl, "http://localhost:$port", "http://127.0.0.1:$port").distinct()
        candidates.firstOrNull { isHealthy(it) }.also {
            Log.i(TAG, "Backend candidates $candidates → using ${it ?: "none reachable"}")
        }
    }

    private fun isHealthy(baseUrl: String): Boolean = try {
        val request = Request.Builder().url(baseUrl.trimEnd('/') + API_PATH + "health").build()
        probeClient.newCall(request).execute().use { it.isSuccessful }
    } catch (e: Exception) {
        Log.w(TAG, "Backend not reachable at $baseUrl: ${e.message}")
        false
    }

    private fun portOf(url: String): Int? =
        Regex("^https?://[^/:]+:(\\d+)").find(url)?.groupValues?.get(1)?.toIntOrNull()
}
