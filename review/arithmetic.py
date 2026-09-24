#!/usr/bin/env python3
"""Reproduce the arithmetic claims. No card text printed. No hand labels read."""
import json
import math
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    if n == 0:
        return None
    if n % 2:
        return xs[n // 2]
    return (xs[n // 2 - 1] + xs[n // 2]) / 2


def load():
    cards = {c["id"]: c for c in json.load(open(ROOT / "data/cards.json"))["cards"]}
    dropped = set()
    for line in open(ROOT / "data/dedupe-groups.jsonl"):
        if line.strip():
            dropped.update(json.loads(line)["merged"])
    rows = []
    seen = set()
    for line in open(ROOT / "data/classified-sonnet-v2.jsonl"):
        if not line.strip():
            continue
        r = json.loads(line)
        if r["id"] in dropped or r["id"] in seen:
            continue
        seen.add(r["id"])
        c = cards[r["id"]]
        r["v"] = c.get("v") or 0
        r["f"] = c.get("f") or 0
        r["chips"] = c.get("chips") or []
        rows.append(r)
    jev = {}
    for line in open(ROOT / "data/classified-jev.jsonl"):
        if line.strip():
            j = json.loads(line)
            jev[j["id"]] = j
    noise = {}
    for line in open(ROOT / "data/classified-noise.jsonl"):
        if line.strip():
            n = json.loads(line)
            noise[n["id"]] = n
    return rows, jev, noise


def top_share(values, p):
    vs = sorted(values, reverse=True)
    k = max(1, math.ceil(p * len(vs)))
    return k, sum(vs[:k]), sum(vs[:k]) / sum(vs) if sum(vs) else 0


def main():
    rows, jev, noise = load()
    base = [r for r in rows if r["family"] != "not_a_jev_build"]
    N = len(base)
    out = {"use_case_base": N, "deduped": len(rows)}

    # Claim 1 arithmetic from the model, not yet corrected.
    bcount = Counter(r["baseline"] for r in base)
    repl = bcount["classic_classifier_or_ml"] + bcount["rules_or_regex"] + bcount["vendor_api"]
    out["baseline"] = {
        "none": bcount["none"],
        "none_pct": 100 * bcount["none"] / N,
        "frontier": bcount["frontier_llm"],
        "frontier_pct": 100 * bcount["frontier_llm"] / N,
        "small": bcount["small_llm"],
        "small_pct": 100 * bcount["small_llm"] / N,
        "replacement": repl,
        "replacement_pct": 100 * repl / N,
        "parts": {k: bcount[k] for k in ("classic_classifier_or_ml", "rules_or_regex", "vendor_api")},
    }

    # Claim 8. Views on the use-case base, matching analyze.py.
    views = [r["v"] for r in base]
    likes = [r["f"] for r in base]
    total_v = sum(views)
    k, top_v, share = top_share(views, 0.01)
    half_n = 0
    running = 0
    for v in sorted(views, reverse=True):
        running += v
        half_n += 1
        if running >= 0.5 * total_v:
            break
    suspect = [r for r in base if r["v"] >= 100_000 and r["v"] > 0 and (r["f"] / r["v"]) < 0.002]
    keep = [r["v"] for r in base if r not in suspect]
    k2, _, share_ex = top_share(keep, 0.01)
    top_card = max(base, key=lambda r: r["v"])
    keep1 = [r["v"] for r in base if r["id"] != top_card["id"]]
    _, _, share_ex1 = top_share(keep1, 0.01)
    _, _, like_share = top_share(likes, 0.01)
    raw_views = [c.get("v") or 0 for c in json.load(open(ROOT / "data/cards.json"))["cards"]]
    _, _, raw_share = top_share(raw_views, 0.01)
    out["views"] = {
        "cards": N,
        "total_views": total_v,
        "top1_cards": k,
        "top1_share": share,
        "cards_holding_half": half_n,
        "half_as_pct_of_posts": 100 * half_n / N,
        "top_card_views": top_card["v"],
        "top_card_likes": top_card["f"],
        "top_card_like_rate": top_card["f"] / top_card["v"],
        "top1_excl_top_card": share_ex1,
        "suspect_n": len(suspect),
        "suspect_views": sum(r["v"] for r in suspect),
        "suspect_share": sum(r["v"] for r in suspect) / total_v,
        "top1_excl_suspect": share_ex,
        "top1_excl_suspect_cards": k2,
        "top1_likes_share": like_share,
        "raw_all_cards_top1": raw_share,
        "raw_n": len(raw_views),
    }

    # Claim 10. Chip medians on the use-case base.
    cost_re = re.compile(r"^([\d.,]+)\s*×\s*cheaper$")
    speed_re = re.compile(r"^([\d.,]+)\s*×\s*faster$")
    cost, speed = [], []
    for r in base:
        for ch in r["chips"]:
            m = cost_re.match(ch.strip())
            if m:
                cost.append(float(m.group(1).replace(",", "")))
            m = speed_re.match(ch.strip())
            if m:
                speed.append(float(m.group(1).replace(",", "")))
    def pack(xs):
        drop = [x for x in xs if x != 1.0]
        return {
            "chips": len(xs),
            "median": median(xs),
            "median_without_1x": median(drop),
            "n_1x": sum(1 for x in xs if x == 1.0),
        }
    out["chips"] = {"cost": pack(cost), "speed": pack(speed)}

    # Claim 9, part 1: Jev vs Sonnet family. Jev had no not_a_jev_build.
    both = []
    for r in rows:
        j = jev.get(r["id"])
        if not j:
            continue
        sonnet_fam = "other_or_meta" if r["family"] == "not_a_jev_build" else r["family"]
        both.append((sonnet_fam, j.get("family"), j.get("p") if "p" in j else j.get("prob") or j.get("probability")))
    # discover probability key from one record without dumping text
    sample_keys = sorted(jev[next(iter(jev))].keys())
    out["jev_keys"] = sample_keys
    agree = sum(1 for a, b, _ in both if a == b)
    hi = [(a, b, p) for a, b, p in both if isinstance(p, (int, float)) and p >= 0.99]
    hi_agree = sum(1 for a, b, _ in hi if a == b)
    out["jev_vs_sonnet"] = {
        "n": len(both),
        "agree": agree,
        "agree_pct": 100 * agree / len(both) if both else None,
        "p_ge_0.99": len(hi),
        "p_ge_0.99_agree_sonnet": hi_agree,
        "p_ge_0.99_agree_sonnet_pct": 100 * hi_agree / len(hi) if hi else None,
    }

    # Claim 6 arithmetic: under 300ms and games.
    fast = [r for r in base if r["tier"] in ("frame", "feel", "turn")]
    fast_games = sum(1 for r in fast if r["family"] == "games_control_loops_simulation")
    out["under_300ms"] = {
        "n": len(fast),
        "games": fast_games,
        "games_pct": 100 * fast_games / len(fast) if fast else None,
        "by_tier": dict(Counter(r["tier"] for r in fast)),
        "nongame_by_family": dict(Counter(r["family"] for r in fast if r["family"] != "games_control_loops_simulation")),
    }

    # Claim 4 arithmetic.
    rt = [r for r in base if r["family"] in ("voice_and_turn_taking", "live_chat_streams_events", "collaboration_and_typing")]
    out["realtime_families"] = {
        "n": len(rt),
        "pct": 100 * len(rt) / N,
        "measured_production": sum(1 for r in rt if r["evidence"] == "measured_production"),
        "production_claim": sum(1 for r in rt if r["production_claim"]),
        "by_family": dict(Counter(r["family"] for r in rt)),
    }

    # Claim 5 model rate, not yet corrected.
    rti = [r for r in base if r["realtime_infra"] is True]
    rti_ng = [r for r in rti if r["family"] != "games_control_loops_simulation"]
    out["realtime_infra_model"] = {
        "n": len(rti),
        "pct": 100 * len(rti) / N,
        "nongame": len(rti_ng),
        "nongame_pct_of_posts": 100 * len(rti_ng) / N,
    }

    # Claim 7 model noise.
    meta = [r for r in base if r["family"] == "other_or_meta"]
    sub = Counter()
    missing = 0
    for r in meta:
        n = noise.get(r["id"])
        if not n:
            missing += 1
            continue
        sub[n.get("subtype") or n.get("noise") or n.get("kind") or "NO_KEY"] += 1
    if noise:
        out["noise_keys"] = sorted(noise[next(iter(noise))].keys())
    out["noise_model"] = {
        "other_or_meta": len(meta),
        "pct_of_posts": 100 * len(meta) / N,
        "missing_subtype": missing,
        "subtypes": dict(sub),
        "meme_pct": 100 * sub.get("meme_or_joke", 0) / N,
        "hot_pct": 100 * sub.get("hot_take_or_commentary", 0) / N,
    }

    # Evidence model.
    ev = Counter(r["evidence"] for r in base)
    out["evidence_model"] = {k: {"n": ev[k], "pct": 100 * ev[k] / N} for k in ev}

    UNMEASURED = {"demo_no_numbers", "proposal_or_idea"}

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

    def fairer(r):
        if r["family"] == "other_or_meta" or r["evidence"] == "commentary_or_meme":
            return "noise"
        if r["evidence"] in UNMEASURED:
            if r["framing"] in ("cost", "latency", "accuracy"):
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
        if r["tier"] == "batch" or r["baseline"] in ("small_llm", "vendor_api", "classic_classifier_or_ml", "rules_or_regex"):
            return "cost_only"
        return "measured_other"

    c = Counter(corrected(r) for r in base)
    f = Counter(fairer(r) for r in base)
    hype = [r for r in base if corrected(r) == "hype"]
    only_base = [r for r in hype if r["framing"] not in ("cost", "latency", "accuracy")]
    co = [r for r in base if corrected(r) == "cost_only"]
    out["rules"] = {
        "corrected_pct": {k: round(100 * c[k] / N, 2) for k in c},
        "fairer_pct": {k: round(100 * f[k] / N, 2) for k in f},
        "hype_n": len(hype),
        "hype_only_because_baseline_named": len(only_base),
        "hype_only_because_baseline_framing": dict(Counter(r["framing"] for r in only_base)),
        "cost_only_n": len(co),
        "cost_only_baseline_none": sum(1 for r in co if r["baseline"] == "none"),
        "cost_only_baseline": dict(Counter(r["baseline"] for r in co)),
    }
    print(json.dumps(out["rules"], indent=2))


if __name__ == "__main__":
    main()
