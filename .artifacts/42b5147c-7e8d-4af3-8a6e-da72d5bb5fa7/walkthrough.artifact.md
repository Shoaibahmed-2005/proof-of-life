# Walkthrough - End-to-End Authentication Workflow

The full authentication pipeline is now integrated, connecting local biometric analysis with hardware-backed security and backend verification.

## Changes Made

### 1. State Machine Orchestration
Updated `MainActivity.kt` to manage the complete authentication lifecycle using a sealed `AuthState` class:
- **Selection**: Choose between direct phone login or desktop QR scanning.
- **Capture**: Dynamic lens switching (Back for QR, Front for rPPG).
- **Verification**: Automatic transition to submission once liveness is confirmed.
- **Reporting**: Real-time UI feedback for submission status, success, and errors.

### 2. Secure Payload Signing
Integrated `CryptoManager` to ensure all biometric data sent to the backend is cryptographically signed inside the device's secure hardware (Titan M2 / StrongBox):
- Generates a `BiometricPayload` JSON containing BPM, SNR, Variance, and Device ID.
- Signs the payload with a P-256 ECDSA key.
- Packages the signature and public key into a `VerifyRequest`.

### 3. Automated Zero-Touch UI
Implemented a "visual handshake" that automatically triggers authentication:
- Detects the "Verified Human" status and a primed signal buffer (150 frames).
- Displays a "Liveness Verified" confirmation for 1.2 seconds.
- Automatically dispatches the signed payload to the FastAPI backend.

## Verification Results

### Automated Tests
- [x] **Gradle Build**: Successful compilation and resource merging.
- [x] **Deployment**: Successful installation on Google Pixel 7.

### Manual Verification
- [x] **UI Transition**: Verified the transition from the selection menu to the camera view.
- [x] **Error Handling**: Confirmed the "Error" state displays correctly when the server is unreachable, proving the state machine and UI overlays are functional.

> [!TIP]
> To test the full end-to-end flow on a physical device, update `ApiClient.BASE_URL` and `TelemetryStreamer.DEFAULT_URL` to your computer's local IP address and ensure the FastAPI server is running.
