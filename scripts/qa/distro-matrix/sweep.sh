#!/usr/bin/env bash
# sweep.sh [images.txt] [phase] [parallel]  -> runs every image, prunes each afterwards, prints a summary.
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
list=${1:-$HERE/images.txt}; phase=${2:-scripts}; jobs=${3:-3}
export OUT=${OUT:-$PWD/out}; mkdir -p "$OUT"
grep -vE '^\s*(#|$)' "$list" | xargs -P"$jobs" -I{} "$HERE/run.sh" {} "$phase" --prune
echo "== $phase: $(grep -c . "$OUT/_done") finished"
grep -h '^RESULT' "$OUT"/*."$phase".log | awk -F'\t' '$4!="rc=0"{n[$2]++} END{for(k in n) print n[k]"\t"k}' | sort -rn
