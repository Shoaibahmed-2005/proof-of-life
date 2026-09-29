// JNI layer for the rPPG engine (see rppg_core.h for the signal pipeline).
//
// Kotlin side: com.example.sentinelhard.rppg.RppgNative (a Kotlin `object`,
// so every function receives the singleton instance as `thiz`).
//
// nativeProcessFrame reads the camera's Y/U/V planes directly (direct
// ByteBuffers, no copy) and only touches pixels inside the face ROIs.
// It returns a DoubleArray:
//   [0] bpm (median of recent estimates)   [1] latest estimate
//   [2] SNR dB (latest)                    [3] median SNR dB
//   [4] window fill 0..1                   [5] stable (0/1)
//   [6] new estimate this frame (0/1)      [7] estimates since reset
//   [8] samples in window                  [9] frame had usable face pixels (0/1)
//   [10] skin fraction                     [11] pixels used
//   [12] BPM spread of recent estimates     [13] minimum SNR in use (dB)
//   [14] face brightness (luma 0-255)       [15] window-full gate (0/1)
//   [16] readings-agree gate (0/1)          [17] SNR gate (0/1)
//   [18...] waveform (band-passed pulse, scaled to [-1, 1])

#include <jni.h>
#include <android/log.h>

#include <mutex>
#include <vector>

#include "rppg_core.h"

#define LOG_TAG "SentinelHardNative"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)

namespace {

constexpr int kHeaderSize = 18;
constexpr int kMaxRois = 8;

std::mutex g_lock;
rppg::Engine g_engine;

jdoubleArray toJava(JNIEnv* env, const std::vector<double>& values) {
    const jsize n = static_cast<jsize>(values.size());
    jdoubleArray out = env->NewDoubleArray(n);
    if (out != nullptr && n > 0) env->SetDoubleArrayRegion(out, 0, n, values.data());
    return out;
}

rppg::PlaneView planeView(JNIEnv* env, jobject buffer, jint rowStride, jint pixelStride) {
    rppg::PlaneView view{nullptr, 0, rowStride, pixelStride};
    if (buffer == nullptr) return view;
    void* address = env->GetDirectBufferAddress(buffer);
    const jlong capacity = env->GetDirectBufferCapacity(buffer);
    if (address != nullptr && capacity > 0) {
        view.data = static_cast<const uint8_t*>(address);
        view.size = static_cast<size_t>(capacity);
    }
    return view;
}

}  // namespace

extern "C" JNIEXPORT void JNICALL
Java_com_example_sentinelhard_rppg_RppgNative_nativeConfigure(
        JNIEnv* /* env */, jobject /* thiz */,
        jdouble minSnrDb, jdouble windowSec, jint stableCount, jdouble stableToleranceBpm) {
    std::lock_guard<std::mutex> lock(g_lock);
    rppg::Config cfg;
    cfg.minSnrDb = minSnrDb;
    if (windowSec >= 6.0 && windowSec <= 20.0) cfg.windowSec = windowSec;
    if (stableCount >= 2 && stableCount <= 20) cfg.stableCount = stableCount;
    if (stableToleranceBpm > 0.0) cfg.stableToleranceBpm = stableToleranceBpm;
    g_engine.configure(cfg);
    LOGI("configured: minSnr=%.1f dB window=%.1f s stable=%d estimates within ±%.1f BPM",
         cfg.minSnrDb, cfg.windowSec, cfg.stableCount, cfg.stableToleranceBpm);
}

extern "C" JNIEXPORT void JNICALL
Java_com_example_sentinelhard_rppg_RppgNative_nativeReset(JNIEnv* /* env */, jobject /* thiz */) {
    std::lock_guard<std::mutex> lock(g_lock);
    g_engine.reset();
    LOGI("reset");
}

extern "C" JNIEXPORT jdoubleArray JNICALL
Java_com_example_sentinelhard_rppg_RppgNative_nativeProcessFrame(
        JNIEnv* env, jobject /* thiz */,
        jobject yBuffer, jobject uBuffer, jobject vBuffer,
        jint width, jint height,
        jint yRowStride, jint yPixelStride, jint uvRowStride, jint uvPixelStride,
        jintArray rois, jdouble timestampSeconds) {
    // ROIs arrive as a flat [x, y, w, h, x, y, w, h, ...] array in sensor coordinates.
    rppg::Roi roiList[kMaxRois];
    int nRois = 0;
    if (rois != nullptr) {
        const jsize len = env->GetArrayLength(rois);
        jint flat[kMaxRois * 4];
        const jsize count = len / 4 > kMaxRois ? kMaxRois : len / 4;
        if (count > 0) {
            env->GetIntArrayRegion(rois, 0, count * 4, flat);
            for (jsize i = 0; i < count; ++i) {
                roiList[nRois++] = {flat[4 * i], flat[4 * i + 1], flat[4 * i + 2], flat[4 * i + 3]};
            }
        }
    }

    const rppg::PlaneView y = planeView(env, yBuffer, yRowStride, yPixelStride);
    const rppg::PlaneView u = planeView(env, uBuffer, uvRowStride, uvPixelStride);
    const rppg::PlaneView v = planeView(env, vBuffer, uvRowStride, uvPixelStride);
    const rppg::RgbMean mean = rppg::meanSkinRgb(y, u, v, width, height, roiList, nRois);

    std::lock_guard<std::mutex> lock(g_lock);
    if (mean.valid) g_engine.addSample(timestampSeconds, mean.r, mean.g, mean.b);
    const rppg::Status s = g_engine.update();

    if (s.newEstimate) {
        LOGI("estimate #%d: bpm=%.1f (latest %.1f, spread %.1f) snr=%.1f dB (median %.1f) fill=%.2f "
             "gates[window=%d agree=%d snr=%d] stable=%d skin=%.2f luma=%.0f px=%d",
             s.estimateCount, s.bpm, s.latestBpm, s.spreadBpm, s.snrDb, s.medianSnrDb, s.windowFill,
             s.windowOk ? 1 : 0, s.agreeOk ? 1 : 0, s.snrOk ? 1 : 0, s.stable ? 1 : 0,
             mean.skinFraction, mean.luma, mean.pixels);
    }

    std::vector<double> out = {
        s.bpm, s.latestBpm, s.snrDb, s.medianSnrDb, s.windowFill,
        s.stable ? 1.0 : 0.0, s.newEstimate ? 1.0 : 0.0,
        static_cast<double>(s.estimateCount), static_cast<double>(s.samplesInWindow),
        mean.valid ? 1.0 : 0.0, mean.skinFraction, static_cast<double>(mean.pixels),
        s.spreadBpm, g_engine.config().minSnrDb, mean.luma,
        s.windowOk ? 1.0 : 0.0, s.agreeOk ? 1.0 : 0.0, s.snrOk ? 1.0 : 0.0,
    };
    static_assert(kHeaderSize == 18, "keep in sync with RppgResult.HEADER_SIZE");
    const std::vector<double>& wave = g_engine.waveform();
    out.insert(out.end(), wave.begin(), wave.end());
    return toJava(env, out);
}
