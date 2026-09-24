#!/usr/bin/env python3
"""Corrected estimates from the blinded hand labels.

Plain Python. Run from anywhere:

    python3 review/estimate.py

Reads review/work/strata.json, review/labels/*.jsonl, and the source data.
Does not read data/hand-labels-120.jsonl. Writes review/work/estimate.json.
"""
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REV = ROOT / "review"

RT = {"voice_and_turn_taking", "live_chat_streams_events", "collaboration_and_typing"}
REPL = {"classic_classifier_or_ml", "rules_or_regex", "vendor_api"}
GAMES = "games_control_loops_simulation"
FAST = {"frame", "feel", "turn"}
MEASURED = {"measured_demo", "measured_production"}
UNMEASURED = {"demo_no_numbers", "proposal_or_idea"}
FIELDS = ["family", "tier", "evidence", "framing", "baseline", "realtime_infra", "production_claim"]
FAMILIES = {
    "evals_and_judging", "classification_routing_triage", "moderation_and_guardrails",
    "agent_harness_and_tool_gating", "compaction_and_context", "search_rerank_extraction",
    "browser_and_computer_use", "voice_and_turn_taking", "live_chat_streams_events",
    "collaboration_and_typing", "games_control_loops_simulation", "data_and_telemetry",
    "trading_and_markets", "not_a_jev_build", "other_or_meta",
}
TIERS = {"frame", "feel", "turn", "interaction", "task", "batch", "unclear"}
EVIDENCE = {"measured_production", "measured_demo", "demo_no_numbers", "proposal_or_idea", "commentary_or_meme"}
FRAMING = {"cost", "latency", "accuracy", "capability", "none"}
BASELINE = {"frontier_llm", "small_llm", "classic_classifier_or_ml", "vendor_api", "rules_or_regex", "none"}
NOISE = {
    "benchmark_of_the_model", "tooling_or_wrapper", "explainer_or_tutorial", "news_or_repost",
    "meme_or_joke", "hot_take_or_commentary", "unrelated_or_unclear",
}


def wilson(k, n, z=1.96):
    if n <= 0:
        return {"k": k, "n": n, "p": None, "lo": None, "hi": None}
    ph = k / n
    z2 = z * z
    den = 1 + z2 / n
    centre = (ph + z2 / (2 * n)) / den
    margin = z * math.sqrt(ph * (1 - ph) / n + z2 / (4 * n * n)) / den
    return {"k": k, "n": n, "p": ph, "lo": max(0.0, centre - margin), "hi": min(1.0, centre + margin)}


def pct(x):
    return None if x is None else 100 * x


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


def load_model():
    cards = {c["id"]: c for c in json.load(open(ROOT / "data/cards.json"))["cards"]}
    dropped = set()
    for line in open(ROOT / "data/dedupe-groups.jsonl"):
        if line.strip():
            dropped.update(json.loads(line)["merged"])
    rows = {}
    for line in open(ROOT / "data/classified-sonnet-v2.jsonl"):
        if not line.strip():
            continue
        r = json.loads(line)
        if r["id"] in dropped:
            continue
        c = cards[r["id"]]
        r["v"] = c.get("v") or 0
        r["f"] = c.get("f") or 0
        r["chips"] = c.get("chips") or []
        rows[r["id"]] = r
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


def load_labels():
    labels = {}
    files = sorted((REV / "labels").glob("batch-*.jsonl"))
    bad = []
    for path in files:
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if not line.strip():
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                bad.append(f"{path.name}:{lineno} json")
                continue
            i = str(o.get("id", ""))
            if o.get("family") not in FAMILIES:
                bad.append(f"{i} family {o.get('family')}")
            if o.get("tier") not in TIERS:
                bad.append(f"{i} tier {o.get('tier')}")
            if o.get("evidence") not in EVIDENCE:
                bad.append(f"{i} evidence {o.get('evidence')}")
            if o.get("framing") not in FRAMING:
                bad.append(f"{i} framing {o.get('framing')}")
            if o.get("baseline") not in BASELINE:
                bad.append(f"{i} baseline {o.get('baseline')}")
            if not isinstance(o.get("realtime_infra"), bool):
                bad.append(f"{i} realtime")
            if not isinstance(o.get("production_claim"), bool):
                bad.append(f"{i} production")
            if o.get("family") == "other_or_meta" and o.get("noise") not in NOISE:
                bad.append(f"{i} noise {o.get('noise')}")
            labels[i] = o
    overrides = REV / "work" / "override-production.jsonl"
    n_over = 0
    if overrides.exists():
        for line in overrides.read_text().splitlines():
            if line.strip():
                o = json.loads(line)
                labels[o["id"]] = o
                n_over += 1
    return labels, files, bad, n_over


def agree_block(ids, labels, model):
    out = {}
    both = [i for i in ids if i in labels and i in model]
    for f in FIELDS:
        k = sum(1 for i in both if labels[i][f] == model[i][f])
        out[f] = {"n": len(both), "agree": k, "rate": (k / len(both) if both else None)}
    return out


def scale_count(k_census, sample_k, sample_n, stratum_n):
    """Census count plus a Wilson-scaled sample of a disjoint negative stratum."""
    w = wilson(sample_k, sample_n)
    if w["p"] is None:
        return {"est": k_census, "lo": k_census, "hi": k_census, "wilson": w}
    return {
        "est": k_census + w["p"] * stratum_n,
        "lo": k_census + w["lo"] * stratum_n,
        "hi": k_census + w["hi"] * stratum_n,
        "wilson": w,
        "stratum_n": stratum_n,
    }


def share(count, n):
    return {"count": count, "share": count / n, "pct": 100 * count / n}


def main():
    model, jev, noise = load_model()
    labels, files, bad, n_over = load_labels()
    strata = json.load(open(REV / "work" / "strata.json"))
    base_ids = [i for i, r in model.items() if r["family"] != "not_a_jev_build"]
    N = len(base_ids)
    membership = strata["membership"]
    expected = set(membership)
    missing = sorted(expected - set(labels))
    if missing or bad:
        report = {"error": "labels incomplete or invalid", "missing": len(missing), "missing_ids": missing[:20], "invalid": bad[:30], "files": len(files), "labelled": len(labels)}
        (REV / "work" / "estimate.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        return

    # Per-stratum agreement with the model.
    agreement = {}
    for name, ids in list(strata["exhaustive"].items()) + list(strata["samples"].items()):
        agreement[name] = agree_block(ids, labels, model)

    # Overall agreement on the labelled set.
    agreement["all_labelled"] = agree_block(list(labels), labels, model)

    def L(i):
        return labels[i]

    def mine(i, field):
        return labels[i][field]

    # ----- Claim 1. Baseline distribution.
    none_ids = strata["samples"]["baseline_none"]
    repl_ids = strata["exhaustive"]["replacement_baseline"]
    none_n = strata["meta"]["stratum_population"]["baseline_none"]
    # Unsampled: model frontier + small. Assumed correct in the primary estimate.
    frontier_n = sum(1 for i in base_ids if model[i]["baseline"] == "frontier_llm")
    small_n = sum(1 for i in base_ids if model[i]["baseline"] == "small_llm")

    def repl_like(b):
        return b in REPL

    none_sample_counts = Counter(mine(i, "baseline") for i in none_ids)
    repl_counts = Counter(mine(i, "baseline") for i in repl_ids)

    def est_baseline(cat, pred):
        # census of the replacement stratum + scaled none-sample + model count inside frontier/small
        census = sum(1 for i in repl_ids if pred(mine(i, "baseline")))
        sk = sum(1 for i in none_ids if pred(mine(i, "baseline")))
        scaled = scale_count(census, sk, len(none_ids), none_n)
        assumed = 0
        if cat == "frontier_llm":
            assumed = frontier_n
        elif cat == "small_llm":
            assumed = small_n
        elif cat == "none":
            assumed = 0  # frontier and small are not none, by the model; this is the gap
        # For frontier/small the census+sample estimate is the INFLOW from none and replacement.
        # Add the model count only for frontier and small (treated as unreviewed).
        return {
            "census_in_replacement_stratum": census,
            "in_none_sample": sk,
            "scaled_from_none": scaled,
            "assumed_from_unsampled_frontier_and_small": assumed,
            "est_count": scaled["est"] + assumed,
            "lo": scaled["lo"] + assumed,
            "hi": scaled["hi"] + assumed,
            "est_pct": 100 * (scaled["est"] + assumed) / N,
            "lo_pct": 100 * (scaled["lo"] + assumed) / N,
            "hi_pct": 100 * (scaled["hi"] + assumed) / N,
        }

    claim1 = {
        "denominator": N,
        "model": {
            "none_pct": 100 * none_n / N,
            "frontier_pct": 100 * frontier_n / N,
            "small_pct": 100 * small_n / N,
            "replacement_n": len(repl_ids),
            "replacement_pct": 100 * len(repl_ids) / N,
        },
        "none_sample_baseline": dict(none_sample_counts),
        "replacement_stratum_baseline": dict(repl_counts),
        "corrected": {
            "none": est_baseline("none", lambda b: b == "none"),
            "frontier_llm": est_baseline("frontier_llm", lambda b: b == "frontier_llm"),
            "small_llm": est_baseline("small_llm", lambda b: b == "small_llm"),
            "replacement": est_baseline("replacement", repl_like),
        },
        "gap": "Frontier and small strata were not sampled. Their model counts are added unchanged. False baselines inside those 861 cards are not corrected.",
    }

    # ----- Claim 2. Production with a number.
    prod_ids = strata["exhaustive"]["measured_production"]
    k_prod = sum(1 for i in prod_ids if mine(i, "evidence") == "measured_production")
    demo_nn = strata["samples"]["demo_no_numbers"]
    meas = strata["samples"]["measured_demo"]
    k_nn = sum(1 for i in demo_nn if mine(i, "evidence") == "measured_production")
    k_md = sum(1 for i in meas if mine(i, "evidence") == "measured_production" and i not in set(prod_ids))
    # two negative strata, conservative sum of Wilson bounds
    s1 = scale_count(0, k_nn, len(demo_nn), strata["meta"]["stratum_population"]["demo_no_numbers"])
    s2 = scale_count(0, k_md, len(meas), strata["meta"]["stratum_population"]["measured_demo"])
    est = k_prod + s1["est"] + s2["est"]
    lo = k_prod + s1["lo"] + s2["lo"]
    hi = k_prod + s1["hi"] + s2["hi"]
    claim2 = {
        "model_strict_n": len(prod_ids),
        "model_strict_pct": 100 * len(prod_ids) / N,
        "hold_on_reread": k_prod,
        "misses_in_demo_no_numbers_sample": k_nn,
        "misses_in_measured_demo_sample": k_md,
        "est_count": est,
        "lo": lo,
        "hi": hi,
        "est_pct": 100 * est / N,
        "lo_pct": 100 * lo / N,
        "hi_pct": 100 * hi / N,
        "interval": "sum of per-stratum Wilson bounds, conservative",
        "v1_rows": None,
    }

    # ----- Claim 3. Buckets, from two simple random samples plus the production census.
    # demo_no_numbers represents that stratum. measured_demo represents that stratum.
    # measured_production is a census. proposal + commentary stay on the model bucket.
    def bucket_of_label(i):
        return corrected(labels[i])

    def bucket_of_model(i):
        return corrected(model[i])

    remainder_ids = [i for i in base_ids if model[i]["evidence"] in ("proposal_or_idea", "commentary_or_meme")]
    rem_counts = Counter(bucket_of_model(i) for i in remainder_ids)

    def sample_bucket_counts(ids):
        return Counter(bucket_of_label(i) for i in ids)

    b_nn = sample_bucket_counts(demo_nn)
    b_md = sample_bucket_counts(meas)
    b_prod = Counter(bucket_of_label(i) for i in prod_ids)
    order = ["noise", "hype", "demo", "cost_only", "fast_loop", "material_vs_frontier", "material"]
    N_nn = strata["meta"]["stratum_population"]["demo_no_numbers"]
    N_md = strata["meta"]["stratum_population"]["measured_demo"]
    buckets = {}
    for b in order:
        # Wilson on each sample, plus exact production, plus unsampled remainder at the model count
        w1 = wilson(b_nn[b], len(demo_nn))
        w2 = wilson(b_md[b], len(meas))
        exact = b_prod[b] + rem_counts[b]
        est_c = exact + w1["p"] * N_nn + w2["p"] * N_md
        lo_c = exact + w1["lo"] * N_nn + w2["lo"] * N_md
        hi_c = exact + w1["hi"] * N_nn + w2["hi"] * N_md
        buckets[b] = {
            "est_count": est_c, "lo": lo_c, "hi": hi_c,
            "est_pct": 100 * est_c / N, "lo_pct": 100 * lo_c / N, "hi_pct": 100 * hi_c / N,
            "from_demo_no_numbers_sample": b_nn[b],
            "from_measured_demo_sample": b_md[b],
            "from_production_census": b_prod[b],
            "from_unsampled_proposal_and_commentary_model": rem_counts[b],
        }
    mat_ids = strata["exhaustive"]["material"]
    mat_survives = sum(1 for i in mat_ids if bucket_of_label(i) in ("material", "material_vs_frontier"))
    mat_games = sum(1 for i in mat_ids if bucket_of_label(i) in ("material", "material_vs_frontier") and mine(i, "family") == GAMES)
    claim3 = {
        "model_pct": {
            "demo": 100 * 2154 / N,
            "hype": 100 * 655 / N,
            "cost_only": 100 * 1329 / N,
            "material_plus": 100 * 91 / N,
        },
        "buckets": buckets,
        "material_census_n": len(mat_ids),
        "material_census_still_material": mat_survives,
        "material_census_still_material_and_games": mat_games,
        "material_census_still_material_nongames": mat_survives - mat_games,
        "unsampled_remainder_n": len(remainder_ids),
    }

    # ----- Claim 4. Realtime families.
    rt_ids = strata["exhaustive"]["realtime_family"]
    k_rt = sum(1 for i in rt_ids if mine(i, "family") in RT)
    neg = strata["samples"]["not_realtime_family_not_games"]
    k_miss = sum(1 for i in neg if mine(i, "family") in RT)
    N_neg = strata["meta"]["stratum_population"]["not_realtime_family_not_games"]
    sc = scale_count(k_rt, k_miss, len(neg), N_neg)
    rt_prod = sum(1 for i in rt_ids if mine(i, "family") in RT and mine(i, "evidence") == "measured_production")
    rt_claim = sum(1 for i in rt_ids if mine(i, "family") in RT and mine(i, "production_claim"))
    # misses that are production
    miss_prod = sum(1 for i in neg if mine(i, "family") in RT and (mine(i, "evidence") == "measured_production" or mine(i, "production_claim")))
    claim4 = {
        "model_n": len(rt_ids),
        "model_pct": 100 * len(rt_ids) / N,
        "census_still_in_family": k_rt,
        "misses_in_negative_sample": k_miss,
        "est_count": sc["est"], "lo": sc["lo"], "hi": sc["hi"],
        "est_pct": 100 * sc["est"] / N, "lo_pct": 100 * sc["lo"] / N, "hi_pct": 100 * sc["hi"] / N,
        "census_measured_production": rt_prod,
        "census_production_claim": rt_claim,
        "negative_sample_productionish": miss_prod,
        "gap": "The negative sample excludes games, so a game that is really voice or live chat is not in the miss rate.",
    }

    # ----- Claim 5. realtime_infra.
    rt_true = strata["samples"]["realtime_infra_true_nongame"]
    rt_false = strata["samples"]["realtime_infra_false"]
    N_true = strata["meta"]["stratum_population"]["realtime_infra_true_nongame"]
    N_false = strata["meta"]["stratum_population"]["realtime_infra_false"]
    k_true = sum(1 for i in rt_true if mine(i, "realtime_infra") is True and mine(i, "family") != GAMES)
    k_false_flip = sum(1 for i in rt_false if mine(i, "realtime_infra") is True and mine(i, "family") != GAMES)
    # false stratum includes games. Scale the nongame-flip rate by the whole false stratum only as an upper
    # construction: use the flip rate on the whole false sample for any realtime, and separately nongame.
    k_false_any = sum(1 for i in rt_false if mine(i, "realtime_infra") is True)
    games_true_model = sum(1 for i in base_ids if model[i]["realtime_infra"] is True and model[i]["family"] == GAMES)
    s_true = scale_count(0, k_true, len(rt_true), N_true)
    s_false = scale_count(0, k_false_flip, len(rt_false), N_false)
    # Nongame estimate. The false-sample flip is scaled to all false cards, which overstates nongame misses
    # if some flips are games. Report both.
    nongame_est = s_true["est"] + s_false["est"]
    all_false_scaled = scale_count(0, k_false_any, len(rt_false), N_false)
    # Games: assume the model game-realtime count, and report how the fast-tier sample treats game realtime.
    fast_ids = strata["samples"]["tier_under_300ms"]
    game_fast = [i for i in fast_ids if model[i]["family"] == GAMES]
    game_fast_true = sum(1 for i in game_fast if mine(i, "realtime_infra") is True)
    claim5 = {
        "model_pct": 100 * sum(1 for i in base_ids if model[i]["realtime_infra"] is True) / N,
        "model_nongame_pct": 100 * N_true / N,
        "true_nongame_sample_still_true_and_nongame": k_true,
        "true_nongame_sample_n": len(rt_true),
        "false_sample_flipped_nongame": k_false_flip,
        "false_sample_flipped_any": k_false_any,
        "false_sample_n": len(rt_false),
        "nongame_est_count": nongame_est,
        "nongame_lo": s_true["lo"] + s_false["lo"],
        "nongame_hi": s_true["hi"] + s_false["hi"],
        "nongame_est_pct": 100 * nongame_est / N,
        "nongame_lo_pct": 100 * (s_true["lo"] + s_false["lo"]) / N,
        "nongame_hi_pct": 100 * (s_true["hi"] + s_false["hi"]) / N,
        "any_realtime_est_count": s_true["est"] + all_false_scaled["est"] + games_true_model,
        "any_realtime_note": "Adds the model count of realtime games unchanged.",
        "games_in_fast_tier_sample": len(game_fast),
        "games_in_fast_tier_sample_i_call_realtime": game_fast_true,
        "model_realtime_games": games_true_model,
    }
    any_est = claim5["any_realtime_est_count"]
    claim5["any_realtime_est_pct"] = 100 * any_est / N

    # ----- Claim 6. Under 300 ms, share games.
    fast_pop = strata["meta"]["stratum_population"]["tier_under_300ms"]
    i_fast = [i for i in fast_ids if mine(i, "tier") in FAST]
    i_fast_games = sum(1 for i in i_fast if mine(i, "family") == GAMES)
    w_fast = wilson(i_fast_games, len(i_fast)) if i_fast else wilson(0, 0)
    # How many of the model-fast sample I still call fast, and of those, games by MY family.
    claim6 = {
        "model_fast_n": fast_pop,
        "model_fast_games": sum(1 for i in base_ids if model[i]["tier"] in FAST and model[i]["family"] == GAMES),
        "sample_n": len(fast_ids),
        "sample_i_still_call_fast": len(i_fast),
        "sample_i_call_fast_and_game": i_fast_games,
        "conditional_games_share": w_fast,
        "conditional_pct": pct(w_fast["p"]),
        "conditional_lo_pct": pct(w_fast["lo"]),
        "conditional_hi_pct": pct(w_fast["hi"]),
    }

    # ----- Claim 7. Noise composition.
    meta_ids = strata["samples"]["other_or_meta"]
    N_meta = strata["meta"]["stratum_population"]["other_or_meta"]
    still = [i for i in meta_ids if mine(i, "family") == "other_or_meta"]
    sub = Counter((labels[i].get("noise") or "missing") for i in still)
    moved = Counter(mine(i, "family") for i in meta_ids if mine(i, "family") != "other_or_meta")
    vague_keys = {"unrelated_or_unclear", "benchmark_of_the_model", "tooling_or_wrapper"}
    k_vague = sum(sub[k] for k in vague_keys)
    k_meme = sub["meme_or_joke"]
    k_hot = sub["hot_take_or_commentary"]
    # Scale counts of still-meta subtypes to the meta stratum, then to all posts.
    # Cards I move out of meta shrink the fifth.
    w_still = wilson(len(still), len(meta_ids))
    meta_est = w_still["p"] * N_meta
    claim7 = {
        "model_meta_n": N_meta,
        "model_meta_pct": 100 * N_meta / N,
        "sample_n": len(meta_ids),
        "sample_still_meta": len(still),
        "sample_moved": dict(moved),
        "subtype_among_still": dict(sub),
        "est_meta_count": meta_est,
        "est_meta_pct": 100 * meta_est / N,
        "est_meta_lo_pct": 100 * w_still["lo"] * N_meta / N,
        "est_meta_hi_pct": 100 * w_still["hi"] * N_meta / N,
        "vague_or_benchmark_or_wrapper_in_sample": k_vague,
        "vague_est_count": (k_vague / len(meta_ids)) * N_meta,
        "vague_est_pct": 100 * (k_vague / len(meta_ids)) * N_meta / N,
        "meme": wilson(k_meme, len(meta_ids)),
        "hot": wilson(k_hot, len(meta_ids)),
        "meme_est_pct_of_posts": 100 * (k_meme / len(meta_ids)) * N_meta / N,
        "hot_est_pct_of_posts": 100 * (k_hot / len(meta_ids)) * N_meta / N,
        # Counted among the model's own meta posts (the sub-type file also carries rows for other
        # models' noise sets since 24 Sep, so counting over every base id would drift).
        "model_meme_n": sum(1 for i in base_ids if model[i]["family"] == "other_or_meta" and noise.get(i, {}).get("subtype") == "meme_or_joke"),
        "model_hot_n": sum(1 for i in base_ids if model[i]["family"] == "other_or_meta" and noise.get(i, {}).get("subtype") == "hot_take_or_commentary"),
    }

    # ----- Claim 8. Views. Same construction as analyze.py.
    views = sorted((model[i]["v"] for i in base_ids), reverse=True)
    total_v = sum(views)
    k1 = max(1, math.ceil(0.01 * len(views)))
    top_share = sum(views[:k1]) / total_v
    half_n = 0
    running = 0
    for v in views:
        running += v
        half_n += 1
        if running >= 0.5 * total_v:
            break
    suspect = [i for i in base_ids if model[i]["v"] >= 100_000 and model[i]["v"] > 0 and model[i]["f"] / model[i]["v"] < 0.002]
    keep = sorted((model[i]["v"] for i in base_ids if i not in set(suspect)), reverse=True)
    k2 = max(1, math.ceil(0.01 * len(keep)))
    top_ex = sum(keep[:k2]) / sum(keep)
    likes = sorted((model[i]["f"] for i in base_ids), reverse=True)
    lk = max(1, math.ceil(0.01 * len(likes)))
    like_share = sum(likes[:lk]) / sum(likes)
    claim8 = {
        "cards": N,
        "top1_cards": k1,
        "top1_share": top_share,
        "cards_holding_half": half_n,
        "half_pct_of_posts": 100 * half_n / N,
        "suspect_n": len(suspect),
        "suspect_share": sum(model[i]["v"] for i in suspect) / total_v,
        "top1_excl_suspect": top_ex,
        "top1_likes_share": like_share,
    }

    # ----- Claim 9. Jev vs Sonnet. The 27/28 check is a separate step.
    both = []
    for i, r in model.items():
        j = jev.get(i)
        if not j:
            continue
        fam = "other_or_meta" if r["family"] == "not_a_jev_build" else r["family"]
        both.append((i, fam, j.get("family"), j.get("prob")))
    agree_n = sum(1 for _, a, b, _ in both if a == b)
    hi = [t for t in both if isinstance(t[3], (int, float)) and t[3] >= 0.99]
    hi_agree = sum(1 for _, a, b, _ in hi if a == b)
    # Where I labelled a card and Jev was >= 0.99, was Jev's family mine?
    hi_labelled = [t for t in hi if t[0] in labels]
    hi_right_me = sum(1 for i, a, b, p in hi_labelled if b == labels[i]["family"] or (b == "other_or_meta" and labels[i]["family"] == "not_a_jev_build"))
    claim9 = {
        "n": len(both),
        "agree_sonnet": agree_n,
        "agree_pct": 100 * agree_n / len(both),
        "p_ge_099": len(hi),
        "p_ge_099_agree_sonnet": hi_agree,
        "p_ge_099_agree_sonnet_pct": 100 * hi_agree / len(hi),
        "p_ge_099_in_my_labels": len(hi_labelled),
        "p_ge_099_matches_my_family": hi_right_me,
        "p_ge_099_match_my_family_pct": (100 * hi_right_me / len(hi_labelled) if hi_labelled else None),
    }

    # ----- Claim 10. Chip medians.
    cost_re = re.compile(r"^([\d.,]+)\s*×\s*cheaper$")
    speed_re = re.compile(r"^([\d.,]+)\s*×\s*faster$")
    cost, speed = [], []
    for i in base_ids:
        for ch in model[i]["chips"]:
            m = cost_re.match(str(ch).strip())
            if m:
                cost.append(float(m.group(1).replace(",", "")))
            m = speed_re.match(str(ch).strip())
            if m:
                speed.append(float(m.group(1).replace(",", "")))

    def med(xs):
        xs = sorted(xs)
        n = len(xs)
        if n == 0:
            return None
        if n % 2:
            return xs[n // 2]
        return 0.5 * (xs[n // 2 - 1] + xs[n // 2])

    claim10 = {
        "cost_chips": len(cost),
        "cost_median": med(cost),
        "cost_median_without_1x": med([x for x in cost if x != 1]),
        "cost_1x": sum(1 for x in cost if x == 1),
        "speed_chips": len(speed),
        "speed_median": med(speed),
        "speed_median_without_1x": med([x for x in speed if x != 1]),
        "speed_1x": sum(1 for x in speed if x == 1),
    }

    def is_mat(i):
        return bucket_of_label(i) in ("material", "material_vs_frontier")

    mat_set = set(mat_ids)
    md_pop = [i for i in base_ids if model[i]["evidence"] == "measured_demo"]
    md_out_pop = [i for i in md_pop if i not in mat_set]
    samp_out = [i for i in meas if i not in mat_set]
    k_md_miss = sum(1 for i in samp_out if is_mat(i))
    k_nn_miss = sum(1 for i in demo_nn if is_mat(i))
    w_md = wilson(k_md_miss, len(samp_out))
    w_nn = wilson(k_nn_miss, len(demo_nn))
    mat_est = mat_survives + w_md["p"] * len(md_out_pop) + w_nn["p"] * N_nn
    mat_lo = mat_survives + w_md["lo"] * len(md_out_pop) + w_nn["lo"] * N_nn
    mat_hi = mat_survives + w_md["hi"] * len(md_out_pop) + w_nn["hi"] * N_nn
    material_combined = {
        "census_survivors": mat_survives,
        "census_survivors_nongame": mat_survives - mat_games,
        "census_pct": 100 * mat_survives / N,
        "measured_demo_outside_n": len(md_out_pop),
        "measured_demo_outside_sample_n": len(samp_out),
        "measured_demo_outside_misses": k_md_miss,
        "demo_no_numbers_misses": k_nn_miss,
        "est_count": mat_est,
        "lo": mat_lo,
        "hi": mat_hi,
        "est_pct": 100 * mat_est / N,
        "lo_pct": 100 * mat_lo / N,
        "hi_pct": 100 * mat_hi / N,
    }

    def narrow_hype(r):
        return r["evidence"] in UNMEASURED and r["framing"] in ("cost", "latency", "accuracy")

    def narrow_demo(r):
        return (r["evidence"] in UNMEASURED and not narrow_hype(r)
                and r["family"] != "other_or_meta" and r["evidence"] != "commentary_or_meme")

    def prose_cost(r):
        if r["family"] == "other_or_meta" or r["evidence"] == "commentary_or_meme":
            return False
        if r["evidence"] not in MEASURED:
            return False
        return r["tier"] == "batch" or r["baseline"] in (
            "small_llm", "vendor_api", "classic_classifier_or_ml", "rules_or_regex")

    prose_buckets = {}
    for name, pred in (("hype_cost_speed_accuracy", narrow_hype), ("demo_other_unmeasured", narrow_demo), ("cost_only_as_described", prose_cost)):
        k1 = sum(1 for i in demo_nn if pred(labels[i]))
        k2 = sum(1 for i in meas if pred(labels[i]))
        k3 = sum(1 for i in prod_ids if pred(labels[i]))
        a, b, c = wilson(k1, len(demo_nn)), wilson(k2, len(meas)), k3
        est_c = c + a["p"] * N_nn + b["p"] * N_md
        lo_c = c + a["lo"] * N_nn + b["lo"] * N_md
        hi_c = c + a["hi"] * N_nn + b["hi"] * N_md
        prose_buckets[name] = {
            "est_pct": 100 * est_c / N, "lo_pct": 100 * lo_c / N, "hi_pct": 100 * hi_c / N,
            "est_count": est_c, "sample_demo_no_numbers": k1, "sample_measured_demo": k2, "production_census": k3,
        }

    def labelled_baseline(model_value):
        ids = [i for i in base_ids if model[i]["baseline"] == model_value and i in labels]
        return {"n": len(ids), "mine": dict(Counter(labels[i]["baseline"] for i in ids))}

    baseline_sensitivity = {
        "frontier_llm": labelled_baseline("frontier_llm"),
        "small_llm": labelled_baseline("small_llm"),
        "note": "These cards were labelled because they fell into other strata. Not a random sample of the frontier or small stratum.",
    }

    prior_path = ROOT / "data" / "hand-labels-120.jsonl"
    prior = [json.loads(l) for l in prior_path.read_text().splitlines() if l.strip()]
    overlap = [h for h in prior if h["id"] in labels]
    prior_fields = {}
    for f in FIELDS:
        k = sum(1 for h in overlap if h.get(f) == labels[h["id"]][f])
        prior_fields[f] = {"n": len(overlap), "agree": k, "rate": (k / len(overlap) if overlap else None)}
    hi_prior = [h for h in prior if isinstance(jev.get(h["id"], {}).get("prob"), (int, float)) and jev[h["id"]]["prob"] >= 0.99]

    def fam_match(a, b):
        return a == b or (a == "other_or_meta" and b == "not_a_jev_build")

    prior_agreement = {
        "overlap": len(overlap),
        "prior_n": len(prior),
        "fields": prior_fields,
        "jev_p99_in_prior": len(hi_prior),
        "jev_matches_prior_family": sum(1 for h in hi_prior if fam_match(jev[h["id"]]["family"], h["family"])),
        "jev_p99_also_in_my_labels": sum(1 for h in hi_prior if h["id"] in labels),
        "jev_matches_me_on_that_overlap": sum(
            1 for h in hi_prior if h["id"] in labels and fam_match(jev[h["id"]]["family"], labels[h["id"]]["family"])
        ),
    }

    out = {
        "labelled": len(labels),
        "expected": len(expected),
        "label_files": len(files),
        "production_overrides": n_over,
        "invalid": bad,
        "use_case_base": N,
        "agreement": agreement,
        "claim1": claim1,
        "claim2": claim2,
        "claim3": claim3,
        "claim4": claim4,
        "claim5": claim5,
        "claim6": claim6,
        "claim7": claim7,
        "claim8": claim8,
        "claim9": claim9,
        "claim10": claim10,
        "material_combined": material_combined,
        "prose_buckets": prose_buckets,
        "baseline_sensitivity": baseline_sensitivity,
        "prior_agreement": prior_agreement,
    }
    (REV / "work" / "estimate.json").write_text(json.dumps(out, indent=2))
    # Short console summary. Full numbers are in the json.
    summary = {
        "labelled": len(labels),
        "agreement_all": {f: agreement["all_labelled"][f]["rate"] for f in FIELDS},
        "claim1_replacement_pct": claim1["corrected"]["replacement"]["est_pct"],
        "claim1_none_pct": claim1["corrected"]["none"]["est_pct"],
        "claim2_pct": [claim2["est_pct"], claim2["lo_pct"], claim2["hi_pct"], claim2["hold_on_reread"]],
        "claim3_material_census_survives": mat_survives,
        "claim4_pct": [claim4["est_pct"], claim4["lo_pct"], claim4["hi_pct"]],
        "claim6_games_pct": claim6["conditional_pct"],
        "claim8_top1": claim8["top1_share"],
        "claim9_agree": claim9["agree_pct"],
        "claim10": [claim10["cost_median"], claim10["speed_median"]],
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
