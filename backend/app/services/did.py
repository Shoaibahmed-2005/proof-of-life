"""
Decentralized identifiers (did:key) for P-256 keys.

did:key = "did:key:" + multibase(base58btc, multicodec(p256-pub) + compressed point)
  - multicodec p256-pub = 0x1200 → unsigned varint bytes 0x80 0x24
  - compressed SEC1 point = 33 bytes
  - base58btc multibase prefix "z"
P-256 did:keys therefore always start with "did:key:zDn".

Spec: https://w3c-ccg.github.io/did-method-key/
"""

from __future__ import annotations

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.services.crypto import load_public_key_from_pem

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_P256_MULTICODEC = bytes([0x80, 0x24])


def b58encode(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    out = ""
    while n:
        n, rem = divmod(n, 58)
        out = _B58[rem] + out
    pad = len(data) - len(data.lstrip(b"\0"))
    return "1" * pad + out


def b58decode(text: str) -> bytes:
    n = 0
    for ch in text:
        n = n * 58 + _B58.index(ch)
    pad = len(text) - len(text.lstrip("1"))
    body = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * pad + body


def did_from_public_key(key: ec.EllipticCurvePublicKey) -> str:
    if not isinstance(key.curve, ec.SECP256R1):
        raise ValueError("did:key here supports P-256 keys only")
    point = key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.CompressedPoint)
    return "did:key:z" + b58encode(_P256_MULTICODEC + point)


def did_from_pem(public_key_pem: str) -> str:
    return did_from_public_key(load_public_key_from_pem(public_key_pem))


def public_key_from_did(did: str) -> ec.EllipticCurvePublicKey:
    if not did.startswith("did:key:z"):
        raise ValueError("Not a base58btc did:key")
    raw = b58decode(did[len("did:key:z"):])
    if raw[:2] != _P256_MULTICODEC or len(raw) != 35:
        raise ValueError("Not a P-256 did:key")
    return ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), raw[2:])
