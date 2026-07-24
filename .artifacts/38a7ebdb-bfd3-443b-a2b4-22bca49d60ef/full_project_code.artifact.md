# Project SentinelHard - Full Source Code

This document contains the entire source code for the Project SentinelHard Android application, including Kotlin UI, Native C++ DSP logic, and build configuration.

---

## 1. Project Configuration

### [settings.gradle.kts](file:///C:/Users/praji/AndroidStudioProjects/SentinelHard/settings.gradle.kts)
```kotlin
pluginManagement {
    repositories {
        google {
            content {
                includeGroupByRegex("com\\.android.*")
                includeGroupByRegex("com\\.google.*")
                includeGroupByRegex("androidx.*")
            }
        }
        mavenCentral()
        gradlePluginPortal()
    }
}
plugins {
    id("org.gradle.toolchains.foojay-resolver-convention") version "1.0.0"
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "SentinelHard"
include(":app")
include(":opencv")
project(":opencv").projectDir = file("sdk")
```

### [build.gradle.kts (Root)](file:///C:/Users/praji/AndroidStudioProjects/SentinelHard/build.gradle.kts)
```kotlin
// Top-level build file where you can add configuration options common to all sub-projects/modules.
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.android) apply false
    alias(libs.plugins.compose.compiler) apply false
}
```

### [gradle/libs.versions.toml](file:///C:/Users/praji/AndroidStudioProjects/SentinelHard/gradle/libs.versions.toml)
```toml
[versions]
agp = "9.3.1"
kotlin = "2.2.10"
coreKtx = "1.10.1"
junit = "4.13.2"
junitVersion = "1.1.5"
espressoCore = "3.5.1"
appcompat = "1.6.1"
material = "1.10.0"
constraintlayout = "2.1.4"
mlkitFaceDetection = "17.1.0"
camerax = "1.2.2"
composeBom = "2023.08.00"
activityCompose = "1.7.2"

[libraries]
androidx-core-ktx = { group = "androidx.core", name = "core-ktx", version.ref = "coreKtx" }
junit = { group = "junit", name = "junit", version.ref = "junit" }
androidx-junit = { group = "androidx.test.ext", name = "junit", version.ref = "junitVersion" }
androidx-espresso-core = { group = "androidx.test.espresso", name = "espresso-core", version.ref = "espressoCore" }
androidx-appcompat = { group = "androidx.appcompat", name = "appcompat", version.ref = "appcompat" }
material = { group = "com.google.android.material", name = "material", version.ref = "material" }
androidx-constraintlayout = { group = "androidx.constraintlayout", name = "constraintlayout", version.ref = "constraintlayout" }
play-services-mlkit-face-detection = { group = "com.google.android.gms", name = "play-services-mlkit-face-detection", version.ref = "mlkitFaceDetection" }
androidx-camera-core = { group = "androidx.camera", name = "camera-core", version.ref = "camerax" }
androidx-camera-camera2 = { group = "androidx.camera", name = "camera-camera2", version.ref = "camerax" }
androidx-camera-lifecycle = { group = "androidx.camera", name = "camera-lifecycle", version.ref = "camerax" }
androidx-camera-view = { group = "androidx.camera", name = "camera-view", version.ref = "camerax" }
androidx-compose-bom = { group = "androidx.compose", name = "compose-bom", version.ref = "composeBom" }
androidx-compose-ui = { group = "androidx.compose.ui", name = "ui" }
androidx-compose-ui-graphics = { group = "androidx.compose.ui", name = "ui-graphics" }
androidx-compose-ui-tooling-preview = { group = "androidx.compose.ui", name = "ui-tooling-preview" }
androidx-compose-material3 = { group = "androidx.compose.material3", name = "material3" }
androidx-activity-compose = { group = "androidx.activity", name = "activity-compose", version.ref = "activityCompose" }

[plugins]
android-application = { id = "com.android.application", version.ref = "agp" }
kotlin-android = { id = "org.jetbrains.kotlin.android", version.ref = "kotlin" }
compose-compiler = { id = "org.jetbrains.kotlin.plugin.compose", version.ref = "kotlin" }
```

---

## 2. App Module

### [app/build.gradle.kts](file:///C:/Users/praji/AndroidStudioProjects/SentinelHard/app/build.gradle.kts)
```kotlin
plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.compose.compiler)
}

android {
    namespace = "com.example.sentinelhard"
    compileSdk {
        version = release(35)
    }

    defaultConfig {
        applicationId = "com.example.sentinelhard"
        minSdk = 24
        //noinspection OldTargetApi
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"

        externalNativeBuild {
            cmake {
                cppFlags += ""
                // ADD THIS LINE to tell CMake where OpenCV is:
                arguments += "-DOpenCV_DIR=${project.rootDir}/sdk/native/jni"
                // Note: If your OpenCV folder has an "sdk" subfolder, it might be:
                // arguments += "-DOpenCV_DIR=${project.rootDir}/opencv/sdk/native/jni"
                // --- ADD THIS LINE ---
                abiFilters += setOf("arm64-v8a", "armeabi-v7a")
                arguments += "-DANDROID_LINKER_FLAGS=-Wl,-z,max-page-size=16384"
            }
        }

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        release {
            optimization {
                enable = false
            }
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.22.1"
        }
    }
    buildFeatures {
        viewBinding = true
        compose = true
    }
}

dependencies {
    implementation(project(":opencv"))
    implementation(libs.androidx.appcompat)
    implementation(libs.androidx.constraintlayout)
    implementation(libs.androidx.core.ktx)
    implementation(libs.material)
    implementation(libs.play.services.mlkit.face-detection)
    implementation(libs.androidx.camera.core)
    implementation(libs.androidx.camera.camera2)
    implementation(libs.androidx.camera.lifecycle)
    implementation(libs.androidx.camera.view)

    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.activity.compose)

    testImplementation(libs.junit)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(libs.androidx.junit)
}
```

### [app/src/main/AndroidManifest.xml](file:///C:/Users/praji/AndroidStudioProjects/SentinelHard/app/src/main/AndroidManifest.xml)
```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:tools="http://schemas.android.com/tools">

    <uses-permission android:name="android.permission.CAMERA" />
    <uses-feature android:name="android.hardware.camera.any" />

    <application
        android:allowBackup="true"
        android:dataExtractionRules="@xml/data_extraction_rules"
        android:fullBackupContent="@xml/backup_rules"
        android:icon="@mipmap/ic_launcher"
        android:label="@string/app_name"
        android:roundIcon="@mipmap/ic_launcher_round"
        android:supportsRtl="true"
        android:theme="@style/Theme.SentinelHard">
        <activity
            android:name=".MainActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />

                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>

</manifest>
```

---

## 3. Native Layer

### [app/src/main/cpp/CMakeLists.txt](file:///C:/Users/praji/AndroidStudioProjects/SentinelHard/app/src/main/cpp/CMakeLists.txt)
```cmake
# Sets the minimum CMake version required for this project.
cmake_minimum_required(VERSION 3.22.1)

# Declares the project name.
project("sentinelhard")

# --- Find the OpenCV package ---
find_package(OpenCV REQUIRED)

add_library(${CMAKE_PROJECT_NAME} SHARED
        # List C/C++ source files with relative paths to this CMakeLists.txt.
        native-lib.cpp)

# Specifies libraries CMake should link to your target library.
target_link_libraries(${CMAKE_PROJECT_NAME}
        # List libraries link to the target library
        # --- ADDED: Link OpenCV to your project ---
        ${OpenCV_LIBRARIES}
        android
        log)
```

### [app/src/main/cpp/native-lib.cpp](file:///C:/Users/praji/AndroidStudioProjects/SentinelHard/app/src/main/cpp/native-lib.cpp)
```cpp
#include <jni.h>
#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include <android/log.h>
#include <vector>
#include <algorithm>
#include <cmath>
#include <numeric>

#define LOG_TAG "SentinelHardNative"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)

// --- Signal Processing Constants ---
const double MIN_BPM = 45.0;
const double MAX_BPM = 180.0;
const double FPS = 30.0; // Resampled framerate
const int MAX_BUFFER_SIZE = 150;
const double PI_VAL = 3.14159265358979323846;

// --- Signal Processing Utilities ---

struct SignalSample {
    double timestamp; // in seconds
    double value;     // channel mean
};

class ButterworthBandpassFilter {
private:
    double hp_b0, hp_b1, hp_b2, hp_a1, hp_a2;
    double lp_b0, lp_b1, lp_b2, lp_a1, lp_a2;

    // State history for the IIR delay lines
    double hp_x1 = 0, hp_x2 = 0, hp_y1 = 0, hp_y2 = 0;
    double lp_x1 = 0, lp_x2 = 0, lp_y1 = 0, lp_y2 = 0;

public:
    ButterworthBandpassFilter(double lowCut, double highCut, double sampleRate) {
        updateCoefficients(lowCut, highCut, sampleRate);
    }

    void updateCoefficients(double lowCut, double highCut, double fs) {
        if (fs <= 0.0) fs = 30.0;

        // --- High Pass Filter Coefficients (0.75 Hz) ---
        double omegaHP = std::tan(PI_VAL * lowCut / fs);
        double normHP = 1.0 / (1.0 + std::sqrt(2.0) * omegaHP + omegaHP * omegaHP);
        hp_b0 = normHP;
        hp_b1 = -2.0 * hp_b0;
        hp_b2 = hp_b0;
        hp_a1 = 2.0 * (omegaHP * omegaHP - 1.0) * normHP;
        hp_a2 = (1.0 - std::sqrt(2.0) * omegaHP + omegaHP * omegaHP) * normHP;

        // --- Low Pass Filter Coefficients (2.5 Hz) ---
        double omegaLP = std::tan(PI_VAL * highCut / fs);
        double normLP = 1.0 / (1.0 + std::sqrt(2.0) * omegaLP + omegaLP * omegaLP);
        lp_b0 = omegaLP * omegaLP * normLP;
        lp_b1 = 2.0 * lp_b0;
        lp_b2 = lp_b0;
        lp_a1 = 2.0 * (omegaLP * omegaLP - 1.0) * normLP;
        lp_a2 = (1.0 - std::sqrt(2.0) * omegaLP + omegaLP * omegaLP) * normLP;
    }

    void reset() {
        hp_x1 = hp_x2 = hp_y1 = hp_y2 = 0;
        lp_x1 = lp_x2 = lp_y1 = lp_y2 = 0;
    }

    double process(double sample) {
        if (!std::isfinite(sample)) sample = 0.0;

        // 1. Process High Pass
        double hp_out = hp_b0 * sample + hp_b1 * hp_x1 + hp_b2 * hp_x2 - hp_a1 * hp_y1 - hp_a2 * hp_y2;
        hp_x2 = hp_x1; hp_x1 = sample;
        hp_y2 = hp_y1; hp_y1 = hp_out;

        // 2. Process Low Pass (fed by High Pass output)
        double lp_out = lp_b0 * hp_out + lp_b1 * lp_x1 + lp_b2 * lp_x2 - lp_a1 * lp_y1 - lp_a2 * lp_y2;
        lp_x2 = lp_x1; lp_x1 = hp_out;
        lp_y2 = lp_y1; lp_y1 = lp_out;

        // 3. Self-Healing Check
        if (!std::isfinite(lp_out)) {
            hp_x1 = hp_x2 = hp_y1 = hp_y2 = 0.0;
            lp_x1 = lp_x2 = lp_y1 = lp_y2 = 0.0;
            return 0.0;
        }

        return lp_out;
    }
};

// Global / Persistent state
static std::vector<SignalSample> g_greenBuffer;
static std::vector<SignalSample> g_redBuffer;
static std::vector<SignalSample> g_blueBuffer;

static std::vector<double> g_greenFiltered;
static std::vector<double> g_redFiltered;
static std::vector<double> g_blueFiltered;
static std::vector<double> g_ratioFiltered; // Ratiometric signal

static double g_smoothedBpm = 0.0;
static double g_smoothedSnr = 0.0;

static const double WINDOW_DURATION = 5.0;   // 5-second sliding window
static const double TARGET_FS = 30.0;         // Resample target: 30 Hz
static const double TARGET_DT = 1.0 / TARGET_FS;

// Independent Filter Instances
static ButterworthBandpassFilter filterRatio(0.75, 2.5, 30.0);
static ButterworthBandpassFilter filterR(0.75, 2.5, 30.0);
static ButterworthBandpassFilter filterG(0.75, 2.5, 30.0);
static ButterworthBandpassFilter filterB(0.75, 2.5, 30.0);

// Linear Interpolation
double interpolate(double t, double t0, double v0, double t1, double v1) {
    if (std::abs(t1 - t0) < 1e-6) return v0;
    return v0 + (t - t0) * (v1 - v0) / (t1 - t0);
}

// Resample non-uniform buffer to uniform 30 Hz grid
std::vector<double> resampleToUniform(const std::vector<SignalSample>& buffer) {
    std::vector<double> uniformSignal;
    if (buffer.size() < 2) return uniformSignal;

    double tStart = buffer.front().timestamp;
    double tEnd = buffer.back().timestamp;

    size_t sampleIdx = 0;
    for (double t = tStart; t <= tEnd; t += TARGET_DT) {
        while (sampleIdx < buffer.size() - 2 && buffer[sampleIdx + 1].timestamp < t) {
            sampleIdx++;
        }
        double v = interpolate(
            t,
            buffer[sampleIdx].timestamp, buffer[sampleIdx].value,
            buffer[sampleIdx + 1].timestamp, buffer[sampleIdx + 1].value
        );
        uniformSignal.push_back(v);
    }
    return uniformSignal;
}

// --- Anti-Spoofing Biological Verification ---

bool isScreenFlicker(const std::vector<double>& green, const std::vector<double>& red, double* outCorrelation) {
    if (green.size() < 150 || red.size() < 150) return false;

    size_t startG = green.size() - 150;
    size_t startR = red.size() - 150;

    double meanG = 0, meanR = 0;
    for (size_t i = 0; i < 150; ++i) {
        meanG += green[startG + i];
        meanR += red[startR + i];
    }
    meanG /= 150.0;
    meanR /= 150.0;

    double num = 0.0, denomG = 0.0, denomR = 0.0;
    for (size_t i = 0; i < 150; ++i) {
        double diffG = green[startG + i] - meanG;
        double diffR = red[startR + i] - meanR;
        num += diffG * diffR;
        denomG += diffG * diffG;
        denomR += diffR * diffR;
    }

    double correlation = num / (sqrt(denomG * denomR) + 1e-6);
    if (outCorrelation) *outCorrelation = correlation;
    // Increased threshold to 0.95 for higher noise tolerance
    return correlation > 0.95;
}

// --- Heart Rate Extraction Math ---

std::vector<double> extractVitals(const std::vector<double>& signal, const std::vector<double>& green, const std::vector<double>& red) {
    if (signal.size() < 150) {
        return {0.0, 0.0, 0.0};
    }

    // 1. Signal Variance Check (Photo rejection)
    double sum = std::accumulate(signal.begin(), signal.end(), 0.0);
    double mean = sum / signal.size();
    double sq_sum = std::inner_product(signal.begin(), signal.end(), signal.begin(), 0.0);
    double variance = (sq_sum / (double)signal.size()) - (mean * mean);

    if (variance < 1e-9) {
        LOGI("Spoof: Variance too low (%e)", variance);
        g_smoothedSnr = (0.8 * g_smoothedSnr) + (0.2 * -5.0);
        return {0.0, g_smoothedSnr, 0.0};
    }

    // 2. Correlation Check
    double correlation = 0.0;
    if (isScreenFlicker(green, red, &correlation)) {
        LOGI("Spoof: High Correlation (%f)", correlation);
        g_smoothedSnr = (0.8 * g_smoothedSnr) + (0.2 * -10.0);
        return {0.0, g_smoothedSnr, 0.0};
    }

    int N = 150;
    size_t startIdx = signal.size() - 150;

    // APPLY HAMMING WINDOW to reduce spectral leakage and boost SNR
    std::vector<double> windowedSignal(N);
    for (int i = 0; i < N; ++i) {
        double multiplier = 0.54 - 0.46 * cos(2.0 * PI_VAL * i / (N - 1));
        windowedSignal[i] = signal[startIdx + i] * multiplier;
    }

    double max_power = 0.0;
    int peakIndex = -1;

    std::vector<double> power_spectrum(MAX_BPM - MIN_BPM + 1, 0.0);

    for (int bpm = (int)MIN_BPM; bpm <= (int)MAX_BPM; ++bpm) {
        double f = bpm / 60.0;
        double sum_real = 0.0;
        double sum_imag = 0.0;

        for (int n = 0; n < N; ++n) {
            double angle = -2.0 * PI_VAL * f * (n / FPS);
            sum_real += windowedSignal[n] * cos(angle);
            sum_imag += windowedSignal[n] * sin(angle);
        }

        double power = (sum_real * sum_real) + (sum_imag * sum_imag);
        int spectrumIdx = bpm - (int)MIN_BPM;
        power_spectrum[spectrumIdx] = power;

        if (power > max_power) {
            max_power = power;
            peakIndex = spectrumIdx;
        }
    }

    // 3. Quadratic Peak Interpolation
    double exactPeakBpm = MIN_BPM + peakIndex;
    if (peakIndex > 0 && peakIndex < (int)power_spectrum.size() - 1) {
        double y1 = power_spectrum[peakIndex - 1];
        double y2 = power_spectrum[peakIndex];
        double y3 = power_spectrum[peakIndex + 1];
        double denominator = y1 - 2.0 * y2 + y3;
        if (std::abs(denominator) > 1e-5) {
            double offset = 0.5 * (y1 - y3) / denominator;
            exactPeakBpm = (MIN_BPM + peakIndex) + offset;
        }
    }

    // 4. SNR Calculation
    double signal_power = 0.0;
    double noise_power = 0.0;

    for (int bpm = (int)MIN_BPM; bpm <= (int)MAX_BPM; ++bpm) {
        if (std::abs(bpm - exactPeakBpm) <= 3.0) {
            signal_power += power_spectrum[bpm - (int)MIN_BPM];
        } else {
            noise_power += power_spectrum[bpm - (int)MIN_BPM];
        }
    }

    noise_power = std::max(noise_power, 0.0001);
    double snr = 10.0 * log10(std::max(signal_power / noise_power, 1e-6));

    // 5. SNR Smoothing
    if (g_smoothedSnr == 0.0) g_smoothedSnr = snr;
    else g_smoothedSnr = (0.8 * g_smoothedSnr) + (0.2 * snr);

    // 6. Liveness Threshold (Lowered to 1.0 dB for mobile camera tolerance)
    double is_live = (g_smoothedSnr > 1.0) ? 1.0 : 0.0;

    LOGI("BPM: %.1f | SNR: %.2f | Correlation: %.2f | Live: %.0f", exactPeakBpm, g_smoothedSnr, correlation, is_live);

    return {exactPeakBpm, g_smoothedSnr, is_live};
}

// --- JNI Implementation ---

extern "C" JNIEXPORT void JNICALL
Java_com_example_sentinelhard_MainActivity_resetBuffers(JNIEnv *env, jobject /* thiz */) {
    g_greenBuffer.clear();
    g_redBuffer.clear();
    g_blueBuffer.clear();
    g_greenFiltered.clear();
    g_redFiltered.clear();
    g_blueFiltered.clear();
    g_ratioFiltered.clear();

    filterRatio.reset();
    filterR.reset();
    filterG.reset();
    filterB.reset();

    g_smoothedBpm = 0.0;
    g_smoothedSnr = 0.0;
    LOGI("Buffers and Filters Reset");
}

extern "C"
JNIEXPORT jdoubleArray JNICALL
Java_com_example_sentinelhard_MainActivity_processFrame(
        JNIEnv *env,
        jobject /* this */,
        jbyteArray yuvData,
        jint width,
        jint height,
        jint roiX,
        jint roiY,
        jint roiW,
        jint roiH,
        jdouble timestampSeconds) {

    jbyte *yuv_ptr = env->GetByteArrayElements(yuvData, nullptr);
    cv::Mat mYuv(height + height / 2, width, CV_8UC1, (unsigned char *)yuv_ptr);
    cv::Mat mRgb;
    cv::cvtColor(mYuv, mRgb, cv::COLOR_YUV2RGB_NV21);

    cv::Rect safeRoi(roiX, roiY, roiW, roiH);
    safeRoi &= cv::Rect(0, 0, mRgb.cols, mRgb.rows);

    double rMean = 0.0, gMean = 0.0, bMean = 0.0;
    if (safeRoi.width > 0 && safeRoi.height > 0) {
        cv::Mat skinRegion = mRgb(safeRoi);
        cv::Scalar means = cv::mean(skinRegion);
        rMean = means[0]; // R
        gMean = means[1]; // G
        bMean = means[2]; // B
    }
    env->ReleaseByteArrayElements(yuvData, yuv_ptr, JNI_ABORT);

    g_redBuffer.push_back({timestampSeconds, rMean});
    g_greenBuffer.push_back({timestampSeconds, gMean});
    g_blueBuffer.push_back({timestampSeconds, bMean});

    double cutoffTime = timestampSeconds - WINDOW_DURATION;
    auto purge = [cutoffTime](const SignalSample& s) { return s.timestamp < cutoffTime; };
    g_redBuffer.erase(std::remove_if(g_redBuffer.begin(), g_redBuffer.end(), purge), g_redBuffer.end());
    g_greenBuffer.erase(std::remove_if(g_greenBuffer.begin(), g_greenBuffer.end(), purge), g_greenBuffer.end());
    g_blueBuffer.erase(std::remove_if(g_blueBuffer.begin(), g_blueBuffer.end(), purge), g_blueBuffer.end());

    if (g_greenBuffer.back().timestamp - g_greenBuffer.front().timestamp >= 0.1) {
        std::vector<double> uniformR = resampleToUniform(g_redBuffer);
        std::vector<double> uniformG = resampleToUniform(g_greenBuffer);
        std::vector<double> uniformB = resampleToUniform(g_blueBuffer);

        if (!uniformR.empty() && !uniformG.empty() && !uniformB.empty()) {
            g_redFiltered.push_back(filterR.process(uniformR.back()));
            g_greenFiltered.push_back(filterG.process(uniformG.back()));
            g_blueFiltered.push_back(filterB.process(uniformB.back()));

            // Ratiometric Signal with Safeguard
            double ratio = 0.5;
            if (uniformR.back() + uniformB.back() > 5.0) {
                ratio = uniformG.back() / (uniformR.back() + uniformB.back());
            }
            g_ratioFiltered.push_back(filterRatio.process(ratio));

            while (g_greenFiltered.size() > MAX_BUFFER_SIZE) {
                g_redFiltered.erase(g_redFiltered.begin());
                g_greenFiltered.erase(g_greenFiltered.begin());
                g_blueFiltered.erase(g_blueFiltered.begin());
                g_ratioFiltered.erase(g_ratioFiltered.begin());
            }
        }
    }

    size_t numPoints = g_ratioFiltered.size();
    jdoubleArray result = env->NewDoubleArray((jsize)numPoints);
    if (numPoints > 0) {
        env->SetDoubleArrayRegion(result, 0, (jsize)numPoints, g_ratioFiltered.data());
    }
    return result;
}

extern "C" JNIEXPORT jdoubleArray JNICALL
Java_com_example_sentinelhard_MainActivity_extractHeartMetrics(
        JNIEnv *env, jobject /* thiz */) {

    double current_size = static_cast<double>(g_ratioFiltered.size());
    std::vector<double> metrics = {0.0, 0.0, 0.0, current_size};

    if (current_size >= (double)MAX_BUFFER_SIZE) {
        std::vector<double> vitals = extractVitals(g_ratioFiltered, g_greenFiltered, g_redFiltered);

        double currentBpm = vitals[0];
        if (g_smoothedBpm == 0.0 || std::abs(g_smoothedBpm - currentBpm) > 25.0) {
            g_smoothedBpm = currentBpm;
        } else {
            g_smoothedBpm = (0.85 * g_smoothedBpm) + (0.15 * currentBpm);
        }

        metrics[0] = g_smoothedBpm;
        metrics[1] = vitals[1]; // Smoothed SNR
        metrics[2] = vitals[2]; // Liveness
    }

    jdoubleArray result = env->NewDoubleArray(4);
    env->SetDoubleArrayRegion(result, 0, 4, metrics.data());
    return result;
}
```

---

## 4. Kotlin Layer

### [app/src/main/java/com/example/sentinelhard/MainActivity.kt](file:///C:/Users/praji/AndroidStudioProjects/SentinelHard/app/src/main/java/com/example/sentinelhard/MainActivity.kt)
```kotlin
package com.example.sentinelhard

import android.Manifest
import android.annotation.SuppressLint
import android.content.pm.PackageManager
import androidx.appcompat.app.AppCompatActivity
import android.os.Bundle
import android.util.Log
import android.util.Size
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.*
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.face.FaceDetection
import com.google.mlkit.vision.face.FaceDetectorOptions
import org.opencv.android.OpenCVLoader
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity() {

    private val signalState = mutableStateOf(DoubleArray(0))
    private val bpmState = mutableStateOf(0.0)
    private val snrState = mutableStateOf(0.0)
    private val isLiveState = mutableStateOf(false)
    private val bufferSizeState = mutableStateOf(0.0)
    private val isFaceDetectedState = mutableStateOf(false)

    private var lastDetectionTime = 0L
    private val FACE_LOSS_TIMEOUT_MS = 1500L

    private val livenessHistory = mutableListOf<Boolean>()
    private val LIVENESS_SMOOTHING_WINDOW = 10

    private val cameraExecutor = Executors.newSingleThreadExecutor()

    private val detector = FaceDetection.getClient(
        FaceDetectorOptions.Builder()
            .setPerformanceMode(FaceDetectorOptions.PERFORMANCE_MODE_FAST)
            .setLandmarkMode(FaceDetectorOptions.LANDMARK_MODE_ALL)
            .setContourMode(FaceDetectorOptions.CONTOUR_MODE_ALL)
            .build()
    )

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        if (isGranted) {
            // Permission granted
        } else {
            Log.e("SentinelHard", "Camera permission denied")
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        if (OpenCVLoader.initLocal()) {
            Log.i("SentinelHard", "OpenCV loaded successfully!")
        }

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            requestPermissionLauncher.launch(Manifest.permission.CAMERA)
        }

        setContent {
            MaterialTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = Color(0xFF0A0A0A)
                ) {
                    Box(modifier = Modifier.fillMaxSize()) {
                        CameraPreview(modifier = Modifier.fillMaxSize())
                        HUDOverlay()
                    }
                }
            }
        }
    }

    @Composable
    fun CameraPreview(modifier: Modifier = Modifier) {
        val context = LocalContext.current
        val lifecycleOwner = LocalLifecycleOwner.current
        val cameraProviderFuture = remember { ProcessCameraProvider.getInstance(context) }

        AndroidView(
            factory = { ctx ->
                val previewView = PreviewView(ctx)
                cameraProviderFuture.addListener({
                    val cameraProvider = cameraProviderFuture.get()
                    val preview = Preview.Builder().build().also {
                        it.setSurfaceProvider(previewView.surfaceProvider)
                    }

                    val imageAnalysis = ImageAnalysis.Builder()
                        .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                        .setTargetResolution(Size(640, 480))
                        .build()

                    imageAnalysis.setAnalyzer(cameraExecutor) { imageProxy ->
                        analyzeFrame(imageProxy)
                    }

                    val cameraSelector = CameraSelector.DEFAULT_FRONT_CAMERA

                    try {
                        cameraProvider.unbindAll()
                        val camera = cameraProvider.bindToLifecycle(
                            lifecycleOwner, cameraSelector, preview, imageAnalysis
                        )

                        camera.cameraControl.let { control ->
                            val exposureState = camera.cameraInfo.exposureState
                            if (exposureState.isExposureCompensationSupported) {
                                control.setExposureCompensationIndex(0)
                            }
                        }
                    } catch (exc: Exception) {
                        Log.e("SentinelHard", "Use case binding failed", exc)
                    }
                }, ContextCompat.getMainExecutor(context))
                previewView
            },
            modifier = modifier
        )
    }

    @Composable
    fun HUDOverlay() {
        val signalData by signalState
        val bpm by bpmState
        val snr by snrState
        val isLive by isLiveState
        val trueBufferSize by bufferSizeState
        val isFaceDetected by isFaceDetectedState

        Box(modifier = Modifier.fillMaxSize()) {
            // --- Title ---
            Text(
                text = "SENTINEL HARD",
                color = Color.White.copy(alpha = 0.9f),
                fontSize = 20.sp,
                fontWeight = FontWeight.Black,
                modifier = Modifier
                    .align(Alignment.TopCenter)
                    .padding(top = 16.dp)
            )

            if (!isFaceDetected) {
                Text(
                    text = "POSITION FACE IN FRAME",
                    color = Color.White,
                    fontSize = 18.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.align(Alignment.Center)
                )
            } else if (trueBufferSize < 150.0) {
                val progress = ((trueBufferSize / 150.0) * 100).toInt()
                Column(
                    modifier = Modifier.align(Alignment.Center),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    CircularProgressIndicator(
                        progress = (trueBufferSize / 150.0).toFloat(),
                        color = Color(0xFF00FF66),
                        strokeWidth = 8.dp,
                        modifier = Modifier.size(80.dp)
                    )
                    Spacer(modifier = Modifier.height(16.dp))
                    Text(
                        text = "ANALYZING BIOMETRICS... $progress%",
                        color = Color.Yellow,
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold
                    )
                }
            } else {
                // --- Metrics Pushed Below Title ---
                Column(
                    modifier = Modifier
                        .align(Alignment.TopStart)
                        .padding(start = 24.dp, top = 80.dp)
                ) {
                    MetricItem(label = "HEART RATE", value = "%.1f".format(bpm), unit = "BPM", color = Color(0xFF00FF66))
                    Spacer(modifier = Modifier.height(16.dp))
                    MetricItem(label = "SIGNAL SNR", value = "%.1f".format(snr), unit = "dB", color = Color(0xFF00CCFF))
                }

                Box(
                    modifier = Modifier
                        .align(Alignment.TopEnd)
                        .padding(end = 24.dp, top = 80.dp)
                        .clip(RoundedCornerShape(8.dp))
                        .background(if (isLive) Color(0xFF00FF66).copy(alpha = 0.2f) else Color.Red.copy(alpha = 0.2f))
                        .border(1.dp, if (isLive) Color(0xFF00FF66) else Color.Red, RoundedCornerShape(8.dp))
                        .padding(horizontal = 12.dp, vertical = 6.dp)
                ) {
                    Text(
                        text = if (isLive) "VERIFIED HUMAN" else "SPOOF DETECTED",
                        color = if (isLive) Color(0xFF00FF66) else Color.Red,
                        style = MaterialTheme.typography.labelLarge,
                        fontWeight = FontWeight.Bold
                    )
                }
            }

            Box(
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .padding(bottom = 48.dp)
            ) {
                PulseWaveformView(signalData = signalData)
            }
        }
    }

    @Composable
    fun MetricItem(label: String, value: String, unit: String, color: Color) {
        Column {
            Text(text = label, color = color.copy(alpha = 0.7f), fontSize = 12.sp, fontWeight = FontWeight.Bold)
            Row(verticalAlignment = Alignment.Bottom) {
                Text(text = value, color = color, fontSize = 42.sp, fontWeight = FontWeight.Black)
                Text(text = " $unit", color = color.copy(alpha = 0.7f), fontSize = 14.sp, modifier = Modifier.padding(bottom = 8.dp))
            }
        }
    }

    @Composable
    fun PulseWaveformView(signalData: DoubleArray) {
        Canvas(
            modifier = Modifier
                .fillMaxWidth()
                .height(180.dp)
                .padding(horizontal = 16.dp)
        ) {
            if (signalData.size < 2) return@Canvas

            val width = size.width
            val height = size.height
            val centerY = height / 2f

            val path = Path()
            val xStep = width / (signalData.size - 1).toFloat()

            val maxVal = signalData.maxOrNull() ?: 1.0
            val minVal = signalData.minOrNull() ?: -1.0
            val range = (maxVal - minVal).coerceAtLeast(0.001)

            signalData.forEachIndexed { index, value ->
                val x = index * xStep
                val normalized = (value - minVal) / range - 0.5
                val y = centerY - (normalized * height * 0.8f).toFloat()

                if (index == 0) {
                    path.moveTo(x, y)
                } else {
                    path.lineTo(x, y)
                }
            }

            drawPath(
                path = path,
                color = Color(0xFF00FF66),
                style = Stroke(width = 4f)
            )
        }
    }

    @SuppressLint("UnsafeOptInUsageError")
    fun analyzeFrame(imageProxy: ImageProxy) {
        val mediaImage = imageProxy.image ?: return
        val rotationDegrees = imageProxy.imageInfo.rotationDegrees
        val image = InputImage.fromMediaImage(mediaImage, rotationDegrees)

        detector.process(image)
            .addOnSuccessListener { faces ->
                if (faces.isNotEmpty()) {
                    lastDetectionTime = System.currentTimeMillis()
                    isFaceDetectedState.value = true

                    val face = faces.first()
                    val bounds = face.boundingBox

                    val roiWidth = (bounds.width() * 0.45).toInt()
                    val roiLeft = bounds.centerX() - (roiWidth / 2)
                    val roiHeight = (bounds.height() * 0.20).toInt()
                    val roiTop = bounds.top + (bounds.height() * 0.10).toInt()

                    val (mappedX, mappedY, mappedW, mappedH) = mapRoiToSensor(
                        roiLeft, roiTop, roiWidth, roiHeight,
                        imageProxy.width, imageProxy.height, rotationDegrees
                    )

                    val yuvData = yuvToByteArray(imageProxy)
                    val timestampSeconds = imageProxy.imageInfo.timestamp / 1_000_000_000.0

                    signalState.value = processFrame(
                        yuvData, imageProxy.width, imageProxy.height,
                        mappedX, mappedY, mappedW, mappedH,
                        timestampSeconds
                    )

                    val metrics = extractHeartMetrics()
                    if (metrics.size == 4) {
                        bpmState.value = metrics[0]
                        snrState.value = metrics[1]

                        // Liveness Hysteresis
                        val rawIsLive = metrics[2] > 0.5
                        livenessHistory.add(rawIsLive)
                        if (livenessHistory.size > LIVENESS_SMOOTHING_WINDOW) livenessHistory.removeAt(0)
                        isLiveState.value = livenessHistory.count { it } > (LIVENESS_SMOOTHING_WINDOW / 2)

                        bufferSizeState.value = metrics[3]
                    }
                } else {
                    if (System.currentTimeMillis() - lastDetectionTime > FACE_LOSS_TIMEOUT_MS) {
                        if (isFaceDetectedState.value) {
                            resetBuffers()
                            livenessHistory.clear()
                            isFaceDetectedState.value = false
                            bpmState.value = 0.0
                            snrState.value = 0.0
                            isLiveState.value = false
                            bufferSizeState.value = 0.0
                            signalState.value = DoubleArray(0)
                        }
                    }
                }
            }
            .addOnCompleteListener {
                imageProxy.close()
            }
    }

    private fun mapRoiToSensor(
        x: Int, y: Int, w: Int, h: Int,
        imgW: Int, imgH: Int, rotation: Int
    ): IntArray {
        return when (rotation) {
            90 -> intArrayOf(y, imgW - x - w, h, w)
            180 -> intArrayOf(imgW - x - w, imgH - y - h, w, h)
            270 -> intArrayOf(imgH - y - h, x, h, w)
            else -> intArrayOf(x, y, w, h)
        }
    }

    private fun yuvToByteArray(image: ImageProxy): ByteArray {
        val yBuffer = image.planes[0].buffer
        val uBuffer = image.planes[1].buffer
        val vBuffer = image.planes[2].buffer

        val ySize = yBuffer.remaining()
        val uSize = uBuffer.remaining()
        val vSize = vBuffer.remaining()

        val nv21 = ByteArray(ySize + uSize + vSize)

        yBuffer.get(nv21, 0, ySize)
        vBuffer.get(nv21, ySize, vSize)
        uBuffer.get(nv21, ySize + vSize, uSize)

        return nv21
    }

    companion object {
        init {
            System.loadLibrary("sentinelhard")
        }
    }

    external fun processFrame(
        yuvData: ByteArray, width: Int, height: Int,
        roiX: Int, roiY: Int, roiW: Int, roiH: Int,
        timestampSeconds: Double
    ): DoubleArray

    external fun extractHeartMetrics(): DoubleArray

    external fun resetBuffers()
}
```
