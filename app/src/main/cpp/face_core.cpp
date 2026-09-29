// Face alignment and template averaging — see face_core.h.

#include "face_core.h"

#include <algorithm>
#include <cmath>
#include <numeric>

namespace face {

namespace {

inline int clampByte(double v) { return v < 0 ? 0 : (v > 255 ? 255 : static_cast<int>(v + 0.5)); }

inline int sampleAt(const rppg::PlaneView& p, int x, int y, int pixelStride) {
    const size_t i = static_cast<size_t>(y) * static_cast<size_t>(p.rowStride) +
                     static_cast<size_t>(x) * static_cast<size_t>(pixelStride);
    return i < p.size ? p.data[i] : 0;
}

// Bilinear luma sample at sensor coordinates (x, y).
double lumaBilinear(const rppg::PlaneView& yp, double x, double y, int width, int height) {
    const int x0 = static_cast<int>(std::floor(x)), y0 = static_cast<int>(std::floor(y));
    const double fx = x - x0, fy = y - y0;
    const int x1 = std::min(x0 + 1, width - 1), y1 = std::min(y0 + 1, height - 1);
    const int xa = std::max(x0, 0), ya = std::max(y0, 0);
    const double a = sampleAt(yp, xa, ya, yp.pixelStride), b = sampleAt(yp, x1, ya, yp.pixelStride);
    const double c = sampleAt(yp, xa, y1, yp.pixelStride), d = sampleAt(yp, x1, y1, yp.pixelStride);
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy;
}

}  // namespace

void uprightToSensor(double ux, double uy, int width, int height, int rotation, double& sx, double& sy) {
    // width/height are the SENSOR image size. Upright = sensor rotated clockwise by `rotation`.
    switch (rotation) {
        case 90:  sx = uy;                sy = (height - 1) - ux; break;
        case 180: sx = (width - 1) - ux;  sy = (height - 1) - uy; break;
        case 270: sx = (width - 1) - uy;  sy = ux;                break;
        default:  sx = ux;                sy = uy;                break;
    }
}

AlignResult alignFace(const rppg::PlaneView& y, const rppg::PlaneView& u, const rppg::PlaneView& v,
                      int width, int height, int rotation,
                      double eyeAx, double eyeAy, double eyeBx, double eyeBy, float* out) {
    AlignResult r;
    if (!y.data || !u.data || !v.data || !out || width <= 0 || height <= 0) return r;
    // Order the eyes left→right in the upright image.
    double lx = eyeAx, ly = eyeAy, rx = eyeBx, ry = eyeBy;
    if (rx < lx) { std::swap(lx, rx); std::swap(ly, ry); }
    const double dx = rx - lx, dy = ry - ly;
    const double eyeDist = std::sqrt(dx * dx + dy * dy);
    r.eyeDistance = eyeDist;
    if (eyeDist < 8.0) return r;  // face too small / bad landmarks

    const double theta = std::atan2(dy, dx);
    const double ct = std::cos(theta), st = std::sin(theta);
    const double side = eyeDist * 2.5;
    const double offset = side * 0.15;
    const double cx = (lx + rx) * 0.5 - offset * st;
    const double cy = (ly + ry) * 0.5 + offset * ct;
    const bool swapped = rotation == 90 || rotation == 270;
    const int uprightW = swapped ? height : width, uprightH = swapped ? width : height;

    std::vector<double> lumaCrop(static_cast<size_t>(kSize) * kSize, 0.0);
    double lumaSum = 0;
    for (int j = 0; j < kSize; ++j) {
        for (int i = 0; i < kSize; ++i) {
            const double a = ((i + 0.5) / kSize - 0.5) * side;
            const double b = ((j + 0.5) / kSize - 0.5) * side;
            const double ux = cx + a * ct - b * st;
            const double uy = cy + a * st + b * ct;
            float* px = out + (static_cast<size_t>(j) * kSize + i) * 3;
            if (ux < 0 || uy < 0 || ux > uprightW - 1 || uy > uprightH - 1) {
                px[0] = px[1] = px[2] = -1.0f;  // outside the image: black
                continue;
            }
            double sx, sy;
            uprightToSensor(ux, uy, width, height, rotation, sx, sy);
            const double Y = lumaBilinear(y, sx, sy, width, height);
            const int cxs = std::clamp(static_cast<int>(sx + 0.5), 0, width - 1) / 2;
            const int cys = std::clamp(static_cast<int>(sy + 0.5), 0, height - 1) / 2;
            const double Cb = sampleAt(u, cxs, cys, u.pixelStride) - 128.0;
            const double Cr = sampleAt(v, cxs, cys, v.pixelStride) - 128.0;
            // BT.601 full range → RGB, then [-1, 1].
            px[0] = static_cast<float>(clampByte(Y + 1.402 * Cr) / 127.5 - 1.0);
            px[1] = static_cast<float>(clampByte(Y - 0.344136 * Cb - 0.714136 * Cr) / 127.5 - 1.0);
            px[2] = static_cast<float>(clampByte(Y + 1.772 * Cb) / 127.5 - 1.0);
            lumaCrop[static_cast<size_t>(j) * kSize + i] = Y;
            lumaSum += Y;
        }
    }
    r.luma = lumaSum / (static_cast<double>(kSize) * kSize);

    // Sharpness: variance of the 4-neighbour Laplacian of the luma crop.
    double sum = 0, sumSq = 0;
    int n = 0;
    for (int j = 1; j < kSize - 1; ++j) {
        for (int i = 1; i < kSize - 1; ++i) {
            const size_t k = static_cast<size_t>(j) * kSize + i;
            const double lap = lumaCrop[k - 1] + lumaCrop[k + 1] + lumaCrop[k - kSize] + lumaCrop[k + kSize] - 4 * lumaCrop[k];
            sum += lap; sumSq += lap * lap; ++n;
        }
    }
    const double mean = sum / n;
    r.sharpness = sumSq / n - mean * mean;
    r.ok = true;
    return r;
}

std::vector<float> averageTopK(const float* embeddings, int count, int dim,
                               const float* quality, int k, int minCount) {
    std::vector<float> result;
    if (!embeddings || !quality || count < std::max(1, minCount) || dim <= 0) return result;
    std::vector<int> order(static_cast<size_t>(count));
    std::iota(order.begin(), order.end(), 0);
    std::stable_sort(order.begin(), order.end(), [&](int a, int b) { return quality[a] > quality[b]; });
    const int take = std::min(std::max(k, 1), count);
    std::vector<double> acc(static_cast<size_t>(dim), 0.0);
    for (int t = 0; t < take; ++t) {
        const float* e = embeddings + static_cast<size_t>(order[static_cast<size_t>(t)]) * dim;
        double norm = 0;
        for (int d = 0; d < dim; ++d) norm += static_cast<double>(e[d]) * e[d];
        norm = std::sqrt(norm);
        if (norm < 1e-12) continue;
        for (int d = 0; d < dim; ++d) acc[static_cast<size_t>(d)] += e[d] / norm;
    }
    double norm = 0;
    for (double a : acc) norm += a * a;
    norm = std::sqrt(norm);
    if (norm < 1e-12) return result;
    result.resize(static_cast<size_t>(dim));
    for (int d = 0; d < dim; ++d) result[static_cast<size_t>(d)] = static_cast<float>(acc[static_cast<size_t>(d)] / norm);
    return result;
}

}  // namespace face
