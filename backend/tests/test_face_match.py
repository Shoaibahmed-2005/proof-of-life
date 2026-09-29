"""Unit tests for the face-match rules with simulated embeddings (no database)."""

import pytest

from app.services import face_match as fm
from tests.conftest import random_unit, with_cosine

T_HIGH, T_LOW, ANCHOR_MIN = 0.70, 0.50, 0.55


def decide(probe, current, anchor):
    return fm.decide(probe, current, anchor, t_high=T_HIGH, t_low=T_LOW, anchor_min=ANCHOR_MIN)


def test_cosine_basics():
    a = random_unit(1)
    assert fm.cosine(a, a) == pytest.approx(1.0)
    assert fm.cosine(a, with_cosine(a, 0.8, 2)) == pytest.approx(0.8, abs=1e-9)


@pytest.mark.parametrize("sim,band", [
    (0.95, fm.MatchBand.APPROVE),
    (0.70 + 1e-9, fm.MatchBand.APPROVE),  # at T_high approves
    (0.69, fm.MatchBand.REVIEW),
    (0.50 + 1e-9, fm.MatchBand.REVIEW),   # at T_low reviews
    (0.49, fm.MatchBand.REJECT),
    (0.05, fm.MatchBand.REJECT),
])
def test_three_bands(sim, band):
    base = random_unit(10)
    d = decide(with_cosine(base, sim, 11), base, base)
    assert d.band is band
    assert d.score == pytest.approx(sim, abs=1e-9)


def test_reject_reason_is_face_mismatch():
    base = random_unit(3)
    d = decide(random_unit(4), base, base)
    assert d.band is fm.MatchBand.REJECT and d.reason_code == "FACE_MISMATCH"


def test_high_score_but_far_from_anchor_goes_to_review():
    anchor = random_unit(20)
    current = with_cosine(anchor, 0.45, 21)  # template has drifted below ANCHOR_MIN
    probe = current                          # matches the drifted template perfectly
    d = decide(probe, current, anchor)
    assert d.score == pytest.approx(1.0)
    assert d.band is fm.MatchBand.REVIEW and d.reason_code == "ANCHOR_DRIFT"


def test_blend_only_after_strong_approval():
    base = random_unit(30)
    strong = with_cosine(base, 0.9, 31)
    border = with_cosine(base, 0.6, 32)
    d_strong, d_border = decide(strong, base, base), decide(border, base, base)
    new = fm.blend_template(base, base, strong, d_strong, alpha=0.1, t_high=T_HIGH, anchor_min=ANCHOR_MIN)
    assert new is not None
    assert fm.cosine(new, base) > 0.99            # small, weighted step
    assert abs(sum(x * x for x in new) - 1) < 1e-9  # L2-normalised
    assert fm.blend_template(base, base, border, d_border, alpha=0.1,
                             t_high=T_HIGH, anchor_min=ANCHOR_MIN) is None


def test_template_drift_never_lets_an_impostor_auto_approve():
    """
    Adversarial drift: each 'approved' scan is a little further from the
    registered person, always passing T_high against the current template.
    The template may move, but (a) it stays within ANCHOR_MIN of the anchor,
    and (b) the impostor's own face is never auto-approved, because every
    decision also compares the probe with the never-changing anchor.
    """
    anchor = random_unit(40)
    impostor = random_unit(41)
    current = anchor
    steps = 0
    for _ in range(200):
        probe = fm.l2_normalize([0.85 * c + 0.15 * i for c, i in zip(current, impostor)])
        d = decide(probe, current, anchor)
        if d.band is not fm.MatchBand.APPROVE:
            break
        updated = fm.blend_template(current, anchor, probe, d, alpha=0.3,
                                    t_high=T_HIGH, anchor_min=ANCHOR_MIN)
        if updated is None:
            break
        current = updated
        steps += 1
    assert steps > 0                                   # some drift did happen
    assert fm.cosine(current, anchor) >= ANCHOR_MIN    # (a) floor holds
    d = decide(impostor, current, anchor)
    assert d.band is not fm.MatchBand.APPROVE          # (b) no auto-approval
    assert d.anchor_score < ANCHOR_MIN


def test_embedding_validation():
    with pytest.raises(fm.EmbeddingError):
        fm.validate_embedding([0.0] * 128)                      # zero vector
    with pytest.raises(fm.EmbeddingError):
        fm.validate_embedding([1.0] * 10)                       # too short
    with pytest.raises(fm.EmbeddingError):
        fm.validate_embedding([float("nan")] + [1.0] * 127)     # NaN
    with pytest.raises(fm.EmbeddingError):
        fm.validate_embedding(random_unit(1, 192), expected_dim=128)  # wrong model size
    v = fm.validate_embedding([2.0] * 128)
    assert abs(sum(x * x for x in v) - 1) < 1e-9
