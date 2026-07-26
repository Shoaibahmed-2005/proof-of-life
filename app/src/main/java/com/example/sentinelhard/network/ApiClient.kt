package com.example.sentinelhard.network

import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import java.util.concurrent.TimeUnit

/**
 * Singleton Retrofit client for communicating with the SentinelHard FastAPI backend.
 * Uses kotlinx.serialization for JSON conversion to match @Serializable data classes.
 */
object ApiClient {
    // Android emulator loopback to host machine.
    // Replace with your machine's local IP for physical device testing.
    private const val BASE_URL = "http://192.168.1.5:8000/api/"

    // Lenient JSON parser: ignores unknown fields from server, encodes defaults
    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    // OkHttp with request/response body logging for debugging signed payloads
    private val okHttpClient = OkHttpClient.Builder()
        .addInterceptor(HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BODY
        })
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .build()

    val retrofit: Retrofit by lazy {
        Retrofit.Builder()
            .baseUrl(BASE_URL)
            .client(okHttpClient)
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()
    }

    val apiService: BiometricApiService by lazy {
        retrofit.create(BiometricApiService::class.java)
    }
}
