// rPPG engine core — see rppg_core.h for the pipeline description.

#include "rppg_core.h"

#include <algorithm>
#include <cmath>
#include <numeric>

namespace rppg {

namespace {

constexpr double kPi = 3.14159265358979323846;

// YCbCr skin box (full-range chroma) and luma limits.
constexpr int kCrMin = 133, kCrMax = 173;
constexpr int kCbMin = 77, kCbMax = 127;
constexpr int kLumaMin = 30, kLumaGlare = 235;
constexpr double kMinSkinFraction = 0.25;

double mean(const std::vector<double>& v, size_t from, size_t to) {
    double s = 0;
    for (size_t i = from; i < to; ++i) s += v[i];
    return s / static_cast<double>(to - from);
}

double stddev(const std::vector<double>& v, double m) {
    double s = 0;
    for (double x : v) s += (x - m) * (x - m);
    return std::sqrt(s / static_cast<double>(v.size()));
}

void applyBiquad(const Biquad& q, std::vector<double>& x) {
    // Direct form II transposed, zero initial state.
    double z1 = 0, z2 = 0;
    for (double& v : x) {
        const double in = v;
        const double out = q.b0 * in + z1;
        z1 = q.b1 * in - q.a1 * out + z2;
        z2 = q.b2 * in - q.a2 * out;
        v = out;
    }
}

}  // namespace

// ── Skin colour extraction ──────────────────────────────────────────────

RgbMean meanSkinRgb(const PlaneView& y, const PlaneView& u, const PlaneView& v,
                    int width, int height, const Roi* rois, int nRois, int step) {
    RgbMean out;
    if (!y.data || !u.data || !v.data || nRois <= 0 || width <= 0 || height <= 0) return out;
    step = std::max(1, step);

    double skinY = 0, skinU = 0, skinV = 0;
    double allY = 0, allU = 0, allV = 0;
    long skinN = 0, allN = 0, sampled = 0;

    for (int k = 0; k < nRois; ++k) {
        const int x0 = std::max(0, rois[k].x);
        const int y0 = std::max(0, rois[k].y);
        const int x1 = std::min(width, rois[k].x + rois[k].w);
        const int y1 = std::min(height, rois[k].y + rois[k].h);
        for (int row = y0; row < y1; row += step) {
            const size_t yRow = static_cast<size_t>(row) * y.rowStride;
            const size_t uvRow = static_cast<size_t>(row / 2) * u.rowStride;
            for (int col = x0; col < x1; col += step) {
                const size_t yi = yRow + static_cast<size_t>(col) * y.pixelStride;
                const size_t uvi = uvRow + static_cast<size_t>(col / 2) * u.pixelStride;
                if (yi >= y.size || uvi >= u.size || uvi >= v.size) continue;
                const int Y = y.data[yi], Cb = u.data[uvi], Cr = v.data[uvi];
                ++sampled;
                if (Y >= kLumaGlare) continue;  // specular glare
                allY += Y; allU += Cb; allV += Cr; ++allN;
                if (Y >= kLumaMin && Cr >= kCrMin && Cr <= kCrMax && Cb >= kCbMin && Cb <= kCbMax) {
                    skinY += Y; skinU += Cb; skinV += Cr; ++skinN;
                }
            }
        }
    }
    if (sampled == 0 || allN == 0) return out;

    out.skinFraction = static_cast<double>(skinN) / static_cast<double>(sampled);
    double my, mu, mv;
    if (out.skinFraction >= kMinSkinFraction) {
        my = skinY / skinN; mu = skinU / skinN; mv = skinV / skinN; out.pixels = static_cast<int>(skinN);
    } else {
        my = allY / allN; mu = allU / allN; mv = allV / allN; out.pixels = static_cast<int>(allN);
    }
    // BT.601 full-range YCbCr → RGB. Linear, so converting the mean equals
    // the mean of the converted pixels.
    out.r = my + 1.402 * (mv - 128.0);
    out.g = my - 0.344136 * (mu - 128.0) - 0.714136 * (mv - 128.0);
    out.b = my + 1.772 * (mu - 128.0);
    out.valid = true;
    return out;
}

// ── Filters ─────────────────────────────────────────────────────────────

Biquad butterworthLowpass(double cutoffHz, double fs) {
    const double w0 = 2.0 * kPi * cutoffHz / fs;
    const double c = std::cos(w0), alpha = std::sin(w0) / (2.0 * std::sqrt(0.5));
    const double a0 = 1.0 + alpha;
    return {(1.0 - c) / 2.0 / a0, (1.0 - c) / a0, (1.0 - c) / 2.0 / a0, -2.0 * c / a0, (1.0 - alpha) / a0};
}

Biquad butterworthHighpass(double cutoffHz, double fs) {
    const double w0 = 2.0 * kPi * cutoffHz / fs;
    const double c = std::cos(w0), alpha = std::sin(w0) / (2.0 * std::sqrt(0.5));
    const double a0 = 1.0 + alpha;
    return {(1.0 + c) / 2.0 / a0, -(1.0 + c) / a0, (1.0 + c) / 2.0 / a0, -2.0 * c / a0, (1.0 - alpha) / a0};
}

std::vector<double> filtfilt(const std::vector<Biquad>& sections, const std::vector<double>& x, int pad) {
    const int n = static_cast<int>(x.size());
    if (n < 2) return x;
    pad = std::max(0, std::min(pad, n - 1));
    // Odd reflection about the end points keeps the signal continuous in value
    // and slope, which keeps filter start-up transients out of the data.
    std::vector<double> ext;
    ext.reserve(n + 2 * pad);
    for (int i = pad; i >= 1; --i) ext.push_back(2.0 * x[0] - x[i]);
    ext.insert(ext.end(), x.begin(), x.end());
    for (int i = n - 2; i >= n - 1 - pad; --i) ext.push_back(2.0 * x[n - 1] - x[i]);

    for (const Biquad& q : sections) applyBiquad(q, ext);
    std::reverse(ext.begin(), ext.end());
    for (const Biquad& q : sections) applyBiquad(q, ext);
    std::reverse(ext.begin(), ext.end());
    return std::vector<double>(ext.begin() + pad, ext.begin() + pad + n);
}

// ── Signal shaping ──────────────────────────────────────────────────────

std::vector<double> resampleUniform(const std::vector<double>& t, const std::vector<double>& v,
                                    double t0, double fs, int n) {
    std::vector<double> out(std::max(0, n));
    if (t.empty() || n <= 0) return out;
    size_t j = 0;
    for (int i = 0; i < n; ++i) {
        const double ti = t0 + i / fs;
        while (j + 1 < t.size() && t[j + 1] < ti) ++j;
        // Now t[j] < ti <= t[j + 1], unless ti is outside the sampled range.
        if (ti <= t[0]) { out[i] = v[0]; continue; }
        if (j + 1 >= t.size()) { out[i] = v.back(); continue; }
        const double span = t[j + 1] - t[j];
        const double a = span > 1e-9 ? (ti - t[j]) / span : 0.0;
        out[i] = v[j] + a * (v[j + 1] - v[j]);
    }
    return out;
}

std::vector<double> pos(const std::vector<double>& r, const std::vector<double>& g,
                        const std::vector<double>& b, int l) {
    const size_t n = r.size();
    std::vector<double> h(n, 0.0);
    if (n == 0 || l < 2 || static_cast<size_t>(l) > n) return h;
    std::vector<double> s1(l), s2(l);
    for (size_t end = static_cast<size_t>(l); end <= n; ++end) {
        const size_t m = end - l;
        const double mr = mean(r, m, end), mg = mean(g, m, end), mb = mean(b, m, end);
        if (mr <= 1e-9 || mg <= 1e-9 || mb <= 1e-9) continue;
        for (int k = 0; k < l; ++k) {
            const double rn = r[m + k] / mr, gn = g[m + k] / mg, bn = b[m + k] / mb;
            s1[k] = gn - bn;              // projection 1: (0, 1, -1)
            s2[k] = gn + bn - 2.0 * rn;   // projection 2: (-2, 1, 1)
        }
        const double m1 = mean(s1, 0, l), m2 = mean(s2, 0, l);
        const double sd2 = stddev(s2, m2);
        const double alpha = sd2 > 1e-12 ? stddev(s1, m1) / sd2 : 0.0;
        double hm = 0;
        for (int k = 0; k < l; ++k) hm += s1[k] + alpha * s2[k];
        hm /= l;
        for (int k = 0; k < l; ++k) h[m + k] += (s1[k] + alpha * s2[k]) - hm;
    }
    return h;
}

void detrendLinear(std::vector<double>& x) {
    const size_t n = x.size();
    if (n < 2) return;
    const double tm = static_cast<double>(n - 1) / 2.0;
    const double xm = mean(x, 0, n);
    double num = 0, den = 0;
    for (size_t i = 0; i < n; ++i) {
        const double d = static_cast<double>(i) - tm;
        num += d * (x[i] - xm);
        den += d * d;
    }
    const double slope = den > 0 ? num / den : 0.0;
    for (size_t i = 0; i < n; ++i) x[i] -= xm + slope * (static_cast<double>(i) - tm);
}

// ── Spectrum ────────────────────────────────────────────────────────────

Spectrum bandSpectrum(const std::vector<double>& x, double fs, double fLow, double fHigh, double stepHz) {
    Spectrum s;
    const size_t n = x.size();
    if (n < 4 || stepHz <= 0 || fHigh <= fLow) return s;
    std::vector<double> xw(n);
    for (size_t i = 0; i < n; ++i) {
        const double w = 0.5 - 0.5 * std::cos(2.0 * kPi * static_cast<double>(i) / static_cast<double>(n - 1));  // Hann
        xw[i] = x[i] * w;
    }
    const int bins = static_cast<int>(std::floor((fHigh - fLow) / stepHz + 1e-9)) + 1;
    s.freqs.resize(bins);
    s.power.resize(bins);
    for (int k = 0; k < bins; ++k) {
        const double f = fLow + k * stepHz;
        const double w = 2.0 * kPi * f / fs;
        // Rotate a unit phasor instead of calling sin/cos per sample.
        const double cr = std::cos(w), ci = -std::sin(w);
        double pr = 1.0, pi = 0.0, re = 0.0, im = 0.0;
        for (size_t i = 0; i < n; ++i) {
            re += xw[i] * pr;
            im += xw[i] * pi;
            const double nr = pr * cr - pi * ci;
            pi = pr * ci + pi * cr;
            pr = nr;
        }
        s.freqs[k] = f;
        s.power[k] = re * re + im * im;
    }
    return s;
}

double peakFrequency(const Spectrum& s) {
    if (s.power.empty()) return 0.0;
    const size_t k = static_cast<size_t>(
        std::max_element(s.power.begin(), s.power.end()) - s.power.begin());
    double f = s.freqs[k];
    if (k > 0 && k + 1 < s.power.size()) {
        const double y1 = s.power[k - 1], y2 = s.power[k], y3 = s.power[k + 1];
        const double den = y1 - 2.0 * y2 + y3;
        if (std::abs(den) > 1e-18) {
            const double step = s.freqs[1] - s.freqs[0];
            f += std::clamp(0.5 * (y1 - y3) / den, -0.5, 0.5) * step;
        }
    }
    return f;
}

double snrDb(const Spectrum& s, double f0, double halfWidthHz) {
    double sig = 0, noise = 0;
    for (size_t k = 0; k < s.power.size(); ++k) {
        const double f = s.freqs[k];
        if (std::abs(f - f0) <= halfWidthHz || std::abs(f - 2.0 * f0) <= halfWidthHz) sig += s.power[k];
        else noise += s.power[k];
    }
    if (sig <= 0) return -99.0;
    if (noise <= 0) return 99.0;
    return 10.0 * std::log10(sig / noise);
}

double median(std::vector<double> v) {
    if (v.empty()) return 0.0;
    const size_t mid = v.size() / 2;
    std::nth_element(v.begin(), v.begin() + mid, v.end());
    if (v.size() % 2 == 1) return v[mid];
    const double hi = v[mid];
    const double lo = *std::max_element(v.begin(), v.begin() + mid);
    return (lo + hi) / 2.0;
}

// ── Engine ──────────────────────────────────────────────────────────────

Engine::Engine(const Config& config) : cfg_(config) {}

void Engine::configure(const Config& config) {
    cfg_ = config;
    reset();
}

void Engine::reset() {
    samples_.clear();
    estimates_.clear();
    waveform_.clear();
    lastEstimateT_ = -1e9;
    estimateCount_ = 0;
}

void Engine::addSample(double t, double r, double g, double b) {
    if (!std::isfinite(t) || !std::isfinite(r) || !std::isfinite(g) || !std::isfinite(b)) return;
    if (!samples_.empty()) {
        if (t <= samples_.back().t) return;
        if (t - samples_.back().t > cfg_.maxGapSec) reset();
    }
    samples_.push_back({t, r, g, b});
    while (!samples_.empty() && samples_.front().t < t - cfg_.windowSec) samples_.pop_front();
}

Status Engine::update() {
    Status st;
    st.samplesInWindow = static_cast<int>(samples_.size());
    st.estimateCount = estimateCount_;
    if (samples_.size() < 2) return st;

    const double t0 = samples_.front().t, t1 = samples_.back().t;
    const double span = t1 - t0;
    st.windowFill = std::clamp(span / cfg_.windowSec, 0.0, 1.0);

    const int posLen = static_cast<int>(std::lround(cfg_.posWindowSec * cfg_.fs));
    const int n = static_cast<int>(std::floor(span * cfg_.fs)) + 1;
    if (n >= std::max(posLen, 2 * static_cast<int>(cfg_.fs))) {
        std::vector<double> ts, rs, gs, bs;
        ts.reserve(samples_.size()); rs.reserve(samples_.size());
        gs.reserve(samples_.size()); bs.reserve(samples_.size());
        for (const Sample& s : samples_) {
            ts.push_back(s.t); rs.push_back(s.r); gs.push_back(s.g); bs.push_back(s.b);
        }
        const std::vector<double> r = resampleUniform(ts, rs, t0, cfg_.fs, n);
        const std::vector<double> g = resampleUniform(ts, gs, t0, cfg_.fs, n);
        const std::vector<double> b = resampleUniform(ts, bs, t0, cfg_.fs, n);
        std::vector<double> h = pos(r, g, b, posLen);
        detrendLinear(h);
        const std::vector<Biquad> band = {butterworthHighpass(cfg_.bandLowHz, cfg_.fs),
                                          butterworthLowpass(cfg_.bandHighHz, cfg_.fs)};
        const std::vector<double> filtered = filtfilt(band, h, std::min(n - 1, static_cast<int>(cfg_.fs)));

        // Waveform for display: the last waveformSec, scaled to [-1, 1].
        const int wn = std::min(n, static_cast<int>(cfg_.waveformSec * cfg_.fs));
        waveform_.assign(filtered.end() - wn, filtered.end());
        double peak = 0;
        for (double x : waveform_) peak = std::max(peak, std::abs(x));
        if (peak > 1e-12) for (double& x : waveform_) x /= peak;

        if (span >= cfg_.minEstimateSec && t1 - lastEstimateT_ >= cfg_.estimateIntervalSec) {
            const Spectrum spec = bandSpectrum(filtered, cfg_.fs, cfg_.bandLowHz, cfg_.bandHighHz,
                                               cfg_.spectrumStepBpm / 60.0);
            const double f0 = peakFrequency(spec);
            // Hann main-lobe half-width = 2 / window length.
            const double halfWidth = 2.0 / (n / cfg_.fs);
            estimates_.push_back({t1, f0 * 60.0, snrDb(spec, f0, halfWidth)});
            while (static_cast<int>(estimates_.size()) > cfg_.stableCount) estimates_.pop_front();
            lastEstimateT_ = t1;
            ++estimateCount_;
            st.newEstimate = true;
        }
    }

    st.estimateCount = estimateCount_;
    if (!estimates_.empty()) {
        std::vector<double> bpms, snrs;
        for (const Estimate& e : estimates_) { bpms.push_back(e.bpm); snrs.push_back(e.snrDb); }
        st.bpm = median(bpms);
        st.latestBpm = estimates_.back().bpm;
        st.snrDb = estimates_.back().snrDb;
        st.medianSnrDb = median(snrs);
        bool agree = static_cast<int>(estimates_.size()) >= cfg_.stableCount;
        for (double bpm : bpms) agree = agree && std::abs(bpm - st.bpm) <= cfg_.stableToleranceBpm;
        st.stable = agree && st.windowFill >= cfg_.minWindowFill && st.medianSnrDb >= cfg_.minSnrDb;
    }
    return st;
}

}  // namespace rppg
