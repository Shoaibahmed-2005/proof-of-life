"""
Face-match logic: embedding validation, cosine similarity, the three-band
decision and the ageing-aware template update.

Pure functions over lists of floats (no numpy) so the rules are easy to
unit-test with simulated embeddings. Encryption of stored vectors lives here too.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from app.core.config import settings
from app.core.security import get_template_cipher

MIN_DIM = 64
MAX_DIM = 1024


class EmbeddingError(ValueError):
    """Raised when an embedding is malformed (wrong size, NaN, zero vector)."""


class MatchBand(str, Enum):
    APPROVE = "APPROVE"
    REVIEW = "REVIEW"
    REJECT = "REJECT"


@dataclass(frozen=True)
class MatchDecision:
    band: MatchBand
    score: float         # cosine similarity to current_template
    anchor_score: float  # cosine similarity to anchor_template
    reason_code: str | None = None
    reason: str | None = None


# ── Vector maths ────────────────────────────────────────────────────────

def l2_normalize(vec: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm < 1e-9:
        raise EmbeddingError("Embedding has zero length")
    return [x / norm for x in vec]


def validate_embedding(vec: Sequence[float], expected_dim: int | None = None) -> list[float]:
    """Checks size and values, then returns the L2-normalised embedding."""
    if not (MIN_DIM <= len(vec) <= MAX_DIM):
        raise EmbeddingError(f"Embedding has {len(vec)} values; expected {MIN_DIM}-{MAX_DIM}")
    if expected_dim is not None and len(vec) != expected_dim:
        raise EmbeddingError(
            f"Embedding has {len(vec)} values but the stored template has {expected_dim}"
        )
    if not all(math.isfinite(x) for x in vec):
        raise EmbeddingError("Embedding contains NaN or infinite values")
    return l2_normalize(vec)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        raise EmbeddingError("Cannot compare embeddings of different sizes")
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na < 1e-9 or nb < 1e-9:
        raise EmbeddingError("Embedding has zero length")
    return dot / (na * nb)


# ── Three-band decision (build-prompt §5.3) ─────────────────────────────

def decide(
    probe: Sequence[float],
    current_template: Sequence[float],
    anchor_template: Sequence[float],
    t_high: float | None = None,
    t_low: float | None = None,
    anchor_min: float | None = None,
) -> MatchDecision:
    """
    score ≥ T_high (and close enough to the anchor) → APPROVE
    T_low ≤ score < T_high                          → REVIEW
    score < T_low                                   → REJECT

    A high score against current_template but a low score against the anchor
    means the template may have drifted, so it goes to an officer instead.
    """
    t_high = settings.FACE_T_HIGH if t_high is None else t_high
    t_low = settings.FACE_T_LOW if t_low is None else t_low
    anchor_min = settings.FACE_ANCHOR_MIN if anchor_min is None else anchor_min

    score = cosine(probe, current_template)
    anchor_score = cosine(probe, anchor_template)

    if score < t_low:
        return MatchDecision(MatchBand.REJECT, score, anchor_score,
                             "FACE_MISMATCH", "Face does not match the registered pensioner")
    if score < t_high:
        return MatchDecision(MatchBand.REVIEW, score, anchor_score,
                             "BORDERLINE_MATCH", "Face match is borderline; sent for officer review")
    if anchor_score < anchor_min:
        return MatchDecision(MatchBand.REVIEW, score, anchor_score,
                             "ANCHOR_DRIFT",
                             "Matches the recent template but not the original registration; "
                             "sent for officer review")
    return MatchDecision(MatchBand.APPROVE, score, anchor_score)


# ── Template update (build-prompt §5.4) ─────────────────────────────────

def blend_template(
    current_template: Sequence[float],
    anchor_template: Sequence[float],
    probe: Sequence[float],
    decision: MatchDecision,
    alpha: float | None = None,
    t_high: float | None = None,
    anchor_min: float | None = None,
) -> list[float] | None:
    """
    Returns the updated current_template, or None if no update is allowed.

    Updates only after an automatic approval above T_high. The blended result
    must itself stay within FACE_ANCHOR_MIN of the anchor, so repeated updates
    can never walk the template over to a different person.
    """
    alpha = settings.TEMPLATE_BLEND_ALPHA if alpha is None else alpha
    t_high = settings.FACE_T_HIGH if t_high is None else t_high
    anchor_min = settings.FACE_ANCHOR_MIN if anchor_min is None else anchor_min

    if decision.band is not MatchBand.APPROVE or decision.score < t_high:
        return None
    if decision.anchor_score < anchor_min:
        return None

    cur = l2_normalize(current_template)
    new = l2_normalize(probe)
    blended = l2_normalize([(1.0 - alpha) * c + alpha * p for c, p in zip(cur, new)])
    if cosine(blended, anchor_template) < anchor_min:
        return None
    return blended


# ── Encrypted storage ───────────────────────────────────────────────────

def encrypt_vector(vec: Sequence[float]) -> bytes:
    raw = struct.pack(f"<{len(vec)}f", *vec)
    return get_template_cipher().encrypt(raw)


def decrypt_vector(token: bytes) -> list[float]:
    raw = get_template_cipher().decrypt(token)
    return list(struct.unpack(f"<{len(raw) // 4}f", raw))
