// rPPG engine core: pure C++17, no JNI / OpenCV / Android dependencies, so it
// compiles and is unit-tested on a laptop (tools/rppg/). native-lib.cpp is the
// thin JNI layer around it.
//
// Pipeline (per frame):
//   skin pixels inside the face ROIs (read straight from the YUV planes)
//   → mean RGB sample (timestamped)
// Pipeline (analysis, over the last `windowSec` seconds):
//   resample to `fs` Hz → POS (Wang et al. 2017, 1.6 s overlap-add)
//   → linear detrend → zero-phase Butterworth band-pass 0.7–4 Hz (filtfilt)
//   → Hann-windowed spectrum on a 0.5 BPM grid → peak = heart rate
//   → SNR in dB (de Haan & Jeanne 2013: power around f0 and 2·f0 vs the rest)
// Every `estimateIntervalSec` a new estimate is stored; the reading is
// "stable" when the window is full, the last `stableCount` estimates agree
// within ±`stableToleranceBpm`, and their median SNR ≥ `minSnrDb`.

#pragma once

#include <cstddef>
#include <cstdint>
#include <deque>
#include <vector>

namespace rppg {

struct Config {
    double windowSec = 10.0;          // analysis window
    double fs = 30.0;                 // resampling rate (Hz)
    double bandLowHz = 0.7;           // 42 BPM
    double bandHighHz = 4.0;          // 240 BPM
    double posWindowSec = 1.6;        // POS sub-window
    double minEstimateSec = 5.0;      // first estimate needs this much signal
    double estimateIntervalSec = 0.5; // estimates per second = 2
    int stableCount = 5;              // estimates that must agree
    double stableToleranceBpm = 3.0;  // ± around their median
    double minSnrDb = 3.0;            // required median SNR (calibrate!)
    double minWindowFill = 0.95;      // fraction of windowSec before "stable"
    double maxGapSec = 1.0;           // a longer gap (face lost) restarts the scan
    double spectrumStepBpm = 0.5;     // spectrum grid resolution
    double waveformSec = 5.0;         // length of the waveform shown on screen
};

struct Roi {
    int x, y, w, h;  // in sensor (unrotated image) coordinates
};

struct PlaneView {
    const uint8_t* data;
    size_t size;
    int rowStride;
    int pixelStride;
};

struct RgbMean {
    double r = 0, g = 0, b = 0;
    int pixels = 0;           // pixels used
    double skinFraction = 0;  // share of sampled pixels that passed the skin test
    bool valid = false;
};

// Mean RGB of the skin pixels inside the ROIs of a YUV_420_888 image.
// Skin = chroma in the classic YCbCr skin box and luma away from black/glare;
// if too few pixels pass (unusual light), all non-glare pixels are used.
RgbMean meanSkinRgb(const PlaneView& y, const PlaneView& u, const PlaneView& v,
                    int width, int height, const Roi* rois, int nRois, int step = 2);

struct Status {
    double bpm = 0;           // median of recent estimates (0 = none yet)
    double latestBpm = 0;     // most recent estimate
    double snrDb = -99;       // most recent estimate's SNR
    double medianSnrDb = -99; // median SNR of recent estimates
    double windowFill = 0;    // 0..1 of windowSec
    bool stable = false;
    bool newEstimate = false; // an estimate was made on this update
    int estimateCount = 0;    // since the last reset
    int samplesInWindow = 0;
};

class Engine {
public:
    explicit Engine(const Config& config = Config());

    void configure(const Config& config);
    const Config& config() const { return cfg_; }
    void reset();

    // Adds a colour sample. Non-increasing timestamps are ignored; a gap
    // longer than maxGapSec restarts the scan.
    void addSample(double t, double r, double g, double b);

    // Recomputes the filtered signal and, when due, a new estimate.
    Status update();

    // Last `waveformSec` of the band-passed pulse signal, scaled to [-1, 1].
    const std::vector<double>& waveform() const { return waveform_; }

private:
    struct Sample { double t, r, g, b; };
    struct Estimate { double t, bpm, snrDb; };

    Config cfg_;
    std::deque<Sample> samples_;
    std::deque<Estimate> estimates_;
    std::vector<double> waveform_;
    double lastEstimateT_ = -1e9;
    int estimateCount_ = 0;
};

// ── DSP building blocks (exposed for tests) ─────────────────────────────

struct Biquad {
    double b0, b1, b2, a1, a2;  // normalised (a0 = 1)
};

Biquad butterworthLowpass(double cutoffHz, double fs);
Biquad butterworthHighpass(double cutoffHz, double fs);

// Zero-phase filtering (forward + backward) with odd-reflection padding.
std::vector<double> filtfilt(const std::vector<Biquad>& sections, const std::vector<double>& x, int pad);

// Linear interpolation of (t, v) onto n points starting at t0 with rate fs.
std::vector<double> resampleUniform(const std::vector<double>& t, const std::vector<double>& v,
                                    double t0, double fs, int n);

// Plane-Orthogonal-to-Skin pulse signal (overlap-add over windows of l samples).
std::vector<double> pos(const std::vector<double>& r, const std::vector<double>& g,
                        const std::vector<double>& b, int l);

void detrendLinear(std::vector<double>& x);

struct Spectrum {
    std::vector<double> freqs;  // Hz
    std::vector<double> power;
};

// Hann-windowed power spectrum evaluated directly on a frequency grid.
Spectrum bandSpectrum(const std::vector<double>& x, double fs, double fLow, double fHigh, double stepHz);

// Peak frequency (parabolic refinement on the grid).
double peakFrequency(const Spectrum& s);

// 10·log10(power within ±halfWidth of f0 and 2·f0 / power elsewhere in the band).
double snrDb(const Spectrum& s, double f0, double halfWidthHz);

double median(std::vector<double> v);

}  // namespace rppg
