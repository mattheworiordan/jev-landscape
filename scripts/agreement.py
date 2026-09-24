#!/usr/bin/env python3
"""Pairwise agreement between label files, and accuracy against human labels.

    python3 scripts/agreement.py [name=path ...] [--human PATH] [--matrix]

With no name=path arguments it uses every default file that exists:
    sonnet  data/classified-sonnet-v2.jsonl   (Claude Sonnet 5, rubric v2)
    opus    data/classified-opus.jsonl        (Claude Opus 5.5, rubric v2)
    jev     data/classified-jev.jsonl         (Jev, family only, v1's 14 families)
    grok    review/hand-labels-grok.jsonl     (the Grok audit labels, rubric v2)
The human reference is review/human-labels.jsonl when it exists (--human
overrides; .jsonl or .csv with the same field names). Rows whose value for a
field is empty or null are treated as not labelled for that field.

Prints, for every pair of label files, on the ids both files label:
  1. per-field agreement (%) and Cohen's kappa;
  2. a 14-way family confusion summary: per-family counts, agreement on each
     family (Jaccard: both / either), and the largest cross-family confusions
     (--matrix adds the full 14 x 14 table);
and, when a human file exists, each file's accuracy against the human labels
per field, with 95% Wilson intervals and kappa.

Fields. "family" is the 14-way like-for-like family: rubric v2's
not_a_jev_build is counted as other_or_meta, as in hand_agreement.py, so that
Jev's v1 labels compare with the v2 files. "family_v2" is the 15-way v2-native
family, scored only between files that carry the full v2 rubric. A file with no
"tier" field in any row (Jev) is treated as family-only.
Plain Python; no third-party packages.
"""
from __future__ import annotations

import csv
import json
import math
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTS = {
    'sonnet': ROOT / 'data' / 'classified-sonnet-v2.jsonl',
    'opus': ROOT / 'data' / 'classified-opus.jsonl',
    'jev': ROOT / 'data' / 'classified-jev.jsonl',
    'grok': ROOT / 'review' / 'hand-labels-grok.jsonl',
}
HUMAN = ROOT / 'review' / 'human-labels.jsonl'
FAMILIES_14 = [
    'evals_and_judging', 'classification_routing_triage', 'moderation_and_guardrails',
    'agent_harness_and_tool_gating', 'compaction_and_context', 'search_rerank_extraction',
    'browser_and_computer_use', 'voice_and_turn_taking', 'live_chat_streams_events',
    'collaboration_and_typing', 'games_control_loops_simulation', 'data_and_telemetry',
    'trading_and_markets', 'other_or_meta',
]
FIELDS = ['family', 'family_v2', 'tier', 'evidence', 'framing', 'baseline', 'realtime_infra', 'production_claim']
BOOL_FIELDS = {'realtime_infra', 'production_claim'}
TRUE = {'true', 't', 'yes', 'y', '1'}
FALSE = {'false', 'f', 'no', 'n', '0'}


# ---------------------------------------------------------------- loading

def _norm(field: str, v):
    """Normalise one raw value; None means not labelled."""
    if v is None:
        return None
    if field in BOOL_FIELDS:
        if isinstance(v, bool):
            return v
        s = str(v).strip().lower()
        return True if s in TRUE else False if s in FALSE else None
    s = str(v).strip()
    return s or None


def load(path: Path) -> tuple[dict[str, dict], bool]:
    """Returns (id -> normalised row, full_rubric). full_rubric is False for family-only files."""
    if path.suffix == '.csv':
        with open(path, newline='', encoding='utf-8') as fh:
            raw = list(csv.DictReader(fh))
    else:
        raw = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    full = any('tier' in r for r in raw)
    rows: dict[str, dict] = {}
    for r in raw:
        rid = str(r.get('id', '')).strip()
        if not rid:
            continue
        fam = _norm('family', r.get('family'))
        row = {
            'family': 'other_or_meta' if fam == 'not_a_jev_build' else fam,
            'family_v2': fam if full else None,
        }
        for f in FIELDS[2:]:
            row[f] = _norm(f, r.get(f)) if full else None
        rows[rid] = row
    return rows, full


# ---------------------------------------------------------------- statistics

def kappa(pairs: list[tuple]) -> float:
    n = len(pairs)
    if not n:
        return math.nan
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return (po - pe) / (1 - pe) if pe < 1 else math.nan


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if not n:
        return (math.nan, math.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def pairs_for(a: dict[str, dict], b: dict[str, dict], field: str) -> list[tuple]:
    out = []
    for i in a.keys() & b.keys():
        va, vb = a[i][field], b[i][field]
        if va is not None and vb is not None:
            out.append((va, vb))
    return out


def pct(x: float) -> str:
    return 'n/a' if math.isnan(x) else f'{100 * x:.1f}%'


def num(x: float) -> str:
    return 'n/a' if math.isnan(x) else f'{x:.3f}'


# ---------------------------------------------------------------- report

def field_table(a: dict, b: dict) -> None:
    print(f"  {'field':<17} {'n':>5} {'agree':>7} {'kappa':>7}")
    for f in FIELDS:
        p = pairs_for(a, b, f)
        if not p:
            continue
        k = sum(x == y for x, y in p)
        print(f'  {f:<17} {len(p):>5} {pct(k / len(p)):>7} {num(kappa(p)):>7}')


def family_summary(na: str, a: dict, nb: str, b: dict, show_matrix: bool) -> None:
    p = pairs_for(a, b, 'family')
    if not p:
        return
    ca, cb = Counter(x for x, _ in p), Counter(y for _, y in p)
    both = Counter(x for x, y in p if x == y)
    fams = FAMILIES_14 + sorted((set(ca) | set(cb)) - set(FAMILIES_14))  # unknown labels last
    print(f'  14-way family ({len(p)} ids): count by {na}, count by {nb}, both, Jaccard (both / either)')
    for f in fams:
        either = ca[f] + cb[f] - both[f]
        j = both[f] / either if either else math.nan
        print(f'    {f:<32} {ca[f]:>5} {cb[f]:>5} {both[f]:>5} {pct(j):>7}')
    conf = Counter((x, y) for x, y in p if x != y).most_common(8)
    if conf:
        print(f'  largest confusions ({na} -> {nb}):')
        for (x, y), c in conf:
            print(f'    {c:>4}  {x} -> {y}')
    if show_matrix:
        m = Counter(p)
        abbr = {f: ''.join(w[0] for w in f.split('_'))[:4] for f in fams}
        print(f"  matrix (rows {na}, columns {nb}): " + ' '.join(f'{abbr[f]}={f}' for f in fams))
        print('    ' + ' ' * 5 + ''.join(f'{abbr[f]:>5}' for f in fams))
        for x in fams:
            print(f'    {abbr[x]:<5}' + ''.join(f'{m[(x, y)]:>5}' for y in fams))


def accuracy(name: str, rows: dict, human: dict) -> None:
    print(f'\n{name} vs human')
    print(f"  {'field':<17} {'n':>5} {'correct':>8} {'accuracy':>9} {'95% Wilson':>17} {'kappa':>7}")
    for f in FIELDS:
        p = pairs_for(rows, human, f)
        if not p:
            continue
        k = sum(x == y for x, y in p)
        lo, hi = wilson(k, len(p))
        print(f'  {f:<17} {len(p):>5} {k:>8} {pct(k / len(p)):>9} {pct(lo):>8}-{pct(hi):<8} {num(kappa(p)):>7}')


def main(argv: list[str]) -> None:
    human_path: Path | None = HUMAN
    show_matrix = False
    named: dict[str, Path] = {}
    it = iter(argv)
    for arg in it:
        if arg == '--human':
            human_path = Path(next(it))
        elif arg == '--matrix':
            show_matrix = True
        elif '=' in arg:
            k, v = arg.split('=', 1)
            named[k] = Path(v)
        else:
            raise SystemExit(f'unrecognised argument {arg!r}; use name=path, --human PATH or --matrix')
    if not named:
        named = dict(DEFAULTS)

    files: dict[str, dict] = {}
    for name, path in named.items():
        path = path if path.is_absolute() else ROOT / path
        if not path.exists():
            print(f'skip {name}: {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path} not found')
            continue
        rows, full = load(path)
        files[name] = rows
        print(f"{name}: {len(rows)} ids from {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}"
              f"{'' if full else ' (family only)'}")

    for (na, a), (nb, b) in combinations(files.items(), 2):
        print(f'\n=== {na} vs {nb}: {len(a.keys() & b.keys())} overlapping ids')
        field_table(a, b)
        family_summary(na, a, nb, b, show_matrix)

    if human_path is not None:
        hp = human_path if human_path.is_absolute() else ROOT / human_path
        if hp.exists():
            human, _ = load(hp)
            print(f'\nhuman reference: {len(human)} ids from {hp}')
            for name, rows in files.items():
                accuracy(name, rows, human)
        else:
            print(f'\nno human labels at {hp}; accuracy section skipped')


if __name__ == '__main__':
    main(sys.argv[1:])
