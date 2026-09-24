#!/usr/bin/env python3
"""Per-field agreement of a Sonnet label file with the 120 review hand labels.

    python3 scripts/hand_agreement.py [--reference report/human-labels-120.csv] [labels.jsonl ...]

With no arguments it compares data/classified-sonnet.jsonl (v1) and, where they
exist, the v2 pilot files and data/classified-sonnet-v2.jsonl.

The hand labels (data/hand-labels-120.jsonl) were made against the v1 rubric by
the review agent (Claude Opus 5.5), blind to Sonnet and Jev. They are a careful
reader's labels, not ground truth. v1 had no not_a_jev_build family: the review
put those 7 cards in other_or_meta with a note ("NOT a Jev build", "NOT Jev",
"built WITHOUT Jev"). So family is scored two ways:
  family        like for like: v2's not_a_jev_build counted as other_or_meta
                (the number to compare with v1's 68.3%);
  family_v2     v2-native: the 7 noted cards counted as not_a_jev_build.
--reference swaps in another reference, such as the filled human sheet
(report/human-labels-120.csv, v2 families, "true"/"false" booleans).
Imported by analyze.py (load_hand, score).
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HAND = ROOT / 'data' / 'hand-labels-120.jsonl'
FIELDS = ['family', 'family_v2', 'tier', 'evidence', 'framing', 'baseline', 'realtime_infra', 'production_claim']
NOT_JEV_NOTE = re.compile(r'^(NOT (a )?Jev|built WITHOUT Jev)', re.I)
V1_REVIEW = {  # the review's v1 numbers, for the side-by-side
    'family': 68.3, 'tier': 67.5, 'evidence': 84.2, 'framing': 63.3,
    'baseline': 81.7, 'realtime_infra': 90.0, 'production_claim': 94.2,
}


def read_jsonl(p) -> list[dict]:
    p = Path(p)
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []


def load_hand(path: Path | str | None = None) -> dict[str, dict]:
    path = Path(path) if path else HAND
    out = {}
    if path.suffix == '.csv':
        with open(path, newline='', encoding='utf-8') as fh:
            for r in csv.DictReader(fh):
                if not (r.get('family') or '').strip():
                    continue  # row not labelled yet
                r = {k: (v.strip() if isinstance(v, str) else v) for k, v in r.items()}
                for b in ('realtime_infra', 'production_claim'):
                    r[b] = r[b].lower() in ('true', 't', 'yes', 'y', '1')
                r['family_v2'] = r['family']
                r['family'] = 'other_or_meta' if r['family'] == 'not_a_jev_build' else r['family']
                out[r['id']] = r
        return out
    for r in read_jsonl(path):
        r = dict(r)
        r['family_v2'] = 'not_a_jev_build' if NOT_JEV_NOTE.search(r.get('note', '')) else r['family']
        out[r['id']] = r
    return out


def _value(row: dict, field: str):
    if field == 'family':
        return 'other_or_meta' if row['family'] == 'not_a_jev_build' else row['family']
    if field == 'family_v2':
        return row['family']
    return row[field]


def kappa(pairs: list[tuple]) -> float:
    n = len(pairs)
    if not n:
        return float('nan')
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / n ** 2
    return (po - pe) / (1 - pe) if pe < 1 else float('nan')


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if not n:
        return (float('nan'), float('nan'))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (c - h, c + h)


def score(labels: dict[str, dict], hand: dict[str, dict] | None = None) -> dict:
    """labels: id -> row with the seven rubric fields. Returns field -> stats."""
    hand = hand or load_hand()
    ids = [i for i in hand if i in labels]
    out = {'n': len(ids)}
    for f in FIELDS:
        hf = 'family_v2' if f == 'family_v2' else f
        pairs = [(_value(labels[i], f), hand[i][hf] if f != 'family' else hand[i]['family']) for i in ids]
        k = sum(a == b for a, b in pairs)
        lo, hi = wilson(k, len(pairs))
        conf = Counter((a, b) for a, b in pairs if a != b).most_common(4)
        out[f] = {'agree': k, 'n': len(pairs), 'rate': k / len(pairs) if pairs else float('nan'),
                  'kappa': kappa(pairs), 'ci': (lo, hi), 'top_confusions_label_to_hand': conf}
    return out


def main(paths: list[str]) -> None:
    ref = None
    if paths[:1] == ['--reference']:
        ref, paths = paths[1], paths[2:]
    if not paths:
        paths = [str(ROOT / 'data' / 'classified-sonnet.jsonl')]
        paths += sorted(str(p) for p in (ROOT / 'data' / 'pilot').glob('classified-sonnet-v2.pilot*.jsonl'))
        if (ROOT / 'data' / 'classified-sonnet-v2.jsonl').exists():
            paths.append(str(ROOT / 'data' / 'classified-sonnet-v2.jsonl'))
    hand = load_hand(ref)
    print(f"reference: {ref or HAND} ({len(hand)} labelled rows)")
    res = {}
    for p in paths:
        rows = {r['id']: r for r in read_jsonl(p)}
        res[Path(p).name] = score(rows, hand)
    names = list(res)
    print('| field | review v1 | ' + ' | '.join(names) + ' |')
    print('|---|---|' + '---|' * len(names))
    for f in FIELDS:
        cells = [f"{100 * res[nm][f]['rate']:.1f}% ({res[nm][f]['agree']}/{res[nm][f]['n']}, k {res[nm][f]['kappa']:.2f})" for nm in names]
        print(f"| {f} | {V1_REVIEW.get(f, '')} | " + ' | '.join(cells) + ' |')
    for nm in names:
        print(f'\n{nm}: largest disagreements (label -> hand)')
        for f in ['family', 'tier', 'evidence', 'framing', 'baseline', 'realtime_infra', 'production_claim']:
            print(f"  {f}: {res[nm][f]['top_confusions_label_to_hand']}")


if __name__ == '__main__':
    main(sys.argv[1:])
