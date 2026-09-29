// Stub of <android/log.h> for the laptop syntax check (see ../jni.h).
#pragma once

enum { ANDROID_LOG_INFO = 4 };

int __android_log_print(int prio, const char* tag, const char* fmt, ...)
    __attribute__((format(printf, 3, 4)));
