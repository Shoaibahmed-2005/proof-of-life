"""
Verifiable credentials for issued life certificates (build-prompt §5.5).

Each issued certificate becomes W3C-VC-shaped JSON, signed by the backend's
issuer key (ECDSA P-256 / SHA-256), whose subject is the pensioner's did:key.
The credential holds NO personal data (no name, PPO or scores beyond the
decision), so it can be shared with a bank or treasury, who can verify it:

  1. the signature, against the issuer's did:key (the key is in the DID itself);
  2. that SHA-256(credential) is recorded in the audit ledger;
  3. that the ledger's hash chain is intact.

Proof format: the signature covers the canonical JSON (sorted keys, no
whitespace) of the credential with its proof block minus `proofValue`.
It is a simple, documented "backend-signed JSON" (as the brief asks), not a
full Data Integrity cryptosuite implementation.
"""

from __future__ import annotations

import base64
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.core.config import settings
from app.db.models import LifeCertificate
from app.services.did import did_from_public_key, public_key_from_did
from app.services.ledger import canonical_json, sha256_hex

logger = logging.getLogger(__name__)

CREDENTIAL_TYPE = "LifeCertificateCredential"
PROOF_TYPE = "EcdsaP256Sha256CanonicalJson"

_issuer_key: ec.EllipticCurvePrivateKey | None = None


def _load_issuer_key() -> ec.EllipticCurvePrivateKey:
    if settings.ISSUER_KEY_PEM:
        return serialization.load_pem_private_key(settings.ISSUER_KEY_PEM.encode(), password=None)
    path = settings.DATA_DIR / "issuer_key.pem"
    if path.exists():
        return serialization.load_pem_private_key(path.read_bytes(), password=None)
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    key = ec.generate_private_key(ec.SECP256R1())
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
    logger.warning("[SECURITY] Generated a development credential-issuer key at %s. "
                   "Set ISSUER_KEY_PEM in .env for a stable issuer identity.", path)
    return key


def issuer_key() -> ec.EllipticCurvePrivateKey:
    global _issuer_key
    if _issuer_key is None:
        _issuer_key = _load_issuer_key()
    return _issuer_key


def reset_issuer_key() -> None:
    """Forget the cached key (tests switch DATA_DIR between runs)."""
    global _issuer_key
    _issuer_key = None


def issuer_did() -> str:
    return did_from_public_key(issuer_key().public_key())


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _signing_input(credential: dict[str, Any]) -> bytes:
    unsigned = dict(credential)
    proof = dict(unsigned.get("proof", {}))
    proof.pop("proofValue", None)
    unsigned["proof"] = proof
    return canonical_json(unsigned).encode("utf-8")


def credential_hash(credential: dict[str, Any]) -> str:
    return sha256_hex(canonical_json(credential))


def issue_life_certificate(cert: LifeCertificate, subject_did: str, reviewed_by_officer: bool) -> dict[str, Any]:
    """Builds and signs the credential for an ISSUED certificate."""
    issued = cert.reviewed_at or cert.created_at
    credential: dict[str, Any] = {
        "@context": ["https://www.w3.org/ns/credentials/v2"],
        "id": f"urn:uuid:{uuid.uuid4()}",
        "type": ["VerifiableCredential", CREDENTIAL_TYPE],
        "issuer": issuer_did(),
        "validFrom": _iso(issued),
        "validUntil": f"{cert.year}-12-31T23:59:59Z",
        "credentialSubject": {
            "id": subject_did,
            "lifeCertificateYear": cert.year,
            "proofOfLife": True,
            "verificationMethod": "rPPG pulse + random challenge + 1:1 face match + hardware-bound key",
            "reviewedByOfficer": reviewed_by_officer,
        },
        "proof": {
            "type": PROOF_TYPE,
            "created": _iso(issued),
            "verificationMethod": f"{issuer_did()}#{issuer_did().removeprefix('did:key:')}",
            "proofPurpose": "assertionMethod",
        },
    }
    signature = issuer_key().sign(_signing_input(credential), ec.ECDSA(hashes.SHA256()))
    credential["proof"]["proofValue"] = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
    return credential


def verify_signature(credential: dict[str, Any]) -> tuple[bool, str]:
    """Checks the proof against the public key embedded in the issuer's did:key."""
    try:
        proof = credential["proof"]
        if proof.get("type") != PROOF_TYPE:
            return False, f"Unsupported proof type {proof.get('type')!r}"
        value = proof["proofValue"]
        signature = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        public_key_from_did(credential["issuer"]).verify(
            signature, _signing_input(credential), ec.ECDSA(hashes.SHA256()))
        return True, "Signature valid"
    except InvalidSignature:
        return False, "Signature does not match: the credential was altered or not issued by this issuer"
    except (KeyError, ValueError, TypeError) as e:
        return False, f"Malformed credential: {e}"


def load(cert: LifeCertificate) -> dict[str, Any] | None:
    return json.loads(cert.credential_json) if cert.credential_json else None
