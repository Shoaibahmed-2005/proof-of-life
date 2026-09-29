// Unit tests for face alignment and template averaging (face_core.cpp).

#include <cmath>
#include <cstdio>
#include <functional>
#include <vector>

#include "face_core.h"

using namespace face;

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

// A camera frame in SENSOR orientation, built from an UPRIGHT scene function.
struct Frame {
    int w, h, rotation;
    std::vector<uint8_t> y, u, v;
    rppg::PlaneView Y() const { return {y.data(), y.size(), w, 1}; }
    rppg::PlaneView U() const { return {u.data(), u.size(), w / 2, 1}; }
    rppg::PlaneView V() const { return {v.data(), v.size(), w / 2, 1}; }
};

using Scene = std::function<double(double ux, double uy)>;  // luma of the upright scene

static void sensorToUpright(double sx, double sy, int w, int h, int rot, double& ux, double& uy) {
    switch (rot) {
        case 90:  ux = (h - 1) - sy; uy = sx; break;
        case 180: ux = (w - 1) - sx; uy = (h - 1) - sy; break;
        case 270: ux = sy; uy = (w - 1) - sx; break;
        default:  ux = sx; uy = sy; break;
    }
}

// Sensor size for an upright scene of uw × uh at this rotation.
static Frame makeFrame(const Scene& scene, int uw, int uh, int rot) {
    const bool swapped = rot == 90 || rot == 270;
    Frame f{swapped ? uh : uw, swapped ? uw : uh, rot, {}, {}, {}};
    f.y.resize(static_cast<size_t>(f.w) * f.h);
    f.u.assign(static_cast<size_t>(f.w / 2) * (f.h / 2), 128);  // grey: chroma can't differ between rotations
    f.v.assign(f.u.size(), 128);
    for (int sy = 0; sy < f.h; ++sy)
        for (int sx = 0; sx < f.w; ++sx) {
            double ux, uy;
            sensorToUpright(sx, sy, f.w, f.h, rot, ux, uy);
            const double val = scene(ux, uy);
            f.y[static_cast<size_t>(sy) * f.w + sx] = static_cast<uint8_t>(std::lround(std::fmin(255, std::fmax(0, val))));
        }
    return f;
}

static std::vector<float> align(const Frame& f, double ax, double ay, double bx, double by, AlignResult* res = nullptr) {
    std::vector<float> out(kTensorLength, 0.0f);
    const AlignResult r = alignFace(f.Y(), f.U(), f.V(), f.w, f.h, f.rotation, ax, ay, bx, by, out.data());
    if (res) *res = r;
    return out;
}

static double maxDiff(const std::vector<float>& a, const std::vector<float>& b) {
    double m = 0;
    for (size_t i = 0; i < a.size(); ++i) m = std::fmax(m, std::fabs(a[i] - b[i]));
    return m;
}

static double meanDiff(const std::vector<float>& a, const std::vector<float>& b) {
    double s = 0;
    for (size_t i = 0; i < a.size(); ++i) s += std::fabs(a[i] - b[i]);
    return s / static_cast<double>(a.size());
}

// Smooth "face-like" scene: vertical gradient + bright blob + dark eyes.
static double faceScene(double x, double y) {
    const double blob = 90 * std::exp(-((x - 240) * (x - 240) + (y - 380) * (y - 380)) / (2 * 30.0 * 30.0));
    const double eyes = -70 * std::exp(-((x - 200) * (x - 200) + (y - 300) * (y - 300)) / 200.0)
                        - 70 * std::exp(-((x - 280) * (x - 280) + (y - 300) * (y - 300)) / 200.0);
    return 80 + 0.15 * y + 0.05 * x + blob + eyes;
}

static void testRotationsGiveIdenticalCrops() {
    std::printf("alignment: same crop for sensor rotations 0/90/180/270\n");
    const int uw = 480, uh = 640;  // portrait upright image (front camera, rotation 270 on phones)
    std::vector<float> ref;
    for (int rot : {0, 90, 180, 270}) {
        const Frame f = makeFrame(faceScene, uw, uh, rot);
        AlignResult r;
        const auto crop = align(f, 200, 300, 280, 300, &r);
        CHECK(r.ok, "rotation %d not ok", rot);
        if (ref.empty()) ref = crop;
        // Differences of at most one grey level (1/127.5) come from rounding in the
        // interpolation; a wrong rotation mapping would differ by tens of levels.
        else CHECK(maxDiff(ref, crop) <= 1.0 / 127.5 + 1e-6, "rotation %d differs by %f", rot, maxDiff(ref, crop));
    }
}

static void testEyeOrderAndCentre() {
    std::printf("alignment: eye order, centre, bounds\n");
    const Frame f = makeFrame(faceScene, 480, 640, 270);
    CHECK(maxDiff(align(f, 200, 300, 280, 300), align(f, 280, 300, 200, 300)) == 0.0, "eye order changes the crop");

    // The crop centre is 0.15 × side below the eye midpoint: side = 2.5 × 80 = 200 → (240, 330).
    // A bright dot placed exactly there must land in the middle of the crop.
    const Scene dot = [](double x, double y) { return (std::fabs(x - 240) < 3 && std::fabs(y - 330) < 3) ? 250.0 : 40.0; };
    const auto crop = align(makeFrame(dot, 480, 640, 270), 200, 300, 280, 300);
    const float centre = crop[(static_cast<size_t>(kSize / 2) * kSize + kSize / 2) * 3];
    const float corner = crop[(static_cast<size_t>(5) * kSize + 5) * 3];
    CHECK(centre > 0.8f && corner < -0.5f, "centre %f corner %f", centre, corner);

    AlignResult r;
    align(f, 200, 300, 204, 300, &r);
    CHECK(!r.ok, "eyes 4 px apart should be rejected");
    // Face near the edge: crop partly outside the image → black fill, no crash.
    const auto edge = align(f, 5, 10, 85, 10, &r);
    CHECK(r.ok && edge[0] == -1.0f, "outside pixels should be black (-1)");
}

static void testTiltIsRemoved() {
    std::printf("alignment: a tilted head gives the same crop as a level one\n");
    const double phi = 20 * PI / 180, mx = 240, my = 300;
    const Scene tilted = [&](double x, double y) {  // scene rotated by phi around the eye midpoint
        const double c = std::cos(-phi), s = std::sin(-phi);
        return faceScene(mx + c * (x - mx) - s * (y - my), my + s * (x - mx) + c * (y - my));
    };
    const auto level = align(makeFrame(faceScene, 480, 640, 270), 200, 300, 280, 300);
    const double c = std::cos(phi), s = std::sin(phi);
    const auto rot = align(makeFrame(tilted, 480, 640, 270), mx - 40 * c, my - 40 * s, mx + 40 * c, my + 40 * s);
    CHECK(meanDiff(level, rot) < 0.02, "mean diff %f", meanDiff(level, rot));
}

static void testQualityMeasures() {
    std::printf("alignment: sharpness and brightness\n");
    AlignResult sharp, blurry, dark;
    align(makeFrame([](double x, double y) { return ((static_cast<int>(x) / 3 + static_cast<int>(y) / 3) % 2) ? 200.0 : 60.0; }, 480, 640, 270),
          200, 300, 280, 300, &sharp);
    align(makeFrame(faceScene, 480, 640, 270), 200, 300, 280, 300, &blurry);
    align(makeFrame([](double, double) { return 30.0; }, 480, 640, 270), 200, 300, 280, 300, &dark);
    CHECK(sharp.sharpness > 10 * blurry.sharpness, "sharp %f vs blurry %f", sharp.sharpness, blurry.sharpness);
    CHECK(std::fabs(dark.luma - 30) < 0.5, "luma %f", dark.luma);
}

static void testAverageTopK() {
    std::printf("template: average of the best k embeddings\n");
    const int dim = 4;
    // Three good embeddings near (1,0,0,0) and one bad outlier with low quality.
    std::vector<float> e = {2, 0.1f, 0, 0,   1, -0.1f, 0, 0,   3, 0, 0.1f, 0,   0, 0, 0, 5};
    std::vector<float> q = {0.9f, 0.8f, 0.85f, 0.1f};
    auto t = averageTopK(e.data(), 4, dim, q.data(), 3, 3);
    CHECK(t.size() == 4, "size %zu", t.size());
    double norm = 0;
    for (float x : t) norm += x * x;
    CHECK(std::fabs(norm - 1) < 1e-5, "not normalised %f", norm);
    CHECK(t[0] > 0.99 && std::fabs(t[3]) < 1e-6, "outlier leaked in (%f, %f)", t[0], t[3]);
    CHECK(averageTopK(e.data(), 2, dim, q.data(), 3, 3).empty(), "fewer than minCount should give nothing");
    // Unequal magnitudes don't dominate: each embedding is normalised first.
    std::vector<float> e2 = {100, 0, 0, 0,   0, 1, 0, 0};
    std::vector<float> q2 = {1, 1};
    auto t2 = averageTopK(e2.data(), 2, dim, q2.data(), 2, 2);
    CHECK(std::fabs(t2[0] - t2[1]) < 1e-6, "magnitude dominated: %f vs %f", t2[0], t2[1]);
}

int main() {
    testRotationsGiveIdenticalCrops();
    testEyeOrderAndCentre();
    testTiltIsRemoved();
    testQualityMeasures();
    testAverageTopK();
    if (g_failures) {
        std::printf("%d check(s) FAILED\n", g_failures);
        return 1;
    }
    std::printf("all face tests passed\n");
    return 0;
}
