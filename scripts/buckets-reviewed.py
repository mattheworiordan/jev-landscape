#!/usr/bin/env python3
"""The withdrawn bucket scheme (noise / hype / demo / cost-only / fast loop / material), kept for the record.

The buckets were written for the critical review of 2026-09-23 (Brain: work/content/drafts/jev-landscape-review.md)
and used in report v2. The independent audit of 2026-09-24 (review/critical-review-grok.md, claim 3) found that
they do not hold, so report v3 withdraws them and nothing in the current report reads them. This script
regenerates the record of what they said on the v2 labels. Plain json, no pandas. From the jev-landscape folder:

    python3 scripts/buckets-reviewed.py

It reads the Sonnet v2 labels (data/classified-sonnet-v2.jsonl) on the use-case base that analyze.py uses
(duplicates merged as in data/dedupe-groups.jsonl, not_a_jev_build left out, rubric rule 3 for the Snake card),
with the v1 labels (data/classified-sonnet.jsonl, every card v1 saw) for comparison. It prints three tables:
  A. the rules as pre-registered in jev-positioning-post.md, read literally,
  B. the rules as first applied in jev-landscape-findings.md (v1),
  C. the corrected rules proposed by the review,
and writes them to report/v1/buckets-on-v2-labels.md and report/v1/data/buckets-on-v2-labels/*.csv.
"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARDS = ROOT / 'data' / 'cards.json'
V2 = ROOT / 'data' / 'classified-sonnet-v2.jsonl'
V1 = ROOT / 'data' / 'classified-sonnet.jsonl'
GROUPS = ROOT / 'data' / 'dedupe-groups.jsonl'
OUT_MD = ROOT / 'report' / 'v1' / 'buckets-on-v2-labels.md'
OUT_DIR = ROOT / 'report' / 'v1' / 'data' / 'buckets-on-v2-labels'
GAMES = 'games_control_loops_simulation'
SNAKE_ID = '2101675124747338229'  # rubric rule 3: the Laya-vs-Jev Snake benchmark belongs in games (as analyze.py)
MEASURED = {'measured_demo', 'measured_production'}
UNMEASURED = {'demo_no_numbers', 'proposal_or_idea'}
FIELDS = ['family', 'tier', 'evidence', 'framing', 'baseline', 'realtime_infra']
SHORT = {
    'evals_and_judging': 'evals', 'classification_routing_triage': 'classify', 'moderation_and_guardrails': 'moderate',
    'agent_harness_and_tool_gating': 'agent', 'compaction_and_context': 'context', 'search_rerank_extraction': 'search',
    'browser_and_computer_use': 'browser', 'voice_and_turn_taking': 'voice', 'live_chat_streams_events': 'live',
    'collaboration_and_typing': 'collab', GAMES: 'games', 'data_and_telemetry': 'data', 'trading_and_markets': 'trading',
    'other_or_meta': 'other',
}


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def load():
    """(v2 rows on the use-case base, v1 rows on every card v1 saw), in feed order, with views v and likes f."""
    cards = json.loads(CARDS.read_text())['cards']
    merged = {i for g in read_jsonl(GROUPS) for i in g['merged']}
    v2 = {}
    for r in read_jsonl(V2):
        v2.setdefault(r['id'], r)
    v1 = {}
    for r in read_jsonl(V1):
        v1.setdefault(r['id'], r)
    base, old = [], []
    for c in cards:
        i = str(c['id'])
        vf = {'v': int(c.get('v') or 0), 'f': int(c.get('f') or 0)}
        if i in v1:
            old.append({'id': i, **{k: v1[i][k] for k in FIELDS}, **vf})
        r = v2.get(i)
        if r is None or i in merged:
            continue
        fam = GAMES if i == SNAKE_ID else r['family']
        if fam == 'not_a_jev_build':
            continue
        base.append({'id': i, **{k: r[k] for k in FIELDS}, 'family': fam, **vf})
    return base, old


def is_noise(r):
    return r['family'] == 'other_or_meta' or r['evidence'] == 'commentary_or_meme'


def applied(r):
    """The rules as applied in the findings note (Fable, 2026-09-23)."""
    if is_noise(r):
        return 'noise'
    if (r['tier'] in ('frame', 'feel', 'turn', 'interaction') and r['realtime_infra']
            and r['baseline'] in ('classic_classifier_or_ml', 'rules_or_regex', 'none')
            and r['evidence'] in MEASURED):
        return 'material'
    if r['evidence'] in UNMEASURED:
        if r['framing'] in ('cost', 'latency', 'capability') or r['baseline'] == 'frontier_llm':
            return 'hype'
        return 'unproven_demo'
    return 'cost_only'


def preregistered(r):
    """jev-positioning-post.md, 'the interpretation rubric, fixed BEFORE the numbers land', read literally.
    Anything the written tests do not cover goes to 'not covered'."""
    if is_noise(r):
        return 'noise'
    if (r['tier'] in ('turn', 'interaction') and r['realtime_infra']
            and r['baseline'] in ('classic_classifier_or_ml', 'none') and r['evidence'] in MEASURED):
        return 'material'
    if r['evidence'] in UNMEASURED and r['framing'] in ('cost', 'latency') and r['baseline'] == 'frontier_llm':
        return 'hype'
    if r['evidence'] in MEASURED and r['tier'] in ('batch', 'task') and r['baseline'] in ('small_llm', 'vendor_api'):
        return 'cost_only'
    return 'not_covered'


def corrected(r):
    """The review's proposal. Order matters."""
    if is_noise(r):
        return 'noise'
    if r['evidence'] in UNMEASURED:
        # hype needs a comparative or quantitative claim with no number behind it;
        # a capability-led or claim-free demo is just a demo
        if r['framing'] in ('cost', 'latency', 'accuracy') or r['baseline'] != 'none':
            return 'hype'
        return 'demo'
    # measured from here on
    if r['realtime_infra'] and r['tier'] in ('turn', 'interaction'):
        if r['baseline'] in ('small_llm', 'vendor_api'):
            return 'cost_only'  # a small LLM or a vendor already did it at this tier
        if r['baseline'] == 'frontier_llm':
            return 'material_vs_frontier'  # latency-enabled, but not shown against a small LLM
        return 'material'  # classic ML, rules or no stated alternative
    if r['tier'] in ('frame', 'feel'):
        return 'fast_loop'  # games and control loops: Jev's 200-400 ms is outside the <100 ms budget
    return 'cost_only'


TABLES = [
    ('preregistered', 'A. As pre-registered, read literally', preregistered, ['noise', 'hype', 'cost_only', 'material', 'not_covered']),
    ('applied', 'B. As first applied (v1 findings note)', applied, ['noise', 'hype', 'unproven_demo', 'cost_only', 'material']),
    ('corrected', 'C. Corrected (review)', corrected, ['noise', 'hype', 'demo', 'cost_only', 'fast_loop', 'material_vs_frontier', 'material']),
]
RULES = """| rule | pre-registered (Brain `work/content/drafts/jev-positioning-post.md`, "fixed BEFORE the numbers land") | as first applied (findings note, v1) | corrected (review) |
|---|---|---|---|
| noise | other_or_meta, or commentary | same | same |
| hype | unmeasured AND cost or latency lead AND frontier-LLM baseline | unmeasured AND (cost, latency or capability lead OR frontier baseline) | unmeasured AND (cost, latency or accuracy lead OR any named baseline) |
| demo | (no bucket) | "unproven demo": any other unmeasured card | any other unmeasured card |
| cost-only | measured AND batch or task tier AND small-LLM or vendor baseline | every other measured card | measured, not in the buckets below ("measured, not shown to be new") |
| material | measured AND realtime_infra AND turn or interaction tier AND classic-ML or no baseline | measured AND realtime_infra AND frame, feel, turn or interaction tier AND classic-ML, rules or no baseline | measured AND realtime_infra AND turn or interaction tier AND classic-ML, rules or no baseline; a small-LLM or vendor baseline goes to cost-only |
| material vs frontier | (no bucket) | (inside cost-only) | as material, but the baseline is a frontier LLM |
| fast loop | (no bucket) | (inside material or cost-only) | measured AND frame or feel tier |
| not covered | anything the four tests do not place | (none) | (none) |

"Measured" is measured_demo or measured_production; "unmeasured" is demo_no_numbers or proposal_or_idea."""


def pct(x):
    return f'{100 * x:.1f}%'


def md_table(head, rows):
    return '\n'.join(['| ' + ' | '.join(head) + ' |', '|' + '|'.join(['---'] * len(head)) + '|']
                     + ['| ' + ' | '.join(str(c) for c in r) + ' |' for r in rows])


def main():
    base, old = load()
    n, n1 = len(base), len(old)
    tv, tl = sum(r['v'] for r in base), sum(r['f'] for r in base)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    head = ['bucket', 'posts', 'share of posts', 'share of views', 'share of likes', f'v1 labels (all {n1:,} cards), share of posts']
    per_card = {r['id']: {} for r in base}
    counts, blocks = {}, []
    for key, title, fn, order in TABLES:
        c, v, lk = Counter(), Counter(), Counter()
        for r in base:
            b = fn(r)
            per_card[r['id']][key] = b
            c[b] += 1
            v[b] += r['v']
            lk[b] += r['f']
        c1 = Counter(fn(r) for r in old)
        rows = [[b, c[b], pct(c[b] / n), pct(v[b] / tv), pct(lk[b] / tl), pct(c1[b] / n1)] for b in order]
        counts[key] = c
        with open(OUT_DIR / f'08_buckets_{key}.csv', 'w', newline='') as fh:
            w = csv.writer(fh, lineterminator='\n')
            w.writerow(head)
            w.writerows(rows)
        print(f'\n### {title}\n')
        print(md_table(head, [[b, f'{p:,}', *rest] for b, p, *rest in rows]))
        blocks.append(f'**{title}**\n\n' + md_table(head, [[b, f'{p:,}', *rest] for b, p, *rest in rows]))
    with open(OUT_DIR / '08_bucket_per_card.csv', 'w', newline='') as fh:
        w = csv.writer(fh, lineterminator='\n')
        w.writerow(['id', 'family', 'tier', 'evidence', 'framing', 'baseline', 'realtime_infra', 'bucket_preregistered', 'bucket_applied', 'bucket_corrected'])
        for r in base:
            b = per_card[r['id']]
            w.writerow([r['id'], r['family'], r['tier'], r['evidence'], r['framing'], r['baseline'], r['realtime_infra'],
                        b['preregistered'], b['applied'], b['corrected']])

    mat = [r for r in base if per_card[r['id']]['corrected'] in ('material', 'material_vs_frontier')]
    mat_ng = [r for r in mat if r['family'] != GAMES]
    ff = [r for r in base if per_card[r['id']]['applied'] == 'material' and r['tier'] in ('feel', 'frame')]
    nc = counts['preregistered']['not_covered']
    by_fam = Counter(r['family'] for r in mat).most_common()
    mp = sum(1 for r in mat if r['evidence'] == 'measured_production')
    deviation = (
        f"**Deviation from pre-registration.** The positioning post fixed four tests before the labels existed. Read literally on the v2 labels, "
        f"they place only {pct(1 - nc / n)} of cards: {nc:,} ({pct(nc / n)}) fall into no bucket, because the tests leave out demos with no cost or "
        f"latency claim, measured cards with no baseline, and the frame and feel tiers. So the scheme was finished after the data arrived. The first "
        f"applied version filled the gaps by widening the rules: it let the frame and feel tiers and a rules baseline into \"material\" ({len(ff)} "
        f"feel-tier or frame-tier cards on v2 labels, {sum(1 for r in ff if r['family'] == GAMES)} of them games), counted every unmeasured card that "
        f"leads with capability as hype, and made cost-only the home of every other measured card. The corrected rules keep the pre-registered "
        f"material test (turn or interaction tier, realtime, measured), because Jev's own p50 of about 400 ms is outside the frame and feel budgets; "
        f"they add a rules baseline to it, move measured frame-tier and feel-tier cards to a separate \"fast loop\" bucket, report measured realtime "
        f"results against a frontier LLM on their own, keep hype for unmeasured cards that claim a cost, speed or accuracy win or name a comparison, "
        f"and call every other unmeasured card a demo."
    )
    material = (
        f"Corrected material plus material vs frontier: **{len(mat)} cards ({pct(len(mat) / n)})**, {len(mat_ng)} of them outside games "
        f"({pct(len(mat_ng) / n)} of posts); {mp} {'is' if mp == 1 else 'are'} measured production. By family: "
        + ', '.join(f'{SHORT.get(k, k)} {v}' for k, v in by_fam) + '.'
    )
    doc = f"""# The withdrawn bucket scheme, on the v2 labels (record)

> **Withdrawn on 24 September 2026.** The independent audit ([review/critical-review-grok.md](../../review/critical-review-grok.md), claim 3) found that these buckets do not hold. "Cost-only" was the residual bin for every other measured card, and most of it has no comparison at all. None of the {len(mat)} "materially different" cards did something that was unavailable before: an LLM, rules, a vendor API or a classic model already did each job. Report v3 ([../landscape.md](../landscape.md)) replaces the buckets with a measurement ladder and the audited estimates. This page keeps the tables as report v2 published them (its section 8), regenerated by `scripts/buckets-reviewed.py` on the Sonnet v2 labels of the {n:,}-post use-case base. Nothing in the current report reads these files.

{RULES}

{chr(10).join(b + chr(10) for b in blocks)}
{deviation}

{material}

CSVs: [data/buckets-on-v2-labels/](data/buckets-on-v2-labels/).
"""
    OUT_MD.write_text(doc)
    print(f'\n{material}\nwrote {OUT_MD.relative_to(ROOT)} and {OUT_DIR.relative_to(ROOT)}/*.csv')
    return 0


if __name__ == '__main__':
    sys.exit(main())
