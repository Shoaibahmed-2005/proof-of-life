# For more information about using CMake with Android Studio, read the
# documentation: https://d.android.com/studio/projects/add-native-code.html.

cmake_minimum_required(VERSION 3.22.1)

project("sentinelhard")

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# OpenCV stays linked (the app's Java side loads it via OpenCVLoader).
# The rPPG engine itself (rppg_core.cpp) is plain C++ so it can be unit-tested
# on a laptop: see tools/rppg/.
find_package(OpenCV REQUIRED)

add_library(${CMAKE_PROJECT_NAME} SHARED
        native-lib.cpp
        rppg_core.cpp
        face_core.cpp)

target_link_libraries(${CMAKE_PROJECT_NAME}
        ${OpenCV_LIBRARIES}
        android
        log)
