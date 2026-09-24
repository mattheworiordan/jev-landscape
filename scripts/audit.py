#!/usr/bin/env python3
"""Tables from the independent audit, for the report and the page.

    python3 scripts/audit.py [--labels data/classified-opus.jsonl]     (from the jev-landscape folder)

The audit is review/critical-review-grok.md: an independent reviewer (Grok) labelled 1,681 cards blind
to the model's labels (review/hand-labels-grok.jsonl). Its sample was drawn from the Claude Sonnet 5
(rubric v2) labels of the 5,709-post use-case base (review/sample.py, seed 20260924): the strata are
Sonnet-labelled groups, some taken whole (a census) and some sampled. This script runs the audit's own
scripts and writes their numbers to report/data/13_audit_*.csv:

  review/estimate.py        the audit's estimates and agreement, with Sonnet as the model under test
                            (it rewrites review/work/estimate.json; the output is deterministic)
  review/work/substance.py  what would have done the job before, for the 91 candidate builds
  review/arithmetic.py      the rule arithmetic on the Sonnet labels

The report's labels can be another model's (--labels, default the audited Sonnet v2 file; analyze.py
passes its own). The audit's labels stay the reference; only the model under test changes. reestimate()
repeats review/estimate.py's logic for that model: each sampled stratum is scaled up from the audit's
labels with a 95% Wilson interval, as the audit did, and the strata the audit did not sample (the
frontier and small-LLM baselines, the games outside the realtime-family check, the realtime-flagged
games, the proposal and commentary posts) are filled with the model's labels instead of being assumed
right. With the Sonnet labels as the model it reproduces estimate.json exactly, and the script stops if
it does not. Estimates are shares of the 5,709 posts the audit sampled from.

Two fields are not published. Framing (what a post leads with) is withdrawn: a human calibration showed
that one choice misrepresents posts that lead with cost and latency together. So the ladder's parts are
defined without it: "a cost, speed or accuracy claim with no measurement" is a card whose evidence is
demo_no_numbers and that carries a cost, speed or accuracy chip; "a demo with no numbers" is any other
demo_no_numbers card that is not meta. Latency tier is shown only as the coarse under-300 ms split.

If the Sonnet v2 labels no longer give the strata the audit sampled (a refresh added or changed cards),
the audit describes the earlier snapshot: the script keeps the last estimate.json, prints a warning and
writes snapshot_matches = 0, and charts.mjs refuses to build the page until the audit is redone.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REVIEW = ROOT / "review"
OUTD = ROOT / "report" / "data"
AUDITED_LABELS = DATA / "classified-sonnet-v2.jsonl"
AUDITED_MODEL = "Claude Sonnet 5"
AUDIT_DOC = "review/critical-review-grok.md"
AUDIT_LABELS_FILE = "review/hand-labels-grok.jsonl"
AUDITOR = "Grok"
FIELDS = ["family", "tier", "evidence", "baseline", "realtime_infra", "production_claim"]  # published; framing is withdrawn
RT = {"voice_and_turn_taking", "live_chat_streams_events", "collaboration_and_typing"}
REPL = {"classic_classifier_or_ml", "rules_or_regex", "vendor_api"}
GAMES = "games_control_loops_simulation"
FAST = {"frame", "feel", "turn"}
UNMEASURED = {"demo_no_numbers", "proposal_or_idea"}
REMAINDER = {"proposal_or_idea", "commentary_or_meme"}  # evidence strata the audit did not sample
# The feed's claim chips: cost ($, cents, N× cheaper), speed (N× faster, ms, s, per second) and
# accuracy (N% accurate). The only other chip shape is "N items", a count.
CSA_CHIP = re.compile(r"^(\$[\d.,]+|[\d.,]+¢|[\d.,]+\s*×\s*(cheaper|faster)|[\d.,]+\s*ms|[\d.,]+\s*s|[\d.,e+]+/s|[\d.,]+%\s*accurate)$")

# Plain names for the audit's strata, in the order of its sampling table.
STRATA = [
    ("measured_production", "Measured production (Sonnet label)"),
    ("material", "The 91 candidate builds"),
    ("realtime_family", "Voice, live chat or collaboration"),
    ("replacement_baseline", "Classic ML, rules or vendor baseline"),
    ("baseline_none", "No comparison named"),
    ("demo_no_numbers", "Demo, no numbers"),
    ("measured_demo", "Measured demo"),
    ("not_realtime_family_not_games", "Not a realtime family, not games"),
    ("realtime_infra_false", "Realtime flag false"),
    ("realtime_infra_true_nongame", "Realtime flag true, not games"),
    ("other_or_meta", "Other or meta"),
    ("tier_under_300ms", "Under 300 ms (frame, feel or turn)"),
]
BEFORE = [  # review/work/substance.py "before" keys, in the audit's order, plus the bar it sets
    ("llm", "An LLM"),
    ("rules", "Rules or heuristics"),
    ("vendor", "A vendor API"),
    ("classic", "A classic model"),
    ("unavailable", "Unavailable at any price"),
]
JOBS = {  # review/work/substance.py job keys, named as groups of posts
    "feed_filter": "Feed or comment filters", "voice_command": "Voice commands", "typing_or_form": "Typing or form fill",
    "voice_turn": "Voice turn-taking", "triage": "Triage", "speech_score": "Speech scoring", "guard": "Guards",
    "trading": "Trading decisions", "game_or_sim": "Games or simulations", "classify": "Classification",
    "computer_use": "Computer use", "live_control": "Live control", "search": "Search", "alerts": "Alerts",
    "personal_tool": "Personal tools",
}


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _json_of(script: Path) -> dict:
    out = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, cwd=ROOT, check=False)
    if out.returncode != 0:
        raise SystemExit(f"{script.relative_to(ROOT)} failed:\n{out.stderr.strip()}")
    return json.loads(out.stdout)


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def _merged() -> set[str]:
    return {i for r in _read_jsonl(DATA / "dedupe-groups.jsonl") for i in r["merged"]}


def load_labels(path: Path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for r in _read_jsonl(path):
        rows.setdefault(str(r["id"]), r)
    return rows


def use_case_base(rows: dict[str, dict]) -> list[str]:
    merged = _merged()
    return [i for i, r in rows.items() if i not in merged and r["family"] != "not_a_jev_build"]


def has_csa_chip(chips) -> bool:
    return any(CSA_CHIP.match(str(c).strip()) for c in chips or [])


def current_strata(sample) -> dict:
    """Stratum sizes on the current audited labels, with the predicates of review/sample.py."""
    merged = _merged()
    rows = {}
    for r in _read_jsonl(AUDITED_LABELS):
        if r["id"] not in merged:
            rows[r["id"]] = r  # last wins, as review/sample.py
    base = [r for r in rows.values() if r["family"] != "not_a_jev_build"]
    preds = {
        "measured_production": lambda r: r["evidence"] == "measured_production",
        "material": lambda r: sample.corrected(r) in ("material", "material_vs_frontier"),
        "realtime_family": lambda r: r["family"] in RT,
        "replacement_baseline": lambda r: r["baseline"] in REPL,
        "baseline_none": lambda r: r["baseline"] == "none",
        "demo_no_numbers": lambda r: r["evidence"] == "demo_no_numbers",
        "measured_demo": lambda r: r["evidence"] == "measured_demo",
        "not_realtime_family_not_games": lambda r: r["family"] not in RT and r["family"] != GAMES,
        "realtime_infra_false": lambda r: r["realtime_infra"] is False,
        "realtime_infra_true_nongame": lambda r: r["realtime_infra"] is True and r["family"] != GAMES,
        "other_or_meta": lambda r: r["family"] == "other_or_meta",
        "tier_under_300ms": lambda r: r["tier"] in ("feel", "frame", "turn"),
    }
    return {"use_case_base": len(base), **{k: sum(1 for r in base if p(r)) for k, p in preds.items()}}


def agreement_by_stratum(model: dict[str, dict], audit: dict[str, dict], strata: dict) -> list[dict]:
    out = []
    groups = [(k, name, strata["exhaustive"][k] if k in strata["exhaustive"] else strata["samples"][k]) for k, name in STRATA]
    groups.append(("all_labelled", "All audited cards", list(audit)))
    for key, name, ids in groups:
        both = [i for i in ids if i in model and i in audit]
        out.append({"key": key, "stratum": name, "n": len(both),
                    **{f: (sum(1 for i in both if model[i][f] == audit[i][f]) / len(both)) if both else None for f in FIELDS}})
    return out


def reestimate(frame: dict[str, dict], model: dict[str, dict], audit: dict[str, dict], strata: dict, wilson, chips: dict[str, list]) -> dict:
    """review/estimate.py's estimators, with `model` as the model under test.

    frame: the audited base (the Sonnet v2 labels the strata were drawn from), id -> row.
    model: the labels under test; a card they do not label (a refusal) falls back to its frame label.
    Each estimate is a share of the frame base, with a 95% Wilson interval; where two sampled strata are
    added the bounds are summed, as the audit did. Unsampled strata are filled from `model`.
    """
    N = len(frame)
    pop = strata["meta"]["stratum_population"]
    ex, sm = strata["exhaustive"], strata["samples"]

    def M(i: str) -> dict:
        return model.get(i) or frame[i]

    out: dict[str, dict] = {}

    def put(key: str, census: float, parts: list[tuple[int, int, int]], plug: float, **extra) -> None:
        est = lo = hi = census + plug
        for k, n, p in parts:
            w = wilson(k, n)
            est += w["p"] * p
            lo += w["lo"] * p
            hi += w["hi"] * p
        out[key] = {"value": est / N, "lo": lo / N, "hi": hi / N, "count": est, "plug": plug, **extra}

    # comparison baselines (claim 1): census of the replacement stratum, the no-comparison sample, and the
    # frontier and small-LLM strata (not sampled) from the model
    none_s, repl = sm["baseline_none"], ex["replacement_baseline"]
    unsampled_b = [i for i in frame if frame[i]["baseline"] in ("frontier_llm", "small_llm")]
    for key, pred in (("none", lambda b: b == "none"), ("frontier_llm", lambda b: b == "frontier_llm"),
                      ("small_llm", lambda b: b == "small_llm"), ("replacement", lambda b: b in REPL)):
        put(f"baseline_{key}", sum(1 for i in repl if pred(audit[i]["baseline"])),
            [(sum(1 for i in none_s if pred(audit[i]["baseline"])), len(none_s), pop["baseline_none"])],
            sum(1 for i in unsampled_b if pred(M(i)["baseline"])))
    # measured production (claim 2): the census of the strict cards, misses in the two evidence samples,
    # and the proposal and commentary posts (not sampled) from the model
    prod, nn, md = ex["measured_production"], sm["demo_no_numbers"], sm["measured_demo"]
    prod_set = set(prod)
    rem = [i for i in frame if frame[i]["evidence"] in REMAINDER]
    is_mp = lambda r: r["evidence"] == "measured_production"
    put("production_strict", sum(1 for i in prod if is_mp(audit[i])),
        [(sum(1 for i in nn if is_mp(audit[i])), len(nn), pop["demo_no_numbers"]),
         (sum(1 for i in md if is_mp(audit[i]) and i not in prod_set), len(md), pop["measured_demo"])],
        sum(1 for i in rem if is_mp(M(i))), k=sum(1 for i in prod if is_mp(audit[i])), n=len(prod))
    # the ladder's two audited parts, without the framing field: the same evidence strata as production

    def claim_nn(r: dict, i: str) -> bool:
        return r["evidence"] == "demo_no_numbers" and has_csa_chip(chips.get(i))

    def demo_nn(r: dict, i: str) -> bool:
        return r["evidence"] == "demo_no_numbers" and not has_csa_chip(chips.get(i)) and r["family"] != "other_or_meta"

    def no_measurement(r: dict, _i: str) -> bool:
        return r["evidence"] in UNMEASURED or r["evidence"] == "commentary_or_meme"

    def measured_demo(r: dict, _i: str) -> bool:
        return r["evidence"] == "measured_demo"

    for key, pred in (("ladder_claim_no_number", claim_nn), ("ladder_demo_no_numbers", demo_nn),
                      ("ladder_no_measurement", no_measurement), ("ladder_measured_demo", measured_demo)):
        put(key, sum(1 for i in prod if pred(audit[i], i)),
            [(sum(1 for i in nn if pred(audit[i], i)), len(nn), pop["demo_no_numbers"]),
             (sum(1 for i in md if pred(audit[i], i)), len(md), pop["measured_demo"])],
            sum(1 for i in rem if pred(M(i), i)))
    # voice, live chat and collaboration (claim 4): the census, misses outside the realtime families and
    # games, and the games (left out of the negative sample) from the model
    rtc, neg = ex["realtime_family"], sm["not_realtime_family_not_games"]
    games = [i for i in frame if frame[i]["family"] == GAMES]
    in_rt = lambda r: r["family"] in RT
    census = sum(1 for i in rtc if in_rt(audit[i]))
    put("rt_families", census, [(sum(1 for i in neg if in_rt(audit[i])), len(neg), pop["not_realtime_family_not_games"])],
        sum(1 for i in games if in_rt(M(i))), k=census, n=len(rtc))
    out["rt_families_production"] = {"value": sum(1 for i in rtc if in_rt(audit[i]) and is_mp(audit[i]))
                                     + sum(1 for i in games if in_rt(M(i)) and is_mp(M(i)))}
    out["rt_families_production_claims"] = {"value": sum(1 for i in rtc if in_rt(audit[i]) and audit[i]["production_claim"])
                                            + sum(1 for i in games if in_rt(M(i)) and M(i)["production_claim"])}
    # a live loop outside games (claim 5): both realtime-flag samples, and the flagged games (not sampled) from the model
    t_s, f_s = sm["realtime_infra_true_nongame"], sm["realtime_infra_false"]
    rt_games = [i for i in frame if frame[i]["realtime_infra"] is True and frame[i]["family"] == GAMES]
    loop_ng = lambda r: r["realtime_infra"] is True and r["family"] != GAMES
    k_t = sum(1 for i in t_s if loop_ng(audit[i]))
    put("live_loop_nongame", 0, [(k_t, len(t_s), pop["realtime_infra_true_nongame"]),
                                 (sum(1 for i in f_s if loop_ng(audit[i])), len(f_s), pop["realtime_infra_false"])],
        sum(1 for i in rt_games if loop_ng(M(i))), k=k_t, n=len(t_s))
    # games included: the live-loop rate the audit found for the games in its under-300 ms sample, applied to
    # the games the model counts, plus the non-game estimate
    fast = sm["tier_under_300ms"]
    game_fast = [i for i in fast if frame[i]["family"] == GAMES]
    rate = sum(1 for i in game_fast if audit[i]["realtime_infra"] is True) / len(game_fast)
    games_model = sum(1 for i in frame if M(i)["family"] == GAMES)
    out["live_loop_all"] = {"value": (rate * games_model + out["live_loop_nongame"]["count"]) / N,
                            "k": sum(1 for i in game_fast if audit[i]["realtime_infra"] is True), "n": len(game_fast)}
    # decisions under 300 ms (claim 6) and meta posts (claim 7): the audit's samples only
    k_fast = sum(1 for i in fast if audit[i]["tier"] in FAST)
    w = wilson(k_fast, len(fast))
    s = pop["tier_under_300ms"] / N
    out["sub300_set"] = {"value": w["p"] * s, "lo": w["lo"] * s, "hi": w["hi"] * s, "k": k_fast, "n": len(fast)}
    k_g = sum(1 for i in fast if audit[i]["tier"] in FAST and audit[i]["family"] == GAMES)
    wg = wilson(k_g, k_fast)
    out["sub300_games"] = {"value": wg["p"], "lo": wg["lo"], "hi": wg["hi"], "k": k_g, "n": k_fast}
    meta_s = sm["other_or_meta"]
    still = [i for i in meta_s if audit[i]["family"] == "other_or_meta"]
    wm = wilson(len(still), len(meta_s))
    sm_ = pop["other_or_meta"] / N
    out["meta_still"] = {"value": wm["p"] * sm_, "lo": wm["lo"] * sm_, "hi": wm["hi"] * sm_, "k": len(still), "n": len(meta_s)}
    # meta over every post (review/estimate-opus.py's audit-only construction): the re-read sample inside the model's meta
    # stratum, and the evidence samples for the posts outside it; meta_still counts the inside only
    in_meta = {i for i in frame if frame[i]["family"] == "other_or_meta"}
    out_parts = [(sum(1 for i in ids if i not in in_meta and audit[i]["family"] == "other_or_meta"), len(ids), pop[k])
                 for ids, k in ((nn, "demo_no_numbers"), (md, "measured_demo"))]
    put("meta_all_samples", sum(1 for i in prod if i not in in_meta and audit[i]["family"] == "other_or_meta"),
        [(len(still), len(meta_s), pop["other_or_meta"]), *out_parts],
        sum(1 for i in rem if i not in in_meta and M(i)["family"] == "other_or_meta"))
    sub = Counter(audit[i].get("noise") for i in still)
    k_v = sum(sub[k] for k in ("unrelated_or_unclear", "benchmark_of_the_model", "tooling_or_wrapper"))
    out["meta_vague"] = {"value": k_v / len(meta_s) * sm_, "k": k_v, "n": len(meta_s)}
    out["meta_meme"] = {"value": sub["meme_or_joke"] / len(meta_s) * sm_, "k": sub["meme_or_joke"], "n": len(meta_s)}
    out["meta_hot"] = {"value": sub["hot_take_or_commentary"] / len(meta_s) * sm_, "k": sub["hot_take_or_commentary"], "n": len(meta_s)}
    return out


MODEL_AUDIT = REVIEW / "estimate-opus.py"  # the audit's estimators with another label file as the model under test


def _pct_or_none(v: str) -> float | None:
    return None if v in ("", None) else float(v) / 100


def run_model_audit(labels_path: Path) -> dict:
    """review/estimate-opus.py for labels other than the audited Sonnet v2 labels: the source of every audited number then.

    It keeps the audit's strata, Grok's labels and review/estimate.py's estimators, takes shares of the labels' own use-case
    base, fills the regions the audit did not sample from the labels under test, and adds an audit-only variant. It is rerun
    here (half a second, deterministic) so a refresh never reads stale tables.
    """
    tag = labels_path.stem.replace("classified-", "")
    out = subprocess.run([sys.executable, str(MODEL_AUDIT), "--model", _rel(labels_path), "--tag", tag],
                         capture_output=True, text=True, cwd=ROOT, check=False)
    if out.returncode != 0:
        raise SystemExit(f"review/estimate-opus.py failed:\n{out.stderr.strip() or out.stdout.strip()}")
    d = REVIEW / "data"

    def rows(name: str) -> list[dict]:
        with open(d / f"audit-{tag}-{name}.csv", newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    est = {}
    for r in rows("estimates"):
        pct = r["unit"].startswith("%")
        conv = _pct_or_none if pct else (lambda v: None if v in ("", None) else float(v))
        est[r["key"]] = {"value": conv(r["opus_value"]), "lo": conv(r["opus_lo"]), "hi": conv(r["opus_hi"]), "model": conv(r["opus_model"]),
                         "plug": None if r["opus_plug"] == "" else float(r["opus_plug"]),
                         "audit_only": conv(r["audit_only_value"]), "audit_only_lo": conv(r["audit_only_lo"]),
                         "audit_only_hi": conv(r["audit_only_hi"]), "frame_model": conv(r["sonnet_model"]),
                         "frame_audit_only": conv(r["sonnet_audit_only_value"]), "frame_audit_only_lo": conv(r["sonnet_audit_only_lo"]),
                         "frame_audit_only_hi": conv(r["sonnet_audit_only_hi"]), "inside": r["opus_inside"], "note": r["note"],
                         "frame_value": conv(r["sonnet_value"]), "frame_lo": conv(r["sonnet_lo"]), "frame_hi": conv(r["sonnet_hi"])}
    return {"tag": tag, "estimates": est, "claims": {r["claim"]: r for r in rows("claims")},
            "agreement": {r["field"]: r for r in rows("agreement")},
            "json": json.loads((REVIEW / "work" / f"estimate-{tag}.json").read_text()),
            "files": f"review/estimate-opus.py, review/data/audit-{tag}-*.csv, review/audit-{tag}.md"}


def self_test(r: dict, E: dict) -> None:
    """With the Sonnet labels as the model, reestimate() must reproduce review/estimate.py."""
    c1, c2, c4, c5, c6, c7 = (E[f"claim{k}"] for k in (1, 2, 4, 5, 6, 7))
    pairs = [(r[f"baseline_{k}"][f], c1["corrected"][k][g] / 100) for k in ("none", "frontier_llm", "small_llm", "replacement")
             for f, g in (("value", "est_pct"), ("lo", "lo_pct"), ("hi", "hi_pct"))]
    pairs += [(r["production_strict"][f], c2[g] / 100) for f, g in (("value", "est_pct"), ("lo", "lo_pct"), ("hi", "hi_pct"))]
    pairs += [(r["rt_families"][f], c4[g] / 100) for f, g in (("value", "est_pct"), ("lo", "lo_pct"), ("hi", "hi_pct"))]
    pairs += [(r["live_loop_nongame"][f], c5[g] / 100) for f, g in (("value", "nongame_est_pct"), ("lo", "nongame_lo_pct"), ("hi", "nongame_hi_pct"))]
    pairs += [(r["sub300_games"][f], c6[g] / 100) for f, g in (("value", "conditional_pct"), ("lo", "conditional_lo_pct"), ("hi", "conditional_hi_pct"))]
    pairs += [(r["meta_still"][f], c7[g] / 100) for f, g in (("value", "est_meta_pct"), ("lo", "est_meta_lo_pct"), ("hi", "est_meta_hi_pct"))]
    pairs += [(r["meta_vague"]["value"], c7["vague_est_pct"] / 100), (r["meta_meme"]["value"], c7["meme_est_pct_of_posts"] / 100),
              (r["meta_hot"]["value"], c7["hot_est_pct_of_posts"] / 100),
              (r["rt_families_production"]["value"], c4["census_measured_production"]),
              (r["rt_families_production_claims"]["value"], c4["census_production_claim"])]
    bad = [(a, b) for a, b in pairs if abs(a - b) > 1e-9]
    if bad:
        raise SystemExit(f"reestimate() with the Sonnet labels does not reproduce review/estimate.py: {bad[:5]}")


def _write(name: str, rows: list[dict], cols: list[str]) -> None:
    OUTD.mkdir(parents=True, exist_ok=True)
    with open(OUTD / f"{name}.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else (round(r[k], 6) if isinstance(r[k], float) else r[k])) for k in cols})


def _p(x: float | None, d: int = 1) -> str:
    return "n/a" if x is None else f"{100 * x:.{d}f}%"


def _r(lo: float, hi: float, d: int = 1) -> str:
    return f"{100 * lo:.{d}f}–{100 * hi:.{d}f}%"


def _rel(p: Path) -> str:
    return str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)


def model_shares(rows: dict[str, dict], chips: dict[str, list], noise: dict[str, dict]) -> dict:
    """The labels' own shares on their own use-case base (what the page's model counts show)."""
    base = use_case_base(rows)
    n = len(base)
    b = Counter(rows[i]["baseline"] for i in base)
    fast = [i for i in base if rows[i]["tier"] in FAST]
    meta = [i for i in base if rows[i]["family"] == "other_or_meta"]
    return {
        "base": n,
        "baseline_none": b["none"] / n, "baseline_frontier_llm": b["frontier_llm"] / n, "baseline_small_llm": b["small_llm"] / n,
        "baseline_replacement": sum(b[k] for k in REPL) / n,
        "production": sum(1 for i in base if rows[i]["evidence"] == "measured_production"),
        "measured_demo": sum(1 for i in base if rows[i]["evidence"] == "measured_demo"),
        "ladder_no_measurement": sum(1 for i in base if rows[i]["evidence"] in UNMEASURED | {"commentary_or_meme"}) / n,
        "ladder_measured_demo": sum(1 for i in base if rows[i]["evidence"] == "measured_demo") / n,
        "ladder_claim_no_number": sum(1 for i in base if rows[i]["evidence"] == "demo_no_numbers" and has_csa_chip(chips.get(i))) / n,
        "ladder_demo_no_numbers": sum(1 for i in base if rows[i]["evidence"] == "demo_no_numbers" and not has_csa_chip(chips.get(i))
                                      and rows[i]["family"] != "other_or_meta") / n,
        "rt_families": sum(1 for i in base if rows[i]["family"] in RT) / n,
        "live_loop_nongame": sum(1 for i in base if rows[i]["realtime_infra"] is True and rows[i]["family"] != GAMES) / n,
        "live_loop_all": sum(1 for i in base if rows[i]["realtime_infra"] is True) / n,
        "sub300_set": len(fast) / n,
        "sub300_games": (sum(1 for i in fast if rows[i]["family"] == GAMES) / len(fast)) if fast else None,
        "meta_still": len(meta) / n,
        "meta_meme": sum(1 for i in meta if (noise.get(i) or {}).get("subtype") == "meme_or_joke") / n,
        "meta_hot": sum(1 for i in meta if (noise.get(i) or {}).get("subtype") == "hot_take_or_commentary") / n,
    }


def build(labels: Path | str | None = None, verbose: bool = False) -> dict:
    labels_path = Path(labels) if labels else AUDITED_LABELS
    if not labels_path.is_absolute():
        labels_path = (ROOT / labels_path).resolve()
    est = _module("review_estimate", REVIEW / "estimate.py")
    sample = _module("review_sample", REVIEW / "sample.py")
    strata = json.loads((REVIEW / "work" / "strata.json").read_text())
    smeta = strata["meta"]
    now = current_strata(sample)
    want = {"use_case_base": smeta["use_case_base"], **smeta["stratum_population"]}
    snapshot_ok = all(now.get(k) == v for k, v in want.items())
    if snapshot_ok:
        out = subprocess.run([sys.executable, str(REVIEW / "estimate.py")], capture_output=True, text=True, cwd=ROOT, check=False)
        if out.returncode != 0:
            raise SystemExit(f"review/estimate.py failed:\n{out.stderr.strip()}")
    else:
        moved = {k: (want[k], now.get(k)) for k in want if now.get(k) != want[k]}
        print(f"WARNING: the Sonnet v2 labels no longer give the strata the audit sampled {moved}; "
              "the audit tables describe the earlier snapshot and estimate.json is not rerun.")
    E = json.loads((REVIEW / "work" / "estimate.json").read_text())
    if "error" in E or E["labelled"] != E["expected"]:
        raise SystemExit(f"review/work/estimate.json is incomplete: {E.get('error')}")
    N = E["use_case_base"]
    sub = _json_of(REVIEW / "work" / "substance.py")
    ari = _json_of(REVIEW / "arithmetic.py") if snapshot_ok else {}

    audit = {r["id"]: r for r in _read_jsonl(REVIEW / "hand-labels-grok.jsonl")}
    if len(audit) != E["labelled"]:
        raise SystemExit(f"{AUDIT_LABELS_FILE} has {len(audit)} cards; estimate.json labelled {E['labelled']}")
    sonnet, _, _ = est.load_model()  # the frame: the Sonnet v2 labels the audit sampled from
    frame = {i: r for i, r in sonnet.items() if r["family"] != "not_a_jev_build"}
    if len(frame) != N:
        raise SystemExit(f"the audit frame has {len(frame)} posts; estimate.json says {N}")
    cards_json = json.loads((DATA / "cards.json").read_text())["cards"]
    chips = {str(c["id"]): c.get("chips") or [] for c in cards_json}
    card_of = {str(c["id"]): c for c in cards_json}
    noise = {r["id"]: r for r in _read_jsonl(DATA / "classified-noise.jsonl")}
    is_frame_labels = labels_path.resolve() == AUDITED_LABELS.resolve()
    primary = load_labels(labels_path)
    refused = [r["id"] for r in _read_jsonl(labels_path.with_name(labels_path.stem + ".errors.jsonl"))
               if "content-filter" in str(r.get("error", "")) and r["id"] not in primary]

    # ---------------------------------------------------------------- estimates for the frame labels and for the labels under test
    at_frame = reestimate(frame, frame, audit, strata, est.wilson, chips)
    self_test(at_frame, E)
    shares = model_shares(primary, chips, noise)
    mod = None if is_frame_labels else run_model_audit(labels_path)
    if is_frame_labels:
        at_primary = at_frame
    else:
        # every audited number for these labels comes from the model audit; the sample counts (k, n) are the audit's own facts
        at_primary = {}
        for key, e in mod["estimates"].items():
            f = at_frame.get(key, {})
            at_primary[key] = {**e, "k": f.get("k"), "n": f.get("n")}
        ms = mod["estimates"]["meta_still"]
        at_primary["meta_all_samples"] = {"value": ms["audit_only"], "lo": ms["audit_only_lo"], "hi": ms["audit_only_hi"], "model": ms["model"],
                                          "frame_value": ms["frame_audit_only"], "frame_lo": ms["frame_audit_only_lo"],
                                          "frame_hi": ms["frame_audit_only_hi"]}
        rt_all = [a for a in audit.values() if a["family"] in RT]
        at_primary["rt_families_production"] = {"value": sum(1 for a in rt_all if a["evidence"] == "measured_production")}
        at_primary["rt_families_production_claims"] = {"value": sum(1 for a in rt_all if a["production_claim"])}
        for key in ("baseline_none", "baseline_frontier_llm", "baseline_small_llm", "baseline_replacement", "meta_still", "sub300_set",
                    "sub300_games", "rt_families", "live_loop_nongame", "ladder_demo_no_numbers", "ladder_claim_no_number",
                    "ladder_no_measurement", "ladder_measured_demo"):
            got, want = mod["estimates"][key]["model"], shares[key]
            if want is not None and abs(got - want) > 1e-4:
                raise SystemExit(f"model audit and this script disagree on the labels' own {key}: {got} vs {want}")

    # ---------------------------------------------------------------- sampling and agreement
    sampling = []
    for key, name in STRATA:
        census = key in strata["exhaustive"]
        ids = strata["exhaustive"][key] if census else strata["samples"][key]
        sampling.append({"key": key, "stratum": name, "kind": "census" if census else "sample",
                         "population": smeta["stratum_population"][key], "reviewed": len(ids)})
    agree_primary = agreement_by_stratum(primary, audit, strata)
    agree_frame = agree_primary if is_frame_labels else agreement_by_stratum(sonnet, audit, strata)
    for r, e in zip(agree_frame, [E["agreement"][k] for k, _ in STRATA] + [E["agreement"]["all_labelled"]], strict=True):
        if any(abs(r[f] - e[f]["rate"]) > 1e-12 for f in FIELDS):  # the audit's own table, reproduced
            raise SystemExit(f"agreement for {r['key']} differs from estimate.json")
    agreement = [{"labels": _rel(labels_path), **r} for r in agree_primary]
    if not is_frame_labels:
        agreement += [{"labels": _rel(AUDITED_LABELS), **r} for r in agree_frame]
    all_primary = agree_primary[-1]
    all_frame = agree_frame[-1]

    # ---------------------------------------------------------------- estimates (shares are fractions of the audited base, N)
    c3, c8, c9, c10 = E["claim3"], E["claim8"], E["claim9"], E["claim10"]
    pb, mc, pa = E["prose_buckets"], E["material_combined"], E["prior_agreement"]
    v1 = _read_jsonl(DATA / "classified-sonnet.jsonl")
    v1_mp = sum(1 for r in v1 if r.get("evidence") == "measured_production")
    ests = []

    def add(key, label, unit, value, lo=None, hi=None, model_value=None, k=None, n=None, frame_est=None, source="", extra=None):
        fv = frame_est or {}
        ests.append({"key": key, "label": label, "unit": unit, "value": value, "lo": lo, "hi": hi, "model": model_value, "k": k, "n": n,
                     "frame_value": fv.get("value", value if unit == "share" else None), "frame_lo": fv.get("lo", lo),
                     "frame_hi": fv.get("hi", hi), "source": source, **(extra or {})})

    def add_est(key, label, model_value=None, source=""):
        e = at_primary[key]
        f = {k: e[f"frame_{k}"] for k in ("value", "lo", "hi")} if "frame_value" in e else at_frame[key]
        extra = {k: e.get(k) for k in ("audit_only", "audit_only_lo", "audit_only_hi", "plug", "frame_model", "frame_audit_only",
                                        "frame_audit_only_lo", "frame_audit_only_hi")}
        if mod is not None:
            source = f"{mod['files']} ({key})"
            model_value = e.get("model", model_value)
        add(key, label, "share", e["value"], e.get("lo"), e.get("hi"), model_value, e.get("k"), e.get("n"), f, source, extra)

    add("snapshot_matches", "The Sonnet v2 labels still give the audited strata (1 = yes)", "flag", int(snapshot_ok), source="scripts/audit.py")
    add("use_case_base", "Use-case base the audit sampled (Sonnet v2 labels)", "posts", N, source="estimate.json use_case_base")
    add("labels_base", "Use-case base on the labels under test", "posts", shares["base"], source=_rel(labels_path))
    add("estimate_base", "The base the audited shares are shares of", "posts", N if mod is None else mod["json"]["model"]["use_case_base"],
        source="estimate.json use_case_base" if mod is None else mod["files"])
    if mod is not None:
        reg = mod["json"]["model"]["regions"]
        add("plug_frontier_small", "Posts the audit did not sample that compare Jev with a frontier or small LLM (the labels fill them)", "posts",
            reg["frontier_small"], source=mod["files"])
        add("plug_remainder", "Proposal and commentary posts the audit did not sample (the labels fill them)", "posts", reg["remainder"],
            source=mod["files"])
    add("labels_refused", "Posts the labelling model refused (left out)", "posts", len(refused), source=_rel(labels_path.with_name(labels_path.stem + ".errors.jsonl")))
    add("labelled", "Cards the audit labelled", "posts", E["labelled"], source="estimate.json labelled")
    add("census_unique", "Cards in the census strata", "posts", smeta["exhaustive_unique"], source="strata.json meta")
    add("batches", "Label batches", "count", smeta["batches"], source="strata.json meta")
    add("seed", "Sampling seed", "count", smeta["seed"], source="strata.json meta")
    for f in FIELDS:
        add(f"agreement_{f}", f"Agreement of the labels under test with the audit on {f}, all audited cards", "rate", all_primary[f],
            k=round(all_primary[f] * all_primary["n"]), n=all_primary["n"], source="scripts/audit.py agreement_by_stratum")
        add(f"agreement_frame_{f}", f"Agreement of the Sonnet v2 labels with the audit on {f}, all audited cards", "rate", all_frame[f],
            k=round(all_frame[f] * all_frame["n"]), n=all_frame["n"], source="estimate.json agreement.all_labelled")
    # the measurement ladder, without framing
    add_est("ladder_demo_no_numbers", "Demos with no numbers (evidence demo_no_numbers, no cost, speed or accuracy chip, not meta)",
            shares["ladder_demo_no_numbers"], "reestimate(): evidence strata, remainder from the labels")
    add_est("ladder_claim_no_number", "A cost, speed or accuracy claim with no measurement (demo_no_numbers with such a chip)",
            shares["ladder_claim_no_number"], "reestimate(): evidence strata, remainder from the labels")
    add_est("ladder_no_measurement", "No measurement (a demo or claim with no numbers, a proposal or commentary)",
            shares["ladder_no_measurement"], "reestimate(): evidence strata, remainder from the labels")
    add_est("ladder_measured_demo", "Measured demo (a number from the author's own run)",
            shares["ladder_measured_demo"], "reestimate(): evidence strata, remainder from the labels")
    add("ladder_measured_demo_model", "Measured demos, as the labels count them", "posts", shares["measured_demo"],
        model_value=shares["measured_demo"] / shares["base"], source=_rel(labels_path))
    add("production_model", "Measured production, as the labels count them", "posts", shares["production"],
        model_value=shares["production"] / shares["base"], source=_rel(labels_path))
    add_est("production_strict", "Measured production that holds on the audit's re-read", shares["production"] / shares["base"],
            "estimate.json claim2 logic; remainder from the labels")
    add("production_first_pass", "Measured production in the first labelling pass (v1)", "share", v1_mp / len(v1), k=v1_mp, n=len(v1),
        source="data/classified-sonnet.jsonl")
    for key, label in (("none", "Compared with nothing"), ("frontier_llm", "Compared with a frontier LLM"),
                       ("small_llm", "Compared with a small LLM"), ("replacement", "Compared with the tools Jev would replace")):
        add_est(f"baseline_{key}", label, shares[f"baseline_{key}"], "estimate.json claim1 logic; frontier and small-LLM strata from the labels")
    add_est("meta_still", "Posts that stay meta on a blind re-read", shares["meta_still"], "estimate.json claim7")
    add_est("meta_all_samples", "Posts the audit calls meta, over every post (the evidence samples)", shares["meta_still"],
            "reestimate(): evidence strata, remainder from the labels")
    add_est("meta_vague", "Posts that never say what Jev decides, or benchmark or wrap the model", None, "estimate.json claim7")
    add_est("meta_meme", "Memes", shares["meta_meme"], "estimate.json claim7")
    add_est("meta_hot", "Hot takes", shares["meta_hot"], "estimate.json claim7")
    add_est("sub300_set", "Posts that need a decision in under 300 ms", shares["sub300_set"], "estimate.json claim6, Wilson")
    add_est("sub300_games", "Share of the under-300 ms posts that are games", shares["sub300_games"], "estimate.json claim6")
    add_est("rt_families", "Voice, live chat or collaboration", shares["rt_families"], "estimate.json claim4 logic; games from the labels")
    add("rt_families_production", "Voice, live chat or collaboration in measured production", "posts", at_primary["rt_families_production"]["value"],
        source="estimate.json claim4 census; games from the labels" if mod is None else "review/hand-labels-grok.jsonl, every audited post")
    add("rt_families_production_claims", "Voice, live chat or collaboration claiming production", "posts",
        at_primary["rt_families_production_claims"]["value"],
        source="estimate.json claim4 census; games from the labels" if mod is None else "review/hand-labels-grok.jsonl, every audited post")
    add_est("live_loop_nongame", "A live loop outside games", shares["live_loop_nongame"], "estimate.json claim5 logic; flagged games from the labels")
    add_est("live_loop_all", "A live loop, games included", shares["live_loop_all"], "estimate.json claim5: the games' live-loop rate times the games")
    # attention and Jev, as the audit recounted them on its base (the page recounts on the labels' own base)
    add("attention_top1_views", "Share of views on the top 1% of posts (audit base)", "share", c8["top1_share"], k=c8["top1_cards"], n=N,
        source="estimate.json claim8")
    add("attention_top1_views_excl_suspect", "The same without the suspect posts", "share", c8["top1_excl_suspect"], k=c8["suspect_n"],
        source="estimate.json claim8")
    add("attention_top1_likes", "Share of likes on the top 1% of posts", "share", c8["top1_likes_share"], source="estimate.json claim8")
    add("attention_suspect_share", "Views on the suspect posts", "share", c8["suspect_share"], k=c8["suspect_n"], source="estimate.json claim8")
    top_id = max(frame, key=lambda i: sonnet[i]["v"])
    add("attention_top_card", "Views on the single most-viewed post", "share", sonnet[top_id]["v"] / sum(sonnet[i]["v"] for i in frame),
        k=sonnet[top_id]["v"], source="review/estimate.py load_model()")
    add("attention_half_cards", "Posts that hold half of all views", "posts", c8["cards_holding_half"], source="estimate.json claim8")
    add("jev_agree", "Jev picks the Sonnet v2 family (5,943 deduplicated cards)", "share", c9["agree_pct"] / 100, k=c9["agree_sonnet"], n=c9["n"],
        source="estimate.json claim9")
    add("jev_audit_p99", "Jev matches the audit's family at 0.99 or more", "share", c9["p_ge_099_match_my_family_pct"] / 100,
        k=c9["p_ge_099_matches_my_family"], n=c9["p_ge_099_in_my_labels"], source="estimate.json claim9")
    add("jev_prior_p99", "Jev matches the earlier 120-card labels at 0.99 or more", "share",
        pa["jev_matches_prior_family"] / pa["jev_p99_in_prior"], k=pa["jev_matches_prior_family"], n=pa["jev_p99_in_prior"],
        source="estimate.json prior_agreement")
    for key, label, med, n_, x1, ones in [("cost", "cost", "cost_median", "cost_chips", "cost_median_without_1x", "cost_1x"),
                                          ("speed", "speed", "speed_median", "speed_chips", "speed_median_without_1x", "speed_1x")]:
        add(f"chips_{key}_median", f"Median {label} multiple on the claim chips", "multiple", c10[med], n=c10[n_], source="estimate.json claim10")
        add(f"chips_{key}_median_without_1x", f"Median {label} multiple without the 1x chips", "multiple", c10[x1], k=c10[ones],
            source="estimate.json claim10")
    # the candidate builds and the withdrawn buckets (the audit's own numbers)
    add("candidates", "Candidate builds (measured, realtime, turn or interaction tier, Sonnet labels)", "posts", c3["material_census_n"],
        source="estimate.json claim3.material_census_n")
    add("candidates_still_meeting", "Candidates that still meet that test on the audit's labels", "posts", c3["material_census_still_material"],
        model_value=mc["census_pct"] / 100, k=c3["material_census_still_material_nongames"], source="estimate.json claim3")
    add("candidates_combined", "Posts that meet that test, misses included", "share", mc["est_pct"] / 100, mc["lo_pct"] / 100, mc["hi_pct"] / 100,
        model_value=c3["model_pct"]["material_plus"] / 100, source="estimate.json material_combined")
    b = pb["cost_only_as_described"]
    add("cost_only_as_described", "Measured, and a batch or an incumbent already did the job", "share", b["est_pct"] / 100, b["lo_pct"] / 100,
        b["hi_pct"] / 100, model_value=c3["model_pct"]["cost_only"] / 100, source="estimate.json prose_buckets.cost_only_as_described")
    if ari:
        add("cost_only_bin_baseline_none", "Posts in the published cost-only bin with no comparison", "posts", ari["cost_only_baseline_none"],
            n=ari["cost_only_n"], source="review/arithmetic.py rules")
    # what the audit could not check (its last section), as numbers
    bs_ = E["baseline_sensitivity"]
    add("limits_frontier_stratum", "Posts with a frontier-LLM baseline (not sampled)", "posts", sum(1 for r in frame.values() if r["baseline"] == "frontier_llm"),
        k=bs_["frontier_llm"]["mine"].get("frontier_llm", 0), n=bs_["frontier_llm"]["n"],
        source="the Sonnet v2 frame; baseline_sensitivity (k of n: labelled elsewhere, still frontier)")
    add("limits_small_stratum", "Posts with a small-LLM baseline (not sampled)", "posts", sum(1 for r in frame.values() if r["baseline"] == "small_llm"),
        k=bs_["small_llm"]["mine"].get("small_llm", 0), n=bs_["small_llm"]["n"],
        source="the Sonnet v2 frame; baseline_sensitivity (k of n: labelled elsewhere, still small)")
    add("limits_unsampled_remainder", "Proposal and commentary posts left on the model's label", "posts", c3["unsampled_remainder_n"],
        source="estimate.json claim3.unsampled_remainder_n")
    dnn = [i for i, a in audit.items() if a["evidence"] == "demo_no_numbers"]
    dnn_chip = sum(1 for i in dnn if any(ch.isdigit() for chip in chips.get(i, []) for ch in str(chip)))
    add("limits_numeric_chip", "Audited demos with no numbers that still carry a numeric chip", "posts", dnn_chip, k=dnn_chip, n=len(dnn),
        source="review/hand-labels-grok.jsonl and data/cards.json chips")
    add("limits_prior_overlap", "Overlap with the earlier 120 hand labels (k: family agrees)", "posts", pa["overlap"],
        k=pa["fields"]["family"]["agree"], n=pa["overlap"], source="estimate.json prior_agreement")
    add("substance_n", "Candidate builds read for substance", "posts", sub["n"], source="review/work/substance.py")
    add("substance_distinct", "Distinct builds among them", "posts", sub["distinct_builds"], source="review/work/substance.py")
    add("substance_unavailable", "Unavailable at any price before Jev", "posts", sub["unavailable_at_any_price"], source="review/work/substance.py")

    substance = [{"kind": "before", "key": k, "label": label, "posts": sub["unavailable_at_any_price"] if k == "unavailable" else sub["before"].get(k, 0)}
                 for k, label in BEFORE]
    substance += [{"kind": "job", "key": k, "label": JOBS.get(k, k.replace("_", " ")), "posts": v}
                  for k, v in sorted(sub["job"].items(), key=lambda kv: (-kv[1], kv[0]))]
    if sum(r["posts"] for r in substance if r["kind"] == "before") != sub["n"] or sum(sub["job"].values()) != sub["n"]:
        raise SystemExit("review/work/substance.py: the prior methods or the jobs do not sum to the candidates")

    # ---------------------------------------------------------------- the production census, card by card
    production = []
    for i in strata["exhaustive"]["measured_production"]:
        a = audit[i]
        production.append({"id": i, "model_evidence": sonnet[i]["evidence"], "primary_evidence": (primary.get(i) or {}).get("evidence", ""),
                           "audit_evidence": a["evidence"], "holds": int(a["evidence"] == "measured_production"), "audit_family": a["family"],
                           "audit_realtime": int(bool(a["realtime_infra"])), "views": sonnet[i]["v"],
                           "title": card_of.get(i, {}).get("t", ""), "url": card_of.get(i, {}).get("url", ""), "note": a.get("note", "")})

    census_prod = set(strata["exhaustive"]["measured_production"])
    others = [i for i in use_case_base(primary) if primary[i]["evidence"] == "measured_production" and i not in census_prod]
    seen = [i for i in others if i in audit]
    add("production_primary_other", "Production posts on the labels under test outside the audit's re-read "
        "(n: the audit labelled them in its samples; k: it calls them measured production)", "posts", len(others),
        k=sum(1 for i in seen if audit[i]["evidence"] == "measured_production"), n=len(seen), source=_rel(labels_path))
    in_census = [i for i in census_prod if (primary.get(i) or {}).get("evidence") == "measured_production"]
    add("production_primary_in_census", "Production posts on the labels under test that the audit re-read (k: hold)", "posts",
        len(in_census), k=sum(1 for i in in_census if audit[i]["evidence"] == "measured_production"), n=len(in_census),
        source=_rel(labels_path))
    batch_mp = [i for i, a in audit.items() if a["evidence"] == "measured_production" and i not in census_prod]
    add("production_audit_unconfirmed", "Posts the audit's first-pass labels call measured production outside its re-read "
        "(k: the labels under test agree)", "posts", len(batch_mp),
        k=sum(1 for i in batch_mp if (primary.get(i) or {}).get("evidence") == "measured_production"), n=len(batch_mp),
        source="review/hand-labels-grok.jsonl")

    # ---------------------------------------------------------------- the ten claims (wording and verdicts quoted from the audit)
    # The corrected values are the audit's own, with the Sonnet labels as the model. Claim 3's framing-based
    # parts (its demo and hype rules) are left out: the framing field is withdrawn.
    c1, c2, c4, c5, c6, c7 = (E[f"claim{k}"] for k in (1, 2, 4, 5, 6, 7))
    cb = c1["corrected"]
    w_fast = est.wilson(c6["sample_i_still_call_fast"], c6["sample_n"])
    fast_scale = c6["model_fast_n"] / N

    def q(key: str) -> dict:
        return next(r for r in ests if r["key"] == key)

    claims = [
        {"claim": 1, "topic": "Comparison baselines",
         "published": "81.5% compare Jev with nothing, 11.9% with a frontier LLM, 3.0% with a small LLM, 3.6% with the thing Jev would replace",
         "corrected": f"{_p(cb['none']['est_pct'] / 100)} nothing, {_p(cb['frontier_llm']['est_pct'] / 100)} frontier LLM, "
                      f"{_p(cb['small_llm']['est_pct'] / 100)} small LLM, {_p(cb['replacement']['est_pct'] / 100)} the tools Jev would replace",
         "interval": "; ".join(_r(cb[k]["lo_pct"] / 100, cb[k]["hi_pct"] / 100) for k in ("none", "frontier_llm", "small_llm", "replacement")),
         "verdict": "Fails"},
        {"claim": 2, "topic": "Production with numbers",
         "published": "at most 1.6%; 0.9% on a re-read; 0.3% on the strict label",
         "corrected": f"{_p(c2['est_pct'] / 100, 2)} ({c2['hold_on_reread']} of {c2['model_strict_n']} strict cards hold)",
         "interval": f"{c2['lo_pct']:.2f}–{c2['hi_pct']:.1f}%", "verdict": "Holds with correction"},
        {"claim": 3, "topic": "The bucket scheme",
         "published": "about 38% demos with no numbers; about 12% hype; about 23% cost-only; 1.6% (90 posts) materially different, 87 outside games",
         "corrected": f"the demo and hype rules rest on the framing field, since withdrawn; {_p(q('cost_only_as_described')['value'])} of posts fit the "
                      f"cost-only description, not {_p(c3['model_pct']['cost_only'] / 100)}; {c3['material_census_still_material']} of the 91 still "
                      f"meet the material test ({_p(mc['census_pct'] / 100, 2)}; {_p(mc['est_pct'] / 100)} with misses), and none did something "
                      f"unavailable before",
         "interval": f"{_r(q('cost_only_as_described')['lo'], q('cost_only_as_described')['hi'])} cost-only; "
                     f"{_r(q('candidates_combined')['lo'], q('candidates_combined')['hi'])} material",
         "verdict": "Fails"},
        {"claim": 4, "topic": "Voice, live chat and collaboration",
         "published": "2.8% of posts, none in production",
         "corrected": f"{_p(c4['est_pct'] / 100)} of posts; {c4['census_measured_production']} in production; "
                      f"{c4['census_production_claim']} claiming production",
         "interval": _r(c4["lo_pct"] / 100, c4["hi_pct"] / 100), "verdict": "Holds with correction"},
        {"claim": 5, "topic": "A live loop",
         "published": "about a fifth of posts; 5 to 10 percent outside games",
         "corrected": f"{_p(c5['nongame_est_pct'] / 100)} outside games; about a fifth with games ({_p(at_frame['live_loop_all']['value'])})",
         "interval": f"{_r(c5['nongame_lo_pct'] / 100, c5['nongame_hi_pct'] / 100)} outside games", "verdict": "Holds"},
        {"claim": 6, "topic": "Decisions under 300 ms",
         "published": "of posts that need a decision in under 300 ms, about 91% are games",
         "corrected": f"{_p(c6['conditional_pct'] / 100)} are games; the set is {_p(w_fast['p'] * fast_scale)} of posts, not "
                      f"{_p(c6['model_fast_n'] / N, 0)}",
         "interval": f"{_r(c6['conditional_lo_pct'] / 100, c6['conditional_hi_pct'] / 100)} games; "
                     f"{_r(w_fast['lo'] * fast_scale, w_fast['hi'] * fast_scale)} of posts",
         "verdict": "Holds"},
        {"claim": 7, "topic": "Posts that never say what Jev decides",
         "published": "a fifth never say what Jev decides, or are benchmarks or wrappers; memes and hot takes about 1% each",
         "corrected": f"{_p(c7['est_meta_pct'] / 100)} stay meta; {_p(c7['vague_est_pct'] / 100)} vague, a benchmark or a wrapper; "
                      f"memes {_p(c7['meme_est_pct_of_posts'] / 100, 2)}, hot takes {_p(c7['hot_est_pct_of_posts'] / 100, 2)}",
         "interval": f"{_r(c7['est_meta_lo_pct'] / 100, c7['est_meta_hi_pct'] / 100)} still meta", "verdict": "Fails"},
        {"claim": 8, "topic": "Attention",
         "published": "half of all views sit on 1% of posts",
         "corrected": f"the top 1% ({c8['top1_cards']} posts) hold {_p(c8['top1_share'])} of views; {_p(c8['top1_excl_suspect'])} without the "
                      f"{c8['suspect_n']} suspect posts; {_p(c8['top1_likes_share'])} of likes",
         "interval": "a census, no sampling", "verdict": "Holds with correction"},
        {"claim": 9, "topic": "Jev as a classifier",
         "published": "Jev agreed with the model on 77% of cards, and was right 27 of 28 times at 0.99 or more",
         "corrected": f"{_p(c9['agree_pct'] / 100)} ({c9['agree_sonnet']:,} of {c9['n']:,}); {pa['jev_matches_prior_family']} of "
                      f"{pa['jev_p99_in_prior']}; {_p(c9['p_ge_099_match_my_family_pct'] / 100)} on the audit's {c9['p_ge_099_in_my_labels']} cards "
                      f"at 0.99 or more",
         "interval": "a census of Jev's calls", "verdict": "Holds"},
        {"claim": 10, "topic": "The claimed multiples",
         "published": "the median claim is about 28× cheaper and 6× faster",
         "corrected": f"{c10['cost_median']:g}× cheaper ({c10['cost_chips']} chips), {c10['speed_median']:g}× faster ({c10['speed_chips']} chips); "
                      f"{c10['cost_median_without_1x']:g}× and {c10['speed_median_without_1x']:g}× without the 1× chips",
         "interval": "a census of the chips", "verdict": "Holds"},
    ]

    _write("13_audit_sampling", sampling, ["key", "stratum", "kind", "population", "reviewed"])
    _write("13_audit_agreement", agreement, ["labels", "key", "stratum", "n"] + FIELDS)
    _write("13_audit_estimates", ests, ["key", "label", "unit", "value", "lo", "hi", "model", "k", "n", "frame_value", "frame_lo", "frame_hi",
                                        "audit_only", "audit_only_lo", "audit_only_hi", "plug", "frame_model", "frame_audit_only",
                                        "frame_audit_only_lo", "frame_audit_only_hi", "source"])
    _write("13_audit_substance", substance, ["kind", "key", "label", "posts"])
    subm = _module("review_substance", REVIEW / "work" / "substance.py")  # the card-by-card read behind the counts
    _write("13_audit_substance_cards", [{"id": i, "job": job, "before": before, "second_post": dup} for i, job, before, dup in subm.ROWS],
           ["id", "job", "before", "second_post"])
    _write("13_audit_production", production, ["id", "model_evidence", "primary_evidence", "audit_evidence", "holds", "audit_family",
                                               "audit_realtime", "views", "title", "url", "note"])
    for c in claims:  # the model audit's reading of each claim with the labels under test
        m = (mod or {}).get("claims", {}).get(str(c["claim"]), {})
        c["labels_value"], c["labels_audit"], c["labels_verdict"] = m.get("opus_labels", ""), m.get("opus_audit", ""), m.get("opus_verdict", "")
        for k in ("labels_value", "labels_audit"):  # framing is withdrawn: no published number may rest on it
            c[k] = "; ".join(part for part in c[k].split("; ") if "framing" not in part.lower())
    _write("13_audit_claims", claims, ["claim", "topic", "published", "corrected", "interval", "verdict", "labels_value", "labels_audit",
                                       "labels_verdict"])
    kap = (mod or {}).get("agreement", {})
    _write("13_audit_primary_agreement", [{"field": f, "n": all_primary["n"], "agree": round(all_primary[f] * all_primary["n"]), "rate": all_primary[f],
                                           "frame_rate": all_frame[f], "kappa": kap.get(f, {}).get("model_kappa", ""),
                                           "frame_kappa": kap.get(f, {}).get("sonnet_kappa", ""), "labels": _rel(labels_path)} for f in FIELDS],
           ["field", "n", "agree", "rate", "frame_rate", "kappa", "frame_kappa", "labels"])
    if mod is not None:
        for f in FIELDS:
            if abs(float(kap[f]["model_rate"]) - all_primary[f]) > 1e-6 or abs(float(kap[f]["sonnet_rate"]) - all_frame[f]) > 1e-6:
                raise SystemExit(f"agreement on {f}: the model audit and this script disagree")

    summary = {
        "document": AUDIT_DOC,
        "labels_file": AUDIT_LABELS_FILE,
        "auditor": AUDITOR,
        "audited_labels": _rel(AUDITED_LABELS),
        "audited_model": AUDITED_MODEL,
        "labels_under_test": _rel(labels_path),
        "labels_are_frame": is_frame_labels,
        "labels_refused": refused,
        "snapshot_matches": snapshot_ok,
        "use_case_base": N,
        "labelled": E["labelled"],
        "verdicts": dict(Counter(c["verdict"] for c in claims)),
        "labels_verdicts": dict(Counter(c["labels_verdict"] for c in claims if c["labels_verdict"])),
        "model_audit": None if mod is None else {"files": mod["files"], "document": f"review/audit-{mod['tag']}.md",
                                                 "base": mod["json"]["model"]["use_case_base"],
                                                 "production": mod["json"]["sanity"]["production"]},
        "estimates": {r["key"]: {k: r[k] for k in ("value", "lo", "hi", "model", "k", "n", "frame_value", "frame_lo", "frame_hi", "audit_only",
                                                   "audit_only_lo", "audit_only_hi", "plug", "frame_model", "frame_audit_only",
                                                   "frame_audit_only_lo", "frame_audit_only_hi") if r.get(k) is not None}
                      for r in ests},
        "substance": {r["key"]: r["posts"] for r in substance if r["kind"] == "before"},
        "primary_agreement": {f: all_primary[f] for f in FIELDS},
        "frame_agreement": {f: all_frame[f] for f in FIELDS},
    }
    if verbose:
        print(json.dumps({k: summary[k] for k in ("labels_under_test", "snapshot_matches", "use_case_base", "labelled", "verdicts", "substance",
                                                  "primary_agreement", "frame_agreement", "labels_refused")}, indent=1))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labels", default=None, help="the labels under test (default data/classified-sonnet-v2.jsonl)")
    args = ap.parse_args()
    build(args.labels, verbose=True)
    print("wrote report/data/13_audit_*.csv")
    return 0


def candidate_ids() -> list[str]:
    """The 91 candidate builds the audit read for substance (review/work/strata.json)."""
    return list(json.loads((REVIEW / "work" / "strata.json").read_text())["exhaustive"]["material"])


def production_census() -> dict[str, bool]:
    """The audit's re-read of every card the Sonnet v2 labels call measured production: id -> holds."""
    strata = json.loads((REVIEW / "work" / "strata.json").read_text())
    audit = {r["id"]: r for r in _read_jsonl(REVIEW / "hand-labels-grok.jsonl")}
    return {i: audit[i]["evidence"] == "measured_production" for i in strata["exhaustive"]["measured_production"]}


if __name__ == "__main__":
    sys.exit(main())
