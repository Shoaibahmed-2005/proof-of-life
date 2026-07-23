#include <jni.h>
#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include <android/log.h>

extern "C"
JNIEXPORT jdouble JNICALL
Java_com_example_sentinelhard_MainActivity_processFrame(
        JNIEnv *env,
        jobject /* this */,
        jbyteArray yuvData,
        jint width,
        jint height) {

    // 1. Get a pointer to the raw bytes without copying them
    jbyte *yuv_ptr = env->GetByteArrayElements(yuvData, nullptr);

    // 2. Construct an OpenCV Mat directly around that memory pointer
    // An Android YUV NV21 frame requires height + (height/2) for the buffer
    cv::Mat mYuv(height + height / 2, width, CV_8UC1, (unsigned char *)yuv_ptr);

    // 3. Convert the YUV format into a standard RGB matrix for biometric processing
    cv::Mat mRgb;
    cv::cvtColor(mYuv, mRgb, cv::COLOR_YUV2RGB_NV21);

    // --- Complex rPPG Math & Biometric Logic will go here ---
    // For now, let's just return a dummy pulse value
    double heartRate = 72.5;

    // 4. CRITICAL: Release the memory pointer back to Android/Kotlin
    env->ReleaseByteArrayElements(yuvData, yuv_ptr, JNI_ABORT);

    return (jdouble)heartRate;
}
