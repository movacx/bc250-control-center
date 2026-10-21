#!/usr/bin/env bash
# run.sh <image> <phase> [--prune]
# Runs the repository inside one distribution image, as a normal user with sudo.
# Phases: scripts (every installer, entry point and system script), pytest, detail.
# Logs go to $OUT (default ./out). --prune removes the image afterwards, so a
# 100-image sweep fits on a small disk. Needs rootless Podman (or set PODMAN=docker).
set -u
image=${1:?image}; phase=${2:-scripts}; prune=${3:-}
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$HERE/../../.." && pwd)
OUT=${OUT:-$PWD/out}; PODMAN=${PODMAN:-podman}
name=$(echo "$image" | sed 's#.*/##; s#:#_#g'); mkdir -p "$OUT"
# --network=host: the governor's gpu_metrics overlay makes new sysfs mounts fail in userns.
"$PODMAN" run --rm --network=host -v "$REPO":/repo:ro -v "$HERE":/qa:ro,Z -e PHASE="$phase" "$image" sh /qa/boot.sh \
  >"$OUT/$name.$phase.log" 2>&1
rc=$?
echo "$image $phase rc=$rc" >>"$OUT/_done"
[ "$prune" = --prune ] && "$PODMAN" rmi -f "$image" >/dev/null 2>&1
# The container's own status: a failed install or test run fails the sweep.
exit "$rc"
