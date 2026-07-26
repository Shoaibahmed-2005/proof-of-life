# Tasks - Authentication Workflow Integration

- [ ] Update `AuthState` and UI Composables in `MainActivity.kt`
    - [ ] Add `LivenessVerified`, `Submitting`, `Success`, `Error` states
    - [ ] Create `StatusOverlayUI` to handle these new states with animations
- [ ] Implement `submitAuthentication` logic
    - [ ] Construct `BiometricPayload` (JSON)
    - [ ] Sign payload with `CryptoManager`
    - [ ] Execute Retrofit POST call to `/auth/verify`
- [ ] Connect Biometric Pipeline to Submission
    - [ ] Detect "Verified + Primed" condition in `processMetrics()`
    - [ ] Implement 1.2s delay for visual feedback
    - [ ] Handle success/error transitions
- [ ] Final Verification
    - [ ] Test QR -> Biometric -> Submit flow
    - [ ] Test Direct Phone -> Biometric -> Submit flow
