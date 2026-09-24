#!/usr/bin/env python3
"""Audit estimates with another label file as the model under test (default: Claude Opus 5.5).

    python3 review/estimate-opus.py                                    # data/classified-opus.jsonl
    python3 review/estimate-opus.py --model data/classified-opus.jsonl --name "Claude Opus 5.5" --tag opus
    python3 review/estimate-opus.py --model data/classified-sonnet-v2.jsonl --tag sonnet --json-only

What stays fixed: the strata of review/sample.py (drawn from the Claude Sonnet 5 v2 labels, seed
20260924), Grok's 1,681 labels (review/hand-labels-grok.jsonl) as the reference, and the estimators of
review/estimate.py: census strata are counted exactly, each sample is scaled to its stratum with a 95%
Wilson interval, and where strata are added their bounds are summed. wilson(), corrected() and
scale_count() are imported from review/estimate.py.

What changes with --model:
  1. Base. Shares are of the model's own use-case base: duplicates merged, the model's not_a_jev_build
     posts and any post it did not label left out. Each Sonnet-defined stratum is cut to that base.
     The audited posts left in a sampled stratum are a simple random sample of what is left of it
     (domain estimation), so the scaling holds.
  2. Plug-ins. Where review/estimate.py takes a region the audit did not sample from the model's own
     labels (the frontier and small-LLM strata, the proposal and commentary posts, the games for the
     realtime families, the flagged games for the live loop, the posts outside the under-300 ms and
     meta strata), the labels of the model under test are used. For Sonnet those are the counts
     review/estimate.py uses, so a Sonnet run reproduces review/work/estimate.json. Every run checks
     this and stops if it does not.
  3. Model-only posts. Posts in the model's base that Sonnet called not_a_jev_build were never in the
     audit's frame. They enter at the model's labels, like the other plug-ins.
Each estimate reports its plug-in count, so it is clear how much of it rests on the model's own word.

Audit-only variant. The evidence strata (the census of the 15 measured-production posts and the random
samples of 200 demos with no numbers and 200 measured demos) cover every post in the frame except the
85 proposal and commentary posts. Cut to a plug-in region, they estimate what is in that region from
the audit's labels. "audit_only" replaces each plug-in region by that estimate, so it depends on the
model's labels only through the proposal and commentary posts and the model-only posts.

Population weights. The 1,681 audited posts are not a random sample: census strata are read in full
and the rest are sampled at 3% to 65%. Weighted rates use inclusion probabilities from the design
(1 in a census stratum, else 1 - prod(1 - n/N) over the sampled strata that hold the post; strata are
treated as independent draws) and estimate the rate over the whole frame.

Outputs (the tag defaults to "opus"):
  review/work/estimate-<tag>.json      every number, for the audited model and the model under test
  review/data/audit-<tag>-*.csv        tables for the report
  review/audit-<tag>.md                the write-up
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REV = ROOT / "review"
DATA = ROOT / "data"
AUDITED = DATA / "classified-sonnet-v2.jsonl"
AUDITED_NAME = "Claude Sonnet 5"
REFERENCE = REV / "hand-labels-grok.jsonl"
STRATA_FILE = REV / "work" / "strata.json"
SONNET_ESTIMATE = REV / "work" / "estimate.json"


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


EST = _module("review_estimate", REV / "estimate.py")  # the audit's own estimators and bucket rule
wilson, corrected, scale_count = EST.wilson, EST.corrected, EST.scale_count
RT, REPL, GAMES, FAST = EST.RT, EST.REPL, EST.GAMES, EST.FAST
MEASURED, UNMEASURED, FIELDS = EST.MEASURED, EST.UNMEASURED, EST.FIELDS
NJ, META, MP, MD, DNN = "not_a_jev_build", "other_or_meta", "measured_production", "measured_demo", "demo_no_numbers"
REMAINDER = {"proposal_or_idea", "commentary_or_meme"}  # evidence values the audit did not sample
VAGUE = {"unrelated_or_unclear", "benchmark_of_the_model", "tooling_or_wrapper"}
MATERIAL = ("material", "material_vs_frontier")
BUCKETS = ["noise", "hype", "demo", "cost_only", "fast_loop", "material_vs_frontier", "material"]
# The report's claim chips (scripts/audit.py CSA_CHIP, 24 Sep 2026): cost, speed or accuracy. The rebuilt
# report's ladder uses them in place of the withdrawn framing field.
CSA_CHIP = re.compile(r"^(\$[\d.,]+|[\d.,]+¢|[\d.,]+\s*×\s*(cheaper|faster)|[\d.,]+\s*ms|[\d.,]+\s*s|[\d.,e+]+/s|[\d.,]+%\s*accurate)$")
COST_RE = re.compile(r"^([\d.,]+)\s*×\s*cheaper$")
SPEED_RE = re.compile(r"^([\d.,]+)\s*×\s*faster$")

# review/sample.py's stratum predicates, on the audited (Sonnet v2) labels.
PRED = {
    "measured_production": lambda r: r["evidence"] == MP,
    "material": lambda r: corrected(r) in MATERIAL,
    "realtime_family": lambda r: r["family"] in RT,
    "replacement_baseline": lambda r: r["baseline"] in REPL,
    "baseline_none": lambda r: r["baseline"] == "none",
    "demo_no_numbers": lambda r: r["evidence"] == DNN,
    "measured_demo": lambda r: r["evidence"] == MD,
    "not_realtime_family_not_games": lambda r: r["family"] not in RT and r["family"] != GAMES,
    "realtime_infra_false": lambda r: r["realtime_infra"] is False,
    "realtime_infra_true_nongame": lambda r: r["realtime_infra"] is True and r["family"] != GAMES,
    "other_or_meta": lambda r: r["family"] == META,
    "tier_under_300ms": lambda r: r["tier"] in FAST,
}
STRATUM_NAMES = {
    "measured_production": "measured_production", "material": "material", "realtime_family": "realtime families",
    "replacement_baseline": "replacement baseline", "baseline_none": "baseline none", "demo_no_numbers": "demo_no_numbers",
    "measured_demo": "measured_demo", "not_realtime_family_not_games": "not realtime family, not games",
    "realtime_infra_false": "realtime_infra false", "realtime_infra_true_nongame": "realtime_infra true, not games",
    "other_or_meta": "other_or_meta", "tier_under_300ms": "tier under 300 ms", "all_labelled": "all labelled",
}
# Claim-level groupings for the recount by the model's label.
GROUPS = [
    ("rt_family", "family is voice, live chat or collaboration", lambda r: r["family"] in RT),
    ("games", "family is games", lambda r: r["family"] == GAMES),
    ("meta", "family is other_or_meta", lambda r: r["family"] == META),
    ("not_a_jev_build", "family is not_a_jev_build", lambda r: r["family"] == NJ),
    ("measured_production", "evidence is measured_production", lambda r: r["evidence"] == MP),
    ("measured", "evidence is measured (demo or production)", lambda r: r["evidence"] in MEASURED),
    ("no_measurement", "evidence is demo_no_numbers, proposal or commentary", lambda r: r["evidence"] not in MEASURED),
    ("baseline_none", "baseline is none", lambda r: r["baseline"] == "none"),
    ("baseline_replacement", "baseline is classic ML, rules or vendor API", lambda r: r["baseline"] in REPL),
    ("tier_under_300ms", "tier is frame, feel or turn", lambda r: r["tier"] in FAST),
    ("live_loop_nongame", "realtime_infra true, not games", lambda r: r["realtime_infra"] is True and r["family"] != GAMES),
    ("realtime_infra", "realtime_infra true", lambda r: r["realtime_infra"] is True),
    ("candidate", "meets the material test (corrected bucket material)", lambda r: corrected(r) in MATERIAL),
    ("production_claim", "production_claim true", lambda r: r["production_claim"] is True),
]


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def model_name(path: Path) -> str:
    s = path.name.lower()
    if "opus" in s:
        return "Claude Opus 5.5"
    if "sonnet-v2" in s:
        return "Claude Sonnet 5"
    return path.stem


def load_rows(path: Path, cards: dict, dropped: set) -> dict[str, dict]:
    rows = {}
    for r in read_jsonl(path):
        i = str(r["id"])
        if i in dropped:
            continue
        c = cards[i]
        rows[i] = dict(r, id=i, v=c.get("v") or 0, f=c.get("f") or 0, chips=c.get("chips") or [])  # last wins, as review/estimate.py
    return rows


def load_reference() -> dict[str, dict]:
    ref, bad = {}, []
    for o in read_jsonl(REFERENCE):
        i = str(o["id"])
        for f, allowed in (("family", EST.FAMILIES), ("tier", EST.TIERS), ("evidence", EST.EVIDENCE),
                           ("framing", EST.FRAMING), ("baseline", EST.BASELINE)):
            if o.get(f) not in allowed:
                bad.append(f"{i} {f} {o.get(f)}")
        for f in ("realtime_infra", "production_claim"):
            if not isinstance(o.get(f), bool):
                bad.append(f"{i} {f}")
        if o.get("family") == META and o.get("noise") not in EST.NOISE:
            bad.append(f"{i} noise {o.get('noise')}")
        ref[i] = dict(o, id=i)
    if bad:
        raise SystemExit(f"{REFERENCE.relative_to(ROOT)} has invalid labels: {bad[:10]}")
    return ref


def load_context() -> dict:
    cards = {str(c["id"]): c for c in json.loads((DATA / "cards.json").read_text())["cards"]}
    dropped = {str(i) for r in read_jsonl(DATA / "dedupe-groups.jsonl") for i in r["merged"]}
    sonnet_all = load_rows(AUDITED, cards, dropped)
    frame = {i: r for i, r in sonnet_all.items() if r["family"] != NJ}
    strata = json.loads(STRATA_FILE.read_text())
    ref = load_reference()
    if set(ref) != set(strata["membership"]):
        raise SystemExit("the reference labels do not cover exactly the audited posts in review/work/strata.json")
    # The strata must still be what review/sample.py drew: same base, same stratum sizes, same census lists.
    pops = {k: sorted(i for i, r in frame.items() if p(r)) for k, p in PRED.items()}
    meta = strata["meta"]
    problems = []
    if len(frame) != meta["use_case_base"]:
        problems.append(f"base {len(frame)} != {meta['use_case_base']}")
    for k, ids in pops.items():
        if len(ids) != meta["stratum_population"][k]:
            problems.append(f"{k}: {len(ids)} != {meta['stratum_population'][k]}")
    for k, ids in strata["exhaustive"].items():
        if sorted(ids) != pops[k]:
            problems.append(f"census {k} differs")
    for k, ids in strata["samples"].items():
        if not set(ids) <= set(pops[k]):
            problems.append(f"sample {k} is not inside its stratum")
    if problems:
        raise SystemExit("the Sonnet v2 labels no longer give the audited strata: " + "; ".join(problems))
    # Inclusion probabilities of the audit's design, for population-weighted rates.
    census = set().union(*(set(v) for v in strata["exhaustive"].values()))
    popset = {k: set(v) for k, v in pops.items()}
    frac = {k: len(v) / len(pops[k]) for k, v in strata["samples"].items()}
    pi = {}
    for i in frame:
        if i in census:
            pi[i] = 1.0
            continue
        miss = 1.0
        for k, f in frac.items():
            if i in popset[k]:
                miss *= 1.0 - f
        pi[i] = 1.0 - miss
    jev = {str(j["id"]): j for j in read_jsonl(DATA / "classified-jev.jsonl")}
    noise = {str(n["id"]): n for n in read_jsonl(DATA / "classified-noise.jsonl")}
    prior = read_jsonl(DATA / "hand-labels-120.jsonl")
    return {"cards": cards, "dropped": dropped, "sonnet_all": sonnet_all, "frame": frame, "strata": strata, "ref": ref,
            "pops": pops, "pi": pi, "jev": jev, "noise": noise, "prior": prior}


def kappa(pairs: list[tuple], weights: list[float] | None = None) -> float | None:
    """Cohen's kappa for (model, reference) pairs, optionally weighted."""
    if not pairs:
        return None
    w = weights or [1.0] * len(pairs)
    tot = sum(w)
    po = sum(wi for (a, b), wi in zip(pairs, w) if a == b) / tot
    pm, pg = Counter(), Counter()
    for (a, b), wi in zip(pairs, w):
        pm[a] += wi
        pg[b] += wi
    pe = sum(pm[c] * pg[c] for c in pm) / (tot * tot)
    return None if pe >= 1 else (po - pe) / (1 - pe)


def median(xs: list[float]) -> float | None:
    xs = sorted(xs)
    n = len(xs)
    if n == 0:
        return None
    return xs[n // 2] if n % 2 else 0.5 * (xs[n // 2 - 1] + xs[n // 2])


def has_csa_chip(chips) -> bool:
    return any(CSA_CHIP.match(str(c).strip()) for c in chips or [])


def baseline_is(pred):
    """A (row, id) predicate on the baseline field."""
    return lambda r, i: pred(r["baseline"])


def run(model_all: dict[str, dict], ctx: dict, base: str = "model") -> dict:
    """review/estimate.py's claims with `model_all` as the model under test.

    base="model": shares of the model's own use-case base (strata cut to it; model-only posts plugged in).
    base="frame": shares of the audited frame (5,709), a post the model did not label falls back to its
    Sonnet label (the construction of scripts/audit.py reestimate()).
    """
    frame, pops, ref, strata, cards = ctx["frame"], ctx["pops"], ctx["ref"], ctx["strata"], ctx["cards"]
    if base == "model":
        B = [i for i, r in model_all.items() if r["family"] != NJ]

        def M(i: str) -> dict:
            return model_all[i]
    else:
        B = list(frame)

        def M(i: str) -> dict:
            return model_all.get(i) or frame[i]
    Bset = set(B)
    N = len(B)
    X = sorted(Bset - set(frame))  # in the model's base, never in the audit's frame

    def dom(ids) -> list[str]:
        return [i for i in ids if i in Bset]

    D = {k: dom(v) for k, v in pops.items()}  # Sonnet-defined strata, cut to the base
    S = {k: dom(v) for k, v in strata["samples"].items()}
    frame_in = [i for i in frame if i in Bset]
    REG = {  # regions review/estimate.py takes from the model's labels, per claim
        "frontier_small": [i for i in frame_in if frame[i]["baseline"] in ("frontier_llm", "small_llm")],
        "remainder": [i for i in frame_in if frame[i]["evidence"] in REMAINDER],
        "games": [i for i in frame_in if frame[i]["family"] == GAMES],
        "rt_true_games": [i for i in frame_in if frame[i]["realtime_infra"] is True and frame[i]["family"] == GAMES],
        "not_fast": [i for i in frame_in if frame[i]["tier"] not in FAST],
        "not_meta": [i for i in frame_in if frame[i]["family"] != META],
    }

    def pct(c: float) -> float:
        return 100 * c / N

    def rec(est: float, lo: float, hi: float, plug: float = 0, **kw) -> dict:
        return {"est_count": est, "lo": lo, "hi": hi, "est_pct": pct(est), "lo_pct": pct(lo), "hi_pct": pct(hi), "plug": plug, **kw}

    def model_count(q, ids=None) -> int:
        return sum(1 for i in (B if ids is None else ids) if q(M(i), i))

    def ep(q, region=None) -> dict:
        """The evidence strata, optionally cut to a region: census + two Wilson-scaled samples + plug-ins."""
        rs = None if region is None else set(region)

        def cut(ids):
            return [i for i in ids if rs is None or i in rs]
        census_ids = cut(D["measured_production"])
        census = sum(1 for i in census_ids if q(ref[i], i))
        est = lo = hi = float(census)
        parts, plug = {}, 0
        for h in (DNN, MD):
            pop, smp = cut(D[h]), cut(S[h])
            if pop and not smp:  # no audited post in this cell: fall back to the model
                c = model_count(q, pop)
                plug += c
                parts[h] = {"pop": len(pop), "n": 0, "k": None, "model_plug": c}
                continue
            if not pop:
                parts[h] = {"pop": 0, "n": 0, "k": 0}
                continue
            k = sum(1 for i in smp if q(ref[i], i))
            w = wilson(k, len(smp))
            est += w["p"] * len(pop)
            lo += w["lo"] * len(pop)
            hi += w["hi"] * len(pop)
            parts[h] = {"pop": len(pop), "n": len(smp), "k": k}
        rem = cut(REG["remainder"]) + [i for i in X if rs is None or i in rs]
        plug += model_count(q, rem)
        return {"est_count": est + plug, "lo": lo + plug, "hi": hi + plug, "census": census, "census_n": len(census_ids),
                "plug": plug, "parts": parts}

    def region_check(q, region_key: str) -> dict:
        """What the model says is in a plug-in region, against the audit's estimate of it."""
        ids = REG[region_key]
        a = ep(q, ids)
        audited = [i for i in ids if i in ref]
        return {"region": region_key, "region_n": len(ids), "model_n": model_count(q, ids), "audit_est": a["est_count"],
                "audit_lo": a["lo"], "audit_hi": a["hi"], "audit_plug": a["plug"], "audit": a,
                "audited_n": len(audited), "audited_model_pos": sum(1 for i in audited if q(M(i), i)),
                "audited_model_pos_ref_pos": sum(1 for i in audited if q(M(i), i) and q(ref[i], i)),
                "audited_ref_pos": sum(1 for i in audited if q(ref[i], i))}

    out = {"base_mode": base, "use_case_base": N, "model_only_posts": len(X), "model_only_ids": X,
           "frame_posts_outside_base": len(frame) - len(frame_in),
           "domain": {k: {"population": len(D[k]), "frame_population": len(pops[k]),
                          "sample": len(S.get(k, [])) if k in S else None} for k in pops},
           "regions": {k: len(v) for k, v in REG.items()}}

    # ----- Claim 1. Baselines: replacement census, the none sample, frontier and small strata (plug-in).
    none_S, repl_D, none_N = S["baseline_none"], D["replacement_baseline"], len(D["baseline_none"])
    plug1 = REG["frontier_small"] + X
    cats = (("none", lambda b: b == "none"), ("frontier_llm", lambda b: b == "frontier_llm"),
            ("small_llm", lambda b: b == "small_llm"), ("replacement", lambda b: b in REPL))
    c1 = {"none_sample_n": len(none_S), "none_stratum_n": none_N, "replacement_census_n": len(repl_D),
          "none_sample_baseline": dict(Counter(ref[i]["baseline"] for i in none_S)),
          "replacement_stratum_baseline": dict(Counter(ref[i]["baseline"] for i in repl_D)), "corrected": {}}
    for cat, p in cats:
        q = baseline_is(p)
        census = sum(1 for i in repl_D if p(ref[i]["baseline"]))
        k = sum(1 for i in none_S if p(ref[i]["baseline"]))
        sc = scale_count(census, k, len(none_S), none_N)
        assumed = model_count(q, plug1)
        assumed_frame = sum(1 for i in REG["frontier_small"] if p(frame[i]["baseline"])) + model_count(q, X)
        chk = region_check(q, "frontier_small")
        x_plug = model_count(q, X)
        c1["corrected"][cat] = {
            "census_in_replacement_stratum": census, "in_none_sample": k, "scaled_from_none": sc,
            "assumed_from_unsampled": assumed,
            **rec(sc["est"] + assumed, sc["lo"] + assumed, sc["hi"] + assumed, plug=assumed),
            "model_n": model_count(q), "model_pct": pct(model_count(q)),
            "unsampled_at_sonnet_labels": rec(sc["est"] + assumed_frame, sc["lo"] + assumed_frame, sc["hi"] + assumed_frame, plug=assumed_frame),
            "region_check": chk,
            "audit_only": rec(sc["est"] + chk["audit_est"] + x_plug, sc["lo"] + chk["audit_lo"] + x_plug,
                              sc["hi"] + chk["audit_hi"] + x_plug, plug=chk["audit_plug"] + x_plug),
        }
    # the frontier and small posts that happen to be audited through other strata (not a random sample of them)
    c1["baseline_sensitivity"] = {}
    for value in ("frontier_llm", "small_llm"):
        ids = [i for i in B if M(i)["baseline"] == value and i in ref]
        c1["baseline_sensitivity"][value] = {"n": len(ids), "audit": dict(Counter(ref[i]["baseline"] for i in ids))}
    out["claim1"] = c1

    # ----- Claim 2. Measured production: census of Sonnet's 15, misses in the two evidence samples, remainder (plug-in).
    prod_D, prod_set = D["measured_production"], set(pops["measured_production"])
    is_mp = lambda r, i=None: r["evidence"] == MP
    k_prod = sum(1 for i in prod_D if is_mp(ref[i]))
    k_nn = sum(1 for i in S[DNN] if is_mp(ref[i]))
    k_md = sum(1 for i in S[MD] if is_mp(ref[i]) and i not in prod_set)
    s1 = scale_count(0, k_nn, len(S[DNN]), len(D[DNN]))
    s2 = scale_count(0, k_md, len(S[MD]), len(D[MD]))
    plug2 = model_count(is_mp, REG["remainder"] + X)
    out["claim2"] = {
        "model_n": model_count(is_mp), "model_pct": pct(model_count(is_mp)), "census_n": len(prod_D), "hold_on_reread": k_prod,
        "misses_in_demo_no_numbers_sample": k_nn, "misses_in_measured_demo_sample": k_md,
        **rec(k_prod + s1["est"] + s2["est"] + plug2, k_prod + s1["lo"] + s2["lo"] + plug2, k_prod + s1["hi"] + s2["hi"] + plug2, plug=plug2),
        "interval": "sum of per-stratum Wilson bounds, conservative",
    }

    # ----- Claim 3. Buckets (the review's rule), the prose buckets, the material census, and the ladder.
    def bucket_ref(i):
        return corrected(ref[i])

    rem_ids = REG["remainder"] + X
    rem_counts = Counter(corrected(M(i)) for i in rem_ids)
    b_nn, b_md = Counter(bucket_ref(i) for i in S[DNN]), Counter(bucket_ref(i) for i in S[MD])
    b_prod = Counter(bucket_ref(i) for i in prod_D)
    N_nn, N_md = len(D[DNN]), len(D[MD])
    buckets = {}
    for b in BUCKETS:
        w1, w2 = wilson(b_nn[b], len(S[DNN])), wilson(b_md[b], len(S[MD]))
        exact = b_prod[b] + rem_counts[b]
        buckets[b] = {
            **rec(exact + w1["p"] * N_nn + w2["p"] * N_md, exact + w1["lo"] * N_nn + w2["lo"] * N_md,
                  exact + w1["hi"] * N_nn + w2["hi"] * N_md, plug=rem_counts[b]),
            "from_demo_no_numbers_sample": b_nn[b], "from_measured_demo_sample": b_md[b], "from_production_census": b_prod[b],
            "from_unsampled_remainder_model": rem_counts[b],
            "model_n": model_count(lambda r, i, b_=b: corrected(r) == b_), "model_pct": pct(model_count(lambda r, i, b_=b: corrected(r) == b_)),
        }
    mat_D = D["material"]
    mat_survives = sum(1 for i in mat_D if bucket_ref(i) in MATERIAL)
    mat_games = sum(1 for i in mat_D if bucket_ref(i) in MATERIAL and ref[i]["family"] == GAMES)
    mat_set = set(pops["material"])
    md_out_pop = [i for i in D[MD] if i not in mat_set]
    samp_out = [i for i in S[MD] if i not in mat_set]
    k_md_miss = sum(1 for i in samp_out if bucket_ref(i) in MATERIAL)
    k_nn_miss = sum(1 for i in S[DNN] if bucket_ref(i) in MATERIAL)
    w_md, w_nn = wilson(k_md_miss, len(samp_out)), wilson(k_nn_miss, len(S[DNN]))
    plug_mat = model_count(lambda r, i: corrected(r) in MATERIAL, rem_ids)
    material_combined = {
        "census_n": len(mat_D), "census_survivors": mat_survives, "census_survivors_nongame": mat_survives - mat_games,
        "census_pct": pct(mat_survives), "measured_demo_outside_n": len(md_out_pop), "measured_demo_outside_sample_n": len(samp_out),
        "measured_demo_outside_misses": k_md_miss, "demo_no_numbers_misses": k_nn_miss,
        **rec(mat_survives + w_md["p"] * len(md_out_pop) + w_nn["p"] * N_nn + plug_mat,
              mat_survives + w_md["lo"] * len(md_out_pop) + w_nn["lo"] * N_nn + plug_mat,
              mat_survives + w_md["hi"] * len(md_out_pop) + w_nn["hi"] * N_nn + plug_mat, plug=plug_mat),
        "model_n": model_count(lambda r, i: corrected(r) in MATERIAL),
        "model_pct": pct(model_count(lambda r, i: corrected(r) in MATERIAL)),
    }

    def narrow_hype(r, i=None):
        return r["evidence"] in UNMEASURED and r["framing"] in ("cost", "latency", "accuracy")

    def narrow_demo(r, i=None):
        return (r["evidence"] in UNMEASURED and not narrow_hype(r) and r["family"] != META and r["evidence"] != "commentary_or_meme")

    def prose_cost(r, i=None):
        if r["family"] == META or r["evidence"] == "commentary_or_meme" or r["evidence"] not in MEASURED:
            return False
        return r["tier"] == "batch" or r["baseline"] in ("small_llm", "vendor_api", "classic_classifier_or_ml", "rules_or_regex")

    prose = {}
    for name, pred in (("hype_cost_speed_accuracy", narrow_hype), ("demo_other_unmeasured", narrow_demo),
                       ("cost_only_as_described", prose_cost)):
        k1 = sum(1 for i in S[DNN] if pred(ref[i]))
        k2 = sum(1 for i in S[MD] if pred(ref[i]))
        k3 = sum(1 for i in prod_D if pred(ref[i]))
        a, b_ = wilson(k1, len(S[DNN])), wilson(k2, len(S[MD]))
        # review/estimate.py leaves the proposal and commentary posts out of these three; kept, and its size reported
        prose[name] = {
            **rec(k3 + a["p"] * N_nn + b_["p"] * N_md, k3 + a["lo"] * N_nn + b_["lo"] * N_md, k3 + a["hi"] * N_nn + b_["hi"] * N_md),
            "sample_demo_no_numbers": k1, "sample_measured_demo": k2, "production_census": k3,
            "left_out_remainder_at_model_labels": model_count(pred, rem_ids),
            "model_n": model_count(pred), "model_pct": pct(model_count(pred)),
        }
    chips = {i: (cards[i].get("chips") or []) for i in cards}

    def claim_nn(r, i):
        return r["evidence"] == DNN and has_csa_chip(chips.get(i))

    def demo_nn(r, i):
        return r["evidence"] == DNN and not has_csa_chip(chips.get(i)) and r["family"] != META

    ladder = {}
    for name, q in (("ladder_demo_no_numbers", demo_nn), ("ladder_claim_no_number", claim_nn),
                    ("ladder_no_measurement", lambda r, i: r["evidence"] not in MEASURED),
                    ("ladder_measured_demo", lambda r, i: r["evidence"] == MD),
                    ("ladder_measured_production", lambda r, i: r["evidence"] == MP)):
        e = ep(q)
        ladder[name] = {**rec(e["est_count"], e["lo"], e["hi"], plug=e["plug"]), "census": e["census"], "parts": e["parts"],
                        "model_n": model_count(q), "model_pct": pct(model_count(q))}
    out["claim3"] = {"buckets": buckets, "material_combined": material_combined, "prose_buckets": prose, "ladder": ladder,
                     "unsampled_remainder_n": len(REG["remainder"]), "model_only_n": len(X)}

    # ----- Claim 4. Voice, live chat and collaboration: census, negative sample, games (plug-in).
    in_rt = lambda r, i=None: r["family"] in RT
    rt_D, neg_S, neg_N = D["realtime_family"], S["not_realtime_family_not_games"], len(D["not_realtime_family_not_games"])
    k_rt = sum(1 for i in rt_D if in_rt(ref[i]))
    k_miss = sum(1 for i in neg_S if in_rt(ref[i]))
    sc4 = scale_count(k_rt, k_miss, len(neg_S), neg_N)
    plug4 = model_count(in_rt, REG["games"] + X)
    chk4 = region_check(in_rt, "games")
    x4 = model_count(in_rt, X)
    out["claim4"] = {
        "model_n": model_count(in_rt), "model_pct": pct(model_count(in_rt)), "census_n": len(rt_D),
        "census_still_in_family": k_rt, "negative_sample_n": len(neg_S), "negative_stratum_n": neg_N, "misses_in_negative_sample": k_miss,
        **rec(sc4["est"] + plug4, sc4["lo"] + plug4, sc4["hi"] + plug4, plug=plug4),
        "census_measured_production": sum(1 for i in rt_D if in_rt(ref[i]) and is_mp(ref[i])),
        "census_production_claim": sum(1 for i in rt_D if in_rt(ref[i]) and ref[i]["production_claim"]),
        "plugin_measured_production": model_count(lambda r, i: in_rt(r) and is_mp(r), REG["games"] + X),
        "plugin_production_claim": model_count(lambda r, i: in_rt(r) and r["production_claim"], REG["games"] + X),
        "negative_sample_productionish": sum(1 for i in neg_S if in_rt(ref[i]) and (is_mp(ref[i]) or ref[i]["production_claim"])),
        "model_measured_production": model_count(lambda r, i: in_rt(r) and is_mp(r)),
        "model_production_claim": model_count(lambda r, i: in_rt(r) and r["production_claim"]),
        "region_check": chk4,
        "audit_only": rec(sc4["est"] + chk4["audit_est"] + x4, sc4["lo"] + chk4["audit_lo"] + x4, sc4["hi"] + chk4["audit_hi"] + x4,
                          plug=chk4["audit_plug"] + x4),
    }

    # ----- Claim 5. A live loop: both realtime-flag samples; flagged games (plug-in).
    loop_ng = lambda r, i=None: r["realtime_infra"] is True and r["family"] != GAMES
    loop_any = lambda r, i=None: r["realtime_infra"] is True
    t_S, f_S = S["realtime_infra_true_nongame"], S["realtime_infra_false"]
    N_true, N_false = len(D["realtime_infra_true_nongame"]), len(D["realtime_infra_false"])
    k_true = sum(1 for i in t_S if loop_ng(ref[i]))
    k_flip = sum(1 for i in f_S if loop_ng(ref[i]))
    k_any = sum(1 for i in f_S if loop_any(ref[i]))
    s_true, s_false = scale_count(0, k_true, len(t_S), N_true), scale_count(0, k_flip, len(f_S), N_false)
    s_false_any = scale_count(0, k_any, len(f_S), N_false)
    plug5 = model_count(loop_ng, REG["rt_true_games"] + X)
    plug5_any = model_count(loop_any, REG["rt_true_games"] + X)
    chk5 = region_check(loop_ng, "rt_true_games")
    x5 = model_count(loop_ng, X)
    fast_S = S["tier_under_300ms"]
    game_fast = [i for i in fast_S if M(i)["family"] == GAMES]
    game_fast_live = sum(1 for i in game_fast if ref[i]["realtime_infra"] is True)
    games_model = model_count(lambda r, i: r["family"] == GAMES)
    nongame = rec(s_true["est"] + s_false["est"] + plug5, s_true["lo"] + s_false["lo"] + plug5, s_true["hi"] + s_false["hi"] + plug5, plug=plug5)
    rate = game_fast_live / len(game_fast) if game_fast else None
    live_all = (rate * games_model + nongame["est_count"]) if rate is not None else None
    any_ep = ep(loop_any)
    out["claim5"] = {
        "model_n": model_count(loop_any), "model_pct": pct(model_count(loop_any)),
        "model_nongame_n": model_count(loop_ng), "model_nongame_pct": pct(model_count(loop_ng)),
        "true_nongame_sample_still_true_and_nongame": k_true, "true_nongame_sample_n": len(t_S),
        "false_sample_flipped_nongame": k_flip, "false_sample_flipped_any": k_any, "false_sample_n": len(f_S),
        "nongame": nongame,
        "any_realtime": rec(s_true["est"] + s_false_any["est"] + plug5_any, s_true["lo"] + s_false_any["lo"] + plug5_any,
                            s_true["hi"] + s_false_any["hi"] + plug5_any, plug=plug5_any),
        "games_in_fast_tier_sample": len(game_fast), "games_in_fast_tier_sample_live": game_fast_live, "games_live_rate": rate,
        "model_games": games_model,
        "live_loop_all": {"est_count": live_all, "est_pct": pct(live_all) if live_all is not None else None,
                          "note": "the live-loop rate of the model's games in the under-300 ms sample, times the model's games, plus the non-game estimate"},
        "region_check": chk5,
        "audit_only_nongame": rec(s_true["est"] + s_false["est"] + chk5["audit_est"] + x5, s_true["lo"] + s_false["lo"] + chk5["audit_lo"] + x5,
                                  s_true["hi"] + s_false["hi"] + chk5["audit_hi"] + x5, plug=chk5["audit_plug"] + x5),
        "audit_only_any": {**rec(any_ep["est_count"], any_ep["lo"], any_ep["hi"], plug=any_ep["plug"]), "parts": any_ep["parts"]},
    }

    # ----- Claim 6. Under 300 ms: the tier sample; posts outside it (plug-in for the set's size).
    fast_q = lambda r, i=None: r["tier"] in FAST
    fast_N = len(D["tier_under_300ms"])
    i_fast = [i for i in fast_S if fast_q(ref[i])]
    i_fast_games = sum(1 for i in i_fast if ref[i]["family"] == GAMES)
    w_fast = wilson(i_fast_games, len(i_fast)) if i_fast else wilson(0, 0)
    w_set = wilson(len(i_fast), len(fast_S))
    plug6 = model_count(fast_q, REG["not_fast"] + X)
    chk6 = region_check(fast_q, "not_fast")
    x6 = model_count(fast_q, X)
    chk6g = region_check(lambda r, i: fast_q(r) and r["family"] == GAMES, "not_fast")
    set_est = w_set["p"] * fast_N
    ao_set = set_est + chk6["audit_est"] + x6
    ao_games = i_fast_games / len(fast_S) * fast_N + chk6g["audit_est"] + model_count(lambda r, i: fast_q(r) and r["family"] == GAMES, X)
    out["claim6"] = {
        "model_fast_n": model_count(fast_q), "model_fast_pct": pct(model_count(fast_q)),
        "model_fast_games": model_count(lambda r, i: fast_q(r) and r["family"] == GAMES),
        "model_games_share": (model_count(lambda r, i: fast_q(r) and r["family"] == GAMES) / model_count(fast_q)) if model_count(fast_q) else None,
        "sample_n": len(fast_S), "stratum_n": fast_N, "sample_still_fast": len(i_fast), "sample_still_fast_and_game": i_fast_games,
        "conditional_games_share": w_fast, "conditional_pct": 100 * w_fast["p"] if w_fast["p"] is not None else None,
        "conditional_lo_pct": 100 * w_fast["lo"] if w_fast["lo"] is not None else None,
        "conditional_hi_pct": 100 * w_fast["hi"] if w_fast["hi"] is not None else None,
        "set": rec(set_est + plug6, w_set["lo"] * fast_N + plug6, w_set["hi"] * fast_N + plug6, plug=plug6),
        "region_check": chk6, "region_check_games": chk6g,
        "audit_only_set": rec(ao_set, w_set["lo"] * fast_N + chk6["audit_lo"] + x6, w_set["hi"] * fast_N + chk6["audit_hi"] + x6,
                              plug=chk6["audit_plug"] + x6),
        "audit_only_games_share": (ao_games / ao_set) if ao_set else None,
    }

    # ----- Claim 7. Meta posts: the other_or_meta sample; posts outside it (plug-in).
    meta_S, N_meta = S["other_or_meta"], len(D["other_or_meta"])
    meta_q = lambda r, i=None: r["family"] == META
    still = [i for i in meta_S if meta_q(ref[i])]
    sub = Counter((ref[i].get("noise") or "missing") for i in still)
    moved = Counter(ref[i]["family"] for i in meta_S if not meta_q(ref[i]))
    w_still = wilson(len(still), len(meta_S))
    plug7 = model_count(meta_q, REG["not_meta"] + X)
    chk7 = region_check(meta_q, "not_meta")
    x7 = model_count(meta_q, X)
    k_vague, k_meme, k_hot = sum(sub[k] for k in VAGUE), sub["meme_or_joke"], sub["hot_take_or_commentary"]
    noise = ctx["noise"]
    model_meta = [i for i in B if meta_q(M(i))]
    with_sub = [i for i in model_meta if i in noise]
    ao = {}
    for key, qq in (("vague", lambda r, i: meta_q(r) and r.get("noise") in VAGUE),
                    ("meme", lambda r, i: meta_q(r) and r.get("noise") == "meme_or_joke"),
                    ("hot", lambda r, i: meta_q(r) and r.get("noise") == "hot_take_or_commentary")):
        k = {"vague": k_vague, "meme": k_meme, "hot": k_hot}[key]
        c = region_check(qq, "not_meta")
        ao[key] = {"sample_k": k, "region_audit_est": c["audit_est"], "est_count": k / len(meta_S) * N_meta + c["audit_est"],
                   "est_pct": pct(k / len(meta_S) * N_meta + c["audit_est"])}
    out["claim7"] = {
        "model_meta_n": len(model_meta), "model_meta_pct": pct(len(model_meta)),
        "sample_n": len(meta_S), "stratum_n": N_meta, "sample_still_meta": len(still), "sample_moved": dict(moved),
        "subtype_among_still": dict(sub),
        **rec(w_still["p"] * N_meta + plug7, w_still["lo"] * N_meta + plug7, w_still["hi"] * N_meta + plug7, plug=plug7),
        "samples_only": rec(w_still["p"] * N_meta, w_still["lo"] * N_meta, w_still["hi"] * N_meta),
        "vague_in_sample": k_vague, "vague_est_pct": pct(k_vague / len(meta_S) * N_meta),
        "meme": wilson(k_meme, len(meta_S)), "hot": wilson(k_hot, len(meta_S)),
        "meme_est_pct": pct(k_meme / len(meta_S) * N_meta), "hot_est_pct": pct(k_hot / len(meta_S) * N_meta),
        "model_meme_n": sum(1 for i in model_meta if (noise.get(i) or {}).get("subtype") == "meme_or_joke"),
        "model_hot_n": sum(1 for i in model_meta if (noise.get(i) or {}).get("subtype") == "hot_take_or_commentary"),
        "model_vague_n": sum(1 for i in model_meta if (noise.get(i) or {}).get("subtype") in VAGUE),
        "model_meta_with_subtype": len(with_sub),
        "region_check": chk7,
        "audit_only": rec(w_still["p"] * N_meta + chk7["audit_est"] + x7, w_still["lo"] * N_meta + chk7["audit_lo"] + x7,
                          w_still["hi"] * N_meta + chk7["audit_hi"] + x7, plug=chk7["audit_plug"] + x7),
        "audit_only_subtypes": ao,
    }

    # ----- Claim 8. Views on the base (a census; the base is the only thing the model changes).
    vv = {i: cards[i].get("v") or 0 for i in B}
    ff = {i: cards[i].get("f") or 0 for i in B}
    views = sorted(vv.values(), reverse=True)
    total_v = sum(views)
    k1 = max(1, math.ceil(0.01 * len(views)))
    half_n, running = 0, 0
    for v in views:
        running += v
        half_n += 1
        if running >= 0.5 * total_v:
            break
    suspect = [i for i in B if vv[i] >= 100_000 and ff[i] / vv[i] < 0.002]
    keep = sorted((vv[i] for i in B if i not in set(suspect)), reverse=True)
    k2 = max(1, math.ceil(0.01 * len(keep)))
    likes = sorted(ff.values(), reverse=True)
    lk = max(1, math.ceil(0.01 * len(likes)))
    top_id = max(B, key=lambda i: vv[i])
    out["claim8"] = {"cards": N, "top1_cards": k1, "top1_share": sum(views[:k1]) / total_v, "cards_holding_half": half_n,
                     "half_pct_of_posts": 100 * half_n / N, "suspect_n": len(suspect),
                     "suspect_share": sum(vv[i] for i in suspect) / total_v, "top1_excl_suspect": sum(keep[:k2]) / sum(keep),
                     "top1_likes_share": sum(likes[:lk]) / sum(likes), "top_card_share": vv[top_id] / total_v}

    # ----- Claim 9. Jev against the model's family (not_a_jev_build counts as other_or_meta; Jev had no such option).
    jev = ctx["jev"]
    both = []
    for i, r in model_all.items():
        j = jev.get(i)
        if not j:
            continue
        fam = META if r["family"] == NJ else r["family"]
        both.append((i, fam, j.get("family"), j.get("prob")))
    agree_n = sum(1 for _, a, b, _ in both if a == b)
    hi = [t for t in both if isinstance(t[3], (int, float)) and t[3] >= 0.99]
    hi_agree = sum(1 for _, a, b, _ in hi if a == b)
    hi_ref = [t for t in hi if t[0] in ref]
    hi_ref_right = sum(1 for i, a, b, p in hi_ref if b == ref[i]["family"] or (b == META and ref[i]["family"] == NJ))
    out["claim9"] = {"n": len(both), "agree_model": agree_n, "agree_pct": 100 * agree_n / len(both),
                     "kappa": kappa([(b, a) for _, a, b, _ in both]),
                     "p_ge_099": len(hi), "p_ge_099_agree_model": hi_agree, "p_ge_099_agree_model_pct": 100 * hi_agree / len(hi),
                     "p_ge_099_in_audit": len(hi_ref), "p_ge_099_matches_audit_family": hi_ref_right,
                     "p_ge_099_match_audit_pct": 100 * hi_ref_right / len(hi_ref) if hi_ref else None}

    # ----- Claim 10. Chip medians on the base (a census of the chips; the base is the only thing the model changes).
    cost, speed = [], []
    for i in B:
        for ch in cards[i].get("chips") or []:
            m = COST_RE.match(str(ch).strip())
            if m:
                cost.append(float(m.group(1).replace(",", "")))
            m = SPEED_RE.match(str(ch).strip())
            if m:
                speed.append(float(m.group(1).replace(",", "")))
    out["claim10"] = {"cost_chips": len(cost), "cost_median": median(cost), "cost_median_without_1x": median([x for x in cost if x != 1]),
                      "cost_1x": sum(1 for x in cost if x == 1), "speed_chips": len(speed), "speed_median": median(speed),
                      "speed_median_without_1x": median([x for x in speed if x != 1]), "speed_1x": sum(1 for x in speed if x == 1)}
    return out


def agreement(model_all: dict[str, dict], ctx: dict) -> dict:
    """Agreement with the reference on the audited posts: raw, kappa, per stratum, and population-weighted."""
    ref, strata, pi = ctx["ref"], ctx["strata"], ctx["pi"]
    ids = [i for i in ref if i in model_all]
    out = {"n": len(ids), "fields": {}, "strata": {}}
    for f in FIELDS:
        pairs = [(model_all[i][f], ref[i][f]) for i in ids]
        w = [1 / pi[i] for i in ids]
        k = sum(1 for a, b in pairs if a == b)
        wk = sum(wi for (a, b), wi in zip(pairs, w) if a == b) / sum(w)
        out["fields"][f] = {"n": len(ids), "agree": k, "rate": k / len(ids), "kappa": kappa(pairs),
                            "weighted_rate": wk, "weighted_kappa": kappa(pairs, w)}
    groups = list(strata["exhaustive"].items()) + list(strata["samples"].items()) + [("all_labelled", list(ref))]
    for name, sids in groups:
        both = [i for i in sids if i in model_all and i in ref]
        out["strata"][name] = {f: {"n": len(both), "agree": sum(1 for i in both if model_all[i][f] == ref[i][f]),
                                   "rate": (sum(1 for i in both if model_all[i][f] == ref[i][f]) / len(both)) if both else None}
                               for f in FIELDS}
    out["weight_total"] = sum(1 / pi[i] for i in ids)
    out["uncovered_frame_posts"] = sum(1 for v in pi.values() if v == 0)
    return out


def recount(model_all: dict[str, dict], ctx: dict, base_ids: list[str]) -> dict:
    """Among the audited posts, by the model's own label: how often the reference agrees (not a random sample)."""
    ref, pi = ctx["ref"], ctx["pi"]
    ids = [i for i in ref if i in model_all]
    base_count = {f: Counter(model_all[i][f] for i in base_ids) for f in FIELDS}
    rows = []
    for f in FIELDS:
        values = sorted({model_all[i][f] for i in ids} | set(base_count[f]), key=lambda v: str(v))
        for v in values:
            pos = [i for i in ids if model_all[i][f] == v]
            refpos = [i for i in ids if ref[i][f] == v]
            k = sum(1 for i in pos if ref[i][f] == v)
            w = wilson(k, len(pos)) if pos else {"p": None, "lo": None, "hi": None}
            wp = (sum(1 / pi[i] for i in pos if ref[i][f] == v) / sum(1 / pi[i] for i in pos)) if pos else None
            wr = (sum(1 / pi[i] for i in refpos if model_all[i][f] == v) / sum(1 / pi[i] for i in refpos)) if refpos else None
            rows.append({"field": f, "value": v, "base_count": base_count[f].get(v, 0), "audited_n": len(pos), "audit_agrees": k,
                         "precision": w["p"], "lo": w["lo"], "hi": w["hi"], "weighted_precision": wp,
                         "audit_n": len(refpos), "recall": (sum(1 for i in refpos if model_all[i][f] == v) / len(refpos)) if refpos else None,
                         "weighted_recall": wr})
    groups = []
    for key, label, q in GROUPS:
        pos = [i for i in ids if q(model_all[i])]
        neg = [i for i in ids if not q(model_all[i])]
        refpos = [i for i in ids if q(ref[i])]
        k = sum(1 for i in pos if q(ref[i]))
        km = sum(1 for i in neg if q(ref[i]))
        w = wilson(k, len(pos)) if pos else {"p": None, "lo": None, "hi": None}

        def wrate(sel, cond):
            den = sum(1 / pi[i] for i in sel)
            return (sum(1 / pi[i] for i in sel if cond(i)) / den) if den else None
        groups.append({"group": key, "label": label, "base_count": sum(1 for i in base_ids if q(model_all[i])),
                       "deduped_count": sum(1 for r in model_all.values() if q(r)),
                       "audited_n": len(pos), "audit_agrees": k, "precision": w["p"], "lo": w["lo"], "hi": w["hi"],
                       "weighted_precision": wrate(pos, lambda i, q=q: q(ref[i])),
                       "audited_negative_n": len(neg), "audit_positive_among_negative": km,
                       "weighted_miss_rate": wrate(neg, lambda i, q=q: q(ref[i])),
                       "audit_positive_n": len(refpos), "recall": (sum(1 for i in refpos if q(model_all[i])) / len(refpos)) if refpos else None,
                       "weighted_recall": wrate(refpos, lambda i, q=q: q(model_all[i]))})
    return {"values": rows, "groups": groups}


def check_reproduction(son: dict, agr: dict, E: dict) -> list[str]:
    """The Sonnet run must reproduce review/work/estimate.json."""
    pairs = []
    for cat in ("none", "frontier_llm", "small_llm", "replacement"):
        for f in ("est_pct", "lo_pct", "hi_pct"):
            pairs.append((f"claim1.{cat}.{f}", son["claim1"]["corrected"][cat][f], E["claim1"]["corrected"][cat][f]))
    for f in ("est_pct", "lo_pct", "hi_pct"):
        pairs.append((f"claim2.{f}", son["claim2"][f], E["claim2"][f]))
        pairs.append((f"claim4.{f}", son["claim4"][f], E["claim4"][f]))
        pairs.append((f"material_combined.{f}", son["claim3"]["material_combined"][f], E["material_combined"][f]))
        for b in BUCKETS:
            pairs.append((f"claim3.{b}.{f}", son["claim3"]["buckets"][b][f], E["claim3"]["buckets"][b][f]))
        for p in ("hype_cost_speed_accuracy", "demo_other_unmeasured", "cost_only_as_described"):
            pairs.append((f"prose.{p}.{f}", son["claim3"]["prose_buckets"][p][f], E["prose_buckets"][p][f]))
    pairs += [("claim2.hold", son["claim2"]["hold_on_reread"], E["claim2"]["hold_on_reread"]),
              ("claim3.material_survives", son["claim3"]["material_combined"]["census_survivors"], E["claim3"]["material_census_still_material"]),
              ("claim4.census_mp", son["claim4"]["census_measured_production"], E["claim4"]["census_measured_production"]),
              ("claim4.census_claim", son["claim4"]["census_production_claim"], E["claim4"]["census_production_claim"]),
              ("claim5.nongame_est_pct", son["claim5"]["nongame"]["est_pct"], E["claim5"]["nongame_est_pct"]),
              ("claim5.nongame_lo_pct", son["claim5"]["nongame"]["lo_pct"], E["claim5"]["nongame_lo_pct"]),
              ("claim5.nongame_hi_pct", son["claim5"]["nongame"]["hi_pct"], E["claim5"]["nongame_hi_pct"]),
              ("claim5.any_pct", son["claim5"]["any_realtime"]["est_pct"], E["claim5"]["any_realtime_est_pct"]),
              ("claim5.games_fast", son["claim5"]["games_in_fast_tier_sample"], E["claim5"]["games_in_fast_tier_sample"]),
              ("claim5.games_fast_live", son["claim5"]["games_in_fast_tier_sample_live"], E["claim5"]["games_in_fast_tier_sample_i_call_realtime"]),
              ("claim6.conditional_pct", son["claim6"]["conditional_pct"], E["claim6"]["conditional_pct"]),
              ("claim6.conditional_lo_pct", son["claim6"]["conditional_lo_pct"], E["claim6"]["conditional_lo_pct"]),
              ("claim6.conditional_hi_pct", son["claim6"]["conditional_hi_pct"], E["claim6"]["conditional_hi_pct"]),
              ("claim7.est_pct", son["claim7"]["est_pct"], E["claim7"]["est_meta_pct"]),
              ("claim7.lo_pct", son["claim7"]["lo_pct"], E["claim7"]["est_meta_lo_pct"]),
              ("claim7.hi_pct", son["claim7"]["hi_pct"], E["claim7"]["est_meta_hi_pct"]),
              ("claim7.vague", son["claim7"]["vague_est_pct"], E["claim7"]["vague_est_pct"]),
              ("claim7.meme", son["claim7"]["meme_est_pct"], E["claim7"]["meme_est_pct_of_posts"]),
              ("claim7.hot", son["claim7"]["hot_est_pct"], E["claim7"]["hot_est_pct_of_posts"]),
              ("claim7.model_meme", son["claim7"]["model_meme_n"], E["claim7"]["model_meme_n"]),
              ("claim8.top1", son["claim8"]["top1_share"], E["claim8"]["top1_share"]),
              ("claim8.excl", son["claim8"]["top1_excl_suspect"], E["claim8"]["top1_excl_suspect"]),
              ("claim8.likes", son["claim8"]["top1_likes_share"], E["claim8"]["top1_likes_share"]),
              ("claim8.half", son["claim8"]["cards_holding_half"], E["claim8"]["cards_holding_half"]),
              ("claim9.agree", son["claim9"]["agree_pct"], E["claim9"]["agree_pct"]),
              ("claim9.p99", son["claim9"]["p_ge_099_agree_model_pct"], E["claim9"]["p_ge_099_agree_sonnet_pct"]),
              ("claim9.p99_audit", son["claim9"]["p_ge_099_matches_audit_family"], E["claim9"]["p_ge_099_matches_my_family"]),
              ("claim10.cost", son["claim10"]["cost_median"], E["claim10"]["cost_median"]),
              ("claim10.speed", son["claim10"]["speed_median"], E["claim10"]["speed_median"])]
    for f in ("frontier_llm", "small_llm"):
        pairs.append((f"sensitivity.{f}", son["claim1"]["baseline_sensitivity"][f]["audit"], E["baseline_sensitivity"][f]["mine"]))
    for name, block in agr["strata"].items():
        for f in FIELDS:
            pairs.append((f"agreement.{name}.{f}", block[f]["rate"], E["agreement"][name][f]["rate"]))
    bad = []
    for key, a, b in pairs:
        if isinstance(a, dict) or isinstance(b, dict) or a is None or b is None:
            if a != b:
                bad.append(f"{key}: {a} != {b}")
        elif abs(a - b) > 1e-9:
            bad.append(f"{key}: {a} != {b}")
    return bad


# ---------------------------------------------------------------- sanity checks


def sanity(ctx: dict, model_all_raw: list[dict], model_all: dict[str, dict], mrun: dict, name: str) -> dict:
    ref, frame, strata, sonnet_all = ctx["ref"], ctx["frame"], ctx["strata"], ctx["sonnet_all"]
    base = [i for i, r in model_all.items() if r["family"] != NJ]
    out = {}

    # 1. measured production
    whole = [str(r["id"]) for r in model_all_raw if r["evidence"] == MP]
    mp = [i for i in base if model_all[i]["evidence"] == MP]
    census = strata["exhaustive"]["measured_production"]
    holds = [i for i in census if ref[i]["evidence"] == MP]
    audited = [i for i in mp if i in ref]
    in_md_sample = [i for i in mp if i in set(strata["samples"]["measured_demo"])]
    md_pop_mp = [i for i in mp if i in frame and frame[i]["evidence"] == MD]
    w_md = wilson(sum(1 for i in in_md_sample if ref[i]["evidence"] == MP), len(in_md_sample)) if in_md_sample else None
    out["production"] = {
        "whole_corpus": len(whole), "base": len(mp),
        "by_sonnet_evidence": dict(Counter((sonnet_all[i]["evidence"] if i in sonnet_all else "unlabelled") for i in mp)),
        "sonnet_census": len(census), "census_holds": len(holds),
        "model_mp_on_census": sum(1 for i in census if model_all.get(i, {}).get("evidence") == MP),
        "model_mp_on_holds": sum(1 for i in holds if model_all.get(i, {}).get("evidence") == MP),
        "holds_model_labels": dict(Counter(model_all.get(i, {}).get("evidence", "unlabelled") for i in holds)),
        "census_not_holding_model_mp": sum(1 for i in census if i not in set(holds) and model_all.get(i, {}).get("evidence") == MP),
        "census_model_not_mp": {i: {"model": model_all.get(i, {}).get("evidence"), "audit": ref[i]["evidence"]}
                                for i in census if model_all.get(i, {}).get("evidence") != MP},
        "model_mp_audited": len(audited), "model_mp_audited_holds": sum(1 for i in audited if ref[i]["evidence"] == MP),
        "model_mp_outside_census": len([i for i in mp if i not in set(census)]),
        "model_mp_outside_census_audited": len([i for i in audited if i not in set(census)]),
        "model_mp_outside_census_audited_audit_labels": dict(Counter(ref[i]["evidence"] for i in audited if i not in set(census))),
        "model_mp_outside_census_audited_production_claim": sum(1 for i in audited if i not in set(census) and ref[i]["production_claim"]),
        "model_mp_in_md_sample": len(in_md_sample),
        "model_mp_in_md_sample_audit_mp": sum(1 for i in in_md_sample if ref[i]["evidence"] == MP),
        "model_mp_sonnet_md_population": len(md_pop_mp),
        "md_cell_scaled_hi": (w_md["hi"] * len(md_pop_mp)) if w_md else None,
        "model_mp_unaudited": len([i for i in mp if i not in ref]),
    }

    # 2. the three realtime families
    rt_m = [i for i in base if model_all[i]["family"] in RT]
    census = strata["exhaustive"]["realtime_family"]
    kept = [i for i in census if ref[i]["family"] in RT]
    dropped_ = [i for i in census if ref[i]["family"] not in RT]
    outside = [i for i in rt_m if i not in set(census)]
    outside_aud = [i for i in outside if i in ref]
    neg = strata["samples"]["not_realtime_family_not_games"]
    neg_miss = [i for i in neg if ref[i]["family"] in RT]
    out["realtime_families"] = {
        "whole_corpus": sum(1 for r in model_all_raw if r["family"] in RT), "base": len(rt_m),
        "by_sonnet_family": dict(Counter(("realtime family" if sonnet_all[i]["family"] in RT else sonnet_all[i]["family"]) for i in rt_m)),
        "census": len(census), "census_kept": len(kept), "census_dropped": len(dropped_),
        "kept_model_rt": sum(1 for i in kept if model_all.get(i, {}).get("family") in RT),
        "dropped_model_rt": sum(1 for i in dropped_ if model_all.get(i, {}).get("family") in RT),
        "dropped_audit_families": dict(Counter(ref[i]["family"] for i in dropped_)),
        "model_rt_outside_census": len(outside), "model_rt_outside_census_audited": len(outside_aud),
        "model_rt_outside_census_audit_rt": sum(1 for i in outside_aud if ref[i]["family"] in RT),
        "model_rt_outside_census_audit_families": dict(Counter(ref[i]["family"] for i in outside_aud)),
        "negative_sample": len(neg), "negative_sample_misses": len(neg_miss),
        "negative_misses_model_rt": sum(1 for i in neg_miss if model_all.get(i, {}).get("family") in RT),
        "negative_sample_model_rt": sum(1 for i in neg if model_all.get(i, {}).get("family") in RT),
        "negative_sample_model_rt_audit_rt": sum(1 for i in neg if model_all.get(i, {}).get("family") in RT and ref[i]["family"] in RT),
        "model_rt_audited": sum(1 for i in rt_m if i in ref), "model_rt_audited_audit_rt": sum(1 for i in rt_m if i in ref and ref[i]["family"] in RT),
        "model_rt_measured_production": sum(1 for i in rt_m if model_all[i]["evidence"] == MP),
        "model_rt_production_claim": sum(1 for i in rt_m if model_all[i]["production_claim"]),
    }

    # 3. not_a_jev_build
    nj_whole = [str(r["id"]) for r in model_all_raw if r["family"] == NJ]
    nj = [i for i, r in model_all.items() if r["family"] == NJ]
    nj_frame = [i for i in nj if i in frame]
    nj_aud = [i for i in nj_frame if i in ref]
    ref_nj = [i for i in ref if ref[i]["family"] == NJ]
    meta_s = strata["samples"]["other_or_meta"]
    ref_nj_meta = [i for i in meta_s if ref[i]["family"] == NJ]
    model_nj_meta = [i for i in meta_s if model_all.get(i, {}).get("family") == NJ]
    frame_meta = [i for i in frame if frame[i]["family"] == META]
    out["not_a_jev_build"] = {
        "whole_corpus": len(nj_whole), "deduped": len(nj), "both_nj": sum(1 for i in nj if sonnet_all.get(i, {}).get("family") == NJ),
        "in_frame": len(nj_frame), "in_frame_by_sonnet_family": dict(Counter(frame[i]["family"] for i in nj_frame)),
        "in_frame_audited": len(nj_aud), "in_frame_audited_audit_nj": sum(1 for i in nj_aud if ref[i]["family"] == NJ),
        "in_frame_audited_audit_families": dict(Counter(ref[i]["family"] for i in nj_aud if ref[i]["family"] != NJ)),
        "in_frame_audited_audit_noise": dict(Counter(ref[i].get("noise") for i in nj_aud if ref[i]["family"] == META)),
        "audit_nj": len(ref_nj), "audit_nj_model_nj": sum(1 for i in ref_nj if model_all.get(i, {}).get("family") == NJ),
        "audit_nj_model_families": dict(Counter(model_all.get(i, {}).get("family") for i in ref_nj if model_all.get(i, {}).get("family") != NJ)),
        "meta_sample": len(meta_s), "meta_sample_audit_nj": len(ref_nj_meta), "meta_sample_model_nj": len(model_nj_meta),
        "meta_sample_both_nj": len(set(ref_nj_meta) & set(model_nj_meta)),
        "meta_sample_model_nj_audit_labels": dict(Counter(ref[i]["family"] if ref[i]["family"] != META else f"meta/{ref[i].get('noise')}"
                                                          for i in model_nj_meta)),
        "meta_stratum": len(frame_meta), "meta_stratum_model_nj": sum(1 for i in frame_meta if model_all.get(i, {}).get("family") == NJ),
        "meta_stratum_audit_nj_scaled": len(ref_nj_meta) / len(meta_s) * len(frame_meta),
        "meta_stratum_audit_nj_wilson": wilson(len(ref_nj_meta), len(meta_s)),
    }
    return out


def frame_ep_nj(ctx: dict) -> dict:
    """The audit's estimate of not_a_jev_build posts in the frame, from the evidence strata (Sonnet labels for the remainder)."""
    frame, pops, ref, strata = ctx["frame"], ctx["pops"], ctx["ref"], ctx["strata"]
    q = lambda r: r["family"] == NJ
    census = sum(1 for i in pops["measured_production"] if q(ref[i]))
    est = lo = hi = float(census)
    parts = {}
    for h in (DNN, MD):
        smp = strata["samples"][h]
        k = sum(1 for i in smp if q(ref[i]))
        w = wilson(k, len(smp))
        est += w["p"] * len(pops[h])
        lo += w["lo"] * len(pops[h])
        hi += w["hi"] * len(pops[h])
        parts[h] = {"k": k, "n": len(smp), "pop": len(pops[h])}
    return {"est": est, "lo": lo, "hi": hi, "census": census, "parts": parts,
            "remainder_n": sum(1 for i in frame if frame[i]["evidence"] in REMAINDER),
            "note": "proposal and commentary posts (not sampled) count as zero: the frame is Sonnet's base, where none is not_a_jev_build"}


# ---------------------------------------------------------------- side by side


def side_by_side(son: dict, opu: dict, opf: dict, ctx: dict) -> list[dict]:
    rows = []
    sao = {  # Sonnet's audit-only values, keyed like the rows below
        **{f"baseline_{c}": son["claim1"]["corrected"][c]["audit_only"] for c in ("none", "frontier_llm", "small_llm", "replacement")},
        "rt_families": son["claim4"]["audit_only"], "live_loop_nongame": son["claim5"]["audit_only_nongame"],
        "live_loop_all": son["claim5"]["audit_only_any"], "sub300_set": son["claim6"]["audit_only_set"],
        "sub300_games": {"est_pct": 100 * son["claim6"]["audit_only_games_share"]}, "meta_still": son["claim7"]["audit_only"],
        "meta_vague": {"est_pct": son["claim7"]["audit_only_subtypes"]["vague"]["est_pct"]},
        "meta_meme": {"est_pct": son["claim7"]["audit_only_subtypes"]["meme"]["est_pct"]},
        "meta_hot": {"est_pct": son["claim7"]["audit_only_subtypes"]["hot"]["est_pct"]},
    }

    def add(claim, key, label, unit, s_model, s, o_model, o, of=None, ao=None, note=""):
        """s, o, of, ao: dicts with est_pct, lo_pct, hi_pct (or value/lo/hi for rates)."""
        def g(d, k):
            return None if d is None else d.get(k)
        row = {"claim": claim, "key": key, "label": label, "unit": unit,
               "sonnet_model": s_model, "sonnet_value": g(s, "est_pct"), "sonnet_lo": g(s, "lo_pct"), "sonnet_hi": g(s, "hi_pct"),
               "opus_model": o_model, "opus_value": g(o, "est_pct"), "opus_lo": g(o, "lo_pct"), "opus_hi": g(o, "hi_pct"),
               "opus_plug": g(o, "plug"),
               "audit_only_value": g(ao, "est_pct"), "audit_only_lo": g(ao, "lo_pct"), "audit_only_hi": g(ao, "hi_pct"),
               "sonnet_audit_only_value": g(sao.get(key), "est_pct"), "sonnet_audit_only_lo": g(sao.get(key), "lo_pct"),
               "sonnet_audit_only_hi": g(sao.get(key), "hi_pct"),
               "opus_frame_value": g(of, "est_pct"), "opus_frame_lo": g(of, "lo_pct"), "opus_frame_hi": g(of, "hi_pct"),
               "note": note}

        def inside(m, lo, hi):
            if m is None or lo is None or hi is None:
                return None
            return int(lo - 1e-9 <= m <= hi + 1e-9)
        row["sonnet_inside"] = inside(s_model, row["sonnet_lo"], row["sonnet_hi"])
        row["opus_inside"] = inside(o_model, row["opus_lo"], row["opus_hi"])
        row["sonnet_inside_audit_only"] = inside(s_model, row["sonnet_audit_only_lo"], row["sonnet_audit_only_hi"])
        row["opus_inside_audit_only"] = inside(o_model, row["audit_only_lo"], row["audit_only_hi"])
        rows.append(row)

    S1, O1, F1 = son["claim1"]["corrected"], opu["claim1"]["corrected"], opf["claim1"]["corrected"]
    for cat, label in (("none", "Compared with nothing"), ("frontier_llm", "Compared with a frontier LLM"),
                       ("small_llm", "Compared with a small LLM"), ("replacement", "Compared with classic ML, rules or a vendor API")):
        add(1, f"baseline_{cat}", label, "% of posts", S1[cat]["model_pct"], S1[cat], O1[cat]["model_pct"], O1[cat], F1[cat], O1[cat]["audit_only"],
            "plug-in: the frontier and small-LLM strata (not sampled) at the model's labels")
    add(2, "production_strict", "Measured production that holds on the audit's reading", "% of posts", son["claim2"]["model_pct"], son["claim2"],
        opu["claim2"]["model_pct"], opu["claim2"], opf["claim2"], None, "census of Sonnet's 15 plus misses in two samples of 200")
    L, LO, LF = son["claim3"]["ladder"], opu["claim3"]["ladder"], opf["claim3"]["ladder"]
    for key, label in (("ladder_no_measurement", "Ladder: no measurement"), ("ladder_measured_demo", "Ladder: measured demo"),
                       ("ladder_measured_production", "Ladder: measured production"),
                       ("ladder_demo_no_numbers", "Demos with no numbers (report rule: no claim chip, not meta)"),
                       ("ladder_claim_no_number", "A cost, speed or accuracy claim with no number (report rule: claim chip)")):
        add(3, key, label, "% of posts", L[key]["model_pct"], L[key], LO[key]["model_pct"], LO[key], LF[key], None,
            "evidence strata; proposal and commentary posts at the model's labels")
    B, BO, BF = son["claim3"]["buckets"], opu["claim3"]["buckets"], opf["claim3"]["buckets"]
    add(3, "review_demo_bucket", "Demos with no numbers (review rule, framing field)", "% of posts", B["demo"]["model_pct"], B["demo"],
        BO["demo"]["model_pct"], BO["demo"], BF["demo"], None, "the review's bucket rule")
    P, PO, PF = son["claim3"]["prose_buckets"], opu["claim3"]["prose_buckets"], opf["claim3"]["prose_buckets"]
    add(3, "review_hype_no_number", "A cost, speed or accuracy lead with no number (review rule, framing field)", "% of posts",
        P["hype_cost_speed_accuracy"]["model_pct"], P["hype_cost_speed_accuracy"], PO["hype_cost_speed_accuracy"]["model_pct"],
        PO["hype_cost_speed_accuracy"], PF["hype_cost_speed_accuracy"], None, "proposal and commentary posts left out, as in review/estimate.py")
    add(3, "cost_only_as_described", "Measured, and a batch or an incumbent already did the job", "% of posts",
        P["cost_only_as_described"]["model_pct"], P["cost_only_as_described"], PO["cost_only_as_described"]["model_pct"],
        PO["cost_only_as_described"], PF["cost_only_as_described"], None, "proposal and commentary posts left out, as in review/estimate.py")
    MC, MCO, MCF = son["claim3"]["material_combined"], opu["claim3"]["material_combined"], opf["claim3"]["material_combined"]
    add(3, "candidates_combined", "Posts that meet the material test, misses included", "% of posts", MC["model_pct"], MC, MCO["model_pct"], MCO, MCF,
        None, "census of Sonnet's 91 plus misses in two samples")
    C4, O4, F4 = son["claim4"], opu["claim4"], opf["claim4"]
    add(4, "rt_families", "Voice, live chat or collaboration", "% of posts", C4["model_pct"], C4, O4["model_pct"], O4, F4, O4["audit_only"],
        "plug-in: games (outside the negative sample) at the model's labels")
    C5, O5, F5 = son["claim5"], opu["claim5"], opf["claim5"]
    add(5, "live_loop_nongame", "A live loop outside games", "% of posts", C5["model_nongame_pct"], C5["nongame"], O5["model_nongame_pct"],
        O5["nongame"], F5["nongame"], O5["audit_only_nongame"], "plug-in: flagged games (not sampled) at the model's labels")
    add(5, "live_loop_all", "A live loop, games included (the review's rough construction)", "% of posts", C5["model_pct"],
        {"est_pct": C5["live_loop_all"]["est_pct"]}, O5["model_pct"], {"est_pct": O5["live_loop_all"]["est_pct"]},
        {"est_pct": F5["live_loop_all"]["est_pct"]}, O5["audit_only_any"], "audit-only column: the evidence strata, with interval")
    C6, O6, F6 = son["claim6"], opu["claim6"], opf["claim6"]
    add(6, "sub300_set", "Posts that need a decision in under 300 ms", "% of posts", C6["model_fast_pct"], C6["set"], O6["model_fast_pct"],
        O6["set"], F6["set"], O6["audit_only_set"], "plug-in: posts outside Sonnet's under-300 ms stratum at the model's labels")

    def cond(c):
        return {"est_pct": c["conditional_pct"], "lo_pct": c["conditional_lo_pct"], "hi_pct": c["conditional_hi_pct"]}
    add(6, "sub300_games", "Share of the under-300 ms posts that are games", "% of that set", 100 * C6["model_games_share"], cond(C6),
        100 * O6["model_games_share"], cond(O6), cond(F6),
        {"est_pct": 100 * O6["audit_only_games_share"]} if O6["audit_only_games_share"] is not None else None,
        "from the tier sample only; audit-only column adds misses, point estimate")
    C7, O7, F7 = son["claim7"], opu["claim7"], opf["claim7"]
    add(7, "meta_still", "Posts that are meta (never say what Jev decides, benchmark, wrapper, commentary)", "% of posts", C7["model_meta_pct"], C7,
        O7["model_meta_pct"], O7, F7, O7["audit_only"], "plug-in: posts outside Sonnet's meta stratum at the model's labels")
    add(7, "meta_vague", "Unrelated or unclear, a benchmark, or a wrapper", "% of posts", 100 * C7["model_vague_n"] / son["use_case_base"],
        {"est_pct": C7["vague_est_pct"]}, 100 * O7["model_vague_n"] / opu["use_case_base"], {"est_pct": O7["vague_est_pct"]},
        {"est_pct": F7["vague_est_pct"]}, {"est_pct": O7["audit_only_subtypes"]["vague"]["est_pct"]},
        "sample only; the model's count uses the noise sub-types, which exist only for Sonnet's noise posts")
    add(7, "meta_meme", "Memes", "% of posts", 100 * C7["model_meme_n"] / son["use_case_base"], {"est_pct": C7["meme_est_pct"]},
        100 * O7["model_meme_n"] / opu["use_case_base"], {"est_pct": O7["meme_est_pct"]}, {"est_pct": F7["meme_est_pct"]},
        {"est_pct": O7["audit_only_subtypes"]["meme"]["est_pct"]}, "sample only")
    add(7, "meta_hot", "Hot takes", "% of posts", 100 * C7["model_hot_n"] / son["use_case_base"], {"est_pct": C7["hot_est_pct"]},
        100 * O7["model_hot_n"] / opu["use_case_base"], {"est_pct": O7["hot_est_pct"]}, {"est_pct": F7["hot_est_pct"]},
        {"est_pct": O7["audit_only_subtypes"]["hot"]["est_pct"]}, "sample only")
    for key, label, f in (("attention_top1_views", "Share of views on the top 1% of posts", "top1_share"),
                          ("attention_top1_views_excl_suspect", "The same without the low-like-rate posts", "top1_excl_suspect"),
                          ("attention_top1_likes", "Share of likes on the top 1% of posts", "top1_likes_share")):
        add(8, key, label, "% (census)", None, {"est_pct": 100 * son["claim8"][f]}, None, {"est_pct": 100 * opu["claim8"][f]}, None, None,
            "a census; only the base changes")
    add(9, "jev_agree", "Jev picks the model's family", "% of posts (census)", None, {"est_pct": son["claim9"]["agree_pct"]}, None,
        {"est_pct": opu["claim9"]["agree_pct"]}, None, None, "not_a_jev_build counted as other_or_meta")
    add(9, "jev_agree_p99", "The same at a stated probability of 0.99 or more", "% (census)", None, {"est_pct": son["claim9"]["p_ge_099_agree_model_pct"]},
        None, {"est_pct": opu["claim9"]["p_ge_099_agree_model_pct"]}, None, None, "")
    add(9, "jev_audit_p99", "Jev matches the audit's family at 0.99 or more", "% of audited", None, {"est_pct": son["claim9"]["p_ge_099_match_audit_pct"]},
        None, {"est_pct": opu["claim9"]["p_ge_099_match_audit_pct"]}, None, None, "does not involve the model")
    add(10, "chips_cost_median", "Median cost multiple on the claim chips", "×", None, {"est_pct": son["claim10"]["cost_median"]}, None,
        {"est_pct": opu["claim10"]["cost_median"]}, None, None, "a census of the chips; only the base changes")
    add(10, "chips_speed_median", "Median speed multiple on the claim chips", "×", None, {"est_pct": son["claim10"]["speed_median"]}, None,
        {"est_pct": opu["claim10"]["speed_median"]}, None, None, "a census of the chips; only the base changes")
    return rows


# ---------------------------------------------------------------- write-up

SHORT_LABEL = {"sub300_set": "the under-300 ms set", "meta_still": "meta posts"}
REVIEW_VERDICT = {1: "Fails", 2: "Holds with correction", 3: "Fails", 4: "Holds with correction", 5: "Holds", 6: "Holds",
                  7: "Fails", 8: "Holds with correction", 9: "Holds", 10: "Holds"}
TOPIC = {1: "Comparison baselines", 2: "Production with numbers", 3: "The measurement ladder (was the bucket scheme)",
         4: "Voice, live chat and collaboration", 5: "A live loop", 6: "Decisions under 300 ms", 7: "Meta posts",
         8: "Attention", 9: "Jev as a classifier", 10: "The claimed multiples"}
PUBLISHED = {1: "81.5% none, 11.9% frontier, 3.0% small, 3.6% replacement", 2: "at most 1.6%; 0.9% on a re-read; 0.3% strict",
             3: "38% demos with no numbers; 12% hype; 23% cost-only; 1.6% materially different",
             4: "2.8% of posts, none in production", 5: "about a fifth; 5 to 10 percent outside games",
             6: "about 91% of sub-300 ms posts are games", 7: "a fifth meta, benchmark or wrapper; memes and hot takes about 1% each",
             8: "half of all views on 1% of posts", 9: "77% agreement; 27 of 28 at 0.99 or more", 10: "median 28x cheaper, 6x faster"}


def _p(x, d=1):
    return "n/a" if x is None else f"{x:.{d}f}%"


def _r(lo, hi, d=1):
    return "n/a" if lo is None or hi is None else f"{lo:.{d}f}–{hi:.{d}f}%"


def _e(rec, d=1):
    """'20.9% (19.4–22.2%)' from a record with est_pct, lo_pct, hi_pct."""
    if rec is None or rec.get("est_pct") is None:
        return "n/a"
    if rec.get("lo_pct") is None:
        return _p(rec["est_pct"], d)
    return f"{_p(rec['est_pct'], d)} ({_r(rec['lo_pct'], rec['hi_pct'], d)})"


def _c(x):
    return "n/a" if x is None else f"{round(x):,}"


def _f(x, d=1):
    return "n/a" if x is None else f"{100 * x:.{d}f}%"


def _row(res, key):
    return next(r for r in res["side_by_side"] if r["key"] == key)


def claim_rows(res: dict) -> list[dict]:
    son, opu = res["sonnet"], res["model"]
    R = {r["key"]: r for r in res["side_by_side"]}

    def both(key, d=1):
        r = R[key]
        return (f"{_p(r['sonnet_model'], d)}", f"{_p(r['sonnet_value'], d)} ({_r(r['sonnet_lo'], r['sonnet_hi'], d)})",
                f"{_p(r['opus_model'], d)}", f"{_p(r['opus_value'], d)} ({_r(r['opus_lo'], r['opus_hi'], d)})",
                f"{_p(r['audit_only_value'], d)} ({_r(r['audit_only_lo'], r['audit_only_hi'], d)})" if r["audit_only_lo"] is not None else "")
    rows = []
    # 1
    keys = ["baseline_none", "baseline_frontier_llm", "baseline_small_llm", "baseline_replacement"]
    parts = [both(k) for k in keys]
    o_in = [R[k]["opus_inside"] for k in keys]
    s_in = [R[k]["sonnet_inside"] for k in keys]
    v1 = "Holds" if all(o_in) else ("Holds with correction" if sum(o_in) >= 2 else "Fails")
    rows.append({"claim": 1, "topic": TOPIC[1], "published": PUBLISHED[1],
                 "sonnet_labels": "; ".join(p[0] for p in parts), "sonnet_audit": "; ".join(p[1] for p in parts),
                 "opus_labels": "; ".join(p[2] for p in parts), "opus_audit": "; ".join(p[3] for p in parts),
                 "audit_only": "; ".join(p[4] for p in parts), "review_verdict": REVIEW_VERDICT[1], "opus_verdict": v1,
                 "change": (f"more supported: {sum(o_in)} of 4 Opus shares inside their interval, {sum(s_in)} of 4 for Sonnet; "
                            f"on the audit-only estimate {sum(R[k]['opus_inside_audit_only'] for k in keys)} of 4 and "
                            f"{sum(R[k]['sonnet_inside_audit_only'] for k in keys)} of 4")})
    # 2
    c2s, c2o = son["claim2"], opu["claim2"]
    r2 = R["production_strict"]
    ratio = c2o["model_n"] / c2o["est_count"] if c2o["est_count"] else None
    rows.append({"claim": 2, "topic": TOPIC[2], "published": PUBLISHED[2],
                 "sonnet_labels": f"{c2s['model_n']} posts, {_p(c2s['model_pct'], 2)}", "sonnet_audit": _e(c2s, 2),
                 "opus_labels": f"{c2o['model_n']} posts, {_p(c2o['model_pct'], 2)}", "opus_audit": _e(c2o, 2), "audit_only": "",
                 "review_verdict": REVIEW_VERDICT[2],
                 "opus_verdict": "Holds with correction" if r2["opus_inside"] else "Fails",
                 "change": (f"less supported: inside only because the interval's top is the bound on zero misses; Opus's count is "
                            f"{ratio:.1f}x the audit's point estimate of {c2o['hold_on_reread']}, against {c2s['model_n'] / c2s['est_count']:.1f}x "
                            f"for Sonnet" if ratio else "")})
    # 3
    lad = ["ladder_no_measurement", "ladder_measured_demo", "ladder_demo_no_numbers", "ladder_claim_no_number",
           "review_demo_bucket", "review_hype_no_number", "cost_only_as_described", "candidates_combined"]
    o_in = [R[k]["opus_inside"] for k in lad]
    s_in = [R[k]["sonnet_inside"] for k in lad]
    names = ["no measurement", "measured demo", "demos, no numbers (chip rule)", "claim, no number (chip rule)",
             "demo bucket (framing rule)", "hype, no number (framing rule)", "cost-only as described", "material test"]
    plain = ["the no-measurement share", "the measured-demo share", "the chip-rule demo share", "the chip-rule claim share",
             "the framing-rule demo bucket", "the framing-rule hype share", "the cost-only share", "the material-test share"]
    rows.append({"claim": 3, "topic": TOPIC[3], "published": PUBLISHED[3],
                 "sonnet_labels": "; ".join(f"{n} {_p(R[k]['sonnet_model'])}" for n, k in zip(names, lad)),
                 "sonnet_audit": "; ".join(f"{n} {_p(R[k]['sonnet_value'])} ({_r(R[k]['sonnet_lo'], R[k]['sonnet_hi'])})" for n, k in zip(names, lad)),
                 "opus_labels": "; ".join(f"{n} {_p(R[k]['opus_model'])}" for n, k in zip(names, lad)),
                 "opus_audit": "; ".join(f"{n} {_p(R[k]['opus_value'])} ({_r(R[k]['opus_lo'], R[k]['opus_hi'])})" for n, k in zip(names, lad)),
                 "audit_only": "", "review_verdict": REVIEW_VERDICT[3] + " (the bucket scheme, since withdrawn)",
                 "opus_verdict": "The ladder shares hold" if all(o_in) else "Some ladder shares fail",
                 "change": (("slightly more supported" if sum(o_in) > sum(s_in) else "about the same")
                            + f": {sum(o_in)} of {len(lad)} Opus figures inside, {sum(s_in)} of {len(lad)} for Sonnet (Sonnet's misses: "
                            + " and ".join(n for n, k in zip(plain, lad) if not R[k]["sonnet_inside"]) + ")")})
    # 4
    c4s, c4o = son["claim4"], opu["claim4"]
    b4 = both("rt_families")
    rows.append({"claim": 4, "topic": TOPIC[4], "published": PUBLISHED[4],
                 "sonnet_labels": f"{b4[0]} ({c4s['model_n']} posts)", "sonnet_audit": b4[1],
                 "opus_labels": f"{b4[2]} ({c4o['model_n']} posts; {c4o['model_measured_production']} measured production)",
                 "opus_audit": f"{b4[3]}; {c4o['census_measured_production'] + c4o['plugin_measured_production']} in measured production",
                 "audit_only": b4[4], "review_verdict": REVIEW_VERDICT[4],
                 "opus_verdict": "Holds" if R["rt_families"]["opus_inside"] else "Fails",
                 "change": "more supported: Opus's share is near the centre of the interval; Sonnet's was at its bottom edge"})
    # 5
    r5, ra = R["live_loop_nongame"], R["live_loop_all"]
    rows.append({"claim": 5, "topic": TOPIC[5], "published": PUBLISHED[5],
                 "sonnet_labels": f"outside games {_p(r5['sonnet_model'])}; all {_p(ra['sonnet_model'])}",
                 "sonnet_audit": f"outside games {_p(r5['sonnet_value'])} ({_r(r5['sonnet_lo'], r5['sonnet_hi'])}); all {_p(ra['sonnet_value'])}",
                 "opus_labels": f"outside games {_p(r5['opus_model'])}; all {_p(ra['opus_model'])}",
                 "opus_audit": f"outside games {_p(r5['opus_value'])} ({_r(r5['opus_lo'], r5['opus_hi'])}); all {_p(ra['opus_value'])}",
                 "audit_only": f"outside games {_p(r5['audit_only_value'])} ({_r(r5['audit_only_lo'], r5['audit_only_hi'])}); all "
                               f"{_p(ra['audit_only_value'])} ({_r(ra['audit_only_lo'], ra['audit_only_hi'])})",
                 "review_verdict": REVIEW_VERDICT[5],
                 "opus_verdict": "Holds" if r5["opus_inside"] else "Fails",
                 "change": ("more supported: Opus's non-game share is inside the interval; Sonnet's was outside (on the audit-only "
                            "estimate both are inside, and Opus's all-posts share is inside while Sonnet's is not)"
                            if r5["opus_inside"] and not r5["sonnet_inside"] else "about the same")})
    # 6
    r6, g6 = R["sub300_set"], R["sub300_games"]
    rows.append({"claim": 6, "topic": TOPIC[6], "published": PUBLISHED[6],
                 "sonnet_labels": f"set {_p(r6['sonnet_model'])}; games {_p(g6['sonnet_model'])}",
                 "sonnet_audit": f"set {_p(r6['sonnet_value'])} ({_r(r6['sonnet_lo'], r6['sonnet_hi'])}); games {_p(g6['sonnet_value'])} ({_r(g6['sonnet_lo'], g6['sonnet_hi'])})",
                 "opus_labels": f"set {_p(r6['opus_model'])}; games {_p(g6['opus_model'])}",
                 "opus_audit": f"set {_p(r6['opus_value'])} ({_r(r6['opus_lo'], r6['opus_hi'])}); games {_p(g6['opus_value'])} ({_r(g6['opus_lo'], g6['opus_hi'])})",
                 "audit_only": f"set {_p(r6['audit_only_value'])} ({_r(r6['audit_only_lo'], r6['audit_only_hi'])}); games {_p(g6['audit_only_value'])}",
                 "review_verdict": REVIEW_VERDICT[6],
                 "opus_verdict": ("Holds" if g6["opus_inside"] else "Fails") + ("" if r6["opus_inside"] else "; the set's size does not"),
                 "change": (f"about the same on the claim: the games share holds under both (Sonnet's {_p(g6['sonnet_model'])} equals the audit's "
                            f"point, Opus's {_p(g6['opus_model'])} is inside). On the set's size Opus's {_p(r6['opus_model'])} is nearer the audit "
                            f"than Sonnet's {_p(r6['sonnet_model'])}, and still outside")})
    # 7
    r7 = R["meta_still"]
    mm, mh = R["meta_meme"], R["meta_hot"]
    rows.append({"claim": 7, "topic": TOPIC[7], "published": PUBLISHED[7],
                 "sonnet_labels": f"meta {_p(r7['sonnet_model'])}; memes {_p(mm['sonnet_model'], 2)}; hot takes {_p(mh['sonnet_model'], 2)}",
                 "sonnet_audit": f"meta {_p(r7['sonnet_value'])} ({_r(r7['sonnet_lo'], r7['sonnet_hi'])}); memes {_p(mm['sonnet_value'], 2)}; hot takes {_p(mh['sonnet_value'], 2)}",
                 "opus_labels": f"meta {_p(r7['opus_model'])}; memes {_p(mm['opus_model'], 2)}; hot takes {_p(mh['opus_model'], 2)}",
                 "opus_audit": f"meta {_p(r7['opus_value'])} ({_r(r7['opus_lo'], r7['opus_hi'])}); memes {_p(mm['opus_value'], 2)}; hot takes {_p(mh['opus_value'], 2)}",
                 "audit_only": f"meta {_p(r7['audit_only_value'])} ({_r(r7['audit_only_lo'], r7['audit_only_hi'])}); Sonnet base "
                               f"{_p(r7['sonnet_audit_only_value'])} ({_r(r7['sonnet_audit_only_lo'], r7['sonnet_audit_only_hi'])})",
                 "review_verdict": REVIEW_VERDICT[7],
                 "opus_verdict": ("Holds with correction" if r7["opus_inside_audit_only"] else "Fails")
                                 + ": the fifth holds on the audit-only estimate; memes and hot takes are under half a percent each",
                 "change": ("more supported: Opus's share is inside the audit-only interval and just above the same-logic one; Sonnet's is "
                            "far outside the same-logic interval and inside the audit-only one")})
    # 8-10
    c8s, c8o = son["claim8"], opu["claim8"]
    rows.append({"claim": 8, "topic": TOPIC[8], "published": PUBLISHED[8],
                 "sonnet_labels": "", "sonnet_audit": f"top 1% ({c8s['top1_cards']} posts) hold {_f(c8s['top1_share'])} of views; {_f(c8s['top1_excl_suspect'])} without the suspect posts",
                 "opus_labels": "", "opus_audit": f"top 1% ({c8o['top1_cards']} posts) hold {_f(c8o['top1_share'])} of views; {_f(c8o['top1_excl_suspect'])} without the suspect posts",
                 "audit_only": "", "review_verdict": REVIEW_VERDICT[8], "opus_verdict": REVIEW_VERDICT[8],
                 "change": f"unchanged: a census, only the base moves (shares move by {max(abs(c8o[k] - c8s[k]) for k in ('top1_share', 'top1_excl_suspect', 'top1_likes_share')) * 100:.1f} point at most)"})
    c9s, c9o = son["claim9"], opu["claim9"]
    rows.append({"claim": 9, "topic": TOPIC[9], "published": PUBLISHED[9],
                 "sonnet_labels": "", "sonnet_audit": f"Jev = Sonnet {_p(c9s['agree_pct'])}; {_p(c9s['p_ge_099_agree_model_pct'])} at 0.99",
                 "opus_labels": "", "opus_audit": f"Jev = Opus {_p(c9o['agree_pct'])}; {_p(c9o['p_ge_099_agree_model_pct'])} at 0.99",
                 "audit_only": f"Jev = audit at 0.99: {c9o['p_ge_099_matches_audit_family']} of {c9o['p_ge_099_in_audit']}",
                 "review_verdict": REVIEW_VERDICT[9], "opus_verdict": "Holds", "change": "unchanged"})
    c10s, c10o = son["claim10"], opu["claim10"]
    rows.append({"claim": 10, "topic": TOPIC[10], "published": PUBLISHED[10],
                 "sonnet_labels": "", "sonnet_audit": f"{c10s['cost_median']:g}x cheaper ({c10s['cost_chips']} chips), {c10s['speed_median']:g}x faster ({c10s['speed_chips']} chips)",
                 "opus_labels": "", "opus_audit": f"{c10o['cost_median']:g}x cheaper ({c10o['cost_chips']} chips), {c10o['speed_median']:g}x faster ({c10o['speed_chips']} chips)",
                 "audit_only": "", "review_verdict": REVIEW_VERDICT[10], "opus_verdict": "Holds",
                 "change": "unchanged medians" + "".join(
                     f"; without the 1x chips the {k} median moves from {c10s[k + '_median_without_1x']:g}x to {c10o[k + '_median_without_1x']:g}x"
                     for k in ("cost", "speed") if c10s[k + "_median_without_1x"] != c10o[k + "_median_without_1x"])})
    return rows


def render_md(res: dict, claims: list[dict], tag: str) -> str:
    m, son, opu, opf = res["meta"], res["sonnet"], res["model"], res["model_frame_base"]
    A, As = res["agreement"]["model"], res["agreement"]["sonnet"]
    rc, san = res["recount"]["model"], res["sanity"]
    R = {r["key"]: r for r in res["side_by_side"]}
    name, short = m["model_name"], m["model_name"].replace("Claude ", "").split()[0]
    groups = {g["group"]: g for g in rc["groups"]}
    sgroups = {g["group"]: g for g in res["recount"]["sonnet"]["groups"]}
    reg = opu["regions"]
    L = []
    w = L.append

    def gline(key):
        g = groups[key]
        return (f"{g['audited_n']:,} audited, the audit agrees on {g['audit_agrees']:,} ({_f(g['precision'])}; weighted "
                f"{_f(g['weighted_precision'])})")

    inside_o = sum(1 for r in res["side_by_side"] if r["opus_inside"] == 1)
    inside_s = sum(1 for r in res["side_by_side"] if r["sonnet_inside"] == 1)
    tested = sum(1 for r in res["side_by_side"] if r["opus_inside"] is not None)
    outside_o = [r for r in res["side_by_side"] if r["opus_inside"] == 0]
    fa, fs = A["fields"], As["fields"]
    c1o, c1s = opu["claim1"]["corrected"], son["claim1"]["corrected"]
    c2o = opu["claim2"]
    c7o, c7s = opu["claim7"], son["claim7"]
    sp, sr, sn = san["production"], san["realtime_families"], san["not_a_jev_build"]

    w(f"# Audit estimates with {name} as the model under test\n")
    w(f"Written by `review/estimate-{tag}.py` (the script also writes every number to `review/work/estimate-{tag}.json` and the tables to "
      f"`review/data/audit-{tag}-*.csv`). Reference labels: Grok's {m['labelled']:,} blind labels (`{m['reference']}`), with the 15 "
      f"production re-reads. Model under test: {name} (`{m['model_file']}`, rubric v2). Comparison: {m['audited_name']} "
      f"(`{m['audited_file']}`), the labels the audit sampled from. Estimators: `review/estimate.py`'s, unchanged.\n")

    w("## Bottom line\n")
    w(f"- {short} agrees with the audit more often than Sonnet on every field: family {_f(fa['family']['rate'])} against "
      f"{_f(fs['family']['rate'])} (kappa {fa['family']['kappa']:.2f} against {fs['family']['kappa']:.2f}), tier {_f(fa['tier']['rate'])} against "
      f"{_f(fs['tier']['rate'])}, evidence {_f(fa['evidence']['rate'])} against {_f(fs['evidence']['rate'])}, baseline {_f(fa['baseline']['rate'])} "
      f"against {_f(fs['baseline']['rate'])}, realtime flag {_f(fa['realtime_infra']['rate'])} against {_f(fs['realtime_infra']['rate'])}.")
    w(f"- Of the {tested} figures in the side-by-side table that have an interval, {inside_o} {short} figures are inside the audit's 95% "
      f"interval, against {inside_s} for Sonnet. The {short} figures outside: "
      + "; ".join(f"{SHORT_LABEL.get(r['key'], r['label'])} ({short} {_p(r['opus_model'])}, audit {_p(r['opus_value'])}, {_r(r['opus_lo'], r['opus_hi'])}"
                  + (f"; audit-only {_r(r['audit_only_lo'], r['audit_only_hi'])}" if r["audit_only_lo"] is not None else "") + ")"
                  for r in outside_o) + ".")
    w(f"- Do not publish {short}'s measured-production count as it stands. {short} labels {c2o['model_n']} posts; the audit's census and samples give "
      f"{round(c2o['est_count'])} posts, {_e(c2o, 2)}, and the audit agrees with {sp['model_mp_audited_holds']} of the {sp['model_mp_audited']} "
      f"{short} production posts it read.")
    w(f"- Two of the review's estimators take the posts outside their sampled strata as correctly labelled. The audit's own random samples of "
      f"demos say they are not. Estimated from those samples instead, Sonnet's base has {_p(R['baseline_none']['sonnet_audit_only_value'])} "
      f"({_r(R['baseline_none']['sonnet_audit_only_lo'], R['baseline_none']['sonnet_audit_only_hi'])}) of posts with no comparison and "
      f"{_p(R['meta_still']['sonnet_audit_only_value'])} ({_r(R['meta_still']['sonnet_audit_only_lo'], R['meta_still']['sonnet_audit_only_hi'])}) "
      f"meta posts. Sonnet's own {_p(R['baseline_none']['sonnet_model'])} and {_p(R['meta_still']['sonnet_model'])} are inside those intervals "
      f"(so are its three other baseline shares), so the review's \"Fails\" on claims 1 and 7 rests on that assumption. The \"audit-only\" "
      f"column below gives these estimates wherever a claim has such a region.\n")

    w("## How the estimates are formed\n")
    w(f"1. **Strata and reference.** The strata stay as `review/sample.py` drew them from Sonnet's labels (seed 20260924). The script checks "
      f"that Sonnet's labels still give the same stratum sizes and census lists, and stops if they do not. Grok's labels are the reference. "
      f"{short}'s labels on the same posts are the model under test.")
    w("2. **Estimators.** `wilson()`, `corrected()` and `scale_count()` are imported from `review/estimate.py`. Census strata are counted "
      "exactly, each sample is scaled to its stratum with a 95% Wilson interval, and where strata are added the bounds are summed (wider than "
      "a joint interval). Run with Sonnet as the model, the script reproduces `review/work/estimate.json` to 1e-9 on every claim and on the "
      "agreement table. It checks this on every run.")
    w(f"3. **Base.** Shares are of {short}'s own use-case base, {m['model_base']:,} posts: {m['model_rows']:,} labelled, "
      f"{m['model_rows'] - m['model_rows_deduped']} duplicates merged, {sn['deduped']} not_a_jev_build left out. {len(m['refused'])} post was refused by "
      f"{short}'s safety filter and has no label. The audit's frame is Sonnet's base ({m['frame']:,}). {opu['frame_posts_outside_base']} frame posts are "
      f"outside {short}'s base ({sn['in_frame']} {short} calls not_a_jev_build, and the refused post). Each stratum is cut to {short}'s base. The "
      f"audited posts left in a sampled stratum are still a simple random sample of what is left of it (domain estimation), so the scaling holds.")
    w(f"4. **Plug-ins.** Where `review/estimate.py` takes a region the audit did not sample from the model's own labels, this run takes "
      f"{short}'s labels. The regions, in {short}'s base: the frontier and small-LLM strata ({reg['frontier_small']:,} posts, claim 1); the proposal "
      f"and commentary posts ({reg['remainder']}, claims 2 and 3); games, outside the realtime-family negative sample ({reg['games']:,}, claim 4); "
      f"flagged games ({reg['rt_true_games']:,}, claim 5); posts outside Sonnet's under-300 ms stratum ({reg['not_fast']:,}, claim 6) and outside "
      f"its meta stratum ({reg['not_meta']:,}, claim 7). With Sonnet as the model these regions add nothing, or exactly what the review assumed. "
      f"The {opu['model_only_posts']} posts in {short}'s base that Sonnet called not_a_jev_build were never in the frame; they enter at {short}'s "
      f"labels too. The column \"on {short}'s word\" gives the size of these terms.")
    w(f"5. **Audit-only variant.** The evidence strata cover every frame post except the {son['regions']['remainder']} proposal and commentary "
      f"posts: the census of Sonnet's 15 measured-production posts and random samples of 200 demos with no numbers and 200 measured demos. Cut "
      f"to a plug-in region, the samples that fall inside it are a random sample of that part of the region. \"Audit-only\" replaces each "
      f"plug-in region by that estimate. It takes neither model's word except on the proposal, commentary and model-only posts. Its intervals "
      f"are wide where few sampled posts fall in the region.")
    w(f"6. **Not a random sample.** The {m['labelled']:,} audited posts over-represent the census strata (read in full) and are sampled at 3% to "
      f"65% elsewhere, on Sonnet's labels. Raw agreement on them is not a population rate. The \"weighted\" columns reweight each audited post "
      f"by 1/(its inclusion probability) under the design (1 in a census stratum, else 1 − ∏(1 − n/N) over the sampled strata that hold it, "
      f"treating the eight samples as independent draws). The weights sum to {m['weight_total']:,.0f}, against {m['frame']:,} frame posts.")
    w(f"7. **`scripts/audit.py`.** Its `reestimate()` (checked against the 24 Sep 09:23 version) gives shares of the frame, not of {short}'s base. On claims 1 to 5 "
      f"its numbers equal this script's frame-base variant (`model_frame_base` in the JSON) to 1e-9. It differs on claims 6 and 7, where it "
      f"uses the samples only, and on the games' live-loop rate in claim 5, where it counts Sonnet's games in the under-300 ms sample. \"Samples "
      f"only\" keeps Sonnet's assumption that no post outside Sonnet's meta or under-300 ms stratum belongs in it. With {short}'s labels it prints "
      f"{_p(opf['claim7']['samples_only']['est_pct'])} meta posts next to {short}'s {_p(R['meta_still']['opus_model'])}.\n")

    w(f"## Agreement with the audit on the {m['labelled']:,} audited posts\n")
    w(f"| field | {short} agrees | {short} kappa | {short} weighted | {short} weighted kappa | Sonnet agrees | Sonnet kappa | Sonnet weighted |")
    w("|---|---:|---:|---:|---:|---:|---:|---:|")
    for f in FIELDS:
        a, s_ = fa[f], fs[f]
        w(f"| {f} | {a['agree']:,} ({_f(a['rate'])}) | {a['kappa']:.2f} | {_f(a['weighted_rate'])} | {a['weighted_kappa']:.2f} | "
          f"{s_['agree']:,} ({_f(s_['rate'])}) | {s_['kappa']:.2f} | {_f(s_['weighted_rate'])} |")
    w(f"\nThe framing field is withdrawn from the rebuilt report; it is kept here because the review's bucket rule uses it. Kappa on "
      f"production_claim is low for both models because the audit marks it true on only {groups['production_claim']['audit_positive_n']} "
      f"of the {m['labelled']:,} audited posts.\n")
    w(f"By stratum. Percent agreement, {short} / Sonnet. Strata are Sonnet-defined; within a sampled stratum the posts are a random sample.\n")
    w("| stratum | n | family | tier | evidence | framing | baseline | realtime | production |")
    w("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for key in list(res["agreement"]["model"]["strata"]):
        b, bs = A["strata"][key], As["strata"][key]
        w(f"| {STRATUM_NAMES[key]} | {b['family']['n']:,} | " + " | ".join(
            f"{100 * b[f]['rate']:.0f} / {100 * bs[f]['rate']:.0f}" for f in FIELDS) + " |")

    w(f"\n## Recount by {short}'s own label\n")
    w(f"Among the audited posts, grouped by {short}'s label: how often the audit gives the same label. These posts are not a random sample of "
      f"{short}'s labels. The strata were drawn on Sonnet's labels, and rare strata were read in full. The weighted columns correct for the "
      f"design (method, point 6); they estimate the rate over the frame, not over the audited posts. Sonnet's weighted precision is given for "
      f"comparison.\n")
    w(f"| {short} label | {short} posts | audited | audit agrees | precision | weighted | Sonnet weighted | recall | weighted recall |")
    w("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for key, label, _q in GROUPS:
        g, gs = groups[key], sgroups[key]
        cnt = g["deduped_count"] if key == "not_a_jev_build" else g["base_count"]
        w(f"| {label} | {cnt:,} | {g['audited_n']:,} | {g['audit_agrees']:,} | {_f(g['precision'])} | {_f(g['weighted_precision'])} | "
          f"{_f(gs['weighted_precision'])} | {_f(g['recall'])} | {_f(g['weighted_recall'])} |")
    w(f"\nBy field and value (every value {short} uses). Precision: of the audited posts {short} gives this value, the share the audit gives "
      f"it too. Recall: of the audited posts the audit gives this value, the share {short} gives it too.\n")
    w(f"| field | {short} value | {short} posts | audited | agrees | precision | weighted | recall | weighted recall |")
    w("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for v in rc["values"]:
        if v["audited_n"] == 0 and v["base_count"] == 0:
            continue
        w(f"| {v['field']} | {v['value']} | {v['base_count']:,} | {v['audited_n']:,} | {v['audit_agrees']:,} | {_f(v['precision'])} | "
          f"{_f(v['weighted_precision'])} | {_f(v['recall'])} | {_f(v['weighted_recall'])} |")
    w(f"\n\"{short} posts\" counts {short}'s use-case base, so not_a_jev_build shows 0 there ({sn['deduped']} after merging duplicates).\n")

    w("## The ten claims\n")
    # 1
    w("**1. Baselines.** " + "; ".join(
        f"{lab} {short} {_p(R[k]['opus_model'])}, audit {_e({'est_pct': R[k]['opus_value'], 'lo_pct': R[k]['opus_lo'], 'hi_pct': R[k]['opus_hi']})}"
        for lab, k in (("none", "baseline_none"), ("frontier", "baseline_frontier_llm"), ("small", "baseline_small_llm"),
                       ("replacement", "baseline_replacement"))) + ". "
      f"All four {short} shares are inside their intervals; Sonnet's none, frontier and small shares were outside theirs. The {reg['frontier_small']:,} "
      f"frontier and small-LLM posts were not sampled, so the estimate takes {short}'s word there ({c1o['none']['region_check']['model_n']} none, "
      f"{c1o['frontier_llm']['region_check']['model_n']} frontier, {c1o['small_llm']['region_check']['model_n']} small, "
      f"{c1o['replacement']['region_check']['model_n']} replacement). The audit's own samples put that region at "
      f"{_c(c1o['none']['region_check']['audit_est'])} none, {_c(c1o['frontier_llm']['region_check']['audit_est'])} frontier, "
      f"{_c(c1o['small_llm']['region_check']['audit_est'])} small and {_c(c1o['replacement']['region_check']['audit_est'])} replacement, close to "
      f"{short}'s split and far from Sonnet's ({c1s['frontier_llm']['region_check']['model_n']} frontier, {c1s['small_llm']['region_check']['model_n']} "
      f"small, 0 none). Of those posts that happen to be audited, {short}'s frontier label holds on "
      f"{opu['claim1']['baseline_sensitivity']['frontier_llm']['audit'].get('frontier_llm', 0)} of {opu['claim1']['baseline_sensitivity']['frontier_llm']['n']} "
      f"(Sonnet {son['claim1']['baseline_sensitivity']['frontier_llm']['audit'].get('frontier_llm', 0)} of {son['claim1']['baseline_sensitivity']['frontier_llm']['n']}). "
      f"Recount by {short}'s label: replacement baseline {gline('baseline_replacement')}; none {gline('baseline_none')}.\n")
    # 2
    w(f"**2. Production.** {short}: {c2o['model_n']} posts, {_p(c2o['model_pct'], 2)}. Audit: {round(c2o['est_count'])} posts, {_e(c2o, 2)}: "
      f"{c2o['hold_on_reread']} of Sonnet's {c2o['census_n']} hold on the re-read, and neither sample of 200 demos has a production post. "
      f"{short}'s share is inside the interval only because the interval's top is the Wilson bound on zero misses in 400 sampled demos. The recount "
      f"is direct: {sp['model_mp_audited']} of {short}'s {sp['base']} production posts were audited and {sp['model_mp_audited_holds']} hold "
      f"(sanity check 1). Publish the audited count, not {short}'s.\n")
    # 3
    lad = [("ladder_no_measurement", "no measurement"), ("ladder_measured_demo", "measured demo"),
           ("ladder_demo_no_numbers", "demos with no numbers, report rule (no claim chip, not meta)"),
           ("ladder_claim_no_number", "a claim chip with no measurement, report rule"),
           ("review_demo_bucket", "demos with no numbers, review rule"),
           ("review_hype_no_number", "a cost, speed or accuracy lead with no number, review rule"),
           ("cost_only_as_described", "measured, and a batch or an incumbent already did it"),
           ("candidates_combined", "posts that meet the material test, misses included")]
    w("**3. The measurement ladder.** " + "; ".join(
        f"{lab}: {short} {_p(R[k]['opus_model'])}, audit {_p(R[k]['opus_value'])} ({_r(R[k]['opus_lo'], R[k]['opus_hi'])})" for k, lab in lad)
      + f". Every {short} figure is inside its interval. The ladder rests on the evidence field, where {short}'s measured label holds on "
      f"{_f(groups['measured']['weighted_precision'])} (weighted) and its no-measurement label on {_f(groups['no_measurement']['weighted_precision'])}. "
      f"The review-rule rows leave out the proposal and commentary posts, as `review/estimate.py` does. {short}'s own count of posts that meet the "
      f"material test is {groups['candidate']['base_count']}; {gline('candidate')}.\n")
    # 4
    c4o = opu["claim4"]
    w(f"**4. Voice, live chat and collaboration.** {short}: {c4o['model_n']} posts, {_p(c4o['model_pct'])}. Audit: {_e(c4o)}, "
      f"{c4o['plug']} posts on {short}'s word ({c4o['region_check']['model_n']} games {short} moves into these families, and "
      f"{c4o['plug'] - c4o['region_check']['model_n']} model-only). Sonnet's {_p(R['rt_families']['sonnet_model'])} sat at the bottom of its interval; "
      f"{short}'s is near the centre. Recount: {gline('rt_family')}. Production: the audit has {c4o['census_measured_production'] + c4o['plugin_measured_production']} "
      f"of these posts in measured production ({short} labels {c4o['model_measured_production']}, the live news feed the audit re-read as having no "
      f"number). On the audit's own labels two of these posts claim production without a measurement: the Discord moderation bot in the "
      f"negative sample, which the review read and did not count, and the same news feed, which Sonnet had in classification, so the "
      f"census of 156 did not see it.\n")
    # 5
    c5o = opu["claim5"]
    w(f"**5. A live loop.** Outside games: {short} {_p(c5o['model_nongame_pct'])}, audit {_e(c5o['nongame'])}, {c5o['nongame']['plug']} posts on "
      f"{short}'s word. Sonnet's {_p(R['live_loop_nongame']['sonnet_model'])} was outside its interval. With games: {short} flags "
      f"{_p(c5o['model_pct'])}; the review's rough construction gives {_p(c5o['live_loop_all']['est_pct'])}; the evidence strata alone give "
      f"{_e(c5o['audit_only_any'])}. Both halves of the claim (about a fifth; 5 to 10 percent outside games) fit {short}'s figures. Recount: realtime "
      f"flag true and not games, {gline('live_loop_nongame')}.\n")
    # 6
    c6o = opu["claim6"]
    w(f"**6. Under 300 ms.** {short} puts {c6o['model_fast_n']:,} posts ({_p(c6o['model_fast_pct'])}) under 300 ms. Audit: {_e(c6o['set'])}: "
      f"{c6o['sample_still_fast']} of the {c6o['sample_n']} sampled posts in Sonnet's stratum stay under 300 ms, plus {c6o['set']['plug']} posts "
      f"that {short} alone puts there, on {short}'s word. The audit's samples put {_c(c6o['region_check']['audit_est'])} "
      f"({_c(c6o['region_check']['audit_lo'])}–{_c(c6o['region_check']['audit_hi'])}) such posts outside Sonnet's stratum, not "
      f"{c6o['region_check']['model_n']}; audit-only {_e(c6o['audit_only_set'])}. {short}'s share is outside both, though nearer than Sonnet's "
      f"{_p(R['sub300_set']['sonnet_model'])}. Recount: {gline('tier_under_300ms')}. The games share holds: {short} {_p(100 * c6o['model_games_share'])}, "
      f"audit {c6o['sample_still_fast_and_game']} of {c6o['sample_still_fast']}, {_p(c6o['conditional_pct'])} ({_r(c6o['conditional_lo_pct'], c6o['conditional_hi_pct'])}).\n")
    # 7
    in_meta = c7o["model_meta_n"] - c7o["plug"]
    w(f"**7. Meta posts.** {short}: {c7o['model_meta_n']:,} posts, {_p(c7o['model_meta_pct'])}. Audit, same logic: {_e(c7o)}, of which "
      f"{c7o['plug']} posts on {short}'s word ({c7o['region_check']['model_n']} outside Sonnet's meta stratum, and "
      f"{c7o['plug'] - c7o['region_check']['model_n']} model-only). Audit-only: {_e(c7o['audit_only'])}: the audit's samples put "
      f"{_c(c7o['region_check']['audit_est'])} ({_c(c7o['region_check']['audit_lo'])}–{_c(c7o['region_check']['audit_hi'])}) meta posts outside "
      f"Sonnet's stratum, close to {short}'s {c7o['region_check']['model_n']}. Inside the stratum {short} calls {in_meta:,} of {c7o['stratum_n']:,} "
      f"posts meta; the sample says {c7o['sample_still_meta']} of {c7o['sample_n']} ({_f(c7o['sample_still_meta'] / c7o['sample_n'])}), about "
      f"{_c(c7o['sample_still_meta'] / c7o['sample_n'] * c7o['stratum_n'])}. So {short} over-calls meta inside Sonnet's stratum and is about right "
      f"outside it. {short}'s share is just above the same-logic interval and inside the audit-only one. The review's "
      f"{_p(c7s['est_pct'])} ({_r(c7s['lo_pct'], c7s['hi_pct'])}) for Sonnet leaves out the same region; with it, Sonnet's base is "
      f"{_e(c7s['audit_only'])} meta, and Sonnet's {_p(c7s['model_meta_pct'])} is inside. \"A fifth of posts\" holds under both models once that "
      f"region is counted. Memes {_p(c7o['meme_est_pct'], 2)} and hot takes {_p(c7o['hot_est_pct'], 2)} of posts ({c7o['subtype_among_still'].get('meme_or_joke', 0)} "
      f"and {c7o['subtype_among_still'].get('hot_take_or_commentary', 0)} of {c7o['sample_n']} sampled): \"about 1% each\" still fails. Unrelated, "
      f"a benchmark or a wrapper: {_p(c7o['vague_est_pct'])} on the sample, {_p(c7o['audit_only_subtypes']['vague']['est_pct'])} with the region "
      f"outside the stratum. {short} has no noise sub-types of its own; its meme and hot-take counts use the noise file, which covers "
      f"{c7o['model_meta_with_subtype']:,} of its {c7o['model_meta_n']:,} meta posts. Recount: {gline('meta')}.\n")
    # 8-10
    c8o, c8s = opu["claim8"], son["claim8"]
    w(f"**8. Attention (a census).** Only the base moves. Top 1% ({c8o['top1_cards']} posts; {c8s['top1_cards']} on Sonnet's base) hold "
      f"{_f(c8o['top1_share'])} of views ({_f(c8s['top1_share'])}); {_f(c8o['top1_excl_suspect'])} without the {c8o['suspect_n']} low-like-rate posts "
      f"({_f(c8s['top1_excl_suspect'])}); {_f(c8o['top1_likes_share'])} of likes ({_f(c8s['top1_likes_share'])}); {c8o['cards_holding_half']} posts "
      f"hold half of all views ({c8s['cards_holding_half']}). The verdict does not change.\n")
    c9o, c9s = opu["claim9"], son["claim9"]
    w(f"**9. Jev as a classifier.** Jev matches {short}'s family on {c9o['agree_model']:,} of {c9o['n']:,} posts ({_p(c9o['agree_pct'])}, kappa "
      f"{c9o['kappa']:.2f}; Sonnet {_p(c9s['agree_pct'])}, kappa {c9s['kappa']:.2f}), and on {_p(c9o['p_ge_099_agree_model_pct'])} of the "
      f"{c9o['p_ge_099']:,} posts where Jev states 0.99 or more (Sonnet {_p(c9s['p_ge_099_agree_model_pct'])}). Against the audit, Jev at 0.99 or "
      f"more matches on {c9o['p_ge_099_matches_audit_family']} of {c9o['p_ge_099_in_audit']}, and on 27 of the 28 such posts in the earlier 120 "
      f"labels; neither depends on the model. Holds.\n")
    c10o, c10s = opu["claim10"], son["claim10"]
    w(f"**10. Claimed multiples (a census of the chips).** Only the base moves: {c10o['cost_chips']} cost chips (Sonnet's base "
      f"{c10s['cost_chips']}), median {c10o['cost_median']:g}× ({c10o['cost_median_without_1x']:g}× without the {c10o['cost_1x']} 1× chips; "
      f"{c10s['cost_median_without_1x']:g}× on Sonnet's base); {c10o['speed_chips']} speed chips ({c10s['speed_chips']}), median "
      f"{c10o['speed_median']:g}× ({c10o['speed_median_without_1x']:g}× without the {c10o['speed_1x']} 1× chips; "
      f"{c10s['speed_median_without_1x']:g}× on Sonnet's base). The headline medians hold; the speed figure without 1× chips needs "
      f"updating if the report prints it.\n")

    w("## Side by side\n")
    w(f"Shares are of each model's own use-case base (Sonnet {son['use_case_base']:,}, {short} {opu['use_case_base']:,}). \"Audit\" is the "
      f"review's estimator with that model as the model under test. \"On {short}'s word\" is the number of posts the {short} estimate takes from "
      f"{short}'s labels. \"Audit-only\" is on {short}'s base; Sonnet's base gives nearly the same (CSV). ✓ = the model's own figure is inside "
      f"the audit interval.\n")
    w(f"| claim | quantity | Sonnet labels | audit, Sonnet as model | {short} labels | audit, {short} as model | on {short}'s word | audit-only | Sonnet ✓ | {short} ✓ |")
    w("|---:|---|---:|---:|---:|---:|---:|---:|:---:|:---:|")

    def ci(v, lo, hi, d=1):
        if v is None:
            return ""
        return _p(v, d) if lo is None else f"{_p(v, d)} ({_r(lo, hi, d)})"

    def tick(x):
        return "" if x is None else ("✓" if x else "✗")
    for r in res["side_by_side"]:
        d = 2 if r["key"] in ("production_strict", "ladder_measured_production", "meta_meme", "meta_hot") else 1
        if r["unit"] in ("×",):
            sv, ov = f"{r['sonnet_value']:g}×", f"{r['opus_value']:g}×"
            w(f"| {r['claim']} | {r['label']} |  | {sv} |  | {ov} |  |  |  |  |")
            continue
        w(f"| {r['claim']} | {r['label']} | {_p(r['sonnet_model'], d) if r['sonnet_model'] is not None else ''} | "
          f"{ci(r['sonnet_value'], r['sonnet_lo'], r['sonnet_hi'], d)} | {_p(r['opus_model'], d) if r['opus_model'] is not None else ''} | "
          f"{ci(r['opus_value'], r['opus_lo'], r['opus_hi'], d)} | {'' if r['opus_plug'] is None else _c(r['opus_plug'])} | "
          f"{ci(r['audit_only_value'], r['audit_only_lo'], r['audit_only_hi'], d)} | {tick(r['sonnet_inside'])} | {tick(r['opus_inside'])} |")
    w("")
    w(f"Rows 3 use the evidence strata directly, so they have no audit-only variant. The review-rule \"hype\" row compares like with like: the "
      f"model figure is the same rule on the model's labels ({_p(R['review_hype_no_number']['sonnet_model'])} for Sonnet), not the review's "
      f"published hype bucket (11.5%).\n")

    w(f"## Which claims are more or less supported under {short}\n")
    for c in claims:
        w(f"- **{c['claim']}. {c['topic']}.** Review: {c['review_verdict']}. With {short}: {c['opus_verdict']}. {c['change'][0].upper() + c['change'][1:]}.")
    w("")
    w(f"In short: {short}'s figures are better supported than Sonnet's on baselines, the realtime families, the live loop and meta posts, and "
      f"nearer the audit on the size of the under-300 ms set. Two stay unsupported: measured production (publish the audited count, not {short}'s {c2o['model_n']}) and the size of "
      f"the under-300 ms set ({_p(R['sub300_set']['opus_model'])} against the audit's {_p(R['sub300_set']['opus_value'])}, "
      f"{_r(R['sub300_set']['opus_lo'], R['sub300_set']['opus_hi'])}). "
      f"The census claims (8, 9, 10) do not depend on the model.\n")

    w("## Sanity checks\n")
    w(f"**1. Measured production: {short}'s {sp['whole_corpus']} against the audit's re-read.** {short} labels {sp['whole_corpus']} posts "
      f"measured production ({sp['base']} in its base). {sp['by_sonnet_evidence'].get('measured_production', 0)} are among Sonnet's "
      f"{sp['sonnet_census']}, which the audit re-read; {sp['by_sonnet_evidence'].get('measured_demo', 0)} are posts Sonnet called measured demos. "
      f"Of the {sp['census_holds']} posts that hold on the re-read, {short} labels all {sp['model_mp_on_holds']} measured production. {short} drops "
      f"{len(sp['census_model_not_mp'])} of Sonnet's {sp['sonnet_census']}, and the re-read rejects all {len(sp['census_model_not_mp'])} of them too. It keeps "
      f"{sp['census_not_holding_model_mp']} that the re-read rejects (a $127,000 hyperbole, a latency measured in dev, a live news feed with no "
      f"number). Of its other {sp['model_mp_outside_census']}, the audit read {sp['model_mp_outside_census_audited']} on first-pass labels: "
      f"{sp['model_mp_outside_census_audited_audit_labels'].get('measured_production', 0)} measured production and "
      f"{sp['model_mp_outside_census_audited_audit_labels'].get('measured_demo', 0)} measured demos. {sp['model_mp_in_md_sample']} of those 9 fell "
      f"in the random sample of measured demos, and the audit calls {sp['model_mp_in_md_sample_audit_mp']} of them production. "
      f"{sp['model_mp_unaudited']} were never audited. Net: "
      f"{sp['model_mp_audited_holds']} of {sp['model_mp_audited']} audited {short} production posts hold ({_f(groups['measured_production']['precision'])}; "
      f"weighted {_f(groups['measured_production']['weighted_precision'])}). The audit's point estimate stays {round(c2o['est_count'])} posts "
      f"({_p(c2o['est_pct'], 2)}), at most {_p(c2o['hi_pct'], 1)}. At least {sp['model_mp_audited_holds']} posts are production on the audit's own "
      f"labels (the {sp['model_mp_audited_holds'] - sp['census_holds']} beyond the re-read are first-pass labels from other strata, which the "
      f"estimator does not add). {short}'s {sp['base']} ({_p(c2o['model_pct'], 2)}) is {sp['base'] / sp['model_mp_audited_holds']:.1f} times "
      f"the {sp['model_mp_audited_holds']} the audit confirms and {sp['base'] / c2o['est_count']:.1f} times its point estimate.\n")
    w(f"**2. The three realtime families: {short}'s {sr['whole_corpus']} against the audit's census of {sr['census']}.** "
      f"{sr['by_sonnet_family'].get('realtime family', 0)} of {short}'s {sr['base']} are in Sonnet's census, and {sr['model_rt_outside_census']} are "
      f"outside it (Sonnet had {sr['by_sonnet_family'].get('other_or_meta', 0)} of those as meta, {sr['by_sonnet_family'].get('classification_routing_triage', 0)} "
      f"as classification, {sr['by_sonnet_family'].get('moderation_and_guardrails', 0)} as moderation). Of the {sr['census_kept']} census posts the audit "
      f"keeps in these families, {short} keeps {sr['kept_model_rt']}. Of the {sr['census_dropped']} the audit moves out, {short} still has "
      f"{sr['dropped_model_rt']}. Of {short}'s {sr['model_rt_outside_census']} outside the census, the audit read {sr['model_rt_outside_census_audited']} "
      f"and puts {sr['model_rt_outside_census_audit_rt']} in these families. In the random negative sample of {sr['negative_sample']}, the audit "
      f"finds {sr['negative_sample_misses']} misses and {short} has {sr['negative_misses_model_rt']} of them. Overall {sr['model_rt_audited_audit_rt']} "
      f"of {sr['model_rt_audited']} audited {short} posts hold ({_f(groups['rt_family']['precision'])}; weighted {_f(groups['rt_family']['weighted_precision'])}). "
      f"The audit estimates {_c(opu['claim4']['est_count'])} posts ({_e(opu['claim4'])}); {short}'s {sr['base']} is inside. {short}'s extra posts "
      f"are partly real (the misses Sonnet had) and partly not ({sr['dropped_model_rt']} census posts the audit rejects).\n")
    fe = sn["frame_audit_estimate"]
    w(f"**3. not_a_jev_build: {short}'s {sn['whole_corpus']} against the audit's re-label.** {sn['whole_corpus']} on the whole feed is "
      f"{sn['deduped']} after merging duplicates. {sn['both_nj']} of them Sonnet also calls not_a_jev_build; those were outside the audit's frame "
      f"and were never read. The other {sn['in_frame']} are in the frame: {sn['in_frame_by_sonnet_family'].get('other_or_meta', 0)} Sonnet meta, "
      f"{sn['in_frame_by_sonnet_family'].get('games_control_loops_simulation', 0)} games, the rest spread. The audit read {sn['in_frame_audited']} of "
      f"them and calls {sn['in_frame_audited_audit_nj']} not_a_jev_build; {sn['in_frame_audited_audit_families'].get('other_or_meta', 0)} more it "
      f"keeps as meta. In the audit's re-label of {sn['meta_sample']} Sonnet meta posts (claim 7), it moved {sn['meta_sample_audit_nj']} to "
      f"not_a_jev_build; {short} calls all {sn['meta_sample_both_nj']} of those not_a_jev_build, and {sn['meta_sample_model_nj'] - sn['meta_sample_both_nj']} "
      f"more that the audit keeps as meta. Scaled, the audit puts {_c(sn['meta_stratum_audit_nj_scaled'])} "
      f"({_c(sn['meta_stratum_audit_nj_wilson']['lo'] * sn['meta_stratum'])}–{_c(sn['meta_stratum_audit_nj_wilson']['hi'] * sn['meta_stratum'])}) "
      f"of Sonnet's {sn['meta_stratum']:,} meta posts outside Jev builds; {short} has {sn['meta_stratum_model_nj']}. Across all audited posts, "
      f"{short} catches {sn['audit_nj_model_nj']} of the audit's {sn['audit_nj']} not_a_jev_build posts, and its own not_a_jev_build label holds "
      f"on {_f(groups['not_a_jev_build']['precision'])} (weighted {_f(groups['not_a_jev_build']['weighted_precision'])}). Over the whole frame the "
      f"evidence samples estimate {_c(fe['est'])} ({_c(fe['lo'])}–{_c(fe['hi'])}) posts the audit would call not_a_jev_build; {short}'s "
      f"{sn['in_frame']} is inside that range, above the point. {short}'s larger count agrees with the audit's re-label of meta posts; its "
      f"not_a_jev_build calls on other posts hold about two times in three.\n")

    w("## Limits\n")
    w(f"- The strata were drawn on Sonnet's labels. For {short} they are a valid stratification, but less efficient: only "
      f"{sr['by_sonnet_family'].get('realtime family', 0)} of {short}'s {sr['base']} realtime-family posts are in the census, for example. An "
      f"{short}-drawn sample would give tighter intervals where the two models disagree.")
    w(f"- The \"same logic\" estimate takes {short}'s word on the regions the review did not sample; the \"on {short}'s word\" column sizes that. "
      f"The audit-only variant avoids it with few posts (for claim 1, "
      f"{c1o['none']['region_check']['audit']['parts']['demo_no_numbers']['n']} + {c1o['none']['region_check']['audit']['parts']['measured_demo']['n']} "
      f"sampled posts fall in the {reg['frontier_small']:,}-post region), so its intervals are wide.")
    w(f"- {opu['model_only_posts']} model-only posts and {reg['remainder']} proposal and commentary posts enter at {short}'s labels.")
    w("- Grok is another AI model, not a person. Agreement with it is not correctness; it is agreement with an independent reader using the same rubric.")
    w("- Summed Wilson bounds are conservative, and the weighted rates treat the eight samples as independent draws.")
    w(f"- The production re-read covered Sonnet's 15 posts. {sp['model_mp_unaudited']} of {short}'s {sp['base']} were never audited.\n")
    w("## Files\n")
    w(f"- `review/estimate-{tag}.py`: the estimation (run: `python3 review/estimate-{tag}.py --model {m['model_file']}`).")
    w(f"- `review/work/estimate-{tag}.json`: every number, for Sonnet (`sonnet`), {short} on its own base (`model`) and on the frame (`model_frame_base`).")
    w(f"- `review/data/audit-{tag}-agreement.csv`: agreement and kappa per field, raw and weighted, both models.")
    w(f"- `review/data/audit-{tag}-agreement-strata.csv`: agreement per Sonnet-defined stratum, both models.")
    w(f"- `review/data/audit-{tag}-recount.csv` and `audit-{tag}-recount-groups.csv`: the recount by each model's own label.")
    w(f"- `review/data/audit-{tag}-estimates.csv`: the side-by-side table, with the audit-only and frame-base columns.")
    w(f"- `review/data/audit-{tag}-claims.csv`: one row per claim, with both verdicts.")
    w(f"- `review/data/audit-{tag}-sanity.csv`: the three sanity checks.")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- output


def write_csv(path: Path, rows: list[dict], cols: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else (round(r[k], 6) if isinstance(r[k], float) else r[k])) for k in cols})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="data/classified-opus.jsonl", help="label file of the model under test")
    ap.add_argument("--name", default=None, help="the model's name for the write-up (default: from the file name)")
    ap.add_argument("--tag", default=None, help="output tag (default: opus, or the file stem)")
    ap.add_argument("--json-only", action="store_true", help="write review/work/estimate-<tag>.json only")
    args = ap.parse_args()
    mpath = Path(args.model) if Path(args.model).is_absolute() else ROOT / args.model
    if not mpath.exists():
        raise SystemExit(f"label file not found: {mpath}")
    name = args.name or model_name(mpath)
    tag = args.tag or ("opus" if "opus" in mpath.name.lower() else mpath.stem.replace("classified-", ""))

    ctx = load_context()
    raw = read_jsonl(mpath)
    model_all = load_rows(mpath, ctx["cards"], ctx["dropped"])
    errors_path = mpath.with_name(mpath.stem + ".errors.jsonl")
    refused = [str(r["id"]) for r in read_jsonl(errors_path)] if errors_path.exists() else []
    refused = [i for i in refused if i not in model_all]

    son = run(ctx["sonnet_all"], ctx, "model")
    son_agr = agreement(ctx["sonnet_all"], ctx)
    E = json.loads(SONNET_ESTIMATE.read_text())
    bad = check_reproduction(son, son_agr, E)
    if bad:
        raise SystemExit("the Sonnet run does not reproduce review/work/estimate.json:\n  " + "\n  ".join(bad[:20]))

    opu = run(model_all, ctx, "model")
    opf = run(model_all, ctx, "frame")
    agr = agreement(model_all, ctx)
    base_ids = [i for i, r in model_all.items() if r["family"] != NJ]
    rc = recount(model_all, ctx, base_ids)
    rc_son = recount(ctx["sonnet_all"], ctx, list(ctx["frame"]))
    san = sanity(ctx, raw, model_all, opu, name)
    san["not_a_jev_build"]["frame_audit_estimate"] = frame_ep_nj(ctx)
    sbs = side_by_side(son, opu, opf, ctx)

    result = {
        "meta": {"model_file": str(mpath.relative_to(ROOT)), "model_name": name, "audited_file": str(AUDITED.relative_to(ROOT)),
                 "audited_name": AUDITED_NAME, "reference": str(REFERENCE.relative_to(ROOT)), "labelled": len(ctx["ref"]),
                 "model_rows": len(raw), "model_rows_deduped": len(model_all), "refused": refused,
                 "frame": len(ctx["frame"]), "model_base": len(base_ids), "sonnet_reproduces_estimate_json": True,
                 "uncovered_frame_posts": son_agr["uncovered_frame_posts"], "weight_total": son_agr["weight_total"]},
        "sonnet": son, "model": opu, "model_frame_base": opf,
        "agreement": {"model": agr, "sonnet": son_agr},
        "recount": {"model": rc, "sonnet": rc_son},
        "sanity": san, "side_by_side": sbs,
    }
    (REV / "work").mkdir(parents=True, exist_ok=True)
    (REV / "work" / f"estimate-{tag}.json").write_text(json.dumps(result, indent=1, default=str))
    if args.json_only:
        print(f"wrote review/work/estimate-{tag}.json")
        return 0

    outd = REV / "data"
    # agreement per field
    arows = []
    for f in FIELDS:
        a, s = agr["fields"][f], son_agr["fields"][f]
        arows.append({"field": f, "n": a["n"], "model_agree": a["agree"], "model_rate": a["rate"], "model_kappa": a["kappa"],
                      "model_weighted_rate": a["weighted_rate"], "model_weighted_kappa": a["weighted_kappa"],
                      "sonnet_agree": s["agree"], "sonnet_rate": s["rate"], "sonnet_kappa": s["kappa"],
                      "sonnet_weighted_rate": s["weighted_rate"], "sonnet_weighted_kappa": s["weighted_kappa"], "model": name})
    write_csv(outd / f"audit-{tag}-agreement.csv", arows,
              ["field", "n", "model_agree", "model_rate", "model_kappa", "model_weighted_rate", "model_weighted_kappa",
               "sonnet_agree", "sonnet_rate", "sonnet_kappa", "sonnet_weighted_rate", "sonnet_weighted_kappa", "model"])
    srows = []
    for key in list(ctx["strata"]["exhaustive"]) + list(ctx["strata"]["samples"]) + ["all_labelled"]:
        for who, block in (("model", agr["strata"][key]), ("sonnet", son_agr["strata"][key])):
            srows.append({"stratum": key, "stratum_label": STRATUM_NAMES[key], "labels": name if who == "model" else AUDITED_NAME,
                          "n": block["family"]["n"], **{f: block[f]["rate"] for f in FIELDS}})
    write_csv(outd / f"audit-{tag}-agreement-strata.csv", srows, ["stratum", "stratum_label", "labels", "n"] + FIELDS)
    rrows = [dict(r, labels=name) for r in rc["values"]] + [dict(r, labels=AUDITED_NAME) for r in rc_son["values"]]
    write_csv(outd / f"audit-{tag}-recount.csv", rrows,
              ["labels", "field", "value", "base_count", "audited_n", "audit_agrees", "precision", "lo", "hi", "weighted_precision",
               "audit_n", "recall", "weighted_recall"])
    grows = [dict(r, labels=name) for r in rc["groups"]] + [dict(r, labels=AUDITED_NAME) for r in rc_son["groups"]]
    write_csv(outd / f"audit-{tag}-recount-groups.csv", grows,
              ["labels", "group", "label", "base_count", "deduped_count", "audited_n", "audit_agrees", "precision", "lo", "hi", "weighted_precision",
               "audited_negative_n", "audit_positive_among_negative", "weighted_miss_rate", "audit_positive_n", "recall", "weighted_recall"])
    write_csv(outd / f"audit-{tag}-estimates.csv", sbs,
              ["claim", "key", "label", "unit", "sonnet_model", "sonnet_value", "sonnet_lo", "sonnet_hi", "sonnet_inside",
               "opus_model", "opus_value", "opus_lo", "opus_hi", "opus_inside", "opus_plug",
               "audit_only_value", "audit_only_lo", "audit_only_hi", "opus_inside_audit_only",
               "sonnet_audit_only_value", "sonnet_audit_only_lo", "sonnet_audit_only_hi", "sonnet_inside_audit_only",
               "opus_frame_value", "opus_frame_lo", "opus_frame_hi", "note"])
    sanity_rows = []
    for check, block in san.items():
        for k, v in block.items():
            if isinstance(v, (int, float, str)) or v is None:
                sanity_rows.append({"check": check, "key": k, "value": v})
            else:
                sanity_rows.append({"check": check, "key": k, "value": json.dumps(v, sort_keys=True, default=str)})
    write_csv(outd / f"audit-{tag}-sanity.csv", sanity_rows, ["check", "key", "value"])
    claims = claim_rows(result)
    write_csv(outd / f"audit-{tag}-claims.csv", claims,
              ["claim", "topic", "published", "sonnet_labels", "sonnet_audit", "opus_labels", "opus_audit", "audit_only",
               "review_verdict", "opus_verdict", "change"])
    (REV / f"audit-{tag}.md").write_text(render_md(result, claims, tag))
    print(json.dumps({"model": name, "base": len(base_ids), "frame": len(ctx["frame"]), "sonnet_reproduces": True,
                      "agreement": {f: round(agr["fields"][f]["rate"], 3) for f in FIELDS}}, indent=1))
    print(f"wrote review/work/estimate-{tag}.json, review/data/audit-{tag}-*.csv and review/audit-{tag}.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
