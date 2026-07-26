#include <jni.h>
#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include <android/log.h>
#include <vector>
#include <deque>
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
const int FFT_SIZE = 1024; // Zero-padded FFT: ~1.76 BPM/bin resolution at 30 Hz

// --- Confidence Engine Weights (must sum to 1.0) ---
const double WEIGHT_TEXTURE     = 0.30;
const double WEIGHT_QR          = 0.30;
const double WEIGHT_CORRELATION = 0.20;
const double WEIGHT_HRV         = 0.20;

// --- Confidence Engine Thresholds ---
const double SHARPNESS_MIN   = 30.0;   // Below: too smooth (screen/print spoof)
const double SHARPNESS_MAX   = 500.0;  // Above: saturated (glare/overexposure)
const double QR_SCORE_MIN    = 0.8;    // SNR lower bound for full QR score
const double QR_SCORE_MAX    = 1.6;    // SNR upper bound for full QR score
const double CORR_SCORE_MIN  = 0.90;   // Correlation lower bound
const double CORR_SCORE_MAX  = 0.98;   // Correlation upper bound (screen flicker threshold)
const double HRV_STD_TARGET  = 0.3;    // Target BPM std-dev for max HRV liveness score
const double EMA_SLOW        = 0.90;   // Confidence EMA slow factor
const double EMA_FAST        = 0.10;   // Confidence EMA fast factor

// --- Hysteresis Dead-Band (Schmitt Trigger — preserves anti-flicker behaviour) ---
const double HYSTERESIS_HUMAN_ENTER  = 0.65; // ANALYZING → HUMAN
const double HYSTERESIS_HUMAN_LEAVE  = 0.60; // HUMAN → ANALYZING
const double HYSTERESIS_SPOOF_ENTER  = 0.45; // ANALYZING → SPOOF
const double HYSTERESIS_SPOOF_LEAVE  = 0.50; // SPOOF → ANALYZING

// --- Signal Processing Utilities ---

struct SignalSample {
    double timestamp; // in seconds
    double value;     // channel mean
};

// --- Helper Functions ---
double calculateMean(const std::vector<double>& data) {
    if (data.empty()) return 0.0;
    double sum = std::accumulate(data.begin(), data.end(), 0.0);
    return sum / data.size();
}

double calculateStdDev(const std::vector<double>& data, double mean) {
    if (data.empty()) return 0.0;
    double variance = 0.0;
    for (double val : data) {
        variance += (val - mean) * (val - mean);
    }
    return std::sqrt(variance / data.size());
}

// Applies a zero-phase moving average subtraction to center the signal
void applyFIRDetrending(const std::vector<double>& posSignal, std::vector<double>& outDetrended) {
    size_t N = posSignal.size();
    outDetrended.resize(N, 0.0);

    // 1-second moving average window (assuming ~30 FPS)
    int windowSize = 30;

    for (size_t i = 0; i < N; ++i) {
        double sum = 0.0;
        int count = 0;

        // Calculate the local baseline (moving average)
        int startIdx = std::max(0, static_cast<int>(i) - windowSize / 2);
        int endIdx = std::min(static_cast<int>(N) - 1, static_cast<int>(i) + windowSize / 2);

        for (int j = startIdx; j <= endIdx; ++j) {
            sum += posSignal[j];
            count++;
        }

        double localMean = sum / count;

        // Detrend: Subtract baseline from the actual signal
        outDetrended[i] = posSignal[i] - localMean;
    }
}

// Global / Persistent state
static std::vector<SignalSample> g_redBuffer;
static std::vector<SignalSample> g_greenBuffer;
static std::vector<SignalSample> g_blueBuffer;

static std::vector<double> g_redClean;
static std::vector<double> g_greenClean;
static std::vector<double> g_blueClean;

// Cached detrended POS signal — computed once per frame in processFrame, reused by extractVitals
static std::vector<double> g_cachedDetrendedPOS;

// Kalman Filter State
static double g_kalmanBpm = 75.0; // Initial state estimate
static double g_kalmanCovariance = 10.0;
const double PROCESS_NOISE = 0.05; // How fast HR can change

// Multi-Modal Anti-Spoofing State
static std::deque<double> g_bpmHistory;
static double g_lastSharpness = 0.0;
static double g_smoothedConfidence = 0.5;

double computeStdDev(const std::deque<double>& data) {
    if (data.empty()) return 0.0;
    double sum = std::accumulate(data.begin(), data.end(), 0.0);
    double mean = sum / (double)data.size();
    double sq_sum = std::inner_product(data.begin(), data.end(), data.begin(), 0.0);
    double variance = (sq_sum / (double)data.size()) - (mean * mean);
    return std::sqrt(std::max(0.0, variance));
}

static const double WINDOW_DURATION = 5.0;   // 5-second sliding window
static const double TARGET_FS = 30.0;         // Resample target: 30 Hz
static const double TARGET_DT = 1.0 / TARGET_FS;

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

// POS (Plane-Orthogonal-to-Skin) Engine
void applyPOS(const std::vector<double>& bufferR,
              const std::vector<double>& bufferG,
              const std::vector<double>& bufferB,
              std::vector<double>& outSignal) {

    size_t N = bufferR.size();
    if (N == 0) return;
    outSignal.resize(N);

    double meanR = calculateMean(bufferR);
    double meanG = calculateMean(bufferG);
    double meanB = calculateMean(bufferB);

    std::vector<double> X(N, 0.0);
    std::vector<double> Y(N, 0.0);

    for (size_t i = 0; i < N; ++i) {
        double normR = bufferR[i] / (meanR + 1e-6);
        double normG = bufferG[i] / (meanG + 1e-6);
        double normB = bufferB[i] / (meanB + 1e-6);

        X[i] = normG - normB;
        Y[i] = normG + normB - (2.0 * normR);
    }

    double meanX = calculateMean(X);
    double meanY = calculateMean(Y);
    double stdX = calculateStdDev(X, meanX);
    double stdY = calculateStdDev(Y, meanY);

    double alpha = stdX / (stdY + 1e-6);

    for (size_t i = 0; i < N; ++i) {
        outSignal[i] = X[i] + (alpha * Y[i]);
    }
}

// Anti-Spoofing: Correlation Check
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
    // Increased threshold for higher noise tolerance
    return correlation > 0.98;
}

// Adaptive 1D Kalman Filter for BPM stabilization
double applyKalmanStabilization(double rawBpm, double qualityRatio) {
    if (qualityRatio < 1.0) {
        return g_kalmanBpm;
    }

    double pPredict = g_kalmanCovariance + PROCESS_NOISE;
    double measurementNoise = 20.0 / (qualityRatio * qualityRatio);
    double K = pPredict / (pPredict + measurementNoise);

    g_kalmanBpm = g_kalmanBpm + K * (rawBpm - g_kalmanBpm);
    g_kalmanCovariance = (1.0 - K) * pPredict;

    return g_kalmanBpm;
}

// Heart Rate Extraction with POS and FIR Detrending
std::vector<double> extractVitals() {
    // Use the cached detrended POS signal (populated by processFrame each frame)
    // This avoids recomputing POS + FIR detrending redundantly.
    if (g_cachedDetrendedPOS.size() < 150) return {0.0, 0.0, 0.0};

    // Apply Hamming window to the last 150 samples of the cached detrended signal
    const size_t N = 150;
    const size_t startIdx = g_cachedDetrendedPOS.size() - N;
    std::vector<double> processedSignal(N);

    for (size_t i = 0; i < N; ++i) {
        double multiplier = 0.54 - 0.46 * cos(2.0 * PI_VAL * i / (N - 1)); // Hamming window
        processedSignal[i] = g_cachedDetrendedPOS[startIdx + i] * multiplier;
    }

    // 3. SIGNAL POWER check
    double powerSum = 0.0;
    for (double val : processedSignal) powerSum += (val * val);
    double signalPower = std::sqrt(powerSum / N);

    if (signalPower < 0.001) {
        LOGI("Spoof: Signal Power too low (%.6f)", signalPower);
        return {0.0, 0.0, 0.0};
    }

    // 4. Correlation Check (isFlicker return value unused; correlation out-param is what matters)
    double correlation = 0.0;
    isScreenFlicker(g_greenClean, g_redClean, &correlation);

    // 5. FFT-BASED SPECTRAL ANALYSIS — O(N log N), zero-padded to FFT_SIZE for ~1.76 BPM/bin resolution
    cv::Mat fftInput = cv::Mat::zeros(1, FFT_SIZE, CV_64F);
    for (size_t i = 0; i < N; ++i) {
        fftInput.at<double>(0, (int)i) = processedSignal[i];
    }
    cv::Mat fftOutput;
    cv::dft(fftInput, fftOutput, cv::DFT_COMPLEX_OUTPUT);

    const double FREQ_RES = TARGET_FS / (double)FFT_SIZE; // Hz per bin (~0.0293 Hz for 1024-pt)
    const int FFT_BINS = FFT_SIZE / 2 + 1;                // unique bins for real-valued input

    std::vector<double> power_spectrum(FFT_BINS, 0.0);
    for (int bin = 0; bin < FFT_BINS; ++bin) {
        cv::Vec2d c = fftOutput.at<cv::Vec2d>(0, bin);
        power_spectrum[bin] = c[0] * c[0] + c[1] * c[1];
    }

    // Identify cardiac band and peak within it
    const int binMin = (int)std::ceil(MIN_BPM / 60.0 / FREQ_RES);
    const int binMax = std::min((int)std::floor(MAX_BPM / 60.0 / FREQ_RES), FFT_BINS - 1);

    double max_power = 0.0;
    int peakBin = binMin;
    for (int bin = binMin; bin <= binMax; ++bin) {
        if (power_spectrum[bin] > max_power) {
            max_power = power_spectrum[bin];
            peakBin = bin;
        }
    }

    // 6. Quality Ratio (SNR) — peak vs mean non-peak bins within cardiac band
    //    Uses same in-band semantics as original DTFT SNR, so existing thresholds remain valid.
    double noiseSum = 0.0;
    int noiseCount = 0;
    for (int bin = binMin; bin <= binMax; ++bin) {
        if (bin != peakBin) {
            noiseSum += power_spectrum[bin];
            noiseCount++;
        }
    }
    double qualityRatio = max_power / ((noiseCount > 0 ? noiseSum / noiseCount : 1.0) + 1e-6);

    // 7. Sub-bin BPM precision via quadratic interpolation
    double exactPeakBpm = peakBin * FREQ_RES * 60.0;
    if (peakBin > binMin && peakBin < binMax) {
        double y1 = power_spectrum[peakBin - 1], y2 = power_spectrum[peakBin], y3 = power_spectrum[peakBin + 1];
        double den = y1 - 2.0 * y2 + y3;
        if (std::abs(den) > 1e-5) {
            exactPeakBpm += 0.5 * (y1 - y3) / den * FREQ_RES * 60.0;
        }
    }

    // 8. HRV Check
    g_bpmHistory.push_back(exactPeakBpm);
    if (g_bpmHistory.size() > 10) g_bpmHistory.pop_front();
    double bpmStdDev = computeStdDev(g_bpmHistory);

    // 9. WEIGHTED CONFIDENCE ENGINE
    double confidence = 0.0;

    // Texture Score
    double textureScore = 1.0;
    if (g_lastSharpness < SHARPNESS_MIN) textureScore = g_lastSharpness / SHARPNESS_MIN;
    else if (g_lastSharpness > SHARPNESS_MAX) textureScore = std::max(0.0, 1.0 - (g_lastSharpness - SHARPNESS_MAX) / SHARPNESS_MAX);
    confidence += WEIGHT_TEXTURE * std::clamp(textureScore, 0.0, 1.0);

    // QR (SNR) Score
    double qrScore = std::clamp((qualityRatio - QR_SCORE_MIN) / (QR_SCORE_MAX - QR_SCORE_MIN), 0.0, 1.0);
    confidence += WEIGHT_QR * qrScore;

    // Correlation Score
    double corrScore = std::clamp(1.0 - (correlation - CORR_SCORE_MIN) / (CORR_SCORE_MAX - CORR_SCORE_MIN), 0.0, 1.0);
    confidence += WEIGHT_CORRELATION * corrScore;

    // HRV Score
    double hrvScore = (g_bpmHistory.size() < 10) ? 0.5 : std::clamp(bpmStdDev / HRV_STD_TARGET, 0.0, 1.0);
    confidence += WEIGHT_HRV * hrvScore;

    // Temporal Confidence Smoothing (EMA)
    g_smoothedConfidence = EMA_SLOW * g_smoothedConfidence + EMA_FAST * confidence;

    // --- Bug 4 Fix: Hysteresis Dead-Band ---
    static double prev_status = 1.0;
    double status = 1.0; // ANALYZING

    if (prev_status == 2.0) {
        // Must drop below HYSTERESIS_HUMAN_LEAVE to exit HUMAN state
        status = (g_smoothedConfidence < HYSTERESIS_HUMAN_LEAVE) ? 1.0 : 2.0;
    } else if (prev_status == 0.0) {
        // Must rise above HYSTERESIS_SPOOF_LEAVE to exit SPOOF state
        status = (g_smoothedConfidence > HYSTERESIS_SPOOF_LEAVE) ? 1.0 : 0.0;
    } else {
        // Entering from ANALYZING
        if (g_smoothedConfidence > HYSTERESIS_HUMAN_ENTER) status = 2.0;
        else if (g_smoothedConfidence < HYSTERESIS_SPOOF_ENTER) status = 0.0;
    }
    prev_status = status;

    LOGI("Vitals: Conf=%.2f (Smoothed=%.2f) | QR=%.2f | BPM=%.1f | Status=%.0f",
         confidence, g_smoothedConfidence, qualityRatio, exactPeakBpm, status);

    double smoothedBpm = applyKalmanStabilization(exactPeakBpm, qualityRatio);

    return {smoothedBpm, qualityRatio, status};
}

// JNI Implementations
extern "C" JNIEXPORT void JNICALL
Java_com_example_sentinelhard_MainActivity_resetBuffers(JNIEnv *env, jobject /* thiz */) {
    g_redBuffer.clear(); g_greenBuffer.clear(); g_blueBuffer.clear();
    g_redClean.clear(); g_greenClean.clear(); g_blueClean.clear();
    g_cachedDetrendedPOS.clear();
    g_bpmHistory.clear();
    g_kalmanBpm = 75.0; g_kalmanCovariance = 10.0;
    g_smoothedConfidence = 0.5;
    LOGI("State Reset");
}

extern "C" JNIEXPORT jdoubleArray JNICALL
Java_com_example_sentinelhard_MainActivity_processFrame(
        JNIEnv *env, jobject /* thiz */, jbyteArray yuvData,
        jint width, jint height, jint roiX, jint roiY, jint roiW, jint roiH,
        jdouble timestampSeconds) {

    jbyte *yuv_ptr = env->GetByteArrayElements(yuvData, nullptr);
    cv::Mat mYuv(height + height / 2, width, CV_8UC1, (unsigned char *)yuv_ptr);
    cv::Mat mRgb;
    cv::cvtColor(mYuv, mRgb, cv::COLOR_YUV2RGB_NV21);

    cv::Rect safeRoi(roiX, roiY, roiW, roiH);
    safeRoi &= cv::Rect(0, 0, mRgb.cols, mRgb.rows);

    double rMean = 0, gMean = 0, bMean = 0;
    if (safeRoi.width > 0 && safeRoi.height > 0) {
        cv::Mat roi = mRgb(safeRoi);

        // Laplacian Texture Check — variance of Laplacian as sharpness score
        cv::Mat gray, lap;
        cv::cvtColor(roi, gray, cv::COLOR_RGB2GRAY);
        cv::Laplacian(gray, lap, CV_64F);
        cv::Scalar mL, sL;
        cv::meanStdDev(lap, mL, sL);
        g_lastSharpness = sL[0] * sL[0];

        // Adaptive Glare Masking
        double rS = 0, gS = 0, bS = 0;
        int valid = 0;
        for (int y = 0; y < roi.rows; ++y) {
            const cv::Vec3b* p = roi.ptr<cv::Vec3b>(y);
            for (int x = 0; x < roi.cols; ++x) {
                if (p[x][2] > 240 || p[x][1] > 240 || p[x][0] > 240) continue;
                int maxC = std::max({p[x][0], p[x][1], p[x][2]});
                int minC = std::min({p[x][0], p[x][1], p[x][2]});
                if (maxC > 180 && (maxC - minC) < 15) continue;
                rS += p[x][2]; gS += p[x][1]; bS += p[x][0];
                valid++;
            }
        }
        if (valid > 0) {
            rMean = rS / valid; gMean = gS / valid; bMean = bS / valid;
        } else {
            cv::Scalar m = cv::mean(roi);
            rMean = m[2]; gMean = m[1]; bMean = m[0];
        }
    }
    env->ReleaseByteArrayElements(yuvData, yuv_ptr, JNI_ABORT);

    g_redBuffer.push_back({timestampSeconds, rMean});
    g_greenBuffer.push_back({timestampSeconds, gMean});
    g_blueBuffer.push_back({timestampSeconds, bMean});

    double cutoff = timestampSeconds - WINDOW_DURATION;
    auto purge = [cutoff](const SignalSample& s) { return s.timestamp < cutoff; };
    g_redBuffer.erase(std::remove_if(g_redBuffer.begin(), g_redBuffer.end(), purge), g_redBuffer.end());
    g_greenBuffer.erase(std::remove_if(g_greenBuffer.begin(), g_greenBuffer.end(), purge), g_greenBuffer.end());
    g_blueBuffer.erase(std::remove_if(g_blueBuffer.begin(), g_blueBuffer.end(), purge), g_blueBuffer.end());

    if (g_greenBuffer.size() > 2) {
        std::vector<double> uR = resampleToUniform(g_redBuffer);
        std::vector<double> uG = resampleToUniform(g_greenBuffer);
        std::vector<double> uB = resampleToUniform(g_blueBuffer);
        if (!uR.empty()) {
            g_redClean = uR; g_greenClean = uG; g_blueClean = uB;
        }
    }

    // Compute and cache the detrended POS signal — used by both visualization and extractVitals.
    // Doing it here once eliminates the redundant computation in extractVitals.
    if (g_redClean.size() >= 150) {
        std::vector<double> rawPos;
        applyPOS(g_redClean, g_greenClean, g_blueClean, rawPos);
        applyFIRDetrending(rawPos, g_cachedDetrendedPOS);
    }

    // Return last 150 samples for waveform visualization
    std::vector<double> visSignal;
    if (g_cachedDetrendedPOS.size() >= 150) {
        size_t start = g_cachedDetrendedPOS.size() - 150;
        visSignal.assign(g_cachedDetrendedPOS.begin() + start, g_cachedDetrendedPOS.end());
    }

    jdoubleArray res = env->NewDoubleArray(visSignal.size());
    env->SetDoubleArrayRegion(res, 0, visSignal.size(), visSignal.data());
    return res;
}

extern "C" JNIEXPORT jdoubleArray JNICALL
Java_com_example_sentinelhard_MainActivity_extractHeartMetrics(JNIEnv *env, jobject /* thiz */) {
    std::vector<double> v = extractVitals();
    double current_size = static_cast<double>(g_greenClean.size());
    std::vector<double> m = {v[0], v[1], v[2], current_size};
    jdoubleArray res = env->NewDoubleArray(4);
    env->SetDoubleArrayRegion(res, 0, 4, m.data());
    return res;
}
