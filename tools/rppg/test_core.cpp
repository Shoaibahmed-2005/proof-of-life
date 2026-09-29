// Unit tests for the rPPG core building blocks. Built and run by run_tests.py.

#include <cmath>
#include <complex>
#include <cstdio>
#include <random>
#include <vector>

#include "rppg_core.h"

using namespace rppg;

static int g_failures = 0;
#define CHECK(cond, ...)                                                   \
    do {                                                                   \
        if (!(cond)) {                                                     \
            ++g_failures;                                                  \
            std::printf("  FAIL %s:%d: %s — ", __FILE__, __LINE__, #cond); \
            std::printf(__VA_ARGS__);                                      \
            std::printf("\n");                                             \
        }                                                                  \
    } while (0)

static const double PI = 3.14159265358979323846;

static double gainAt(const Biquad& q, double f, double fs) {
    const std::complex<double> z = std::polar(1.0, -2.0 * PI * f / fs);  // z^-1
    const std::complex<double> num = q.b0 + q.b1 * z + q.b2 * z * z;
    const std::complex<double> den = 1.0 + q.a1 * z + q.a2 * z * z;
    return std::abs(num / den);
}

static std::vector<double> sine(double f, double fs, int n, double amp = 1.0) {
    std::vector<double> x(n);
    for (int i = 0; i < n; ++i) x[i] = amp * std::sin(2 * PI * f * i / fs);
    return x;
}

static double rms(const std::vector<double>& x, int from, int to) {
    double s = 0;
    for (int i = from; i < to; ++i) s += x[i] * x[i];
    return std::sqrt(s / (to - from));
}

static void testButterworth() {
    std::printf("butterworth\n");
    const double fs = 30;
    const Biquad lp = butterworthLowpass(4.0, fs), hp = butterworthHighpass(0.7, fs);
    CHECK(std::abs(gainAt(lp, 0.0, fs) - 1.0) < 1e-9, "LP DC gain %f", gainAt(lp, 0, fs));
    CHECK(std::abs(gainAt(lp, 4.0, fs) - std::sqrt(0.5)) < 1e-6, "LP -3dB at fc: %f", gainAt(lp, 4.0, fs));
    CHECK(std::abs(gainAt(hp, 0.7, fs) - std::sqrt(0.5)) < 1e-6, "HP -3dB at fc: %f", gainAt(hp, 0.7, fs));
    CHECK(gainAt(hp, 0.0, fs) < 1e-9, "HP DC gain %f", gainAt(hp, 0.0, fs));
    CHECK(std::abs(gainAt(hp, 15.0, fs) - 1.0) < 1e-9, "HP Nyquist gain %f", gainAt(hp, 15.0, fs));
}

static void testFiltfiltBand() {
    std::printf("filtfilt band-pass\n");
    const double fs = 30;
    const int n = 300;
    const std::vector<Biquad> band = {butterworthHighpass(0.7, fs), butterworthLowpass(4.0, fs)};
    auto passRatio = [&](double f) {
        const auto x = sine(f, fs, n);
        const auto y = filtfilt(band, x, 30);
        return rms(y, 60, 240) / rms(x, 60, 240);  // ignore the edges
    };
    CHECK(passRatio(1.2) > 0.85, "1.2 Hz (72 BPM) should pass: %f", passRatio(1.2));
    CHECK(passRatio(2.5) > 0.85, "2.5 Hz should pass (theory: 0.93^2 = 0.87): %f", passRatio(2.5));
    CHECK(passRatio(0.15) < 0.05, "0.15 Hz drift should be removed: %f", passRatio(0.15));
    CHECK(passRatio(10.0) < 0.1, "10 Hz noise should be removed: %f", passRatio(10.0));

    // Zero phase: the filtered 1.2 Hz sine lines up with the input (no lag).
    const auto x = sine(1.2, fs, n);
    const auto y = filtfilt(band, x, 30);
    double best = -1e9;
    int bestLag = 99;
    for (int lag = -5; lag <= 5; ++lag) {
        double c = 0;
        for (int i = 60; i < 240; ++i) c += x[i] * y[i + lag];
        if (c > best) { best = c; bestLag = lag; }
    }
    CHECK(bestLag == 0, "phase lag %d samples", bestLag);
}

static void testResampleAndDetrend() {
    std::printf("resample / detrend / median\n");
    std::vector<double> t = {0.0, 0.031, 0.070, 0.100, 0.135};
    std::vector<double> v;
    for (double ti : t) v.push_back(3.0 * ti + 1.0);
    const auto r = resampleUniform(t, v, 0.0, 30.0, 5);
    for (int i = 0; i < 4; ++i) CHECK(std::abs(r[i] - (3.0 * i / 30.0 + 1.0)) < 1e-9, "resample[%d]=%f", i, r[i]);

    std::vector<double> x;
    for (int i = 0; i < 100; ++i) x.push_back(0.5 * i + 7.0);
    detrendLinear(x);
    double m = 0;
    for (double xi : x) m = std::max(m, std::abs(xi));
    CHECK(m < 1e-9, "a pure line detrends to zero: %g", m);

    CHECK(median({3, 1, 2}) == 2, "odd median");
    CHECK(median({4, 1, 3, 2}) == 2.5, "even median");
}

static void testPosRejectsBrightnessChanges() {
    std::printf("POS\n");
    const int n = 300;
    std::vector<double> r(n), g(n), b(n);
    // Pure illumination change: every channel scaled together → no pulse.
    for (int i = 0; i < n; ++i) {
        const double k = 1.0 + 0.05 * std::sin(2 * PI * 1.2 * i / 30.0);
        r[i] = 180 * k; g[i] = 130 * k; b[i] = 110 * k;
    }
    auto h = pos(r, g, b, 48);
    CHECK(rms(h, 0, n) < 1e-9, "brightness-only change leaks into POS: %g", rms(h, 0, n));

    // Blood-volume pulse (green-dominant signature) → strong POS output.
    for (int i = 0; i < n; ++i) {
        const double p = 0.004 * std::sin(2 * PI * 1.2 * i / 30.0);
        r[i] = 180 * (1 + 0.33 * p); g[i] = 130 * (1 + 0.77 * p); b[i] = 110 * (1 + 0.53 * p);
    }
    h = pos(r, g, b, 48);
    CHECK(rms(h, 48, n - 48) > 1e-3, "pulse lost in POS: %g", rms(h, 48, n - 48));
}

static void testSpectrumAndSnr() {
    std::printf("spectrum / SNR\n");
    const double fs = 30;
    const auto x = sine(1.25, fs, 300);  // 75 BPM
    const Spectrum s = bandSpectrum(x, fs, 0.7, 4.0, 0.5 / 60.0);
    const double f0 = peakFrequency(s);
    CHECK(std::abs(f0 * 60 - 75.0) < 0.5, "peak %f BPM", f0 * 60);
    CHECK(snrDb(s, f0, 0.2) > 15.0, "clean sine SNR %f dB", snrDb(s, f0, 0.2));

    std::mt19937 rng(42);
    std::normal_distribution<double> nd(0, 1);
    double sum = 0;
    for (int trial = 0; trial < 50; ++trial) {
        std::vector<double> w(300);
        for (double& v : w) v = nd(rng);
        const std::vector<Biquad> band = {butterworthHighpass(0.7, fs), butterworthLowpass(4.0, fs)};
        const Spectrum sn = bandSpectrum(filtfilt(band, w, 30), fs, 0.7, 4.0, 0.5 / 60.0);
        sum += snrDb(sn, peakFrequency(sn), 0.2);
    }
    CHECK(sum / 50 < 0.0, "band-limited noise mean SNR %f dB should be below 0", sum / 50);
}

// Builds a YUV_420_888 image laid out like an NV21 camera buffer
// (interleaved V/U, pixelStride 2), with optional row padding.
struct TestImage {
    int w, h, rowStride;
    std::vector<uint8_t> yPlane, vu;
    PlaneView y() const { return {yPlane.data(), yPlane.size(), rowStride, 1}; }
    PlaneView v() const { return {vu.data(), vu.size(), rowStride, 2}; }
    PlaneView u() const { return {vu.data() + 1, vu.size() - 1, rowStride, 2}; }
};

static TestImage makeImage(int w, int h, int pad) {
    TestImage img{w, h, w + pad, {}, {}};
    img.yPlane.assign(static_cast<size_t>(img.rowStride) * h, 0);
    // Last chroma row is shorter in real buffers: size = rowStride*(h/2-1) + w - 1 for U.
    img.vu.assign(static_cast<size_t>(img.rowStride) * (h / 2 - 1) + w, 0);
    return img;
}

static void paint(TestImage& img, int x0, int y0, int x1, int y1, uint8_t Y, uint8_t Cb, uint8_t Cr) {
    for (int r = y0; r < y1; ++r)
        for (int c = x0; c < x1; ++c) {
            img.yPlane[static_cast<size_t>(r) * img.rowStride + c] = Y;
            const size_t uv = static_cast<size_t>(r / 2) * img.rowStride + (c / 2) * 2;
            img.vu[uv] = Cr;
            if (uv + 1 < img.vu.size()) img.vu[uv + 1] = Cb;
        }
}

static void testSkinExtraction() {
    std::printf("skin extraction from YUV planes\n");
    for (int pad : {0, 16}) {
        TestImage img = makeImage(64, 48, pad);
        paint(img, 0, 0, 64, 48, 60, 150, 110);    // background: bluish, not skin
        paint(img, 16, 12, 48, 36, 150, 110, 150); // skin patch
        const Roi roi{8, 8, 48, 32};                // covers skin and some background
        const RgbMean m = meanSkinRgb(img.y(), img.u(), img.v(), img.w, img.h, &roi, 1);
        const double er = 150 + 1.402 * 22, eg = 150 - 0.344136 * (-18) - 0.714136 * 22, eb = 150 + 1.772 * (-18);
        CHECK(m.valid, "pad %d: invalid", pad);
        CHECK(std::abs(m.r - er) < 1e-6 && std::abs(m.g - eg) < 1e-6 && std::abs(m.b - eb) < 1e-6,
              "pad %d: skin-only mean (%f,%f,%f) expected (%f,%f,%f)", pad, m.r, m.g, m.b, er, eg, eb);
        CHECK(m.skinFraction > 0.4 && m.skinFraction < 0.8, "pad %d: skin fraction %f", pad, m.skinFraction);

        // ROI hanging off the image edge, touching the last (short) chroma row: no out-of-bounds read.
        const Roi edge{40, 30, 100, 100};
        const RgbMean e = meanSkinRgb(img.y(), img.u(), img.v(), img.w, img.h, &edge, 1, 1);
        CHECK(e.valid, "pad %d: edge ROI should still produce a mean", pad);
    }
    // Glare (Y ≥ 235) is ignored.
    TestImage img = makeImage(32, 32, 0);
    paint(img, 0, 0, 32, 32, 150, 110, 150);
    paint(img, 0, 0, 32, 8, 250, 110, 150);
    const Roi all{0, 0, 32, 32};
    const RgbMean m = meanSkinRgb(img.y(), img.u(), img.v(), 32, 32, &all, 1);
    CHECK(std::abs((m.r + m.g + m.b) / 3 - 150) < 20, "glare should be excluded, mean %f", (m.r + m.g + m.b) / 3);
    // Multiple ROIs are pooled.
    const Roi two[2] = {{0, 8, 16, 8}, {16, 16, 16, 8}};
    CHECK(meanSkinRgb(img.y(), img.u(), img.v(), 32, 32, two, 2).pixels == 64, "two ROIs pooled");
    // Null data is safe.
    const PlaneView none{nullptr, 0, 0, 0};
    CHECK(!meanSkinRgb(none, none, none, 32, 32, &all, 1).valid, "null planes");
}

static void testEngineGapsAndOrder() {
    std::printf("engine gaps / ordering\n");
    Engine e;
    for (int i = 0; i < 90; ++i) e.addSample(i / 30.0, 180, 130, 110);
    CHECK(e.update().samplesInWindow == 90, "90 samples");
    e.addSample(1.0, 180, 130, 110);  // older timestamp → ignored
    CHECK(e.update().samplesInWindow == 90, "out-of-order sample ignored");
    e.addSample(10.0, 180, 130, 110); // > maxGapSec later → restart
    const Status s = e.update();
    CHECK(s.samplesInWindow == 1 && s.estimateCount == 0, "gap restarts the scan (%d samples)", s.samplesInWindow);
    e.addSample(10.03, NAN, 1, 1);
    CHECK(e.update().samplesInWindow == 1, "NaN sample ignored");
}

int main() {
    testButterworth();
    testFiltfiltBand();
    testResampleAndDetrend();
    testPosRejectsBrightnessChanges();
    testSpectrumAndSnr();
    testSkinExtraction();
    testEngineGapsAndOrder();
    if (g_failures) {
        std::printf("%d check(s) FAILED\n", g_failures);
        return 1;
    }
    std::printf("all C++ unit tests passed\n");
    return 0;
}
