"""
Liveness Validation Service.
Evaluates biometric payloads to prevent spoofing and video loop attacks.
"""

from __future__ import annotations

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class SpoofingDetectedError(Exception):
    """Raised when biometric data falls outside human liveness parameters."""

    def __init__(self, message: str, reason_code: str = "NO_PULSE") -> None:
        super().__init__(message)
        self.reason_code = reason_code


def validate_liveness(bpm: float, snr: float | None = None, variance: float | None = None) -> bool:
    """
    Legacy AUTH flow checks (original app payload), unchanged apart from
    accepting a fractional BPM.

    Raises:
        SpoofingDetectedError: If any metric fails threshold checks.
    """
    # Use default values for optional snr and variance if omitted
    effective_snr = 5.0 if snr is None else snr
    effective_variance = 2.5 if variance is None else variance

    bpm_min = settings.BPM_MIN
    bpm_max = settings.BPM_MAX

    # 1. Absolute Biological Limits
    if not (bpm_min <= bpm <= bpm_max):
        logger.warning("Liveness failure: BPM %.1f out of human range [%.0f, %.0f].", bpm, bpm_min, bpm_max)
        raise SpoofingDetectedError(
            f"BPM {bpm:.1f} is outside acceptable biological limits ({bpm_min:.0f}-{bpm_max:.0f} BPM)."
        )

    # 2. Signal Quality (legacy linear peak ratio from the original app)
    if effective_snr < settings.LEGACY_MIN_SNR:
        logger.warning("Liveness failure: SNR %.2f too low (Spoofing suspected).", effective_snr)
        raise SpoofingDetectedError("Signal quality insufficient. Ensure good lighting and hold still.")

    # 3. Variance / Loop Detection
    if effective_variance <= 0.01:
        logger.warning("Liveness failure: BPM variance %.4f too low (Video loop suspected).", effective_variance)
        raise SpoofingDetectedError("Unnatural signal stability detected.")

    if effective_variance > 15.0:
        logger.warning("Liveness failure: BPM variance %.2f too high (Motion artifact).", effective_variance)
        raise SpoofingDetectedError("Too much movement detected during scan.")

    logger.info("Liveness validation passed (BPM=%.1f, SNR=%.2f, Var=%.2f).", bpm, effective_snr, effective_variance)
    return True


def check_liveness(bpm: float, snr_db: float, liveness_passed: bool) -> None:
    """
    Liveness checks for ENROLLMENT / LIFE_CERTIFICATE payloads (build-prompt §5.2 step 5).
    The phone decides "stable pulse" itself; the backend re-checks the numbers
    against its own configured limits so a lenient app build cannot pass.

    Raises:
        SpoofingDetectedError (reason_code NO_PULSE) on any failure.
    """
    if not liveness_passed:
        raise SpoofingDetectedError("No pulse detected: the scan did not find a stable heartbeat.")
    if not (settings.BPM_MIN <= bpm <= settings.BPM_MAX):
        raise SpoofingDetectedError(
            f"No pulse detected: heart rate {bpm:.0f} BPM is outside the plausible range."
        )
    if snr_db < settings.MIN_SNR_DB:
        raise SpoofingDetectedError(
            f"No pulse detected: pulse signal too weak ({snr_db:.1f} dB, need {settings.MIN_SNR_DB:.1f} dB)."
        )
