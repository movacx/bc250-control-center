#!/usr/bin/env bash
# Build assets/screenshots/demo.gif: the README's moving preview, a slow
# cross-fade through the application's screenshots. Needs ffmpeg.
#
#   scripts/development/build-readme-demo.sh [width] [seconds-per-picture]
#
# The pictures and their order are listed below; the TUI and Decky pictures
# are not part of it. Output is written next to the screenshots.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
command -v ffmpeg >/dev/null || { echo "ffmpeg is required" >&2; exit 69; }

WIDTH="${1:-1200}"
HOLD="${2:-2.6}"
FADE=0.4
FPS=8
PICTURES=(
  dashboard-overview cpu-tuning compute-units gpu-governor
  additional-compatibility additional-scaling memory-swap additional-drivers
  monitor-1 fan-control black-box firmware-bios
  settings-general settings-appearance settings-terminal
)

inputs=()
chain=""
labels=""
index=0
for name in "${PICTURES[@]}"; do
  file="assets/screenshots/${name}.png"
  [[ -f "$file" ]] || { echo "missing $file" >&2; exit 66; }
  inputs+=(-loop 1 -t "$HOLD" -i "$file")
  labels+="[$index:v]scale=${WIDTH}:-2:flags=lanczos,fps=${FPS},format=yuv420p[v$index];"
  index=$((index + 1))
done
previous="v0"
offset=0
for ((i = 1; i < index; i++)); do
  offset=$(awk -v o="$offset" -v h="$HOLD" -v f="$FADE" 'BEGIN { printf "%.3f", o + h - f }')
  chain+="[$previous][v$i]xfade=transition=fade:duration=${FADE}:offset=${offset}[x$i];"
  previous="x$i"
done
filter="${labels}${chain}[${previous}]split[a][b];[a]palettegen=max_colors=160:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle"
ffmpeg -hide_banner -loglevel error -y "${inputs[@]}" -filter_complex "$filter" -loop 0 assets/screenshots/demo.gif
ls -l assets/screenshots/demo.gif
