#!/usr/bin/env python3
"""Helpers for scripts/refresh.sh. Run from the jev-landscape folder.

    python3 scripts/refresh_report.py cap USAGE_FILE PLUS
        print the spend already recorded in USAGE_FILE plus PLUS dollars (the MAX_USD for a run)
    python3 scripts/refresh_report.py coverage
        say which cards in data/cards.json still lack a Sonnet v2 label, a reference label (LABELS, default
        data/classified-opus.jsonl; posts its safety filter refused do not count as missing), a Jev label or,
        for the reference labels' noise cards, a sub-type; exit 1 if any do
    python3 scripts/refresh_report.py missing-ids LABELS_FILE OUT_FILE
        write the ids of data/cards.json that LABELS_FILE lacks (refusals left out) to OUT_FILE as jsonl
        ({"id": ...} per line, the format of classify-model.ts --ids) and print how many
    python3 scripts/refresh_report.py report BEFORE_DIR
        print what the refresh changed: cards before and after, new cards by posting day,
        the headline numbers before and after, the measurement ladder, and whether the
        independent audit still describes this base (BEFORE_DIR holds cards.json,
        summary.json and 08_ladder.csv from before the refresh)
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REPORT = ROOT / "report"
MOVE = 0.005  # flag a share that moved by more than half a percentage point


def read_jsonl(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()] if p.exists() else []


def day_of(card_id: str) -> str:
    return datetime.fromtimestamp(((int(card_id) >> 22) + 1288834974657) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def cmd_cap(usage: str, plus: str) -> None:
    spent = sum(float(r.get("usd", 0)) for r in read_jsonl(Path(usage)))
    print(f"{spent + float(plus):.4f}")


def noise_ids(cards: set[str], labels: dict[str, dict]) -> set[str]:
    return {
        i for i in cards if i in labels
        and (labels[i]["family"] == "other_or_meta" or (labels[i]["evidence"] == "commentary_or_meme" and labels[i]["family"] != "not_a_jev_build"))
    }


REFERENCE = os.environ.get("LABELS", "data/classified-opus.jsonl")


def refused(labels_file: Path) -> set[str]:
    """Posts the labelling model's safety filter refused (its .errors.jsonl): left out, not missing."""
    errs = labels_file.with_name(labels_file.stem + ".errors.jsonl")
    return {str(r["id"]) for r in read_jsonl(errs) if "content-filter" in str(r.get("error", ""))}


def labelled(labels_file: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in read_jsonl(labels_file):
        out.setdefault(str(r["id"]), r)
    return out


def cmd_coverage() -> int:
    ids = {str(c["id"]) for c in json.loads((DATA / "cards.json").read_text())["cards"]}
    v2 = labelled(DATA / "classified-sonnet-v2.jsonl")
    ref_file = ROOT / REFERENCE
    ref = labelled(ref_file) if ref_file.exists() else v2
    jev = {r["id"] for r in read_jsonl(DATA / "classified-jev.jsonl")}
    sub = {r["id"] for r in read_jsonl(DATA / "classified-noise.jsonl")}
    nz = noise_ids(ids, ref)
    gaps = {"Sonnet v2 label": len(ids - set(v2))}
    if ref_file.exists() and ref_file.name != "classified-sonnet-v2.jsonl":
        gaps["reference label"] = len(ids - set(ref) - refused(ref_file))
    gaps.update({"Jev label": len(ids - jev), "noise sub-type": len(nz - sub)})
    print(f"coverage: {len(ids):,} cards; " + "; ".join(f"missing {k}: {v}" for k, v in gaps.items())
          + f" ({len(nz):,} noise cards on {REFERENCE if ref_file.exists() else 'data/classified-sonnet-v2.jsonl'})")
    return 1 if any(gaps.values()) else 0


def cmd_missing_ids(labels_file: str, out_file: str) -> None:
    ids = [str(c["id"]) for c in json.loads((DATA / "cards.json").read_text())["cards"]]
    lf = ROOT / labels_file
    have = set(labelled(lf)) | refused(lf)
    todo = [i for i in ids if i not in have]
    Path(out_file).write_text("".join(json.dumps({"id": i}) + "\n" for i in todo))
    print(len(todo))


# ---------------------------------------------------------------- the before/after report
def get(d: dict, path: str):
    for k in path.split("."):
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


SHARES = [  # (label, summary.json path) for shares: before, after and the change in points
    ("top 1% of posts: share of views", "concentration.top1pct_views"),
    ("top 1% of posts: share of likes", "concentration.top1pct_likes"),
    ("top 1% views, without the top post", "concentration.top1pct_views_excl_top_card"),
    ("top 1% views, without the low-like-rate posts", "concentration.top1pct_views_excl_suspect"),
    ("production, at most (first pass)", "production.v1_share"),
    ("production on re-read", "production.reread_share"),
    ("measured production (v2)", "production.v2_share"),
    ("production claims (v2)", "production.v2_production_claim_share"),
    ("baseline: nothing", "baseline_shares.none"),
    ("baseline: frontier LLM", "baseline_shares.frontier_llm"),
    ("baseline: small LLM", "baseline_shares.small_llm"),
    ("baseline: classic ML, rules or vendor API", "baseline_shares.incumbent_classic_rules_vendor"),
    ("realtime families: share of posts", "realtime_families.share_posts"),
    ("realtime families: share of views", "realtime_families.share_views"),
    ("realtime families: share of likes", "realtime_families.share_likes"),
    ("realtime_infra flag: share of posts", "realtime.share_posts"),
    ("realtime_infra flag outside games", "realtime.non_game_share_of_all_posts"),
    ("realtime, 120-card hand calibration", "realtime.hand_sample.calibrated_all.estimate"),
    ("realtime outside games, 120-card hand calibration", "realtime.hand_sample.calibrated_non_game.estimate"),
    ("ladder: no measurement (labels)", "ladder.no_measurement.share_posts"),
    ("ladder: measured demo (labels)", "ladder.measured_demo.share_posts"),
    ("noise: share of posts (labels)", "noise.share_posts"),
    ("Japanese posts", "language.ja"),
    ("Jev agrees with the reference labels", "agreement.jev_vs_v2"),
    ("Jev agrees at 0.99 or more", "agreement.top_bin_agreement_v2"),
]
COUNTS = [
    ("posts (cards)", "posts"),
    ("authors", "authors"),
    ("use-case base", "use_case_base"),
    ("not_a_jev_build", "not_a_jev_build"),
    ("duplicates merged", "duplicates_merged"),
    ("realtime-family posts", "realtime_families.cards"),
    ("measured production posts (labels)", "production.v2_measured_production"),
    ("measured production confirmed by the audit", "ladder.measured_production.confirmed_by_audit"),
    ("candidate builds in the base", "candidates.in_base"),
    ("noise posts", "noise.posts"),
]


def pp(x) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def table(rows: list[list[str]], head: list[str]) -> str:
    w = [max(len(str(r[i])) for r in [head] + rows) for i in range(len(head))]
    fmt = lambda r: "  ".join(str(c).ljust(w[i]) if i == 0 else str(c).rjust(w[i]) for i, c in enumerate(r))  # noqa: E731
    return "\n".join([fmt(head), fmt(["-" * x for x in w])] + [fmt(r) for r in rows])


def ladder(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return {r["step"]: r for r in csv.DictReader(open(path))}


AUDITED = [  # (label, summary.json audit.estimates key): the audit's corrected estimates, for the record of each run
    ("compared with nothing", "baseline_none"),
    ("compared with the tools Jev would replace", "baseline_replacement"),
    ("demos with no numbers", "ladder_demo_no_numbers"),
    ("a cost, speed or accuracy claim with no number", "ladder_claim_no_number"),
    ("measured production", "production_strict"),
    ("voice, live chat or collaboration", "rt_families"),
    ("a live loop outside games", "live_loop_nongame"),
    ("meta posts", "meta_still"),
    ("under-300 ms posts", "sub300_set"),
]


def cmd_report(before_dir: str) -> None:
    bd = Path(before_dir)
    b_cards = {str(c["id"]): c for c in json.loads((bd / "cards.json").read_text())["cards"]}
    a_raw = json.loads((DATA / "cards.json").read_text())
    a_cards = {str(c["id"]): c for c in a_raw["cards"]}
    meta = a_raw["meta"]
    b_sum = json.loads((bd / "summary.json").read_text())
    a_sum = json.loads((REPORT / "summary.json").read_text())

    new = sorted(set(a_cards) - set(b_cards))
    gone = sorted(set(b_cards) - set(a_cards))
    changed = [i for i in set(a_cards) & set(b_cards) if (a_cards[i].get("v"), a_cards[i].get("f")) != (b_cards[i].get("v"), b_cards[i].get("f"))]
    dv = sum(int(a_cards[i].get("v") or 0) - int(b_cards[i].get("v") or 0) for i in changed)
    print("=" * 78)
    print("REFRESH SUMMARY")
    print("=" * 78)
    print(f"Feed: {meta.get('latest_snapshot')} (updated {meta.get('updated')}); {meta.get('feed_cards', 0):,} of its cards are in the window, "
          f"{meta.get('kept_from_earlier', 0)} kept from earlier snapshots, {meta.get('cut_after_through', 0)} posted after {meta.get('through')} left out.")
    print(f"Cards: {len(b_cards):,} before -> {len(a_cards):,} after ({len(new):+,} new, {len(gone)} gone).")
    print(f"Existing cards with changed views or likes: {len(changed)} ({dv:+,} views).")
    if new:
        by_day = Counter(day_of(i) for i in new)
        print("\nNew cards by posting day (UTC):")
        print(table([[d, f"{n:,}"] for d, n in sorted(by_day.items())], ["day", "new cards"]))
    b_last, a_last = get(b_sum, "window_utc"), get(a_sum, "window_utc")
    if b_last and a_last:
        print(f"\nLast post: {b_last[1][:16]} UTC -> {a_last[1][:16]} UTC.")

    rows = []
    for label, path in COUNTS:
        b, a = get(b_sum, path), get(a_sum, path)
        rows.append([label, "n/a" if b is None else f"{b:,}", "n/a" if a is None else f"{a:,}", "" if b is None or a is None else f"{a - b:+,}"])
    print("\nCounts:")
    print(table(rows, ["", "before", "after", "change"]))

    moved = []
    rows = []
    for label, path in SHARES:
        b, a = get(b_sum, path), get(a_sum, path)
        d = None if b is None or a is None else a - b
        flag = "  <-- moved > 0.5 pt" if d is not None and abs(d) > MOVE else ""
        if flag:
            moved.append(f"{label}: {pp(b)} -> {pp(a)}")
        rows.append([label, pp(b), pp(a), "" if d is None else f"{100 * d:+.2f} pt{flag}"])
    print("\nHeadline shares (share of the use-case base unless the label says otherwise):")
    print(table(rows, ["", "before", "after", "change"]))

    chips = []
    for key, label in [("cost multiple (N× cheaper)", "cost claim, median"), ("speed multiple (N× faster)", "speed claim, median")]:
        b, a = get(b_sum, f"chips.{key}"), get(a_sum, f"chips.{key}")
        if b and a:
            chips.append([label, f"{b['median']:.3g}x ({b['median_without_1x']:.3g}x)", f"{a['median']:.3g}x ({a['median_without_1x']:.3g}x)"])
    if chips:
        print("\nClaim chips (median, and without the 1x chips):")
        print(table(chips, ["", "before", "after"]))

    bl, al = ladder(bd / "08_ladder.csv"), ladder(REPORT / "data" / "08_ladder.csv")
    rows = []
    for k in al or bl:
        b, a = bl.get(k), al.get(k)
        bs = float(b["share_posts"]) if b else None
        as_ = float(a["share_posts"]) if a else None
        d = None if bs is None or as_ is None else as_ - bs
        flag = "  <-- moved > 0.5 pt" if d is not None and abs(d) > MOVE else ""
        if flag:
            moved.append(f"ladder {k}: {pp(bs)} -> {pp(as_)} of posts")
        rows.append([k, b["posts"] if b else "", a["posts"] if a else "", pp(bs), pp(as_), "" if d is None else f"{100 * d:+.2f} pt{flag}",
                     pp(float(b["share_views"])) if b else "", pp(float(a["share_views"])) if a else ""])
    print("\nMeasurement ladder (the reference labels' evidence field):")
    print(table(rows, ["step", "posts", "posts", "share", "share", "change", "views", "views"]))
    print("  (columns: before, after)")

    au = get(a_sum, "audit") or {}
    if au:
        est = au.get("estimates", {})
        def pa(x) -> str:  # small shares keep two decimals (production is 0.14%)
            return "n/a" if x is None else (f"{100 * x:.2f}%" if x < 0.01 else pp(x))

        rows = [[label, pa(get(est, f"{key}.value")),
                 "" if get(est, f"{key}.lo") is None else f"{pa(get(est, f'{key}.lo'))} to {pa(get(est, f'{key}.hi'))}"] for label, key in AUDITED]
        vd = au.get("verdicts", {})
        print(f"\nIndependent audit ({au.get('document')}): {au.get('labelled', 0):,} cards labelled blind; claims: "
              + ", ".join(f"{k} {v}" for k, v in vd.items()) + ".")
        print(table(rows, ["audited estimate", "share", "95% interval"]))
        if not au.get("snapshot_matches", False):
            print("NOTE: the audit sampled an earlier state of the Sonnet v2 labels; its numbers describe that base, and the page is"
                  " not rebuilt until the audit is redone.")

    bn, an = get(b_sum, "noise.subtypes") or {}, get(a_sum, "noise.subtypes") or {}
    if an:
        rows = []
        for k in an:
            b, a = bn.get(k), an.get(k)
            d = None if not b else a["share_noise"] - b["share_noise"]
            flag = "  <-- moved > 0.5 pt" if d is not None and abs(d) > MOVE else ""
            rows.append([k, b["posts"] if b else "", a["posts"], pp(b["share_noise"]) if b else "", pp(a["share_noise"]), "" if d is None else f"{100 * d:+.2f} pt{flag}"])
        print("\nNoise sub-types (share of the noise):")
        print(table(rows, ["sub-type", "posts", "posts", "share", "share", "change"]))
        print("  (columns: before, after)")

    print("\nMoved by more than half a point:" if moved else "\nNo headline share moved by more than half a point.")
    for m in moved:
        print(f"  - {m}")
    if get(a_sum, "observations.stale"):
        wf = get(a_sum, "observations.written_for")
        print(f"\nNOTE: the observation paragraphs in report/landscape.md (scripts/observations.md) were written for the {wf['feed']} "
              f"snapshot ({wf['posts']:,} posts). landscape.md says so at the top. The page, the charts, the tables, the headline "
              f"numbers and the noise section are regenerated from this run.")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "cap":
        cmd_cap(*args)
        return 0
    if cmd == "coverage":
        return cmd_coverage()
    if cmd == "missing-ids":
        cmd_missing_ids(*args)
        return 0
    if cmd == "report":
        cmd_report(*args)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
