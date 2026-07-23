plugins {
    alias(libs.plugins.android.application)
}

android {
    namespace = "com.example.sentinelhard"
    compileSdk {
        version = release(35)
    }

    defaultConfig {
        applicationId = "com.example.sentinelhard"
        minSdk = 24
        //noinspection OldTargetApi
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"

        externalNativeBuild {
            cmake {
                cppFlags += ""
                // ADD THIS LINE to tell CMake where OpenCV is:
                arguments += "-DOpenCV_DIR=${project.rootDir}/sdk/native/jni"
                // Note: If your OpenCV folder has an "sdk" subfolder, it might be:
                // arguments += "-DOpenCV_DIR=${project.rootDir}/opencv/sdk/native/jni"
                // --- ADD THIS LINE ---
                abiFilters += setOf("arm64-v8a", "armeabi-v7a")
            }
        }

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        release {
            optimization {
                enable = false
            }
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.22.1"
        }
    }
    buildFeatures {
        viewBinding = true
    }
}

dependencies {
    implementation(project(":opencv"))
    implementation(libs.androidx.appcompat)
    implementation(libs.androidx.constraintlayout)
    implementation(libs.androidx.core.ktx)
    implementation(libs.material)
    implementation(libs.play.services.mlkit.face.detection)
    implementation(libs.androidx.camera.core)
    implementation(libs.androidx.camera.camera2)
    implementation(libs.androidx.camera.lifecycle)
    implementation(libs.androidx.camera.view)
    testImplementation(libs.junit)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(libs.androidx.junit)
}