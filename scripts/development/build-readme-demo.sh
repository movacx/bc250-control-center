#!/usr/bin/env bash
# Build assets/screenshots/demo.gif: the README's moving preview, a slow
# eased horizontal transition through the application's screenshots. Needs ffmpeg.
#
#   scripts/development/build-readme-demo.sh [width] [seconds-per-picture]
#
# The pictures and their order are listed below. Output is written next to
# the screenshots, with desktop, mobile and Game Mode previews on one canvas.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
command -v ffmpeg >/dev/null || { echo "ffmpeg is required" >&2; exit 69; }
command -v ffprobe >/dev/null || { echo "ffprobe is required" >&2; exit 69; }

WIDTH="${1:-1200}"
HOLD="${2:-3.2}"
FADE=$(awk -v hold="$HOLD" 'BEGIN { duration = 0.6; if (duration > hold / 2) duration = hold / 2; printf "%.3f", duration }')
FPS=20
PICTURES=(
  dashboard-overview.png cpu-tuning.png compute-units.png gpu-governor.png
  additional-compatibility.png kernel-boot-options.png additional-scaling.png memory-swap.png additional-drivers.png
  monitor-1.png fan-control.png black-box.png firmware-bios.png
  settings-general.png settings-appearance.png settings-terminal.png
  mobile-dashboard.jpg mobile-cpu-tuning.jpg mobile-compute-units.jpg
  mobile-gpu-governor.jpg mobile-performance-sensors.jpg mobile-fan-control.jpg
  decky-quick-access.png decky-quick-access-monitoring.png
)
size=$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0 "assets/screenshots/${PICTURES[0]}")
HEIGHT=$(awk -v width="$WIDTH" -v source_width="${size%x*}" -v source_height="${size#*x}" 'BEGIN { printf "%d", int(width * source_height / source_width / 2 + 0.5) * 2 }')
# End on the first picture so the repeating GIF has the same transition at
# the loop boundary. Trim its duplicate hold after the last transition.
PICTURES+=("${PICTURES[0]}")

inputs=()
chain=""
labels=""
index=0
for name in "${PICTURES[@]}"; do
  file="assets/screenshots/${name}"
  [[ -f "$file" ]] || { echo "missing $file" >&2; exit 66; }
  inputs+=(-loop 1 -t "$HOLD" -i "$file")
  labels+="[$index:v]scale=${WIDTH}:${HEIGHT}:force_original_aspect_ratio=decrease:force_divisible_by=2:flags=lanczos,pad=${WIDTH}:${HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=0x101113,setsar=1,fps=${FPS},format=yuv420p[v$index];"
  index=$((index + 1))
done
previous="v0"
offset=0
# P runs from one to zero. Ease the reveal across the screen, blending only
# along an 8%-wide edge so the rest of each screenshot stays sharp.
edge="1.08*P*P*(3-2*P)-0.04"
blend="clip((X/W-(${edge}))/0.08+0.5,0,1)"
transition="custom:expr='A*(1-(${blend}))+B*(${blend})'"
for ((i = 1; i < index; i++)); do
  offset=$(awk -v o="$offset" -v h="$HOLD" -v f="$FADE" 'BEGIN { printf "%.3f", o + h - f }')
  chain+="[$previous][v$i]xfade=transition=${transition}:duration=${FADE}:offset=${offset}[x$i];"
  previous="x$i"
done
duration=$(awk -v offset="$offset" -v fade="$FADE" 'BEGIN { printf "%.3f", offset + fade }')
filter="${labels}${chain}[${previous}]trim=duration=${duration},split[a][b];[a]palettegen=max_colors=192:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle"
staged=$(mktemp assets/screenshots/demo.XXXXXX.gif)
trap 'rm -f -- "$staged"' EXIT
ffmpeg -hide_banner -loglevel error -y "${inputs[@]}" -filter_complex "$filter" -loop 0 "$staged"
chmod 0644 "$staged"
mv -- "$staged" assets/screenshots/demo.gif
ls -l assets/screenshots/demo.gif
