#!/usr/bin/env bash
# Download the problem reports of the last N days (default 4) from the
# report endpoint, one JSON file per report, for local analysis.
#
#   BC250_REPORTS_TOKEN=... scripts/maintenance/fetch-reports.sh [days] [out_dir]
#
# The token is read from BC250_REPORTS_TOKEN and only sent to the endpoint
# in the Authorization header; it is never written to disk or printed.
set -euo pipefail

ENDPOINT="${BC250_REPORTS_ENDPOINT:-https://bc250-reports.report-endpoint.workers.dev}"
DAYS="${1:-4}"
OUT="${2:-$HOME/Documentos/bc250-reports}"
: "${BC250_REPORTS_TOKEN:?Set BC250_REPORTS_TOKEN to the admin token first}"
command -v curl >/dev/null && command -v python3 >/dev/null || { echo "curl and python3 are required" >&2; exit 69; }

mkdir -p "$OUT"
auth=(-H "Authorization: Bearer ${BC250_REPORTS_TOKEN}")
since="$(date -u -d "-${DAYS} days" +%Y-%m-%dT%H:%M:%S)"

cursor=""
: > "$OUT/index.jsonl"
while :; do
  url="$ENDPOINT/v1/admin/reports"
  [ -n "$cursor" ] && url="$url?cursor=$cursor"
  page="$(curl -fsS "${auth[@]}" "$url")"
  cursor="$(printf '%s' "$page" | python3 -c '
import json, sys
since = sys.argv[1]
data = json.load(sys.stdin)
with open(sys.argv[2], "a", encoding="utf-8") as out:
    for r in data.get("reports") or []:
        if str(r.get("received") or "") >= since:
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
print(data.get("cursor") or "")
' "$since" "$OUT/index.jsonl")"
  [ -z "$cursor" ] && break
done

count=0
while IFS= read -r id; do
  [ -n "$id" ] || continue
  curl -fsS "${auth[@]}" "$ENDPOINT/v1/admin/reports/$id" > "$OUT/$id.json"
  count=$((count + 1))
done < <(python3 -c 'import json,sys; [print(json.loads(l).get("id","")) for l in open(sys.argv[1])]' "$OUT/index.jsonl")

echo "Saved $count reports received since $since UTC in $OUT"
