# MODEL_INFO.md: Face-recognition model

The app computes face embeddings on the phone with **MobileFaceNet** (TensorFlow Lite, run by LiteRT). The same model must be used for registration and verification, because embeddings from different models are not comparable. Its version string is sent in every signed payload, and the backend refuses a mismatch.

| | |
|---|---|
| File in the app | `app/src/main/assets/mobilefacenet.tflite` |
| Size | 5,233,552 bytes |
| SHA-256 | `be4bc7cfc53f7bc336d0f28b1ab92535f618c913a422b683210750f6b5354854` |
| Source | https://github.com/hugocornellier/face_detection_tflite, file `assets/models/mobilefacenet.tflite` (commit `75b2ca733f`, 2025-12-24, the file's only commit) |
| Licence | Apache License 2.0 (the repository's licence, which states that all its models are Apache 2.0) |
| Architecture | MobileFaceNets (Chen et al., 2018, [arXiv 1804.07573](https://arxiv.org/abs/1804.07573)) |
| Input | `input` float32 `[1, 112, 112, 3]`: aligned face crop, **RGB**, values scaled to **[-1, 1]** |
| Output | `embeddings` float32 `[1, 192]`, already L2-normalised inside the model (`L2_NORMALIZATION` op) |
| Ops | CONV_2D, DEPTHWISE_CONV_2D, ADD, MUL, SUB, ABS, RELU, RESHAPE, L2_NORMALIZATION (all LiteRT built-ins) |
| Runtime | `com.google.ai.edge.litert:litert:1.4.2` (`org.tensorflow.lite.Interpreter` API), pinned in `gradle/libs.versions.toml` |
| Version string | `mobilefacenet-192-v1` (`FaceEmbedder.MODEL_VERSION`; backend `FACE_MODEL_VERSION`) |

The size, checksum, input/output shapes and op list above were checked on the downloaded file (2026-09-30).

## Pre-processing (matches the reference implementation in the same repository)

Implemented in `app/src/main/cpp/face_core.cpp` (`alignFace`), read directly from the camera's YUV planes. Unit-tested on a laptop with `python tools/rppg/run_tests.py`, which checks identical crops for all four sensor rotations, tilt removal and centring.

1. Eye centres come from ML Kit face landmarks (upright image coordinates).
2. The crop is a square with side = 2.5 × eye distance, rotated so the eyes are level, centred at the eye midpoint moved 0.15 × side down the face.
3. It is sampled to 112×112 (bilinear luma), converted YUV→RGB (BT.601 full range), and scaled to [-1, 1].

## Provenance caveat (stated honestly)

The repository says the model is "based on MobileFaceNets" but does not say which dataset the trained weights came from, or whether they were converted from another project. For the hackathon demo it is used under the repository's Apache-2.0 licence. **For any production use, the weights' origin and licence should be confirmed, or a model trained on a documented dataset used instead.**

## Thresholds

The face-match thresholds (`FACE_T_HIGH`, `FACE_T_LOW`, `FACE_ANCHOR_MIN` in `backend/.env`) are placeholders until calibrated on the team's own scans with `backend/scripts/calibrate_thresholds.py` (label genuine vs impostor attempts, then run `report`). Scores from this model are not comparable with numbers published for other models.
