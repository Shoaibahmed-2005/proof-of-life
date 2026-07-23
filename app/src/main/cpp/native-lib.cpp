#include <jni.h>
#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include <android/log.h>

#define LOG_TAG "SentinelHardNative"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)

extern "C"
JNIEXPORT jdouble JNICALL
Java_com_example_sentinelhard_MainActivity_processFrame(
        JNIEnv *env,
        jobject /* this */,
        jbyteArray yuvData,
        jint width,
        jint height,
        jint roiX,
        jint roiY,
        jint roiW,
        jint roiH) {

    // 1. Map memory without copying
    jbyte *yuv_ptr = env->GetByteArrayElements(yuvData, nullptr);

    // An Android YUV NV21 frame requires height + (height/2) for the buffer
    cv::Mat mYuv(height + height / 2, width, CV_8UC1, (unsigned char *)yuv_ptr);

    // 2. Convert to standard RGB space
    cv::Mat mRgb;
    cv::cvtColor(mYuv, mRgb, cv::COLOR_YUV2RGB_NV21);

    // 3. Construct a safe bounding box (preventing out-of-bounds crashes)
    cv::Rect safeRoi(roiX, roiY, roiW, roiH);
    safeRoi &= cv::Rect(0, 0, mRgb.cols, mRgb.rows);

    // Logging to verify alignment as requested
    LOGI("Frame Dim: %dx%d | ROI: x=%d, y=%d, w=%d, h=%d",
         mRgb.cols, mRgb.rows, safeRoi.x, safeRoi.y, safeRoi.width, safeRoi.height);

    double greenChannelAvg = 0.0;

    if (safeRoi.width > 0 && safeRoi.height > 0) {
        // 4. Crop the matrix to isolate the pure skin region
        cv::Mat skinRegion = mRgb(safeRoi);

        // 5. Extract the raw green channel intensity
        // (Blood absorbs green light, making it the strongest rPPG indicator)
        cv::Scalar means = cv::mean(skinRegion);
        greenChannelAvg = means[1]; // RGB format: [0]=R, [1]=G, [2]=B
    }

    // 6. Release memory back to the JVM
    env->ReleaseByteArrayElements(yuvData, yuv_ptr, JNI_ABORT);

    // Return the signal amplitude for live graphing
    return (jdouble)greenChannelAvg;
}
