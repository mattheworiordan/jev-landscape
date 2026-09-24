#!/usr/bin/env python3
"""Step 2a: find duplicate cards (review item 8) and choose one card per project.

    python3 scripts/dedupe.py        (from the jev-landscape folder)

Rules, applied to data/cards.json:
  url     two cards share a post URL.
  chips   two cards carry the same non-empty chip set AND near-identical titles:
          titles lower-cased, punctuation removed, split on whitespace, token
          Jaccard >= 0.8.
  text    two cards with NO chips and near-identical titles (as above) whose post
          text is also near-identical (character-trigram Jaccard >= 0.6, links
          removed). An empty chip set carries no evidence that two posts are the
          same project: read literally, "identical chip set plus near-identical
          title" would also merge different people's builds that share a generic
          title (three separate Tetris players, three Magic 8 Ball apps, "Game
          built with Jev"), whose texts overlap at 0.01 to 0.42. The true
          duplicates among the no-chip pairs overlap at 0.79 to 1.00.
Pairs are joined transitively. Each group keeps its most-viewed card (ties: the
lower id) and records the merged ids. Views of merged cards are not added to the
kept card; they are reported as dropped views.

Also reported, not applied (a sensitivity check): cards that share a set of two
or more chips but whose titles differ. Some are cross-author or cross-language
reposts (a curator retelling a build), others coincidences (TypeSafe's own
"70 ms" and "500 ms", "1x cheaper, 1x faster").

Writes data/dedupe-groups.jsonl and report/data/00_dedupe_groups.csv; imported by
analyze.py (find_duplicates).
"""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TITLE_JACCARD = 0.8
TEXT_JACCARD = 0.6


def title_tokens(t: str) -> set[str]:
    return set(re.sub(r'[^\w\s]', ' ', (t or '').lower()).split())


def text_grams(x: str, n: int = 3) -> set[str]:
    x = re.sub(r'https?://\S+', '', (x or '').lower())
    x = re.sub(r'\s+', ' ', x).strip()
    return {x[i:i + n] for i in range(max(0, len(x) - n + 1))}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if (a | b) else 1.0


def chip_key(c: dict) -> tuple:
    return tuple(sorted(c.get('chips') or []))


def views(c: dict) -> int:
    return int(c.get('v') or 0)


def find_duplicates(cards: list[dict]) -> dict:
    """Returns {'groups': [...], 'merged_to': {merged_id: kept_id}, 'loose_chip_sets': [...]}."""
    by_id = {c['id']: c for c in cards}
    parent = {c['id']: c['id'] for c in cards}
    rules: dict[frozenset, str] = {}

    def find(i: str) -> str:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: str, b: str, rule: str) -> None:
        rules.setdefault(frozenset((a, b)), rule)
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    by_url = defaultdict(list)
    for c in cards:
        by_url[(c.get('url') or '').strip().lower()].append(c['id'])
    for u, ids in by_url.items():
        if u:
            for other in ids[1:]:
                union(ids[0], other, 'url')

    by_chips = defaultdict(list)
    for c in cards:
        by_chips[chip_key(c)].append(c)
    tt = {c['id']: title_tokens(c['t']) for c in cards}
    for key, grp in by_chips.items():
        for i in range(len(grp)):
            for j in range(i + 1, len(grp)):
                a, b = grp[i], grp[j]
                if jaccard(tt[a['id']], tt[b['id']]) < TITLE_JACCARD:
                    continue
                if key:
                    union(a['id'], b['id'], 'chips')
                elif jaccard(text_grams(a['x']), text_grams(b['x'])) >= TEXT_JACCARD:
                    union(a['id'], b['id'], 'text')

    members = defaultdict(list)
    for c in cards:
        members[find(c['id'])].append(c['id'])
    groups, merged_to = [], {}
    for ids in members.values():
        if len(ids) < 2:
            continue
        keep = sorted(ids, key=lambda i: (-views(by_id[i]), i))[0]
        merged = sorted(i for i in ids if i != keep)
        for m in merged:
            merged_to[m] = keep
        used = sorted({r for pair, r in rules.items() if pair <= set(ids)})
        groups.append({
            'keep': keep,
            'merged': merged,
            'rule': '+'.join(used),
            'authors': sorted({by_id[i]['sn'] for i in ids}),
            'kept_views': views(by_id[keep]),
            'dropped_views': sum(views(by_id[m]) for m in merged),
            'dropped_likes': sum(int(by_id[m].get('f') or 0) for m in merged),
            'titles': [by_id[i]['t'] for i in [keep] + merged],
            'urls': [by_id[i]['url'] for i in [keep] + merged],
        })
    groups.sort(key=lambda g: -g['kept_views'])

    loose = []
    for key, grp in by_chips.items():
        if len(key) >= 2 and len(grp) >= 2:
            roots = {find(c['id']) for c in grp}
            if len(roots) > 1:
                loose.append({'chips': list(key), 'cards': len(grp), 'unmerged_extra_cards': len(roots) - 1,
                              'authors': sorted({c['sn'] for c in grp}), 'titles': [c['t'] for c in grp]})
    return {'groups': groups, 'merged_to': merged_to, 'loose_chip_sets': loose}


def main() -> None:
    cards = json.loads((ROOT / 'data' / 'cards.json').read_text())['cards']
    res = find_duplicates(cards)
    g = res['groups']
    with open(ROOT / 'data' / 'dedupe-groups.jsonl', 'w') as fh:
        for row in g:
            fh.write(json.dumps(row, ensure_ascii=False) + '\n')
    out = ROOT / 'report' / 'data' / '00_dedupe_groups.csv'
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['keep', 'merged', 'rule', 'authors', 'kept_views', 'dropped_views', 'dropped_likes', 'titles', 'urls'])
        for row in g:
            w.writerow([row['keep'], ' '.join(row['merged']), row['rule'], ' '.join(row['authors']), row['kept_views'],
                        row['dropped_views'], row['dropped_likes'], ' || '.join(row['titles']), ' '.join(row['urls'])])
    n_merged = len(res['merged_to'])
    print(f"{len(cards):,} cards; {len(g)} duplicate groups; {n_merged} cards merged into their group's most-viewed card; "
          f"{len(cards) - n_merged:,} remain. Dropped views {sum(x['dropped_views'] for x in g):,}.")
    for row in g:
        print(f"  [{row['rule']}] keep {row['keep']} ({row['kept_views']:,} views) <- {', '.join(row['merged'])} | "
              f"{'/'.join(row['authors'])} | {row['titles'][0]}")
    lo = res['loose_chip_sets']
    print(f"Not applied: {len(lo)} sets of 2+ identical chips span unmerged cards "
          f"({sum(x['unmerged_extra_cards'] for x in lo)} extra cards would merge under a chips-only rule).")


if __name__ == '__main__':
    main()
