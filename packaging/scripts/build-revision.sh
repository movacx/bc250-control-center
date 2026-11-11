#!/usr/bin/env bash
# Called by the source and binary packagers with the root being packaged.
set -eu
root="$1"
revision=""
origin=local
if [[ -e "$root/.git" ]]; then
  origin=git
  revision="$(git -C "$root" rev-parse --verify HEAD 2>/dev/null || true)"
elif [[ -f "$root/BUILD_REVISION" ]]; then
  revision="$(cat "$root/BUILD_REVISION")"
  if [[ "$revision" =~ ^[0-9a-f]{40,64}$ ]]; then origin=release; fi
fi
if [[ "${2:-}" == "--type" ]]; then
  printf '%s\n' "$origin"
elif [[ "$revision" =~ ^[0-9a-f]{40,64}$ ]]; then
  printf '%s\n' "$revision"
fi
