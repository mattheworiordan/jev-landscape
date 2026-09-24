#!/usr/bin/env python3
"""Seeded sample for the critical review. Does not print card text.

Population matches scripts/analyze.py: drop ids listed as merged in
data/dedupe-groups.jsonl, then drop family == not_a_jev_build.
That is the use-case base the published shares use.

Seed 20260924. random.Random.sample on sorted id lists, in the order below.
Negatives are the model's complement for that stratum (a card can sit in
more than one negative stratum). Exhaustive strata are not sampled.

Writes:
  review/work/strata.json   population sizes, sampled ids, stratum membership
  review/blind/batch-NN.jsonl   card fields only (no model labels)
"""
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REV = ROOT / "review"
BLIND = REV / "blind"
WORK = REV / "work"

RT = {"voice_and_turn_taking", "live_chat_streams_events", "collaboration_and_typing"}
REPL = {"classic_classifier_or_ml", "rules_or_regex", "vendor_api"}
GAMES = "games_control_loops_simulation"
MEASURED = {"measured_demo", "measured_production"}
UNMEASURED = {"demo_no_numbers", "proposal_or_idea"}
BATCH = 40


def corrected(r):
    if r["family"] == "other_or_meta" or r["evidence"] == "commentary_or_meme":
        return "noise"
    if r["evidence"] in UNMEASURED:
        if r["framing"] in ("cost", "latency", "accuracy") or r["baseline"] != "none":
            return "hype"
        return "demo"
    if r["realtime_infra"] and r["tier"] in ("turn", "interaction"):
        if r["baseline"] in ("small_llm", "vendor_api"):
            return "cost_only"
        if r["baseline"] == "frontier_llm":
            return "material_vs_frontier"
        return "material"
    if r["tier"] in ("frame", "feel"):
        return "fast_loop"
    return "cost_only"


def main():
    cards = {c["id"]: c for c in json.load(open(ROOT / "data/cards.json"))["cards"]}
    dropped = set()
    for line in open(ROOT / "data/dedupe-groups.jsonl"):
        if line.strip():
            dropped.update(json.loads(line)["merged"])
    rows = []
    for line in open(ROOT / "data/classified-sonnet-v2.jsonl"):
        if not line.strip():
            continue
        r = json.loads(line)
        if r["id"] in dropped:
            continue
        rows.append(r)
    by_id = {}
    for r in rows:
        by_id[r["id"]] = r  # last wins if a duplicate id survived
    rows = list(by_id.values())
    base = [r for r in rows if r["family"] != "not_a_jev_build"]
    base.sort(key=lambda r: r["id"])

    for r in base:
        r["_bucket"] = corrected(r)

    def ids(pred):
        return [r["id"] for r in base if pred(r)]

    exhaustive = {
        "measured_production": ids(lambda r: r["evidence"] == "measured_production"),
        "material": ids(lambda r: r["_bucket"] in ("material", "material_vs_frontier")),
        "realtime_family": ids(lambda r: r["family"] in RT),
        "replacement_baseline": ids(lambda r: r["baseline"] in REPL),
    }

    rng = random.Random(20260924)
    plan = [
        ("baseline_none", lambda r: r["baseline"] == "none", 300),
        ("demo_no_numbers", lambda r: r["evidence"] == "demo_no_numbers", 200),
        ("measured_demo", lambda r: r["evidence"] == "measured_demo", 200),
        ("not_realtime_family_not_games", lambda r: r["family"] not in RT and r["family"] != GAMES, 200),
        ("realtime_infra_false", lambda r: r["realtime_infra"] is False, 200),
        ("realtime_infra_true_nongame", lambda r: r["realtime_infra"] is True and r["family"] != GAMES, 100),
        ("other_or_meta", lambda r: r["family"] == "other_or_meta", 150),
        ("tier_under_300ms", lambda r: r["tier"] in ("feel", "frame", "turn"), 150),
    ]
    samples = {}
    for name, pred, n in plan:
        pool = sorted(ids(pred))
        if n > len(pool):
            raise SystemExit(f"{name}: asked {n} from {len(pool)}")
        samples[name] = rng.sample(pool, n)

    membership = {}
    for name, idlist in exhaustive.items():
        for i in idlist:
            membership.setdefault(i, []).append(name)
    for name, idlist in samples.items():
        for i in idlist:
            membership.setdefault(i, []).append(name)

    # Stable batch order: exhaustive ids first (sorted), then sample-only ids (sorted).
    ex_ids = sorted({i for ids_ in exhaustive.values() for i in ids_})
    sample_only = sorted(set(membership) - set(ex_ids))
    ordered = ex_ids + sample_only

    if BLIND.exists():
        for p in BLIND.glob("batch-*.jsonl"):
            p.unlink()
    BLIND.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)

    batches = []
    for n, start in enumerate(range(0, len(ordered), BATCH)):
        chunk = ordered[start:start + BATCH]
        path = BLIND / f"batch-{n:02d}.jsonl"
        with path.open("w") as f:
            for i in chunk:
                c = cards[i]
                f.write(json.dumps({
                    "id": i,
                    "t": c.get("t") or "",
                    "x": c.get("x") or "",
                    "chips": c.get("chips") or [],
                    "lang": c.get("lang") or "",
                }, ensure_ascii=False) + "\n")
        batches.append({"batch": n, "path": str(path), "n": len(chunk), "ids": chunk})

    # Bucket counts on this base, for the report. No card text.
    from collections import Counter
    buckets = Counter(r["_bucket"] for r in base)
    material_ids = exhaustive["material"]
    games_mat = sum(1 for i in material_ids if by_id[i]["family"] == GAMES)

    meta = {
        "seed": 20260924,
        "rng": "random.Random.sample on sorted ids",
        "sample_order": [p[0] for p in plan],
        "batch_size": BATCH,
        "classified_rows_after_id_dedupe": len(rows),
        "dropped_duplicate_ids": len(dropped),
        "not_a_jev_build": sum(1 for r in rows if r["family"] == "not_a_jev_build"),
        "use_case_base": len(base),
        "exhaustive_n": {k: len(v) for k, v in exhaustive.items()},
        "sample_n": {k: len(v) for k, v in samples.items()},
        "stratum_population": {k: len(v) for k, v in exhaustive.items()} | {
            name: len(ids(pred)) for name, pred, _ in plan
        },
        "unique_cards_to_label": len(ordered),
        "exhaustive_unique": len(ex_ids),
        "sample_only_unique": len(sample_only),
        "batches": len(batches),
        "buckets_corrected": dict(buckets),
        "material_plus_vs_frontier": len(material_ids),
        "material_games": games_mat,
        "material_nongames": len(material_ids) - games_mat,
    }
    out = {
        "meta": meta,
        "exhaustive": exhaustive,
        "samples": samples,
        "membership": membership,
        "batches": [{"batch": b["batch"], "n": b["n"], "ids": b["ids"]} for b in batches],
    }
    (WORK / "strata.json").write_text(json.dumps(out))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
