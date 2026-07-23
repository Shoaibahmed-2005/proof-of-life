# Implement JNI Bridge for Image Processing

The goal is to implement a JNI bridge between Kotlin and C++ that allows passing camera frames (YUV data) to OpenCV for biometric processing (rPPG).

## Proposed Changes

### Kotlin Code

#### [MODIFY] [MainActivity.kt](file:///C:/Users/praji/AndroidStudioProjects/SentinelHard/app/src/main/java/com/example/sentinelhard/MainActivity.kt)
- Update the external function declaration to `processFrame` with a `Double` return type, matching the user's specification.

```kotlin
// Before
external fun processFrameForPulse(yuvFrame: ByteArray, width: Int, height: Int): Float

// After
external fun processFrame(yuvData: ByteArray, width: Int, height: Int): Double
```

### Native Code

#### [MODIFY] [native-lib.cpp](file:///C:/Users/praji/AndroidStudioProjects/SentinelHard/app/src/main/cpp/native-lib.cpp)
- Update the JNI function signature and implementation to match the Kotlin declaration and the user's provided snippet.
- Ensure the package name in the JNI function name is `com_example_sentinelhard`.

```cpp
// Before
extern "C" JNIEXPORT jfloat JNICALL
Java_com_example_sentinelhard_MainActivity_processFrameForPulse(...)

// After
extern "C" JNIEXPORT jdouble JNICALL
Java_com_example_sentinelhard_MainActivity_processFrame(...)
```

## Verification Plan

### Automated Tests
- Run `./gradlew :app:assembleDebug` to ensure the project builds correctly and the JNI bridge is valid.

### Manual Verification
- None required at this stage as the logic is a placeholder.
