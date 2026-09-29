// Minimal jni.h stub used ONLY to syntax/type-check native-lib.cpp on a laptop
// without a JDK/NDK. It declares exactly the JNI types and JNIEnv methods the
// JNI layer uses, with the same C++ signatures as the real <jni.h>. The real
// header from the NDK is used for the actual Android build.
#pragma once

#include <cstdint>

typedef int32_t jint;
typedef int64_t jlong;
typedef double jdouble;
typedef float jfloat;
typedef uint8_t jboolean;
typedef jint jsize;

class _jobject {};
class _jarray : public _jobject {};
class _jintArray : public _jarray {};
class _jdoubleArray : public _jarray {};
class _jfloatArray : public _jarray {};

typedef _jobject* jobject;
typedef _jarray* jarray;
typedef _jintArray* jintArray;
typedef _jdoubleArray* jdoubleArray;
typedef _jfloatArray* jfloatArray;

struct _JNIEnv {
    void* GetDirectBufferAddress(jobject buf);
    jlong GetDirectBufferCapacity(jobject buf);
    jsize GetArrayLength(jarray array);
    void GetIntArrayRegion(jintArray array, jsize start, jsize len, jint* buf);
    jdoubleArray NewDoubleArray(jsize len);
    void SetDoubleArrayRegion(jdoubleArray array, jsize start, jsize len, const jdouble* buf);
    jfloatArray NewFloatArray(jsize len);
    void SetFloatArrayRegion(jfloatArray array, jsize start, jsize len, const jfloat* buf);
    void GetFloatArrayRegion(jfloatArray array, jsize start, jsize len, jfloat* buf);
};
typedef _JNIEnv JNIEnv;

#define JNIEXPORT __attribute__((visibility("default")))
#define JNICALL
