# Implementation Plan - Fix OpenCV CMake Path Issue

The project is failing to build because the OpenCV CMake configuration files expect an `sdk` directory in the project root, but the OpenCV files are currently located in an `opencv` directory. This causes CMake to look for static libraries in a non-existent `sdk` path.

## Proposed Changes

### [Component Name] OpenCV Module Configuration

#### [MODIFY] [settings.gradle.kts](file:///C:/Users/praji/AndroidStudioProjects/SentinelHard/settings.gradle.kts)
- Update the `:opencv` module to point to the `sdk` directory.

#### [MODIFY] [app/build.gradle.kts](file:///C:/Users/praji/AndroidStudioProjects/SentinelHard/app/build.gradle.kts)
- Update `OpenCV_DIR` to point to `${project.rootDir}/sdk/native/jni`.

#### [RENAME] `opencv` directory to `sdk`
- Rename the physical directory `opencv` to `sdk` to match the expectations of the generated OpenCV CMake files.

## Verification Plan

### Automated Tests
- Run `./gradlew :app:assembleDebug` to verify that the project builds successfully and CMake can find the OpenCV libraries.

### Manual Verification
- Check the `build/intermediates/cxx` directory to ensure `libsentinelhard.so` is correctly linked against OpenCV.
