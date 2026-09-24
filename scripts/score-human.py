#!/usr/bin/env python3
"""Score model labels against the human labels on the 150-card sample.

Reads the export of review/labeller.html (default review/human-labels.jsonl)
and compares it with each model label file that exists:

  Sonnet v2        data/classified-sonnet-v2.jsonl   all seven fields
  Opus             data/classified-opus.jsonl        all seven fields
  Jev classifier   data/classified-jev.jsonl         family only (it has no not_a_jev_build)
  Grok hand labels review/hand-labels-grok.jsonl     all seven fields, on its overlap only

For each field it prints the accuracy with a 95% Wilson interval and Cohen's
kappa, for all scored cards, for the 100 random cards (an unbiased estimate
for the deduped base) and for the 50 rare-strata cards (from
review/human-sample-150-strata.json). A field counts only where both the
human and the model gave a value, so a skipped framing is not scored.
Cards marked unsure are left out unless you pass --include-unsure.
A missing model file is reported and skipped.

Usage:
  python3 scripts/score-human.py [labels.jsonl] [--include-unsure] [--strata PATH]
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIELDS = ["family", "tier", "evidence", "framing", "baseline", "realtime_infra", "production_claim"]
COMPARISONS = [
    ("Sonnet v2", "data/classified-sonnet-v2.jsonl", FIELDS),
    ("Opus", "data/classified-opus.jsonl", FIELDS),
    ("Jev classifier", "data/classified-jev.jsonl", ["family"]),
    ("Grok hand labels", "review/hand-labels-grok.jsonl", FIELDS),
]
BLOCKS = [("all", None), ("random-100", "random"), ("rare-50", "rare")]


def norm(v):
    """Booleans and yes/no strings become 'yes'/'no'; empty values become None."""
    if v is None:
        return None
    if isinstance(v, bool):
        return "yes" if v else "no"
    s = str(v).strip().lower()
    if s in ("", "null", "none_given", "skip", "skipped"):
        return None
    return {"true": "yes", "false": "no"}.get(s, s)


def read_jsonl(path: Path) -> tuple[dict[str, dict], int]:
    rows: dict[str, dict] = {}
    bad = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                rows[str(row["id"])] = row
            except (ValueError, KeyError, TypeError):
                bad += 1
    return rows, bad


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, centre - half), min(1.0, centre + half)


def kappa(pairs: list[tuple[str, str]]) -> float | None:
    n = len(pairs)
    if n == 0:
        return None
    po = sum(h == m for h, m in pairs) / n
    hc = Counter(h for h, _ in pairs)
    mc = Counter(m for _, m in pairs)
    pe = sum(hc[k] * mc.get(k, 0) for k in hc) / (n * n)
    return None if pe >= 1 else (po - pe) / (1 - pe)


def cell(pairs: list[tuple[str, str]]) -> str:
    n = len(pairs)
    if n == 0:
        return f"{'-':<24}"
    k = sum(h == m for h, m in pairs)
    lo, hi = wilson(k, n)
    return f"{k / n:5.0%} [{lo:4.0%}-{hi:4.0%}] n={n:<4}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("labels", nargs="?", default=str(ROOT / "review/human-labels.jsonl"))
    ap.add_argument("--include-unsure", action="store_true", help="also score cards marked unsure")
    ap.add_argument("--strata", default=str(ROOT / "review/human-sample-150-strata.json"))
    args = ap.parse_args()

    labels_path = Path(args.labels)
    if not labels_path.exists():
        print(f"No human labels at {labels_path}. Export them from review/labeller.html first.")
        return 2
    raw, bad = read_jsonl(labels_path)
    answered = {i: r for i, r in raw.items() if r.get("unsure") or any(norm(r.get(f)) for f in FIELDS)}
    unsure = {i for i, r in answered.items() if r.get("unsure")}
    human = {i: r for i, r in answered.items() if args.include_unsure or i not in unsure}

    block_of: dict[str, str] = {}
    strata_path = Path(args.strata)
    if strata_path.exists():
        for c in json.loads(strata_path.read_text(encoding="utf-8")).get("cards", []):
            block_of[str(c["id"])] = "random" if c.get("stratum") == "random" else "rare"
    else:
        print(f"note: {strata_path} not found, so the random/rare split is not available")

    print(f"Human labels: {labels_path}")
    print(
        f"  {len(raw)} lines, {len(answered)} answered, {len(unsure)} unsure "
        f"({'included' if args.include_unsure else 'left out'}), {len(human)} scored"
        + (f", {bad} unreadable lines" if bad else "")
    )
    src = Counter(r.get("text_source") or "unknown" for r in human.values())
    blk = Counter(block_of.get(i, "unknown") for i in human)
    print(f"  text_source: {dict(src)}; blocks: {dict(blk)}")
    secs = [r.get("seconds") or 0 for r in human.values() if (r.get("seconds") or 0) > 0]
    if secs:
        print(f"  time: median {statistics.median(secs):.0f} s per card, total {sum(secs) / 60:.0f} min")

    made, skipped = [], []
    for name, rel, fields in COMPARISONS:
        path = ROOT / rel
        if not path.exists():
            skipped.append(f"{name} ({rel} not found)")
            continue
        model, mbad = read_jsonl(path)
        common = [i for i in human if i in model]
        if not common:
            skipped.append(f"{name} (no cards in common)")
            continue
        made.append(name)
        print(f"\n== {name} vs human: {rel}, {len(common)} cards in common" + (f", {mbad} unreadable lines" if mbad else ""))
        print(f"{'field':<17} " + " ".join(f"{b:<24}" for b, _ in BLOCKS) + " kappa")
        for f in fields:
            pairs_by_block = {}
            for b, want in BLOCKS:
                pairs_by_block[b] = [
                    (norm(human[i].get(f)), norm(model[i].get(f)))
                    for i in common
                    if norm(human[i].get(f)) and norm(model[i].get(f)) and (want is None or block_of.get(i) == want)
                ]
            kap = kappa(pairs_by_block["all"])
            print(f"{f:<17} " + " ".join(cell(pairs_by_block[b]) for b, _ in BLOCKS) + (f" {kap:5.2f}" if kap is not None else "   n/a"))
        fam = [(norm(human[i].get("family")), norm(model[i].get("family"))) for i in common]
        misses = Counter((h, m) for h, m in fam if h and m and h != m)
        if misses:
            print("  top family disagreements (human -> model): " + "; ".join(f"{h} -> {m} x{c}" for (h, m), c in misses.most_common(5)))

    print("\nComparisons made: " + (", ".join(made) or "none"))
    if skipped:
        print("Skipped: " + "; ".join(skipped))
    print("random-100 is the unbiased estimate for the deduped base; all mixes in the oversampled rare strata.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
