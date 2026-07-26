"""Pydantic schemas for biometric authentication and verification."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class BiometricPayload(BaseModel):
    """
    The deserialized payload from the Pixel 7.

    This is what the Android app builds before signing:
    {session_id, bpm, timestamp, device_id, snr, variance}
    """
    session_id: str
    bpm: int = Field(..., ge=0, description="Heart rate in beats per minute")
    timestamp: datetime
    device_id: str
    snr: Optional[float] = Field(default=5.0, description="Signal-to-Noise Ratio of the rPPG signal in dB")
    variance: Optional[float] = Field(default=2.5, description="Statistical variance of BPM over measurement window")


class VerifyRequest(BaseModel):
    """
    The full verification request sent by the Pixel 7 to the backend.

    The payload is base64-encoded JSON, signed with the Titan M2 private key.
    The signature and public key are also base64-encoded.
    """
    payload: str = Field(
        ...,
        description="Base64-encoded JSON of BiometricPayload",
    )
    signature: str = Field(
        ...,
        description="Base64-encoded ECDSA-SHA256 signature over the payload bytes",
    )
    public_key: str = Field(
        ...,
        description="Base64-encoded DER public key (SubjectPublicKeyInfo format)",
    )
    attestation_chain: Optional[list[str]] = Field(
        default=None,
        description="Optional list of base64-encoded DER certificates for Android Key Attestation",
    )


class VerifyResponse(BaseModel):
    """Response returned after verifying a biometric payload."""
    status: str = Field(
        ...,
        description="ACCESS_GRANTED or ACCESS_DENIED",
    )
    session_id: str
    reason: Optional[str] = Field(
        default=None,
        description="Human-readable reason for denial, if applicable",
    )
