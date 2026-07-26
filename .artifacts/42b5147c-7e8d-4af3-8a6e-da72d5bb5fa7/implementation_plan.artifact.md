# Implementation Plan - End-to-End Authentication Workflow

This plan orchestrates the rPPG Engine, CryptoManager, Retrofit Client, and QrCodeAnalyzer into a single state-driven authentication flow in `MainActivity.kt`.

## User Review Required

- **Automatic Submission**: As recommended, the app will automatically submit biometrics after a 1.2s visual confirmation delay once liveness is verified and the buffer is primed.

> [!NOTE]
> **Hardware Key Attestation**: `CryptoManager` is configured to use StrongBox (Titan M2). This may take a few seconds on first launch.

## Proposed Changes

### [Component] Authentication State Machine

#### [MODIFY] [MainActivity.kt](file:///C:/Users/praji/Desktop/projrct/SentinelHard/app/src/main/java/com/example/sentinelhard/MainActivity.kt)
- Update `AuthState` sealed class to include `LivenessVerified`, `Submitting`, `Success`, and `Error` states.
- Implement `submitAuthentication(sessionId: String)` using `lifecycleScope` and `Retrofit`.
- Logic for automatic submission:
    - Triggered when `livenessStatus == 2` (HUMAN) and `bufferSize >= 150.0`.
    - Transition to `AuthState.LivenessVerified`.
    - Wait 1.2s (visual handshake).
    - Call `submitAuthentication`.
    - `bpmState` and `snrState`.
    - Combined variance from `nosePositions`.
    - `Settings.Secure.ANDROID_ID` for `deviceId`.
    - ISO-8601 timestamp.
- Use `CryptoManager` to sign the payload and retrieve the public key and attestation chain.
- Update `SelectionMenuUI` and add `SubmittingUI`, `SuccessUI`, and `ErrorUI` using Compose.

### [Component] Networking & Models

#### [MODIFY] [BiometricApiService.kt](file:///C:/Users/praji/Desktop/projrct/SentinelHard/app/src/main/java/com/example/sentinelhard/network/BiometricApiService.kt)
- (Optional) Ensure the base URL in `ApiClient` matches your local environment (currently `10.0.2.2`).

## Verification Plan

### Automated Tests
- `gradle_build` to ensure all components integrate correctly.

### Manual Verification
1. **Selection**: Choose "Login Directly on Phone" or "Scan Desktop QR Code".
2. **Scanning**: If QR, scan a JSON like `{"session_id": "test_123"}`.
3. **Biometrics**: Position face and wait for "VERIFIED HUMAN" and 100% progress.
4. **Submission**: Observe UI transition to "Submitting...".
5. **Success/Error**: Verify final message based on server response.
