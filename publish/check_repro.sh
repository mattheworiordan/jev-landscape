#!/usr/bin/env bash
# Rebuild the tables and the page from a staged tree and the feed, and compare the results with
# the copies in the tree. A pass shows that the published labels and code give the published
# numbers and the published page.
#
#   publish/check_repro.sh [TREE]        TREE defaults to publish/repo
#
# Needs data/cards.json (the feed snapshot) in the project folder. The run uses a temporary copy
# of TREE. On macOS it runs under sandbox-exec with no access to the project folder, so every
# input comes from TREE and cards.json.
#
# Compares, after publish/strip_text.py has emptied the text fields of the rebuilt files:
#   report/data/*.csv, report/summary.json, review/work/*.json and data/dedupe-groups.jsonl
#   index.html and charts/ (the report), technical/index.html and technical/charts/ (the first edition), byte for byte
# Exit status 1 when a step fails or a file differs.
set -euo pipefail
shopt -s nullglob

HERE=$(cd "$(dirname "$0")" && pwd)
PROJECT=$(cd "$HERE/.." && pwd)
TREE=$(cd "${1:-$HERE/repo}" && pwd)
CARDS=$PROJECT/data/cards.json
[[ -f $CARDS ]] || { echo "No $CARDS: fetch the feed first (README.md, step 1)."; exit 1; }
[[ -f $TREE/report/summary.json ]] || { echo "No staged tree at $TREE: run publish/stage.sh first."; exit 1; }

RUN=$(mktemp -d "${TMPDIR:-/tmp}/jev-repro.XXXXXX")
trap 'rm -rf "$RUN"' EXIT
if command -v rsync >/dev/null; then rsync -a --exclude=.git "$TREE/" "$RUN/"; else cp -R "$TREE/." "$RUN/"; rm -rf "$RUN/.git"; fi
cp "$CARDS" "$RUN/data/cards.json"
read -r LABELS MODEL < <(python3 -c 'import json,sys; l=json.load(open(sys.argv[1]))["labels"]; print(l["file"], l["model"])' "$TREE/report/summary.json")

SANDBOX=()
if command -v sandbox-exec >/dev/null; then
  SANDBOX=(sandbox-exec -p "(version 1)(allow default)(deny file-read* file-write* (subpath \"$PROJECT\"))")
fi
run() { (cd "$RUN" && "${SANDBOX[@]}" "$@"); }

FAILED=0
echo "-- rebuild the tables: scripts/analyze.py --labels $LABELS"
if ! run python3 scripts/analyze.py --labels "$LABELS" --labels-model "$MODEL" >"$RUN/analyze.log" 2>&1; then
  tail -20 "$RUN/analyze.log"
  echo "FAIL: analyze.py stopped (above)"
  exit 1
fi
grep -E '^(WARNING|wrote)' "$RUN/analyze.log" | sed 's/^/  /' || true

NOT_SHIPPED=(report/data/06_low_like_rate_cards.csv)   # excluded on purpose (publish/PUBLISHING.md); rebuilt but not compared
compare() {  # compare REL: strip the rebuilt file, then compare it with the tree's copy
  local rel=$1 x
  for x in "${NOT_SHIPPED[@]}"; do [[ $rel == "$x" ]] && return 0; done
  mkdir -p "$RUN/.stripped/$(dirname "$rel")"
  python3 "$HERE/strip_text.py" "$RUN/$rel" "$RUN/.stripped/$rel" >/dev/null
  if cmp -s "$RUN/.stripped/$rel" "$TREE/$rel"; then return 0; fi
  echo "  DIFFERS: $rel"
  return 1
}
n=0 bad=0
for f in "$RUN"/report/data/*.csv "$RUN"/report/summary.json "$RUN"/review/work/*.json "$RUN"/data/dedupe-groups.jsonl; do
  rel=${f#"$RUN"/}
  n=$((n + 1))
  compare "$rel" || bad=$((bad + 1))
done
for f in "$TREE"/report/data/*.csv; do
  [[ -f $RUN/${f#"$TREE"/} ]] || { echo "  MISSING from the rebuild: ${f#"$TREE"/}"; bad=$((bad + 1)); }
done
echo "  $((n - bad)) of $n data files match the tree"
[[ $bad -eq 0 ]] || FAILED=1

echo "-- rebuild the page: report/site/scripts/charts.mjs --labels $LABELS"
if ! run node report/site/scripts/charts.mjs --labels "$LABELS" >"$RUN/charts.log" 2>&1; then
  grep -v '^  ' "$RUN/charts.log" | tail -12
  echo "FAIL: charts.mjs stopped or refused to write (above)"
  exit 1
fi
grep '^COPY CHECK' "$RUN/charts.log" | sed 's/^/  /' || true
pbad=0
cmp -s "$RUN/report/site/index.html" "$TREE/technical/index.html" || { echo "  DIFFERS: technical/index.html"; pbad=$((pbad + 1)); }
for f in "$RUN"/report/site/charts/*.svg "$RUN"/report/site/charts/narrow/*.svg; do
  rel=technical/charts/${f#"$RUN"/report/site/charts/}
  [[ -f $TREE/$rel ]] || continue   # the tree ships only the charts the technical page links
  cmp -s "$f" "$TREE/$rel" || { echo "  DIFFERS: $rel"; pbad=$((pbad + 1)); }
done
echo "  technical page and its SVG files rebuilt; $pbad differ from the tree"

echo "-- rebuild the report: report/site/scripts/page-v3.mjs (TECHNICAL_URL=technical/)"
if ! run env TECHNICAL_URL=technical/ ARTICLE_URL="${ARTICLE_URL:-}" PUBLISHED="${PUBLISHED:-}" node report/site/scripts/page-v3.mjs >"$RUN/page-v3.log" 2>&1; then
  tail -12 "$RUN/page-v3.log"
  echo "FAIL: page-v3.mjs stopped (above)"
  exit 1
fi
cmp -s "$RUN/report/site/v3/index.html" "$TREE/index.html" || { echo "  DIFFERS: index.html"; pbad=$((pbad + 1)); }
for f in "$RUN"/report/site/v3/charts/*.svg "$RUN"/report/site/v3/charts/narrow/*.svg; do
  rel=charts/${f#"$RUN"/report/site/v3/charts/}
  cmp -s "$f" "$TREE/$rel" || { echo "  DIFFERS: $rel"; pbad=$((pbad + 1)); }
done
echo "  report and $(find "$RUN/report/site/v3/charts" -name '*.svg' | wc -l | tr -d ' ') SVG files rebuilt; $pbad differ from the tree in all"
[[ $pbad -eq 0 ]] || FAILED=1

if [[ $FAILED -ne 0 ]]; then
  echo "FAIL: the tree does not reproduce. If report/ was rebuilt after staging, stage again."
  exit 1
fi
echo "PASS: the published labels and code rebuild every table and the page, byte for byte"
