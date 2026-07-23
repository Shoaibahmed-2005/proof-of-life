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

// --- Signal Processing Utilities ---

struct SignalSample {
    double timestamp; // in seconds
    double value;     // raw green channel mean
};

class BiquadFilter {
private:
    double b0, b1, b2, a1, a2;
    double x1 = 0.0, x2 = 0.0;
    double y1 = 0.0, y2 = 0.0;

public:
    BiquadFilter(double b0, double b1, double b2, double a1, double a2)
        : b0(b0), b1(b1), b2(b2), a1(a1), a2(a2) {}

    double process(double input) {
        double output = b0 * input + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
        x2 = x1;
        x1 = input;
        y2 = y1;
        y1 = output;
        return output;
    }
};

// Global / Persistent state
static std::vector<SignalSample> g_sampleBuffer;
static std::vector<double> g_filteredSignal; // History for UI and DSP
static const double WINDOW_DURATION = 5.0;   // 5-second sliding window
static const double TARGET_FS = 30.0;         // Resample target: 30 Hz
static const double TARGET_DT = 1.0 / TARGET_FS;

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

// --- Phase 4: Heart Rate Extraction Math ---

std::vector<double> extractVitals(const std::vector<double>& signal) {
    if (signal.size() < 150) {
        return {0.0, 0.0, 0.0}; // Not enough data yet
    }

    int N = signal.size();
    double max_power = 0.0;
    double peak_bpm = 0.0;

    // Store power for each BPM to calculate SNR later
    std::vector<double> power_spectrum(MAX_BPM - MIN_BPM + 1, 0.0);

    // 1. Calculate DTFT Power Spectrum
    for (int bpm = (int)MIN_BPM; bpm <= (int)MAX_BPM; ++bpm) {
        double f = bpm / 60.0; // Convert BPM to Hz
        double sum_real = 0.0;
        double sum_imag = 0.0;

        for (int n = 0; n < N; ++n) {
            double angle = -2.0 * M_PI * f * (n / FPS);
            sum_real += signal[n] * cos(angle);
            sum_imag += signal[n] * sin(angle);
        }

        double power = (sum_real * sum_real) + (sum_imag * sum_imag);
        power_spectrum[bpm - (int)MIN_BPM] = power;

        if (power > max_power) {
            max_power = power;
            peak_bpm = (double)bpm;
        }
    }

    // 2. Calculate Liveness SNR
    double signal_power = 0.0;
    double noise_power = 0.0;

    // Define the "Signal" band as +/- 3 BPM around the peak
    for (int bpm = (int)MIN_BPM; bpm <= (int)MAX_BPM; ++bpm) {
        if (std::abs(bpm - peak_bpm) <= 3.0) {
            signal_power += power_spectrum[bpm - (int)MIN_BPM];
        } else {
            noise_power += power_spectrum[bpm - (int)MIN_BPM];
        }
    }

    // Protect against divide-by-zero
    noise_power = std::max(noise_power, 0.0001);
    double snr = 10.0 * log10(signal_power / noise_power); // Standard SNR in dB

    // 3. Determine Liveness
    // A clean pulse usually scores above 3.0 dB.
    double is_live = (snr > 3.0) ? 1.0 : 0.0;

    return {peak_bpm, snr, is_live};
}

// --- JNI Implementation ---

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

    double greenChannelAvg = 0.0;
    if (safeRoi.width > 0 && safeRoi.height > 0) {
        cv::Mat skinRegion = mRgb(safeRoi);
        cv::Scalar means = cv::mean(skinRegion);
        greenChannelAvg = means[1];
    }
    env->ReleaseByteArrayElements(yuvData, yuv_ptr, JNI_ABORT);

    g_sampleBuffer.push_back({timestampSeconds, greenChannelAvg});

    double cutoffTime = timestampSeconds - WINDOW_DURATION;
    g_sampleBuffer.erase(
        std::remove_if(g_sampleBuffer.begin(), g_sampleBuffer.end(),
                       [cutoffTime](const SignalSample& s) { return s.timestamp < cutoffTime; }),
        g_sampleBuffer.end()
    );

    static BiquadFilter filter(0.1, 0.0, -0.1, -1.8, 0.85);

    if (g_sampleBuffer.back().timestamp - g_sampleBuffer.front().timestamp >= 1.0) {
        std::vector<double> uniformSignal = resampleToUniform(g_sampleBuffer);
        if (!uniformSignal.empty()) {
            double cleanSample = filter.process(uniformSignal.back());
            g_filteredSignal.push_back(cleanSample);

            if (g_filteredSignal.size() > 150) {
                g_filteredSignal.erase(g_filteredSignal.begin());
            }
        }
    }

    size_t numPoints = g_filteredSignal.size();
    jdoubleArray result = env->NewDoubleArray(numPoints);
    if (numPoints > 0) {
        env->SetDoubleArrayRegion(result, 0, (jsize)numPoints, g_filteredSignal.data());
    }

    return result;
}

extern "C" JNIEXPORT jdoubleArray JNICALL
Java_com_example_sentinelhard_MainActivity_extractHeartMetrics(
        JNIEnv *env, jobject /* thiz */) {

    std::vector<double> metrics = extractVitals(g_filteredSignal);

    jdoubleArray result = env->NewDoubleArray(3);
    env->SetDoubleArrayRegion(result, 0, 3, metrics.data());

    return result;
}
