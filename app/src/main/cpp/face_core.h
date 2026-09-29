// Face alignment and template averaging for the MobileFaceNet embedder.
// Pure C++17 (no JNI / Android), unit-tested on a laptop (tools/rppg/test_face.cpp).
//
// alignFace: cuts a rotated square around the eyes straight out of the camera's
// YUV_420_888 planes and writes the 112×112 RGB crop the model expects
// (NHWC, values scaled to [-1, 1]). Alignment follows the reference
// implementation shipped with the model (hugocornellier/face_detection_tflite):
//   side   = 2.5 × eye distance
//   angle  = angle of the eye line (so the eyes end up level)
//   centre = eye midpoint moved 0.15 × side "down" the face
// Eye positions are in UPRIGHT image coordinates (as ML Kit reports them); the
// camera planes are in SENSOR orientation, rotated by `rotation` degrees.

#pragma once

#include <vector>

#include "rppg_core.h"  // rppg::PlaneView

namespace face {

constexpr int kSize = 112;
constexpr int kTensorLength = kSize * kSize * 3;

struct AlignResult {
    bool ok = false;
    double sharpness = 0;  // variance of the Laplacian of the crop's luma
    double luma = 0;       // mean brightness 0..255 of the crop
    double eyeDistance = 0;
};

// out must hold kTensorLength floats.
AlignResult alignFace(const rppg::PlaneView& y, const rppg::PlaneView& u, const rppg::PlaneView& v,
                      int width, int height, int rotation,
                      double eyeAx, double eyeAy, double eyeBx, double eyeBy, float* out);

// Upright → sensor coordinate mapping (exposed for tests).
void uprightToSensor(double ux, double uy, int width, int height, int rotation, double& sx, double& sy);

// Averages the `k` best embeddings (by quality) after L2-normalising each,
// then L2-normalises the result. Returns an empty vector if fewer than
// `minCount` embeddings are available.
std::vector<float> averageTopK(const float* embeddings, int count, int dim,
                               const float* quality, int k, int minCount);

}  // namespace face
