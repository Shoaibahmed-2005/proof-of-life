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

// Resample non-uniform buffer to uniform 30 Hz grid with rigid loop
std::vector<double> resampleToUniform(const std::vector<SignalSample>& buffer) {
    std::vector<double> uniformSignal;
    if (buffer.size() < 2) return uniformSignal;

    double tStart = buffer.front().timestamp;
    double tEnd = buffer.back().timestamp;

    int totalSamples = static_cast<int>(std::floor((tEnd - tStart) / TARGET_DT));
    size_t sampleIdx = 0;

    for (int i = 0; i <= totalSamples; ++i) {
        double t = tStart + (i * TARGET_DT);
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
    return correlation > 0.95;
}

// --- Heart Rate Extraction Math ---

std::vector<double> extractVitals(const std::vector<double>& signal, const std::vector<double>& green, const std::vector<double>& red) {
    if (signal.size() < 150) {
        return {0.0, 0.0, 0.0};
    }

    // 1. JS LOGIC: SIGNAL POWER (Static Image Check)
    double powerSum = 0.0;
    for (double val : signal) {
        powerSum += (val * val);
    }
    double signalPower = std::sqrt(powerSum / static_cast<double>(signal.size()));

    // Threshold lowered for Ratiometric signal (G/(R+B) is much smaller than raw pixels)
    if (signalPower < 0.001) {
        LOGI("Spoof: Signal Power too low (%.6f)", signalPower);
        return {0.0, 0.0, 0.0};
    }

    // 2. Correlation Check (Multi-layer defense)
    double correlation = 0.0;
    if (isScreenFlicker(green, red, &correlation)) {
        LOGI("Spoof: High Correlation (%.2f)", correlation);
        return {0.0, -10.0, 0.0};
    }

    int N = 150;
    size_t startIdx = signal.size() - 150;

    std::vector<double> windowedSignal(N);
    for (int i = 0; i < N; ++i) {
        double multiplier = 0.54 - 0.46 * cos(2.0 * PI_VAL * i / (N - 1));
        windowedSignal[i] = signal[startIdx + i] * multiplier;
    }

    std::vector<double> power_spectrum(MAX_BPM - MIN_BPM + 1, 0.0);
    double max_power = 0.0;
    int peakIndex = -1;

    for (int bpm = (int)MIN_BPM; bpm <= (int)MAX_BPM; ++bpm) {
        double f = bpm / 60.0;
        double sum_real = 0.0;
        double sum_imag = 0.0;
        for (int n = 0; n < N; ++n) {
            double angle = -2.0 * PI_VAL * f * (n / TARGET_FS);
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

    // 3. JS LOGIC: PEAK-TO-NOISE RATIO (Video Screen Check)
    double noiseSum = 0.0;
    int noiseCount = 0;
    for (int i = 0; i < (int)power_spectrum.size(); i++) {
        if (i != peakIndex) {
            noiseSum += power_spectrum[i];
            noiseCount++;
        }
    }
    double avgNoise = (noiseCount > 0) ? (noiseSum / noiseCount) : 1e-6;
    double qualityRatio = max_power / avgNoise;

    // Threshold lowered for noisy mobile front cameras
    if (qualityRatio < 1.2) {
        LOGI("Spoof: Quality Ratio too low (%.2f) | Power: %.6f", qualityRatio, signalPower);
        return {0.0, qualityRatio, 0.0};
    }

    // 4. Quadratic Peak Interpolation
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

    return {exactPeakBpm, qualityRatio, 1.0};
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
        metrics[1] = vitals[1]; // Quality Ratio
        metrics[2] = vitals[2]; // Liveness
    }

    jdoubleArray result = env->NewDoubleArray(4);
    env->SetDoubleArrayRegion(result, 0, 4, metrics.data());
    return result;
}
