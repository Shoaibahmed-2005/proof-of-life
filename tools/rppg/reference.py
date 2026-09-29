"""
Python reference implementation of the rPPG engine (mirrors
app/src/main/cpp/rppg_core.cpp step by step). Used to cross-check the C++
engine's output and to experiment with parameters quickly.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np
from scipy.signal import lfilter


@dataclass
class Config:
    window_sec: float = 10.0
    fs: float = 30.0
    band_low_hz: float = 0.7
    band_high_hz: float = 4.0
    pos_window_sec: float = 1.6
    min_estimate_sec: float = 5.0
    estimate_interval_sec: float = 0.5
    stable_count: int = 5
    stable_tolerance_bpm: float = 3.0
    min_snr_db: float = 3.0
    min_window_fill: float = 0.95
    max_gap_sec: float = 1.0
    spectrum_step_bpm: float = 0.5
    waveform_sec: float = 5.0


def butter_lowpass(fc: float, fs: float) -> tuple[np.ndarray, np.ndarray]:
    w0 = 2 * np.pi * fc / fs
    c, alpha = np.cos(w0), np.sin(w0) / (2 * np.sqrt(0.5))
    a0 = 1 + alpha
    return np.array([(1 - c) / 2, 1 - c, (1 - c) / 2]) / a0, np.array([1, -2 * c / a0, (1 - alpha) / a0])


def butter_highpass(fc: float, fs: float) -> tuple[np.ndarray, np.ndarray]:
    w0 = 2 * np.pi * fc / fs
    c, alpha = np.cos(w0), np.sin(w0) / (2 * np.sqrt(0.5))
    a0 = 1 + alpha
    return np.array([(1 + c) / 2, -(1 + c), (1 + c) / 2]) / a0, np.array([1, -2 * c / a0, (1 - alpha) / a0])


def filtfilt(sections, x: np.ndarray, pad: int) -> np.ndarray:
    n = x.size
    pad = max(0, min(pad, n - 1))
    ext = np.concatenate([2 * x[0] - x[pad:0:-1], x, 2 * x[-1] - x[-2:-pad - 2:-1]])
    for b, a in sections:
        ext = lfilter(b, a, ext)
    ext = ext[::-1]
    for b, a in sections:
        ext = lfilter(b, a, ext)
    return ext[::-1][pad:pad + n]


def pos(r: np.ndarray, g: np.ndarray, b: np.ndarray, l: int) -> np.ndarray:
    n = r.size
    h = np.zeros(n)
    for end in range(l, n + 1):
        m = end - l
        mr, mg, mb = r[m:end].mean(), g[m:end].mean(), b[m:end].mean()
        rn, gn, bn = r[m:end] / mr, g[m:end] / mg, b[m:end] / mb
        s1, s2 = gn - bn, gn + bn - 2 * rn
        sd2 = s2.std()
        alpha = s1.std() / sd2 if sd2 > 1e-12 else 0.0
        hh = s1 + alpha * s2
        h[m:end] += hh - hh.mean()
    return h


def detrend_linear(x: np.ndarray) -> np.ndarray:
    i = np.arange(x.size)
    tm = (x.size - 1) / 2
    slope = np.sum((i - tm) * (x - x.mean())) / np.sum((i - tm) ** 2)
    return x - (x.mean() + slope * (i - tm))


def band_spectrum(x: np.ndarray, fs: float, f_lo: float, f_hi: float, step: float):
    n = x.size
    xw = x * (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n) / (n - 1)))
    bins = int(np.floor((f_hi - f_lo) / step + 1e-9)) + 1
    freqs = f_lo + np.arange(bins) * step
    phasors = np.exp(-2j * np.pi * np.outer(freqs, np.arange(n)) / fs)
    return freqs, np.abs(phasors @ xw) ** 2


def peak_frequency(freqs: np.ndarray, power: np.ndarray) -> float:
    k = int(np.argmax(power))
    f = freqs[k]
    if 0 < k < power.size - 1:
        y1, y2, y3 = power[k - 1:k + 2]
        den = y1 - 2 * y2 + y3
        if abs(den) > 1e-18:
            f += np.clip(0.5 * (y1 - y3) / den, -0.5, 0.5) * (freqs[1] - freqs[0])
    return float(f)


def snr_db(freqs: np.ndarray, power: np.ndarray, f0: float, half_width: float) -> float:
    sig_mask = (np.abs(freqs - f0) <= half_width) | (np.abs(freqs - 2 * f0) <= half_width)
    sig, noise = power[sig_mask].sum(), power[~sig_mask].sum()
    if sig <= 0:
        return -99.0
    if noise <= 0:
        return 99.0
    return float(10 * np.log10(sig / noise))


class Engine:
    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or Config()
        self.reset()

    def reset(self):
        self.samples: deque = deque()
        self.estimates: deque = deque()
        self.waveform = np.zeros(0)
        self.last_estimate_t = -1e9
        self.estimate_count = 0

    def add_sample(self, t, r, g, b):
        if self.samples:
            if t <= self.samples[-1][0]:
                return
            if t - self.samples[-1][0] > self.cfg.max_gap_sec:
                self.reset()
        self.samples.append((t, r, g, b))
        while self.samples and self.samples[0][0] < t - self.cfg.window_sec:
            self.samples.popleft()

    def update(self) -> dict:
        c = self.cfg
        st = dict(bpm=0.0, latest_bpm=0.0, snr_db=-99.0, median_snr_db=-99.0, window_fill=0.0,
                  stable=False, new_estimate=False, estimate_count=self.estimate_count,
                  samples=len(self.samples))
        if len(self.samples) < 2:
            return st
        arr = np.array(self.samples)
        t0, t1 = arr[0, 0], arr[-1, 0]
        span = t1 - t0
        st["window_fill"] = float(np.clip(span / c.window_sec, 0, 1))
        pos_len = int(round(c.pos_window_sec * c.fs))
        n = int(np.floor(span * c.fs)) + 1
        if n >= max(pos_len, 2 * int(c.fs)):
            grid = t0 + np.arange(n) / c.fs
            r, g, b = (np.interp(grid, arr[:, 0], arr[:, k]) for k in (1, 2, 3))
            h = detrend_linear(pos(r, g, b, pos_len))
            band = [butter_highpass(c.band_low_hz, c.fs), butter_lowpass(c.band_high_hz, c.fs)]
            filtered = filtfilt(band, h, min(n - 1, int(c.fs)))
            wn = min(n, int(c.waveform_sec * c.fs))
            wave = filtered[-wn:]
            peak = np.abs(wave).max()
            self.waveform = wave / peak if peak > 1e-12 else wave
            if span >= c.min_estimate_sec and t1 - self.last_estimate_t >= c.estimate_interval_sec:
                freqs, power = band_spectrum(filtered, c.fs, c.band_low_hz, c.band_high_hz,
                                             c.spectrum_step_bpm / 60)
                f0 = peak_frequency(freqs, power)
                self.estimates.append((t1, f0 * 60, snr_db(freqs, power, f0, 2.0 / (n / c.fs))))
                while len(self.estimates) > c.stable_count:
                    self.estimates.popleft()
                self.last_estimate_t = t1
                self.estimate_count += 1
                st["new_estimate"] = True
        st["estimate_count"] = self.estimate_count
        if self.estimates:
            bpms = np.array([e[1] for e in self.estimates])
            snrs = np.array([e[2] for e in self.estimates])
            st["bpm"] = float(np.median(bpms))
            st["latest_bpm"] = float(bpms[-1])
            st["snr_db"] = float(snrs[-1])
            st["median_snr_db"] = float(np.median(snrs))
            agree = len(bpms) >= c.stable_count and bool(np.all(np.abs(bpms - st["bpm"]) <= c.stable_tolerance_bpm))
            st["stable"] = agree and st["window_fill"] >= c.min_window_fill and st["median_snr_db"] >= c.min_snr_db
        return st


def run(t: np.ndarray, rgb: np.ndarray, cfg: Config | None = None) -> list[dict]:
    """Feeds every sample and returns the status after each one (like the app does per frame)."""
    eng = Engine(cfg)
    out = []
    for ti, (r, g, b) in zip(t, rgb):
        eng.add_sample(ti, r, g, b)
        st = eng.update()
        st["t"] = float(ti)
        out.append(st)
    return out
