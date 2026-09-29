"""
Synthetic face-colour traces for testing the rPPG engine without a phone.

Model (per channel c ∈ R, G, B), after averaging thousands of skin pixels:

    C_c(t) = I(t) · base_c · (1 + A · p(t) · pbv_c) + motion(t) · base_c + noise_c(t)

- p(t): pulse waveform (fundamental + 2nd harmonic) at a heart rate that
  varies slightly (HRV + breathing modulation), optionally ramping.
- pbv: blood-volume-pulse colour signature (de Haan & van Leest 2014),
  strongest in green. A (≈0.2–0.6 %) is the pulsatile amplitude.
- I(t): slow illumination drift, optionally a periodic flicker.
- motion(t): small low-frequency intensity changes from head movement.
- noise: camera noise on the per-frame mean.
- timestamps: ~30 fps with jitter and occasional dropped frames.

A photo is the same model with A = 0 (no pulse).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

SKIN_RGB = np.array([182.0, 128.0, 108.0])
PBV = np.array([0.33, 0.77, 0.53])


@dataclass
class Scenario:
    name: str
    duration_s: float = 30.0
    fps: float = 30.0
    bpm_start: float = 72.0
    bpm_end: float | None = None      # linear ramp if set
    pulse_amp: float = 0.004          # relative pulsatile amplitude (0 = photo)
    noise_std: float = 0.15           # noise on the per-frame channel mean
    motion_std: float = 0.002         # relative low-frequency motion
    drift_amp: float = 0.02           # slow illumination drift
    flicker_hz: float = 0.0           # periodic illumination (e.g. a waving hand, bad light)
    flicker_amp: float = 0.0
    drop_prob: float = 0.03           # dropped frames
    gap: tuple[float, float] | None = None  # (start_s, end_s) with no frames (face lost)
    seed: int = 0
    expect: dict = field(default_factory=dict)

    def true_bpm(self, t: np.ndarray) -> np.ndarray:
        end = self.bpm_start if self.bpm_end is None else self.bpm_end
        return self.bpm_start + (end - self.bpm_start) * np.clip(t / self.duration_s, 0, 1)


def generate(s: Scenario) -> tuple[np.ndarray, np.ndarray]:
    """Returns (timestamps [s], rgb [n×3])."""
    rng = np.random.default_rng(s.seed)
    n_nominal = int(s.duration_s * s.fps)
    t = np.arange(n_nominal) / s.fps + rng.normal(0, 0.003, n_nominal)
    t = np.sort(t) + 5.0  # sensor clocks don't start at zero
    keep = rng.random(n_nominal) >= s.drop_prob
    if s.gap:
        rel = t - 5.0
        keep &= ~((rel >= s.gap[0]) & (rel < s.gap[1]))
    t = t[keep]
    rel = t - 5.0

    # Heart rate with HRV and breathing modulation, integrated to a phase.
    fine = np.arange(0, s.duration_s + 1, 0.01)
    hr = s.true_bpm(fine) + 1.5 * np.sin(2 * np.pi * 0.25 * fine) + rng.normal(0, 0.3, fine.size).cumsum() * 0.02
    phase = 2 * np.pi * np.cumsum(hr / 60.0) * 0.01
    ph = np.interp(rel, fine, phase)
    pulse = np.sin(ph) + 0.35 * np.sin(2 * ph + 0.6)

    illum = 1 + s.drift_amp * np.sin(2 * np.pi * 0.03 * rel + rng.uniform(0, 6)) \
        + s.flicker_amp * np.sin(2 * np.pi * s.flicker_hz * rel)
    motion = np.convolve(rng.normal(0, s.motion_std, rel.size), np.ones(15) / np.sqrt(15), mode="same")

    rgb = (illum[:, None] * SKIN_RGB[None, :] * (1 + s.pulse_amp * pulse[:, None] * PBV[None, :])
           + motion[:, None] * SKIN_RGB[None, :]
           + rng.normal(0, s.noise_std, (rel.size, 3)))
    return t, rgb


def write_csv(path: Path, t: np.ndarray, rgb: np.ndarray) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        for ti, (r, g, b) in zip(t, rgb):
            w.writerow([f"{ti:.6f}", f"{r:.6f}", f"{g:.6f}", f"{b:.6f}"])


SCENARIOS = [
    Scenario("still_72", bpm_start=72, seed=1, expect={"stable": True, "bpm": 72}),
    Scenario("still_58", bpm_start=58, seed=2, expect={"stable": True, "bpm": 58}),
    Scenario("still_110", bpm_start=110, seed=3, expect={"stable": True, "bpm": 110}),
    Scenario("elderly_weak_pulse_66", bpm_start=66, pulse_amp=0.0025, seed=4,
             expect={"stable": True, "bpm": 66}),
    Scenario("ramp_70_to_88", bpm_start=70, bpm_end=88, duration_s=40, seed=5,
             expect={"tracks": True}),
    Scenario("head_motion_75", bpm_start=75, motion_std=0.006, noise_std=0.3, seed=6,
             expect={"never_wrong": True}),
    Scenario("face_lost_2s_80", bpm_start=80, gap=(8.0, 10.0), duration_s=35, seed=7,
             expect={"stable": True, "bpm": 80, "restarts": True}),
    Scenario("photo_still", pulse_amp=0.0, seed=8, expect={"stable": False}),
    Scenario("photo_noisy", pulse_amp=0.0, noise_std=0.4, motion_std=0.004, seed=9,
             expect={"stable": False}),
    Scenario("photo_light_flicker_1.2hz", pulse_amp=0.0, flicker_hz=1.2, flicker_amp=0.01, seed=10,
             expect={"stable": False}),
]
