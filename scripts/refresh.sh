#!/usr/bin/env bash
# Refresh the Jev landscape: pull the OpenChamber feed, label the new cards, and rebuild the
# report, the charts and the page. One command; safe to re-run (every step is resumable).
#
#   ~/Workshop/work/projects/jev-landscape/scripts/refresh.sh        (from anywhere; a few minutes)
#
# Env knobs:
#   THROUGH=YYYY-MM-DD   last posting day (UTC) to include; default 2026-09-23
#   REFRESH_MAX_USD=2    new spend allowed per label file in one refresh (dollars); 0 spends nothing
#   ENV_FILE=...         Gateway credentials; default .env.local (keys are never printed)
#   SKIP_PULL=1          rebuild from the snapshots already kept, without pulling the feed
#   OFFLINE=1            skip steps 4 to 6 (no labelling, no network, no spend): report the coverage and rebuild
#   LABELS=...           reference label file for the analysis, the audit and the page (default data/classified-opus.jsonl,
#                        Claude Opus 5.5; LABELS_MODEL names its model). Sonnet v2 labels are still kept current: the
#                        audit's strata were drawn from them.
#
# Steps:
#   1. Save the current cards, summary and measurement ladder, for the before/after comparison.
#   2. Keep the earlier pull: a raw data/cards.json is copied into data/snapshots/ under its feed time.
#   3. Pull the feed into data/snapshots/ and build data/cards.json from every snapshot
#      (scripts/build_cards.py: posts through THROUGH; cards the feed later dropped are kept).
#   4. Label cards not yet in data/classified-sonnet-v2.jsonl with Claude Sonnet 5 (rubric v2), and cards not
#      yet in the reference labels with their model (Claude Opus 5.5 by default; a post its safety filter
#      refused stays out and is not retried).
#   5. Label cards not yet in data/classified-jev.jsonl with Jev.
#   6. Sub-type the reference labels' noise cards not yet in data/classified-noise.jsonl.
#   7. Rerun scripts/dedupe.py, scripts/analyze.py (it runs the independent audit's scripts, and for labels other
#      than Sonnet v2 review/estimate-opus.py, through scripts/audit.py) and report/site/scripts/charts.mjs (it
#      checks the audit tables against the data).
#   8. Print what changed (scripts/refresh_report.py). The full log is in data/refresh-logs/.
set -euo pipefail

cd "$(dirname "$0")/.."
THROUGH=${THROUGH:-2026-09-23}
REFRESH_MAX_USD=${REFRESH_MAX_USD:-2}
export LABELS=${LABELS:-data/classified-opus.jsonl}
REF_MODEL=${REF_MODEL:-anthropic/claude-opus-5.5}   # the Gateway model behind LABELS
REF_USAGE=${REF_USAGE:-data/usage-opus-5.5.jsonl}
ENV_FILE=${ENV_FILE:-.env.local}
FEED_URL=https://jev.openchamber.dev/data/cards.json
STAMP=$(date -u +%Y%m%d-%H%M)
mkdir -p data/refresh-logs data/snapshots
LOG=data/refresh-logs/refresh-$STAMP.log
SUMMARY=data/refresh-logs/refresh-$STAMP-summary.txt
exec > >(tee -a "$LOG") 2>&1

WARNINGS=()
log() { printf '\n[%s UTC] %s\n' "$(date -u +%H:%M:%S)" "$*"; }
warn() { WARNINGS+=("$*"); printf 'WARNING: %s\n' "$*"; }
[ "${OFFLINE:-0}" = "1" ] || [ -f "$ENV_FILE" ] || { echo "No Gateway env file at $ENV_FILE; set ENV_FILE (or OFFLINE=1)."; exit 1; }
TSX=(pnpm dlx tsx --env-file="$ENV_FILE")
WORK=$(mktemp -d "${TMPDIR:-/tmp}/jev-refresh.XXXXXX")
trap 'rm -rf "$WORK"' EXIT
trap 'echo; echo "REFRESH STOPPED at line $LINENO. Labels and snapshots keep everything finished so far, and data/cards.json changes only in step 3. Fix the cause and run the same command again; every step resumes. Log: $LOG"' ERR

log "Jev landscape refresh $STAMP: posts through $THROUGH (UTC); log $LOG"

log "1/8 Save the current state for the before/after comparison"
cp data/cards.json "$WORK/cards.json"
cp report/summary.json "$WORK/summary.json"
if [ -f report/data/08_ladder.csv ]; then cp report/data/08_ladder.csv "$WORK/08_ladder.csv"; fi
echo "saved $(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))["cards"]))' data/cards.json) cards and the current summary"

log "2/8 Keep the earlier pull as a snapshot"
python3 scripts/build_cards.py adopt

log "3/8 Pull the feed and build the working set"
if [ "${SKIP_PULL:-0}" = "1" ]; then
  echo "SKIP_PULL=1: using the snapshots already in data/snapshots/"
else
  curl -fsS --retry 3 --retry-delay 5 --max-time 180 -o "$WORK/feed.json" "$FEED_URL"
  python3 scripts/build_cards.py add "$WORK/feed.json"
fi
python3 scripts/build_cards.py build --through "$THROUGH"

missing() {  # missing KIND: how many cards still lack that label
  python3 scripts/refresh_report.py coverage | tee "$WORK/coverage.txt" >/dev/null || true
  python3 - "$1" "$WORK/coverage.txt" <<'PY'
import re, sys
m = re.search(rf"missing {re.escape(sys.argv[1])}: (\d+)", open(sys.argv[2]).read())
print(m.group(1) if m else 0)
PY
}

if [ "${OFFLINE:-0}" = "1" ]; then
  log "4-6/8 OFFLINE=1: no labelling (no network, no spend)"
else
log "4/8 Label new cards with Claude Sonnet 5 (rubric v2) and with the reference model"
for attempt in 1 2; do
  cap=$(python3 scripts/refresh_report.py cap data/usage-sonnet-v2.jsonl "$REFRESH_MAX_USD")
  RUBRIC_VERSION=v2 MAX_USD="$cap" "${TSX[@]}" scripts/classify-sonnet.ts || warn "classify-sonnet.ts exited non-zero (attempt $attempt)"
  n=$(missing "Sonnet v2 label"); [ "$n" = "0" ] && break
  echo "$n cards still without a Sonnet v2 label"
done
if [ "$LABELS" != "data/classified-sonnet-v2.jsonl" ]; then
  for attempt in 1 2; do
    n=$(python3 scripts/refresh_report.py missing-ids "$LABELS" "$WORK/ref-ids.jsonl")
    [ "$n" = "0" ] && break
    echo "$n cards without a label in $LABELS"
    cap=$(python3 scripts/refresh_report.py cap "$REF_USAGE" "$REFRESH_MAX_USD")
    "${TSX[@]}" scripts/classify-model.ts --model "$REF_MODEL" --out "$LABELS" --usage "$REF_USAGE" --ids "$WORK/ref-ids.jsonl" \
      --max-usd "$cap" || warn "classify-model.ts exited non-zero (attempt $attempt)"
  done
fi

log "5/8 Label new cards with Jev"
for attempt in 1 2; do
  "${TSX[@]}" scripts/classify-jev.ts || warn "classify-jev.ts exited non-zero (attempt $attempt)"
  n=$(missing "Jev label"); [ "$n" = "0" ] && break
  echo "$n cards still without a Jev label"
done

log "6/8 Sub-type new noise cards (the reference labels' noise)"
for attempt in 1 2; do
  cap=$(python3 scripts/refresh_report.py cap data/usage-noise.jsonl "$REFRESH_MAX_USD")
  MAX_USD="$cap" "${TSX[@]}" scripts/classify-noise.ts || echo "classify-noise.ts left cards to do (attempt $attempt)"
  n=$(missing "noise sub-type"); [ "$n" = "0" ] && break
  echo "$n noise cards still without a sub-type"
done
fi
python3 scripts/refresh_report.py coverage || warn "some cards are still unlabelled (above); the analysis leaves them out"

log "7/8 Rebuild: dedupe, analysis, charts and page"
python3 scripts/dedupe.py
python3 scripts/analyze.py
CHARTS_OK=1
node report/site/scripts/charts.mjs > "$WORK/charts.txt" 2>&1 || CHARTS_OK=0
grep -v '^  ' "$WORK/charts.txt" || true
[ "$CHARTS_OK" = "1" ] || warn "charts.mjs data checks failed (above): the charts and index.html were NOT rewritten"
while IFS= read -r line; do warn "${line#COPY CHECK: }"; done < <(grep '^COPY CHECK: ' "$WORK/charts.txt" | tail -n +2 || true)

log "8/8 What changed"
{
  python3 scripts/refresh_report.py report "$WORK"
  echo
  if [ ${#WARNINGS[@]} -eq 0 ]; then
    echo "Checks: labels complete, chart data checks passed, every worded claim on the page still holds."
  else
    echo "Warnings (${#WARNINGS[@]}):"
    for w in "${WARNINGS[@]}"; do echo "  - $w"; done
  fi
  echo
  echo "Outputs: report/landscape.md, report/summary.json, report/data/*.csv, report/site/index.html, report/site/charts/"
  echo "Log: $LOG"
} | tee "$SUMMARY"

[ "$CHARTS_OK" = "1" ] || exit 1
