#!/usr/bin/env bash
# Builds the panda demo video: fetches pyrite's docs/video kit into .kit/, writes data.js from the recorded
# run, renders video.mp4 (or stills). Recording the run: record.sh (about 3 min).
#
# Usage: make.sh [--stills 3 10 ...]     env: PYRITE (pyrite checkout, default ~/dev/simantic/pyrite),
#                                              PY (python with playwright + imageio-ffmpeg, default python3)
set -euo pipefail
HERE=$(cd -- "$(dirname -- "$0")" && pwd)
PYRITE=${PYRITE:-$HOME/dev/simantic/pyrite} PY=${PY:-python3}
rm -rf "$HERE/.kit" && mkdir -p "$HERE/.kit"
git -C "$PYRITE" archive origin/main docs/video/assets docs/video/render.py | tar -x -C "$HERE/.kit" --strip-components=2
# the repo venv: collect.py decodes the car-bus frame with opendbc
"$HERE/../../.venv/bin/python" "$HERE/collect.py" "$HERE/runs/demo.txt" "$HERE/data.js" "$(head -1 "$HERE/runs/sim-version.txt")"
"$PY" "$HERE/.kit/render.py" "$HERE/video.html" "$@"
