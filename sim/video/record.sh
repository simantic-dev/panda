#!/usr/bin/env bash
# Records the run the video is built from: ./demo's output (openpilot side + the car's own bus log) in
# runs/demo.txt and `sim --version` in runs/sim-version.txt. About 3 min. Then ./make.sh.
set -euo pipefail
HERE=$(cd -- "$(dirname -- "$0")" && pwd)
mkdir -p "$HERE/runs" && "${SIM:-sim}" --version > "$HERE/runs/sim-version.txt"
"$HERE/../../demo" > "$HERE/runs/demo.txt" 2>&1
