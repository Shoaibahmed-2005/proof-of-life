# Fix OpenCV Build Error - Missing Library Path

The project is failing to build because the OpenCV CMake configuration files are searching for libraries in a `sdk/` directory at the project root, while the OpenCV files are actually located in the `opencv/` module.

## Proposed Changes

I will modify the OpenCV CMake configuration files for all supported ABIs to correctly locate the libraries and include headers within the `opencv` directory.

### OpenCV Module

#### [MODIFY] [OpenCVConfig.cmake](file:///C:/Users/praji/AndroidStudioProjects/SentinelHard/opencv/native/jni/abi-arm64-v8a/OpenCVConfig.cmake) (and other ABIs)
- Update `OpenCV_INSTALL_PATH` to correctly point to the `opencv` directory (up 3 levels from the ABI directory instead of 4).
- Update `__OpenCV_INCLUDE_DIRS` to point to `${OpenCV_INSTALL_PATH}/native/jni/include`.

#### [MODIFY] [OpenCVModules.cmake](file:///C:/Users/praji/AndroidStudioProjects/SentinelHard/opencv/native/jni/abi-arm64-v8a/OpenCVModules.cmake) (and other ABIs)
- Update `_IMPORT_PREFIX` to point to the `opencv` directory (up 3 levels from the ABI directory instead of 4).

#### [MODIFY] [OpenCVModules-release.cmake](file:///C:/Users/praji/AndroidStudioProjects/SentinelHard/opencv/native/jni/abi-arm64-v8a/OpenCVModules-release.cmake) (and other ABIs)
- Remove the `sdk/` prefix from all library and file paths, as the `opencv` directory now serves as the root for these files.

## Verification Plan

### Automated Tests
- Run the build task that was failing:
  ```powershell
  ./gradlew :app:buildCMakeDebug[arm64-v8a]
  ```
- Verify that the error regarding missing `libopencv_calib3d.a` is resolved.
