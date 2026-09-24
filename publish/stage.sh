#!/usr/bin/env bash
# Build publish/repo/: the public jev-landscape repository, with the data and the code and
# without the text of any post. publish/PUBLISHING.md says what goes in, what stays out, and why.
#
#   publish/stage.sh              run from anywhere; under a minute
#
# Env knobs:
#   OWNER=mattheworiordan NAME=jev-landscape   the GitHub repository, for the links in README.md
#   ARTICLE_URL=https://...                    the published piece; README.md links it when set
#   SKIP_REPRO=1                               skip the reproduction check (publish/check_repro.sh)
#
# Steps:
#   1. Check that data/cards.json is here (the leak check needs it). Warn when the report looks
#      half rebuilt (the page is older than its tables); the reproduction check in step 6 decides.
#   2. Recreate publish/repo/ and copy the allowlisted files. Data files (JSONL, JSON, CSV) go
#      through publish/strip_text.py, which empties every text field.
#   3. Make ROOT portable in the audit scripts (they name the author's folder).
#   4. Put the report at the root (index.html, charts/: report/site/v3/, rebuilt with its published
#      links) and the first edition under technical/ (index.html, charts/). Render charts/png/ in
#      both from the light SVGs, so that the PNGs always match the SVGs.
#   5. Write manifest.json, README.md, LICENSE, LICENSE-DATA, .gitignore and .nojekyll.
#   6. Check the tree: no post text or feed titles outside the allowed quotes (check_leaks.py),
#      a grep for a few known titles, only label keys in the label files, no secrets, no
#      hard-coded project path in code, no excluded file, every project file shipped or
#      excluded, size under 50 MB, and the tree rebuilds its own tables and page byte for byte
#      (publish/check_repro.sh). Then refresh the chart table in publish/SUBSTACK.md and print
#      the tree.
# A publish/repo/.git folder from an earlier publish is kept, so publish.sh can push an update.
# Exit status 1 when a check fails. The tree stays in place so that you can look at it.
set -euo pipefail
shopt -s nullglob

HERE=$(cd "$(dirname "$0")" && pwd)
PROJECT=$(cd "$HERE/.." && pwd)
OUT=$HERE/repo
OWNER=${OWNER:-mattheworiordan}
NAME=${NAME:-jev-landscape}
ARTICLE_URL=${ARTICLE_URL:-}
CARDS=$PROJECT/data/cards.json
MAX_MB=50
WORK=$(mktemp -d "${TMPDIR:-/tmp}/jev-stage.XXXXXX")
trap 'rm -rf "$WORK"' EXIT
FAILED=0
WARNINGS=0
fail() { printf 'FAIL: %s\n' "$*"; FAILED=1; }
warn() { printf 'WARNING: %s\n' "$*"; WARNINGS=$((WARNINGS + 1)); }
checked() {  # checked RC MESSAGE: 0 passes, 3 is a warning (printed above), anything else fails
  case $1 in 0) ;; 3) WARNINGS=$((WARNINGS + 1)) ;; *) fail "$2" ;; esac
}
step() { printf '\n== %s\n' "$*"; }

# ------------------------------------------------------------------------------- the file plan
# Globs are relative to the project folder. EXCLUDED wins over the other lists.
AS_IS=(                       # code and method documents: no data fields to empty
  "scripts/*"
  "review/*.py" "review/work/*.py" "review/*.rhai" "review/*.md" "review/work/*.md"
  "report/*.md" "report/v1/*.md" "report/site/README.md" "report/site/scripts/*.mjs"
  "package.json" "pnpm-lock.yaml" "pnpm-workspace.yaml"
)
STRIPPED=(                    # data files: publish/strip_text.py empties every text field
  "data/*.jsonl" "data/*.json" "data/pilot/*.jsonl" "data/labels-after-audit/*.jsonl" "data/withdrawn-tables/*.csv"
  "review/*.jsonl" "review/labels/*.jsonl" "review/work/*.jsonl" "review/*.json" "review/work/*.json" "review/data/*.csv"
  "report/summary.json" "report/data/*.csv"
  "report/v1/summary.json" "report/v1/data/*.csv" "report/v1/data/*/*.csv"
  "report/v2/summary.json" "report/v2/data/*.csv"
)
EXCLUDED=(                    # never shipped (publish/PUBLISHING.md gives the reason for each)
  "data/cards.json" "data/cards.json.tmp" "data/snapshots/*" "data/*.log" "data/refresh-logs/*"
  "review/blind/*" "review/fxtwitter-150.json" "review/human-sample-150.json" "review/labeller.html"
  "review/work/material-cards-*.jsonl" "review/work/production-cards.jsonl"
  "report/landscape.md" "report/v1/landscape.md" "report/v2/landscape.md" "report/human-labels-120.csv" "report/human-labels-README.md"
  "report/site/video/*" "data/withdrawn-tables/charts/*"
  "data/snapshots-after-audit/*" "report/site/assets/*" "report/site/jev-week-sorted.pdf" "report/site/summary/*" "report/site/summary/src/*"
)
PUBLISH_FILES=("publish/PUBLISHING.md" "publish/stage.sh" "publish/strip_text.py" "publish/check_leaks.py"
               "publish/check_repro.sh" "publish/templates/*")
LOCAL_ONLY=("publish/publish.sh" "publish/SUBSTACK.md")   # the author's release tools, not part of the repository
# Files that may quote feed titles, with the most titles each file may quote. Data files (JSON,
# JSONL, CSV) and the charts may quote none. The page quotes the most-viewed post of each noise
# sub-type, each with a link. Documents and code use a few titles as worked examples (the rubric
# prompt, the copy checks in charts.mjs). A file over its cap fails: read it, then decide.
ALLOW_TITLES=("index.html:15" "technical/index.html:15" "*.md:3" "*.py:3" "*.ts:3" "*.mjs:6" "*.rhai:3")
# Reviewed false positive: classify-jev.ts imports the SDK with the same line that one post quotes.
ALLOW_TEXT=("scripts/classify-jev.ts:1")

LEAK_ARGS=(--cards "$CARDS" --quiet)
for a in "${ALLOW_TITLES[@]}"; do LEAK_ARGS+=(--allow-titles "$a"); done
for a in "${ALLOW_TEXT[@]}"; do LEAK_ARGS+=(--allow-text "$a"); done

# shellcheck disable=SC2053  # the right-hand side is a glob pattern on purpose
excluded() { local p; for p in "${EXCLUDED[@]}"; do [[ $1 == $p ]] && return 0; done; return 1; }

ship() {  # ship as-is|strip GLOB...
  local how=$1 g f rel
  shift
  for g in "$@"; do
    for f in "$PROJECT"/$g; do
      [[ -f $f ]] || continue
      rel=${f#"$PROJECT"/}
      excluded "$rel" && continue
      mkdir -p "$OUT/$(dirname "$rel")"
      if [[ $how == strip ]]; then
        python3 "$HERE/strip_text.py" --report "$WORK/strip.jsonl" "$f" "$OUT/$rel" >/dev/null
      else
        cp -p "$f" "$OUT/$rel"
      fi
      printf '%s\n' "$rel" >>"$WORK/shipped.txt"
    done
  done
}

# ------------------------------------------------------------------------------- 1. preflight
step "1/6 Preflight"
[[ -f $CARDS ]] || { echo "No $CARDS. The leak check and the manifest need the feed: run scripts/build_cards.py first."; exit 1; }
[[ -f $PROJECT/report/site/index.html && -f $PROJECT/report/summary.json ]] || { echo "No report yet: run scripts/analyze.py and report/site/scripts/charts.mjs."; exit 1; }
for tool in python3 rsvg-convert tree; do command -v "$tool" >/dev/null || warn "$tool is not installed"; done
rc=0
python3 - "$PROJECT" <<'PY' || rc=$?
import sys, time
from pathlib import Path
p = Path(sys.argv[1])
page = (p / "report/site/index.html").stat().st_mtime
inputs = [p / "report/summary.json", *sorted((p / "report/data").glob("*.csv"))]
newest = max(inputs, key=lambda f: f.stat().st_mtime)
lag = newest.stat().st_mtime - page
if lag > 60:
    print(f"WARNING: {newest.relative_to(p)} is {lag / 60:.0f} min newer than report/site/index.html. "
          "The report looks half rebuilt: run node report/site/scripts/charts.mjs, then stage again.")
    sys.exit(3)
print(f"page built {time.strftime('%Y-%m-%d %H:%M', time.localtime(page))}; no table is newer than the page")
PY
checked $rc "the freshness check stopped"

# ------------------------------------------------------------------------------- 2. copy
step "2/6 Copy the allowlisted files into publish/repo/"
mkdir -p "$OUT"
find "$OUT" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +   # keep .git from an earlier publish
: >"$WORK/shipped.txt"
: >"$WORK/strip.jsonl"
ship as-is "${AS_IS[@]}" "${PUBLISH_FILES[@]}"
ship strip "${STRIPPED[@]}"
python3 - "$WORK/strip.jsonl" <<'PY'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1])]
changed = [r for r in rows if r["fields"]]
print(f"{len(rows)} data files through strip_text.py; {len(changed)} had text fields, now empty:")
for r in changed:
    dest = r["dest"].split("/publish/repo/", 1)[-1]
    print(f"  {dest}: " + ", ".join(f"{k} {v}" for k, v in r["fields"].items()))
PY

# ------------------------------------------------------------------------------- 3. portable ROOT
step "3/6 Make ROOT portable in the audit scripts"
python3 - "$OUT" "$PROJECT" <<'PY'
import re, sys
from pathlib import Path
out, project = Path(sys.argv[1]), sys.argv[2]
pat = re.compile(r'^(?P<lead>\s*ROOT\s*=\s*)Path\((?P<q>["\'])' + re.escape(project) + r'/?(?P=q)\)', re.M)
n = 0
for p in sorted(out.rglob("*.py")):
    s = p.read_text()
    up = len(p.relative_to(out).parts) - 1
    new, k = pat.subn(lambda m: f"{m.group('lead')}Path(__file__).resolve().parents[{up}]", s)
    if k:
        p.write_text(new)
        n += k
        print(f"  {p.relative_to(out)}: ROOT = Path(__file__).resolve().parents[{up}]")
print(f"{n} ROOT line(s) rewritten; each resolves to the same folder on the author's machine")
PY

# ------------------------------------------------------------------------------- 4. the pages
step "4/6 Put the report at the root and the first edition under technical/"
# The report is rebuilt with its published links (the technical page at technical/, the opinion piece
# at ARTICLE_URL when set, the byline date PUBLISHED when set). publish/check_repro.sh uses the same env.
if (cd "$PROJECT" && TECHNICAL_URL=technical/ ARTICLE_URL="$ARTICLE_URL" PUBLISHED="${PUBLISHED:-}" node report/site/scripts/page-v3.mjs >"$WORK/page-v3.log" 2>&1); then
  sed -n '1p' "$WORK/page-v3.log"
else
  cat "$WORK/page-v3.log"; fail "page-v3.mjs stopped (above)"
fi
cp -p "$PROJECT/report/site/v3/index.html" "$OUT/index.html"
mkdir -p "$OUT/charts/narrow" "$OUT/charts/png" "$OUT/technical/charts/narrow" "$OUT/technical/charts/png"
cp -p "$PROJECT"/report/site/v3/charts/*.svg "$OUT/charts/"
cp -p "$PROJECT"/report/site/v3/charts/narrow/*.svg "$OUT/charts/narrow/"
cp -p "$PROJECT/report/site/index.html" "$OUT/technical/index.html"
# The technical page's charts: only the ones it links (charts.mjs does not delete files of a chart it renamed).
STEMS=()
while IFS= read -r stem; do STEMS+=("$stem"); done < <(
  grep -oE 'charts/(narrow/)?[0-9]{2}-[a-z0-9-]+\.svg' "$OUT/technical/index.html" \
    | sed -E 's#^charts/(narrow/)?##; s#\.svg$##; s#-(light|dark)$##' | sort -u)
[[ ${#STEMS[@]} -gt 0 ]] || fail "technical/index.html links no chart"
printf '%s\n' "${STEMS[@]}" >"$WORK/stems.txt"
for stem in "${STEMS[@]}"; do
  for v in "" -light -dark; do
    for d in "" narrow/; do
      src=$PROJECT/report/site/charts/$d$stem$v.svg
      if [[ -f $src ]]; then cp -p "$src" "$OUT/technical/charts/$d"; else warn "the technical page links a chart with no file: charts/$d$stem$v.svg"; fi
    done
  done
done
for f in "$PROJECT"/report/site/charts/*.svg "$PROJECT"/report/site/charts/narrow/*.svg; do
  stem=$(basename "$f" .svg); stem=${stem%-light}; stem=${stem%-dark}
  grep -qxF "$stem" "$WORK/stems.txt" || { warn "not shipped: ${f#"$PROJECT"/} (the technical page does not link it; a leftover of a renamed chart)"; }
done
render_pngs() {  # render_pngs DIR: a 1600 px PNG for every -light.svg in DIR, into DIR/png/
  local dir=$1 f base n=0
  for f in "$dir"/*-light.svg; do
    base=$(basename "$f" -light.svg)
    if command -v rsvg-convert >/dev/null; then rsvg-convert -w 1600 -b white "$f" -o "$dir/png/$base.png"; n=$((n + 1)); else fail "no rsvg-convert to render $dir/png/$base.png"; fi
  done
  echo "  ${dir#"$OUT"/}: $(find "$dir" -maxdepth 2 -name '*.svg' | wc -l | tr -d ' ') SVG files, $n PNG files rendered"
}
render_pngs "$OUT/charts"
render_pngs "$OUT/technical/charts"
touch "$OUT/.nojekyll"

# ------------------------------------------------------------------------------- 5. documents
step "5/6 Write manifest.json, README.md, the licenses and .gitignore"
cp "$HERE/templates/gitignore" "$OUT/.gitignore"
python3 "$HERE/check_leaks.py" "$OUT" "${LEAK_ARGS[@]}" --json-out "$WORK/leaks-pre.json" >/dev/null || true
python3 - "$PROJECT" "$OUT" "$WORK" "$OWNER" "$NAME" "$ARTICLE_URL" <<'PY'
import hashlib, json, re, sys
from datetime import datetime, timezone
from pathlib import Path
project, out, work = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
owner, name, article = sys.argv[4], sys.argv[5], sys.argv[6]
repo_url, pages_url = f"https://github.com/{owner}/{name}", f"https://{owner}.github.io/{name}/"
feed = json.loads((project / "data/cards.json").read_text())
meta, cards = feed["meta"], feed["cards"]
summary = json.loads((out / "report/summary.json").read_text())
audit = summary.get("audit", {})
labels = summary.get("labels", {})
staged = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

pulls = []
for p in sorted((project / "data/snapshots").glob("cards-*.json")):
    m = json.loads(p.read_text()).get("meta", {})
    pulls.append({"file": p.name, "feed_updated": m.get("updated"), "cards": m.get("total"), "sha256": sha(p)})
emptied = {}
for line in (work / "strip.jsonl").read_text().splitlines():
    r = json.loads(line)
    if r["fields"]:
        emptied[r["dest"].split("/publish/repo/", 1)[-1]] = r["fields"]
manifest = {
    "title": "A week of Jev, sorted",
    "author": "Matthew O'Riordan",
    "disclosure": "The author is CEO of Ably, a realtime infrastructure company.",
    "repository": repo_url,
    "report": pages_url,
    "staged": staged,
    "feed": {
        "url": "https://jev.openchamber.dev/data/cards.json",
        "snapshot_updated": meta.get("updated"),
        "cards": len(cards),
        "authors": summary.get("authors"),
        "posted_through_utc": meta.get("through"),
        "window_utc": summary.get("window_utc"),
        "cards_in_latest_pull": meta.get("feed_cards"),
        "kept_from_earlier_pulls": meta.get("kept_from_earlier"),
        "built": meta.get("built"),
        "raw_pulls": pulls,
        "in_this_repository": "post ids and labels only; no post text, titles, names or media",
    },
    "analysis": {
        "labels": {k: labels.get(k) for k in ("file", "model", "audited") if k in labels},
        "posts": summary.get("posts"),
        "use_case_base": summary.get("use_case_base"),
        "not_a_jev_build": summary.get("not_a_jev_build"),
        "audit": {k: audit.get(k) for k in ("auditor", "labelled", "audited_labels", "snapshot_matches") if k in audit},
    },
    "text_fields_emptied": emptied,
}
(out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")

# README.md from the template
def n(v):
    return f"{v:,}" if isinstance(v, int) else str(v)

DESCRIBE = {
    "classified-sonnet.jsonl": "Claude Sonnet 5, rubric v1 (the first pass)",
    "classified-sonnet-v2.jsonl": "Claude Sonnet 5, rubric v2 (the labels the audit sampled)",
    "classified-opus.jsonl": "Claude Opus 5.5, rubric v2",
    "classified-jev.jsonl": "Jev (`typesafe-ai/jev`): its family, its stated probability for each family, latency",
    "classified-noise.jsonl": "Claude Sonnet 5: sub-type and stance of the noise posts (rubric-noise.md)",
}
rows = ["| File | Posts | Fields |", "|---|---|---|"]
for p in sorted((out / "data").glob("classified-*.jsonl")):
    if p.name.endswith(".errors.jsonl"):
        continue
    recs = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    keys = list(dict.fromkeys(k for r in recs for k in r))
    shown = [f"{k} (empty)" if p.name in {} else k for k in keys]
    text_keys = {k for k in keys if all(r.get(k) in ("", None, []) for r in recs) and k in ("reason", "note", "title", "text", "t", "x")}
    shown = [f"`{k}` (empty)" if k in text_keys else f"`{k}`" for k in keys]
    what = DESCRIBE.get(p.name, "")
    rows.append(f"| `data/{p.name}` | {n(len(recs))} | {what + ': ' if what else ''}{', '.join(shown)} |")
label_table = "The label files:\n\n" + "\n".join(rows)

leaks = json.loads((work / "leaks-pre.json").read_text())
page_titles = len(leaks.get("findings", {}).get("index.html", {}).get("title_cards", []))
human = out / "review/human-labels.jsonl"
human_n = sum(1 for l in human.read_text().splitlines() if l.strip()) if human.exists() else 0
cost = summary.get("cost", {})
parts = []
v2 = (cost.get("v2_full") or {}).get("usd")
if v2:
    parts.append(f"${v2:.2f} with Claude Sonnet 5")
run = cost.get("labels_run") or {}
if run.get("usd") and run.get("model") and "Sonnet" not in run["model"]:
    parts.append(f"${run['usd']:.2f} with {run['model']}")
if cost.get("jev_usd"):
    parts.append(f"${cost['jev_usd']:.2f} for Jev's own labels")
label_cost = ", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") + parts[-1] if parts else "a few dollars"
window = summary.get("window_utc") or ["", ""]
audit_note = ""
if audit.get("audited_labels") and audit.get("audited_labels") != labels.get("file"):
    audit_note = (f" It sampled the {audit.get('audited_model', 'first')} labels (`{audit['audited_labels']}`),"
                  f" and the page says so where it uses the {labels.get('model')} labels.")
jev_charts = sorted(out.glob("technical/charts/[0-9][0-9]-*jev-grading*-light.svg"))
jev_figure = f"figure {int(jev_charts[0].name[:2])} of the technical page" if jev_charts else "the technical page"
OPTIONAL = [
    ("report/v2", "The tables on the Claude Sonnet 5 v2 labels, which the audit sampled, kept for the record."),
    ("data/withdrawn-tables", "Tables that the page no longer uses, kept for the record."),
    ("review/data", "The audit's tables for each label file, from the audit's scripts."),
]
extra_rows = "".join(f"| `{d}/` | {what} |\n" for d, what in OPTIONAL if (out / d).is_dir() and any((out / d).iterdir()))
values = {
    "AUDIT_NOTE": audit_note,
    "JEV_FIGURE": jev_figure,
    "EXTRA_ROWS": extra_rows,
    "ARTICLE_LINE": f" The piece: {article}" if article else "",
    "PAGES_URL": pages_url,
    "REPO_URL": repo_url,
    "WINDOW_START": str(window[0])[:10],
    "THROUGH": meta.get("through", ""),
    "POSTS": n(summary.get("posts", len(cards))),
    "AUTHORS": n(summary.get("authors")),
    "SNAPSHOT": meta.get("updated", ""),
    "LABELS_MODEL": labels.get("model", ""),
    "LABELS_FILE": labels.get("file", ""),
    "NOT_JEV": n(summary.get("not_a_jev_build")),
    "BASE": n(summary.get("use_case_base")),
    "AUDITOR": audit.get("auditor", "An independent reviewer"),
    "AUDIT_N": n(audit.get("labelled")),
    "HUMAN_LABELS": n(human_n),
    "LABEL_TABLE": label_table,
    "PAGE_TITLES": n(page_titles),
    "LABEL_COST": label_cost,
    "STAGED": staged,
}
def fill(text: str) -> str:
    text = re.sub(r"\{\{([A-Z_]+)\}\}", lambda m: values[m.group(1)], text)
    left = re.findall(r"\{\{[^}]*\}\}", text)
    if left:
        raise SystemExit(f"unfilled placeholders: {left}")
    return text
tpl = project / "publish/templates"
(out / "README.md").write_text(fill((tpl / "README.md").read_text()))
(out / "LICENSE").write_text(fill((tpl / "LICENSE").read_text()))
(out / "LICENSE-DATA").write_text(fill((tpl / "LICENSE-DATA").read_text()))
print(f"manifest.json: feed snapshot {meta.get('updated')}, {len(cards):,} cards, {len(pulls)} raw pulls hashed, "
      f"{len(emptied)} files with emptied text fields")
print(f"README.md: labels {labels.get('model')} ({labels.get('file')}), {page_titles} titles quoted on the page, "
      f"Pages {pages_url}")
PY

# ------------------------------------------------------------------------------- 6. checks
step "6/6 Check the tree"
echo "-- post text and feed titles (publish/check_leaks.py)"
if ! python3 "$HERE/check_leaks.py" "$OUT" "${LEAK_ARGS[@]}" --json-out "$WORK/leaks.json"; then
  fail "check_leaks.py found feed text (above)"
fi

echo "-- grep for known titles and a line of post text"
if ! python3 - "$CARDS" "$OUT" "${ALLOW_TITLES[@]%%:*}" <<'PY'
import fnmatch, json, subprocess, sys
cards_path, out, allowed = sys.argv[1], sys.argv[2], sys.argv[3:]
cards = json.load(open(cards_path))["cards"]
by_views = sorted(cards, key=lambda c: -(c.get("v") or 0))
probes = [c["t"] for c in by_views[:3] if c.get("t")]                    # the three most-viewed titles
probes += [c["t"] for c in cards[len(cards) // 2: len(cards) // 2 + 2] if c.get("t")]  # two from the middle
text = next(c["x"] for c in by_views if c.get("lang") == "ja" and len(c.get("x") or "") > 60)
probes.append(text[10:40])                                               # 30 characters of a Japanese post
problem = False
for s in probes:
    r = subprocess.run(["grep", "-rlF", "--", s, out], capture_output=True, text=True)
    hits = [h[len(out) + 1:] for h in r.stdout.split()]
    bad = [h for h in hits if not any(fnmatch.fnmatch(h, g) for g in allowed)]
    problem |= bool(bad)
    print(f"  {len(hits)} file(s){': ' + ', '.join(hits) if hits else ''}{'  <-- NOT ALLOWED' if bad else ''}")
print("  (the probes are printed as file counts only, so this log carries no feed text)")
sys.exit(1 if problem else 0)
PY
then
  fail "a known title or post line is in a file that may not quote it"
fi

echo "-- label files carry only ids, labels and numbers"
python3 - "$OUT" <<'PY' || fail "a label file has an unexpected key or a filled text field (above)"
import json, sys
from pathlib import Path
out = Path(sys.argv[1])
LABELS = {"id", "family", "tier", "evidence", "framing", "baseline", "realtime_infra", "production_claim",
          "prob", "probs", "latency_ms", "input_tokens", "at", "subtype", "stance", "reason"}
TEXT = {"reason", "note", "title", "titles", "text", "t", "x"}
bad = False
for p in sorted(out.glob("data/**/classified-*.jsonl")):
    if p.name.endswith(".errors.jsonl"):
        continue
    recs = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    keys = set().union(*(r.keys() for r in recs))
    extra = keys - LABELS
    filled = sorted(k for k in keys & TEXT if any(r.get(k) not in ("", None) for r in recs))
    status = "ok" if not extra and not filled else "FAIL"
    bad |= status == "FAIL"
    print(f"  {status:4s} {p.relative_to(out)}: {len(recs):,} rows; keys {', '.join(sorted(keys))}"
          + (f"; unexpected {sorted(extra)}" if extra else "") + (f"; text in {filled}" if filled else ""))
sys.exit(1 if bad else 0)
PY

echo "-- secrets"
if grep -rInE --exclude-dir=.git '(sk-[A-Za-z0-9_-]{24,}|vck_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|xox[abp]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|AI_GATEWAY_API_KEY=[A-Za-z0-9_-]{12,})' "$OUT"; then
  fail "possible secret (above)"
else
  echo "  none"
fi

echo "-- hard-coded project path in code"
if grep -rn --exclude-dir=.git --include='*.py' --include='*.ts' --include='*.mjs' "Path(\"$PROJECT" "$OUT"; then
  fail "a script still resolves the author's folder (above)"
else
  echo "  none; $(grep -rl --exclude-dir=.git "/Users/" "$OUT" | wc -l | tr -d ' ') files mention a local path in a comment, a default or a prompt"
fi

echo "-- excluded files"
leaked=0
while IFS= read -r f; do
  rel=${f#"$OUT"/}
  if excluded "$rel"; then fail "excluded file in the tree: $rel"; leaked=1; fi
done < <(find "$OUT" -path "$OUT/.git" -prune -o -type f -print)
[[ $leaked -eq 1 ]] || echo "  none of the excluded files is in the tree"

echo "-- every project file is shipped, or excluded on purpose"
rc=0
python3 - "$PROJECT" "$WORK/shipped.txt" "$WORK/stems.txt" "${EXCLUDED[@]}" -- "${LOCAL_ONLY[@]}" <<'PY' || rc=$?
import fnmatch, sys
from pathlib import Path
project = Path(sys.argv[1])
shipped = set(Path(sys.argv[2]).read_text().split())
stems = set(Path(sys.argv[3]).read_text().split())
sep = sys.argv.index("--")
excluded, local = sys.argv[4:sep], sys.argv[sep + 1:]
SKIP = {"node_modules", "__pycache__", ".ruff_cache", ".git"}
site = ["report/site/index.html", "report/site/charts/*", "report/site/v3/*"]
counts = {"shipped": 0, "page at the root": 0, "excluded": 0, "old charts": 0, "release tools": 0}

def stem_of(rel):
    name = Path(rel).stem
    for suffix in ("-light", "-dark"):
        name = name[: -len(suffix)] if name.endswith(suffix) else name
    return name
loose = []
for p in sorted(project.rglob("*")):
    rel = p.relative_to(project).as_posix()
    if not p.is_file() or SKIP & set(p.relative_to(project).parts) or p.name == ".DS_Store" or rel.startswith("publish/repo/"):
        continue
    if rel in shipped:
        counts["shipped"] += 1
    elif any(fnmatch.fnmatch(rel, g) for g in site):
        if rel.startswith("report/site/charts/") and stem_of(rel) not in stems:
            counts["old charts"] += 1  # step 4 warned about each one
        else:
            counts["page at the root"] += 1
    elif any(fnmatch.fnmatch(rel, g) for g in excluded):
        counts["excluded"] += 1
    elif rel in local:
        counts["release tools"] += 1
    else:
        loose.append(rel)
print("  " + ", ".join(f"{k} {v}" for k, v in counts.items()))
for rel in loose:
    print(f"  WARNING: not classified, so not shipped: {rel}")
if loose:
    print("  Add each to a list at the top of publish/stage.sh, with a reason in publish/PUBLISHING.md.")
    sys.exit(3)
PY
checked $rc "the file classification stopped"

echo "-- size"
python3 - "$OUT" "$MAX_MB" <<'PY' || fail "the tree is over ${MAX_MB} MB"
import sys
from pathlib import Path
out, limit = Path(sys.argv[1]), int(sys.argv[2])
files = [p for p in out.rglob("*") if p.is_file() and ".git" not in p.relative_to(out).parts]
sizes = sorted(((p.stat().st_size, p.relative_to(out).as_posix()) for p in files), reverse=True)
total = sum(s for s, _ in sizes)
print(f"  {total / 1e6:.1f} MB in {len(files)} files (limit {limit} MB); largest:")
for s, rel in sizes[:5]:
    print(f"    {s / 1e6:5.2f} MB  {rel}")
sys.exit(0 if total < limit * 1e6 else 1)
PY

if [[ ${SKIP_REPRO:-0} == 1 ]]; then
  echo "-- reproduction: skipped (SKIP_REPRO=1)"
else
  echo "-- reproduction (publish/check_repro.sh)"
  if ! "$HERE/check_repro.sh" "$OUT" 2>&1 | sed 's/^/  /'; then
    fail "the tree does not rebuild its own tables and page (above)"
  fi
fi

# ------------------------------------------------------------------------------- SUBSTACK.md
if [[ -f $HERE/SUBSTACK.md ]] && grep -q '<!-- charts:begin -->' "$HERE/SUBSTACK.md"; then
  rc=0
  python3 - "$HERE/SUBSTACK.md" "$OUT" "$OWNER" "$NAME" <<'PY' || rc=$?
import html, re, sys
from pathlib import Path
doc, out, owner, name = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]
rows = ["| # | Upload this PNG | Alt text (the chart's title) |", "|---|---|---|"]
source = ""
for svg in sorted(out.glob("charts/[0-9][0-9]-*-light.svg")):
    base = svg.name[: -len("-light.svg")]
    body = svg.read_text(encoding="utf-8")
    m = re.search(r"<title[^>]*>(.*?)</title>", body, re.S)
    title = html.unescape(m.group(1)).strip() if m else "(no title)"
    rows.append(f"| {int(base[:2])} | `publish/repo/charts/png/{base}.png` | {title} |")
    if not source:  # the chart's own source line, which wraps over two <text> lines
        texts = [html.unescape(re.sub(r"<[^>]+>", "", t)).strip() for t in re.findall(r"<text[^>]*>(.*?)</text>", body, re.S)]
        for i, t in enumerate(texts):
            if t.startswith("Source:"):
                parts = [t]
                for nxt in texts[i + 1:]:
                    if nxt.startswith("Disclosure") or not nxt:
                        break
                    parts.append(nxt)
                source = re.sub(r";\s*analysis by [^.;]+", "", " ".join(parts)).rstrip(" .;") + "."
                break
caption = f"{source} Disclosure: I'm CEO of Ably, a realtime infrastructure company." if source else "(no source line found in the charts)"
table = "\n".join(rows) + f"\n\nCaption for every chart:\n\n> {caption}"
text = doc.read_text()
outside = re.sub(r"<!-- charts:begin -->.*?<!-- charts:end -->", "", text, flags=re.S)
missing = [ref for ref in sorted(set(re.findall(r"charts/png/([0-9]{2}-[a-z0-9-]+)\.png", outside)))
           if not (out / "charts/png" / f"{ref}.png").exists()]
for ref in missing:
    print(f"WARNING: publish/SUBSTACK.md places charts/png/{ref}.png, which is not in the staged tree")
new = re.sub(r"(<!-- charts:begin -->\n).*?(\n<!-- charts:end -->)", lambda m: m.group(1) + table + m.group(2), text, flags=re.S)
if new != text:
    doc.write_text(new)
    print("\npublish/SUBSTACK.md: chart table refreshed from the staged titles")
else:
    print("\npublish/SUBSTACK.md: chart table already matches the staged titles")
sys.exit(3 if missing else 0)
PY
  checked $rc "the SUBSTACK.md refresh stopped"
fi

# ------------------------------------------------------------------------------- the tree
step "publish/repo/"
if command -v tree >/dev/null; then
  (cd "$OUT" && tree -a -I .git --dirsfirst --filelimit 16 -h --noreport . || true) | sed 's/^/  /'   # tree exits 2 when it folds a folder
else
  (cd "$OUT" && find . -maxdepth 2 | sort) | sed 's/^/  /'
fi
echo "  $(find "$OUT" -path "$OUT/.git" -prune -o -type f -print | wc -l | tr -d ' ') files"
if [[ $FAILED -ne 0 ]]; then
  printf '\nSTAGE FAILED: see the FAIL lines above. Nothing is published.\n'
  exit 1
fi
printf '\nSTAGED: %s is ready' "$OUT"
if [[ $WARNINGS -gt 0 ]]; then printf ', with %d warning(s) above.\n' "$WARNINGS"; else printf '.\n'; fi
[[ -x $HERE/publish.sh ]] && printf 'Next: publish/publish.sh --dry-run, then publish/publish.sh\n'
exit 0
