# R8 rules for release builds (debug builds are not minified).
# The release build type references this file; before it existed, release
# builds failed. Project-specific keep rules also live in src/main/keepRules/.

# JNI: native methods are looked up by name from C++.
-keepclasseswithmembernames class * {
    native <methods>;
}
-keep class com.example.sentinelhard.rppg.RppgNative { *; }

# kotlinx.serialization models sent to / received from the backend.
-keep,includedescriptorclasses class com.example.sentinelhard.models.** { *; }
-keepclassmembers class com.example.sentinelhard.models.** {
    *** Companion;
    kotlinx.serialization.KSerializer serializer(...);
}
