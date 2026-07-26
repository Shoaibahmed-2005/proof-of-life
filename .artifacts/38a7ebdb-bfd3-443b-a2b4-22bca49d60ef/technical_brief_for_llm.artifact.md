# Technical Brief: Android rPPG Biometric System Challenges

This document summarizes the architecture and current issues of the **SentinelHard** project to facilitate technical consultation with other AI models.

## 1. Project Goal
Real-time, non-contact heart rate monitoring (rPPG) on Android with robust anti-spoofing (Presentation Attack Detection).

## 2. Technical Stack
- **UI/Capture**: Kotlin, Jetpack Compose, CameraX (1.4.0), ML Kit Face Detection.
- **Engine**: C++ (JNI), OpenCV 4.10.
- **Platform**: Targeted for high-end Android (e.g., Vivo X200 with 16KB page size support).

## 3. The DSP Pipeline (C++)
1.  **ROI Extraction**: Forehead crop (45% face width, 20% height).
2.  **Color Space**: Ratiometric signal extraction: $S = G / (R + B)$.
3.  **Resampling**: Linear interpolation to a strict 30 Hz uniform grid (integer-based loop).
4.  **Filtering**: 2nd-order Butterworth IIR Bandpass (0.75 Hz - 2.5 Hz / 45 - 150 BPM). State-isolated for R, G, B, and Ratio channels.
5.  **Windowing**: Hamming window applied to a 150-sample (5s) sliding buffer.
6.  **Spectral Analysis**: Targeted DTFT (Discrete-Time Fourier Transform) from 45 to 180 BPM.
7.  **Refinement**: Quadratic Peak Interpolation for fractional BPM accuracy.

## 4. Current Anti-Spoofing Layers
- **Laplacian Variance**: Rejects "flat" surfaces (screens/photos) via 2nd derivative edge analysis.
- **RGB Correlation**: Compares R and G channel fluctuations (Real skin is decorrelated; screens are highly correlated).
- **Peak-to-Noise Ratio (QR)**: Ratio of the heart rate peak magnitude to average spectral noise.
- **HRV Plausibility**: Standard deviation of BPM over time (Human heart has variability; digital signals are rigid).
- **Micro-Motion**: ML Kit landmark tracking to detect involuntary head jitter.

## 5. Primary Problems Faced

### A. Low Signal-to-Noise Ratio (SNR)
- **Problem**: The biometric signal (volumetric skin color change) is extremely faint (~0.1% change).
- **Situation**: Camera sensor noise, auto-exposure hunting, and **specular glare** (white forehead reflections) often exceed the signal magnitude.
- **Symptom**: SNR/QR fluctuates wildly or stays negative, causing the BPM to "jump" or stick at 0.

### B. "Stuck" Badge / Math Instability
- **Problem**: IIR filters are stateful. Bad frames (sudden light shifts) can cause NaN/Infinity propagation.
- **Situation**: We implemented "Self-Healing" resets, but the system still struggles to re-prime the 5-second buffer quickly enough for a smooth user experience.

### C. Threshold Conflict
- **Problem**: High-security thresholds (e.g., Correlation > 0.98, SNR > 1.2) are being triggered by **environmental noise** instead of actual spoofs.
- **Situation**: A real face with a reflection looks "mathematically similar" to a digital screen to the C++ engine.

## 6. Questions for Suggestions
1.  How can we further isolate the rPPG signal from specular glare (reflections) without using hardware polarizers?
2.  Are there better alternatives to $G/(R+B)$ (like POS, CHROM, or GREEN-only) that are more resilient to the Vivo/Android camera ISP?
3.  How can we make the DTFT peak detection more robust against motion artifacts (head sway) that create low-frequency "shoulders" near the pulse peak?
4.  What is the optimal temporal smoothing strategy for BPM when the SNR is low?
