"""
Cryptographic Verification Service.

Verifies ECDSA signatures produced by the Android KeyStore (Titan M2 / StrongBox).
The Android side signs with ECDSA using SHA-256 over the P-256 (secp256r1) curve,
which is the default for StrongBox-backed keys.
"""

from __future__ import annotations

import base64
import logging

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils
from cryptography.x509 import load_der_x509_certificate

logger = logging.getLogger(__name__)


class SignatureVerificationError(Exception):
    """Raised when signature verification fails."""
    pass


class InvalidPublicKeyError(Exception):
    """Raised when the public key cannot be parsed."""
    pass


def load_public_key_from_der(public_key_b64: str) -> ec.EllipticCurvePublicKey:
    """
    Load an EC public key from a base64-encoded DER (SubjectPublicKeyInfo) format.

    This is the format returned by Android's
    KeyPair.getPublic().getEncoded().
    """
    try:
        der_bytes = base64.b64decode(public_key_b64)
        key = serialization.load_der_public_key(der_bytes)
        if not isinstance(key, ec.EllipticCurvePublicKey):
            raise InvalidPublicKeyError(
                f"Expected EC public key, got {type(key).__name__}"
            )
        return key
    except Exception as e:
        if isinstance(e, InvalidPublicKeyError):
            raise
        raise InvalidPublicKeyError(f"Failed to parse public key: {e}") from e


def load_public_key_from_pem(public_key_pem: str) -> ec.EllipticCurvePublicKey:
    """Load an EC public key from PEM-encoded string."""
    try:
        key = serialization.load_pem_public_key(public_key_pem.encode())
        if not isinstance(key, ec.EllipticCurvePublicKey):
            raise InvalidPublicKeyError(
                f"Expected EC public key, got {type(key).__name__}"
            )
        return key
    except Exception as e:
        if isinstance(e, InvalidPublicKeyError):
            raise
        raise InvalidPublicKeyError(f"Failed to parse PEM public key: {e}") from e


def extract_public_key_from_certificate(cert_der_b64: str) -> ec.EllipticCurvePublicKey:
    """
    Extract the public key from a DER-encoded X.509 certificate.

    Used to extract keys from Android Key Attestation certificate chains.
    """
    try:
        cert_bytes = base64.b64decode(cert_der_b64)
        cert = load_der_x509_certificate(cert_bytes)
        key = cert.public_key()
        if not isinstance(key, ec.EllipticCurvePublicKey):
            raise InvalidPublicKeyError(
                f"Certificate contains non-EC key: {type(key).__name__}"
            )
        return key
    except Exception as e:
        if isinstance(e, InvalidPublicKeyError):
            raise
        raise InvalidPublicKeyError(
            f"Failed to extract key from certificate: {e}"
        ) from e


def verify_signature(
    payload_b64: str,
    signature_b64: str,
    public_key_b64: str,
) -> bool:
    """
    Verify an ECDSA-SHA256 signature over a payload.

    Args:
        payload_b64: Base64-encoded payload bytes (the signed data).
        signature_b64: Base64-encoded DER-encoded ECDSA signature.
        public_key_b64: Base64-encoded DER public key (SubjectPublicKeyInfo).

    Returns:
        True if the signature is valid.

    Raises:
        SignatureVerificationError: If the signature is invalid.
        InvalidPublicKeyError: If the public key cannot be parsed.
    """
    try:
        payload_bytes = base64.b64decode(payload_b64)
        signature_bytes = base64.b64decode(signature_b64)
    except Exception as e:
        raise SignatureVerificationError(
            f"Failed to decode base64 inputs: {e}"
        ) from e

    public_key = load_public_key_from_der(public_key_b64)

    try:
        public_key.verify(
            signature_bytes,
            payload_bytes,
            ec.ECDSA(hashes.SHA256()),
        )
        logger.info("Signature verification succeeded")
        return True
    except InvalidSignature:
        logger.warning("Signature verification failed: invalid signature")
        raise SignatureVerificationError("Invalid ECDSA signature")
    except Exception as e:
        logger.error("Signature verification error: %s", e)
        raise SignatureVerificationError(f"Verification error: {e}") from e


def require_p256(public_key: ec.EllipticCurvePublicKey) -> None:
    """The app's Keystore key is P-256; reject anything else."""
    if not isinstance(public_key.curve, ec.SECP256R1):
        raise InvalidPublicKeyError(f"Expected a P-256 key, got {public_key.curve.name}")


def public_key_to_pem(public_key_b64: str) -> str:
    """Base64 DER (SubjectPublicKeyInfo) → PEM, for storage in the devices table."""
    key = load_public_key_from_der(public_key_b64)
    return key.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()


def same_public_key(public_key_b64: str, stored_pem: str) -> bool:
    """True if the Base64 DER key and the stored PEM key are the same key."""
    try:
        a = load_public_key_from_der(public_key_b64)
        b = load_public_key_from_pem(stored_pem)
    except InvalidPublicKeyError:
        return False
    fmt = (serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return a.public_bytes(*fmt) == b.public_bytes(*fmt)
