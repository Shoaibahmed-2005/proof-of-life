// Host harness for the C++ rPPG engine: reads "t,r,g,b" CSV samples, runs the
// engine exactly as the app does (addSample + update per frame) and writes one
// status line per sample:
//   t,bpm,latest_bpm,snr_db,median_snr_db,window_fill,stable,new_estimate,estimate_count,samples
// Usage: rppg_cli <samples.csv> <out.csv> [min_snr_db]

#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <string>

#include "rppg_core.h"

int main(int argc, char** argv) {
    if (argc < 3) {
        std::fprintf(stderr, "usage: %s samples.csv out.csv [min_snr_db]\n", argv[0]);
        return 2;
    }
    rppg::Config cfg;
    if (argc > 3) cfg.minSnrDb = std::atof(argv[3]);
    rppg::Engine engine(cfg);

    std::ifstream in(argv[1]);
    std::FILE* out = std::fopen(argv[2], "w");
    if (!in || !out) {
        std::fprintf(stderr, "cannot open files\n");
        return 1;
    }
    std::string line;
    while (std::getline(in, line)) {
        std::stringstream ss(line);
        double v[4];
        char comma;
        if (!(ss >> v[0] >> comma >> v[1] >> comma >> v[2] >> comma >> v[3])) continue;
        engine.addSample(v[0], v[1], v[2], v[3]);
        const rppg::Status s = engine.update();
        std::fprintf(out, "%.6f,%.4f,%.4f,%.4f,%.4f,%.4f,%d,%d,%d,%d\n", v[0], s.bpm, s.latestBpm, s.snrDb,
                     s.medianSnrDb, s.windowFill, s.stable ? 1 : 0, s.newEstimate ? 1 : 0, s.estimateCount,
                     s.samplesInWindow);
    }
    std::fclose(out);
    return 0;
}
