"""
Builds and tests the C++ rPPG engine on a laptop (no phone, no Android SDK).

  python tools/rppg/run_tests.py            # full run
  python tools/rppg/run_tests.py --quick    # skip the slow Python cross-check

Steps:
 1. Compile app/src/main/cpp/rppg_core.cpp with zig (pip install ziglang)
    into the unit tests and a CLI harness; also syntax-check the JNI layer
    (native-lib.cpp) against a minimal jni.h stub.
 2. Check the hand-written Butterworth filters against scipy.
 3. Run the synthetic scenarios (synth.py) through the C++ engine and check
    accuracy, time to a stable reading, and that photos never pass.
 4. Cross-check the C++ output against the Python reference (reference.py).
 5. Monte-Carlo: SNR of genuine vs no-pulse traces → suggested MIN_SNR_DB.

Needs: python -m pip install ziglang numpy scipy
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from scipy.signal import butter

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CPP = ROOT / "app" / "src" / "main" / "cpp"
BUILD = HERE / "build"
EXE = ".exe" if sys.platform == "win32" else ""

sys.path.insert(0, str(HERE))
import reference  # noqa: E402
from synth import SCENARIOS, Scenario, generate, write_csv  # noqa: E402

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("  ok    " if cond else "  FAIL  ") + msg)
    if not cond:
        failures.append(msg)


def compile_cpp() -> None:
    BUILD.mkdir(exist_ok=True)
    zig = [sys.executable, "-m", "ziglang", "c++", "-std=c++17", "-O2",
           "-Wall", "-Wextra", "-Wpedantic", "-Wshadow", "-Wconversion", "-Wno-sign-conversion", f"-I{CPP}"]
    if sys.platform == "win32":
        zig[4:4] = ["-target", "x86_64-windows-gnu"]
    for out, src in [("test_core", HERE / "test_core.cpp"), ("rppg_cli", HERE / "rppg_cli.cpp"),
                     ("test_face", HERE / "test_face.cpp")]:
        cmd = zig + [str(CPP / "rppg_core.cpp"), str(CPP / "face_core.cpp"), str(src), "-o", str(BUILD / (out + EXE))]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:  # Windows sometimes locks a fresh .exe briefly (antivirus); retry once
            r = subprocess.run(cmd, capture_output=True, text=True)
        lines = [l for l in r.stderr.splitlines() if "libcxx" not in l]
        warnings = [l for l in lines if "warning" in l or "error" in l]
        check(r.returncode == 0 and not warnings, f"compile {out} (no warnings)")
        for w in (warnings or (lines[-5:] if r.returncode else []))[:10]:
            print("        " + w)
    # JNI layer: syntax/type check against a jni.h stub with the real signatures we use.
    r = subprocess.run(zig + ["-c", f"-I{HERE / 'fake_jni'}", str(CPP / "native-lib.cpp"),
                              "-o", str(BUILD / "native-lib.o")], capture_output=True, text=True)
    errs = [l for l in r.stderr.splitlines()
            if ("error" in l or "warning" in l) and "libcxx" not in l and "unused-command-line" not in l]
    check(r.returncode == 0 and not errs, "syntax-check native-lib.cpp (JNI layer)")
    for e in errs[:10]:
        print("        " + e)


def run_unit_tests() -> None:
    for exe, label in (("test_core", "C++ rPPG unit tests"), ("test_face", "C++ face alignment / template tests")):
        r = subprocess.run([str(BUILD / (exe + EXE))], capture_output=True, text=True)
        for line in r.stdout.splitlines():
            if "FAIL" in line:
                print("        " + line.strip())
        check(r.returncode == 0, label)


def check_filters_against_scipy() -> None:
    for kind, fc in (("lowpass", 4.0), ("highpass", 0.7)):
        b_ref, a_ref = butter(2, fc, btype=kind, fs=30.0)
        b, a = (reference.butter_lowpass if kind == "lowpass" else reference.butter_highpass)(fc, 30.0)
        check(np.allclose(b, b_ref, atol=1e-12) and np.allclose(a, a_ref, atol=1e-12),
              f"Butterworth {kind} {fc} Hz matches scipy.signal.butter")


def run_cpp(t, rgb, tmp: Path, min_snr: float | None = None) -> list[dict]:
    src, out = tmp / "in.csv", tmp / "out.csv"
    write_csv(src, t, rgb)
    cmd = [str(BUILD / ("rppg_cli" + EXE)), str(src), str(out)]
    if min_snr is not None:
        cmd.append(str(min_snr))
    subprocess.run(cmd, check=True)
    keys = ["t", "bpm", "latest_bpm", "snr_db", "median_snr_db", "window_fill", "stable",
            "new_estimate", "estimate_count", "samples"]
    with out.open() as f:
        return [{k: float(v) for k, v in zip(keys, row)} for row in csv.reader(f)]


def evaluate(s: Scenario, rows: list[dict]) -> dict:
    t0 = rows[0]["t"]
    stable = [r for r in rows if r["stable"] >= 0.5]
    res = {"stable": bool(stable), "first_stable_s": None, "err_at_stable": None, "max_err_stable": None}
    if stable:
        first = stable[0]
        res["first_stable_s"] = first["t"] - t0
        # The window covers the last 10 s, so compare with the true rate at its centre.
        truth = lambda r: float(s.true_bpm(np.array([max(0.0, r["t"] - 5.0 - 5.0)]))[0])
        res["err_at_stable"] = abs(first["bpm"] - truth(first))
        res["max_err_stable"] = max(abs(r["bpm"] - truth(r)) for r in stable)
        res["bpm_at_stable"] = first["bpm"]
        res["snr_at_stable"] = first["median_snr_db"]
    res["final_bpm"] = rows[-1]["bpm"]
    res["max_median_snr"] = max(r["median_snr_db"] for r in rows)
    counts = [r["estimate_count"] for r in rows]
    restarts = [rows[i + 1]["t"] for i, (a, b) in enumerate(zip(counts, counts[1:])) if b < a]
    res["restarted"] = bool(restarts)
    if stable:
        # Time to a stable reading, counted from the last restart before it (face lost → start over).
        start = max([t0] + [t for t in restarts if t <= stable[0]["t"]])
        res["first_stable_s"] = stable[0]["t"] - start
    return res


def scenario_tests(quick: bool) -> None:
    print(f"\n{'scenario':30} {'stable':>6} {'t_stable':>8} {'bpm':>7} {'err':>5} {'maxerr':>6} {'snr':>6}")
    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        for s in SCENARIOS:
            t, rgb = generate(s)
            rows = run_cpp(t, rgb, tmp)
            e = evaluate(s, rows)
            fmt = lambda v, f: (f % v) if v is not None else "-"
            print(f"{s.name:30} {str(e['stable']):>6} {fmt(e['first_stable_s'], '%7.1fs'):>8} "
                  f"{fmt(e.get('bpm_at_stable'), '%7.1f'):>7} {fmt(e['err_at_stable'], '%5.1f'):>5} "
                  f"{fmt(e['max_err_stable'], '%6.1f'):>6} {e['max_median_snr']:6.1f}")
            x = s.expect
            if x.get("stable") is True:
                check(e["stable"], f"{s.name}: reaches a stable reading")
                if e["stable"]:
                    check(e["first_stable_s"] <= 16.0, f"{s.name}: stable within 16 s ({e['first_stable_s']:.1f} s)")
                    check(e["err_at_stable"] <= 3.0, f"{s.name}: BPM within ±3 at pass ({e['err_at_stable']:.1f})")
            if x.get("stable") is False:
                check(not e["stable"], f"{s.name}: never passes (no pulse)")
            if x.get("tracks"):
                check(e["stable"] and e["max_err_stable"] <= 5.0, f"{s.name}: tracks a changing heart rate")
            if x.get("never_wrong"):
                check(not e["stable"] or e["max_err_stable"] <= 5.0, f"{s.name}: never stable at a wrong BPM")
            if x.get("restarts"):
                check(e["restarted"], f"{s.name}: a 2 s face loss restarts the measurement")

            if not quick and s.name in ("still_72", "ramp_70_to_88", "face_lost_2s_80", "photo_noisy"):
                ref = reference.run(t, rgb)
                d_bpm = max(abs(a["bpm"] - b["bpm"]) for a, b in zip(rows, ref))
                d_snr = max(abs(a["median_snr_db"] - b["median_snr_db"]) for a, b in zip(rows, ref)
                            if b["median_snr_db"] > -90)
                same_stable = all((a["stable"] >= 0.5) == b["stable"] for a, b in zip(rows, ref))
                check(d_bpm < 0.05 and d_snr < 0.05 and same_stable,
                      f"{s.name}: C++ matches Python reference (Δbpm {d_bpm:.4f}, ΔSNR {d_snr:.4f} dB)")


DEFAULT_MIN_SNR_DB = 3.0  # keep in sync with RppgConfig.DEFAULT_MIN_SNR_DB and backend MIN_SNR_DB


def best_passing_snr(rows: list[dict]) -> float | None:
    """
    Run with min SNR disabled, so `stable` means "window full and 5 estimates
    agree". A scan passes at threshold T if, within the 30 s scan, some frame
    is stable with median SNR ≥ T. Returns the best such SNR (None = never).
    """
    snrs = [r["median_snr_db"] for r in rows if r["stable"] >= 0.5]
    return max(snrs) if snrs else None


def snr_calibration(trials: int) -> None:
    print(f"\nMonte-Carlo pass rates over {trials} random genuine / no-pulse scans (30 s each)")
    rng = np.random.default_rng(123)
    genuine, nopulse = [], []
    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        for i in range(trials):
            common = dict(duration_s=30, noise_std=float(rng.uniform(0.1, 0.4)),
                          motion_std=float(rng.uniform(0.001, 0.005)), seed=1000 + i)
            g = Scenario("g", bpm_start=float(rng.uniform(55, 110)),
                         pulse_amp=float(rng.uniform(0.002, 0.006)), **common)
            p = Scenario("p", pulse_amp=0.0, flicker_hz=float(rng.uniform(0.8, 2.5)),
                         flicker_amp=float(rng.uniform(0, 0.01)), **common)
            genuine.append(best_passing_snr(run_cpp(*generate(g), tmp, min_snr=-99)))
            nopulse.append(best_passing_snr(run_cpp(*generate(p), tmp, min_snr=-99)))

    def rate(values, t):
        return sum(v is not None and v >= t for v in values) / len(values)

    print("  MIN_SNR_DB   genuine pass   no-pulse (photo) pass")
    for t in (0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0):
        mark = "  ← default" if t == DEFAULT_MIN_SNR_DB else ""
        print(f"     {t:4.1f}        {rate(genuine, t):5.0%}          {rate(nopulse, t):5.0%}{mark}")
    check(rate(nopulse, DEFAULT_MIN_SNR_DB) == 0.0,
          f"no simulated photo passes at the default MIN_SNR_DB={DEFAULT_MIN_SNR_DB}")
    check(rate(genuine, DEFAULT_MIN_SNR_DB) >= 0.8,
          f"≥80% of simulated genuine scans pass at the default ({rate(genuine, DEFAULT_MIN_SNR_DB):.0%})")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--trials", type=int, default=40)
    args = ap.parse_args()

    print("Build")
    compile_cpp()
    print("\nUnit tests")
    run_unit_tests()
    print("\nFilters vs scipy")
    check_filters_against_scipy()
    print("\nScenarios (C++ engine)")
    scenario_tests(args.quick)
    snr_calibration(args.trials if not args.quick else 10)

    print("\n" + ("ALL PASSED" if not failures else f"{len(failures)} FAILED:\n  " + "\n  ".join(failures)))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
