"""
Security helpers: officer password hashing, signed officer tokens, and the
Fernet cipher used to encrypt face templates at rest.

Standard library + `cryptography` only (no extra dependencies).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time

from cryptography.fernet import Fernet

from app.core.config import settings

logger = logging.getLogger(__name__)

_PBKDF2_ITERATIONS = 200_000


# ── Passwords ───────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_hex, digest_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


# ── Officer tokens (HMAC-signed, stateless) ─────────────────────────────

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _sign(body: str) -> str:
    return _b64(hmac.new(settings.SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest())


def create_officer_token(officer_id: int) -> tuple[str, int]:
    """Returns (token, expires_at_unix)."""
    exp = int(time.time()) + settings.OFFICER_TOKEN_TTL_SECONDS
    body = _b64(json.dumps({"sub": officer_id, "exp": exp}).encode())
    return f"{body}.{_sign(body)}", exp


def decode_officer_token(token: str) -> int | None:
    """Returns the officer id, or None if the token is invalid or expired."""
    try:
        body, sig = token.split(".")
        if not hmac.compare_digest(sig, _sign(body)):
            return None
        claims = json.loads(_unb64(body))
        if int(claims["exp"]) < time.time():
            return None
        return int(claims["sub"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


# ── Template encryption (Fernet) ────────────────────────────────────────

_fernet: Fernet | None = None


def _load_template_key() -> bytes:
    if settings.TEMPLATE_KEY:
        return settings.TEMPLATE_KEY.encode()
    key_file = settings.DATA_DIR / "template.key"
    if key_file.exists():
        return key_file.read_bytes().strip()
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    key_file.write_bytes(key)
    logger.warning(
        "[SECURITY] TEMPLATE_KEY not set; generated a development key at %s. "
        "Set TEMPLATE_KEY in .env for any shared or production deployment.",
        key_file,
    )
    return key


def get_template_cipher() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_load_template_key())
    return _fernet


def reset_template_cipher() -> None:
    """Forget the cached cipher (tests switch DATA_DIR between runs)."""
    global _fernet
    _fernet = None
