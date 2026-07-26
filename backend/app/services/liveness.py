"""
Liveness Validation Service.
Evaluates biometric payloads to prevent spoofing and video loop attacks.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class SpoofingDetectedError(Exception):
    """Raised when biometric data falls outside human liveness parameters."""
    pass


def validate_liveness(bpm: int, snr: float | None = None, variance: float | None = None) -> bool:
    """
    Validates biometric parameters to ensure the signal is from a live human.
    
    Args:
        bpm: Beats per minute extracted via the POS algorithm.
        snr: Signal-to-Noise Ratio of the rPPG signal.
        variance: The statistical variance of the BPM over the measurement window.
        
    Returns:
        True if the data passes all liveness checks.
        
    Raises:
        SpoofingDetectedError: If any metric fails threshold checks.
    """
    # Use default values for optional snr and variance if omitted
    effective_snr = 5.0 if snr is None else snr
    effective_variance = 2.5 if variance is None else variance

    # 1. Absolute Biological Limits
    if not (50 <= bpm <= 120):
        logger.warning("Liveness failure: BPM %d out of human range [50, 120].", bpm)
        raise SpoofingDetectedError(f"BPM {bpm} is outside acceptable biological limits (50-120 BPM).")
        
    # 2. Signal Quality (SNR) Threshold
    # A low SNR indicates random noise or a flat video (e.g., holding a picture to the camera)
    # A standard rPPG signal on a mobile phone should ideally exceed 3.5 dB
    if effective_snr < 3.5:
        logger.warning("Liveness failure: SNR %.2f too low (Spoofing suspected).", effective_snr)
        raise SpoofingDetectedError("Signal quality insufficient. Ensure good lighting and hold still.")
        
    # 3. Variance / Loop Detection
    # A variance of <= 0.01 often indicates a looped video or static deepfake injection.
    # Abnormally high variance indicates heavy motion artifacts, making the BPM untrustworthy.
    if effective_variance <= 0.01:
        logger.warning("Liveness failure: BPM variance %.4f too low (Video loop suspected).", effective_variance)
        raise SpoofingDetectedError("Unnatural signal stability detected.")
        
    if effective_variance > 15.0:
        logger.warning("Liveness failure: BPM variance %.2f too high (Motion artifact).", effective_variance)
        raise SpoofingDetectedError("Too much movement detected during scan.")

    logger.info("Liveness validation passed. Human presence confirmed (BPM=%d, SNR=%.2fdB, Var=%.2f).", bpm, effective_snr, effective_variance)
    return True
