#!/usr/bin/env python3
"""
Step 3 (v2 labels, v3 report): join the cards, the reference labels (Sonnet v2 by default, and
v1 for comparison), the Jev labels, the review's hand labels and the independent audit; remove
duplicates; compute every table; write report/data/*.csv, report/landscape.md and report/summary.json.

    python3 scripts/analyze.py            (from the jev-landscape folder)
    python3 scripts/analyze.py --labels data/classified-opus.jsonl --labels-model "Claude Opus 5.5"

Inputs (data/): cards.json; the reference labels (--labels, or the LABELS environment variable;
default classified-sonnet-v2.jsonl; --labels-model or LABELS_MODEL names the model that made them,
otherwise it is read from the file name); classified-sonnet.jsonl (v1), classified-jev.jsonl,
hand-labels-120.jsonl, hand-labels-disputes.jsonl, usage-*.jsonl, pilot/*.jsonl, *.errors.jsonl;
and the independent audit in review/ (scripts/audit.py runs its scripts and writes
report/data/13_audit_*.csv; the audit always describes the Sonnet v2 labels it sampled from).

What v2 changes (review: Brain work/content/drafts/jev-landscape-review.md, §6):
- labels come from rubric v2 (scripts/rubric.ts, report/rubric.md);
- duplicates are merged (scripts/dedupe.py) and not_a_jev_build cards are left out
  of every use-case table (their count and share are reported);
- rubric rule 3 (a benchmark on a named task belongs to that task's family) is
  enforced for the Laya-vs-Jev Snake card if Sonnet did not apply it;
- likes are shown next to views, with medians by posting day;
- v3 (2026-09-24): the noise / hype / demo / cost-only / material buckets failed the independent
  audit (review/critical-review-grok.md) and are withdrawn; their three tables on these labels are
  kept for the record in report/v1/buckets-on-v2-labels.md (scripts/buckets-reviewed.py). The report
  uses a three-step measurement ladder instead, gives the audited estimates with their intervals,
  and publishes the audit's sampling, agreement and verdict tables;
- the accuracy and latency chip medians are dropped; cost and speed multiples stay;
- production examples come from the review's re-read of the 95 production cards;
- agreement is Jev against the reference labels and against the 120 hand labels.

Observations under each table come from scripts/observations.md ("## <key>").
Charts are not drawn (no matplotlib on this machine); every table is a CSV.
"""
from __future__ import annotations

import argparse
import json
SKIPPED_OUTSIDE_BASE = set()  # label rows for cards outside the frozen base (posted after the cut-off)
import math
import os
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REPORT = ROOT / "report"
OUTD = REPORT / "data"
OUTD.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "scripts"))
from audit import AUDITED_MODEL, AUDITOR, candidate_ids, production_census  # noqa: E402
from audit import build as audit_build  # noqa: E402
from dedupe import find_duplicates  # noqa: E402
from hand_agreement import FIELDS as HAND_FIELDS  # noqa: E402
from hand_agreement import V1_REVIEW, load_hand, wilson  # noqa: E402
from hand_agreement import score as hand_score  # noqa: E402

# ---------------------------------------------------------------- the reference labels (one flag)
_ap = argparse.ArgumentParser(description="Jev landscape analysis: tables, landscape.md and summary.json.")
_ap.add_argument("--labels", default=os.environ.get("LABELS") or "data/classified-opus.jsonl",
                 help="reference label file (default data/classified-opus.jsonl, Claude Opus 5.5; env LABELS)")
_ap.add_argument("--labels-model", default=os.environ.get("LABELS_MODEL") or None,
                 help="the model that made the labels, as the report should name it (env LABELS_MODEL)")
ARGS = _ap.parse_args()
LABELS_PATH = (Path(ARGS.labels) if Path(ARGS.labels).is_absolute() else ROOT / ARGS.labels).resolve()
if not LABELS_PATH.exists():
    raise SystemExit(f"label file not found: {LABELS_PATH}")
AUDITED = LABELS_PATH == (DATA / "classified-sonnet-v2.jsonl").resolve()  # the labels the audit sampled from


def _model_from_name(p: Path) -> str:
    n = p.name.lower()
    for key, name in (("sonnet", "Claude Sonnet 5"), ("opus", "Claude Opus"), ("haiku", "Claude Haiku"), ("fable", "Claude Fable")):
        if key in n:
            return name
    return p.stem


def usage_files(p: Path) -> list[Path]:
    """The usage log of a label file: usage-<stem>.jsonl, or usage-<stem>*.jsonl (classify-model.ts adds the model version)."""
    exact = p.with_name(p.name.replace("classified-", "usage-"))
    return [exact] if exact.exists() else sorted(p.parent.glob(p.stem.replace("classified-", "usage-") + "*.jsonl"))


def _model_from_usage(p: Path) -> str | None:
    """'anthropic/claude-opus-5.5' in the usage rows -> 'Claude Opus 5.5'."""
    for f in usage_files(p):
        for line in f.read_text().splitlines():
            m = json.loads(line).get("model") if line.strip() else None
            if m:
                parts = m.split("/")[-1].split("-")
                return " ".join(w if any(ch.isdigit() for ch in w) else w.capitalize() for w in parts)
    return None


LABELS_MODEL = ARGS.labels_model or _model_from_usage(LABELS_PATH) or _model_from_name(LABELS_PATH)
LABELS_SHORT = LABELS_MODEL.replace("Claude ", "").split()[0]  # "Sonnet", "Opus"
LABELS_TAG = "Sonnet v2" if AUDITED else LABELS_SHORT  # how the tables and the prose name the reference labels
LABELS_REL = str(LABELS_PATH.relative_to(ROOT)) if LABELS_PATH.is_relative_to(ROOT) else str(LABELS_PATH)
# cards the labelling model's safety filter refused (logged by classify-model.ts); they are left out
REFUSED = [r["id"] for r in (json.loads(line) for line in LABELS_PATH.with_name(LABELS_PATH.stem + ".errors.jsonl").read_text().splitlines()
                             if line.strip()) if "content-filter" in str(r.get("error", ""))] \
    if LABELS_PATH.with_name(LABELS_PATH.stem + ".errors.jsonl").exists() else []

FAMILIES_V1 = [
    "evals_and_judging",
    "classification_routing_triage",
    "moderation_and_guardrails",
    "agent_harness_and_tool_gating",
    "compaction_and_context",
    "search_rerank_extraction",
    "browser_and_computer_use",
    "voice_and_turn_taking",
    "live_chat_streams_events",
    "collaboration_and_typing",
    "games_control_loops_simulation",
    "data_and_telemetry",
    "trading_and_markets",
    "other_or_meta",
]
NOT_JEV = "not_a_jev_build"
FAMILIES_V2 = FAMILIES_V1[:-1] + [NOT_JEV, "other_or_meta"]
USE_CASE_FAMILIES = [f for f in FAMILIES_V1]  # the tables: every v2 family except not_a_jev_build
GAMES = "games_control_loops_simulation"
RT_FAMILIES = ["voice_and_turn_taking", "live_chat_streams_events", "collaboration_and_typing"]
SHORT = {
    "evals_and_judging": "evals",
    "classification_routing_triage": "classify",
    "moderation_and_guardrails": "moderate",
    "agent_harness_and_tool_gating": "agent",
    "compaction_and_context": "context",
    "search_rerank_extraction": "search",
    "browser_and_computer_use": "browser",
    "voice_and_turn_taking": "voice",
    "live_chat_streams_events": "live",
    "collaboration_and_typing": "collab",
    "games_control_loops_simulation": "games",
    "data_and_telemetry": "data",
    "trading_and_markets": "trading",
    NOT_JEV: "not-Jev",
    "other_or_meta": "other",
}
TIERS = ["frame", "feel", "turn", "interaction", "task", "batch", "unclear"]
EVIDENCE = ["measured_production", "measured_demo", "demo_no_numbers", "proposal_or_idea", "commentary_or_meme"]
MEASURED = ["measured_production", "measured_demo"]
FRAMINGS = ["cost", "latency", "accuracy", "capability", "none"]
BASELINES = ["frontier_llm", "small_llm", "classic_classifier_or_ml", "vendor_api", "rules_or_regex", "none"]
LABEL_FIELDS = ["family", "tier", "evidence", "framing", "baseline", "realtime_infra", "production_claim"]  # as the label files carry them
# Published fields. Framing is withdrawn from every table: a human calibration showed that one choice
# misrepresents posts that lead with cost and latency together. Tier is published only as the audited
# under-300 ms split: the seven-level distribution did not survive a human calibration.
PUBLIC_FIELDS = [f for f in LABEL_FIELDS if f != "framing"]

# Review item 10: the Laya-vs-Jev Snake benchmark (766,872 views). Rubric v2 rule 3 puts a
# benchmark on a named task in that task's family, so this card belongs in games. If Sonnet v2
# did not apply the rule, it is applied here, visibly (see sections["snake"]).
SNAKE_ID = "2101675124747338229"
RULE3_OVERRIDES = {SNAKE_ID: GAMES}

SONNET_PRICE = {"input": 2.0, "output": 10.0, "cacheRead": 0.2, "cacheWrite": 2.5}  # $ per M tokens
JEV_PRICE_INPUT = 0.042  # $ per M input tokens; output free (Gateway list, 2026-09-23)
OPENCHAMBER_SURVEY = "https://openchamber.dev/blog/jev-typesafe-ai/"
REVIEW_NOTE = "Brain `work/content/drafts/jev-landscape-review.md`"


# ---------------------------------------------------------------- helpers
def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def pct(x: float, d: int = 1) -> str:
    return "" if x is None or pd.isna(x) else f"{100 * x:.{d}f}%"


def num(x) -> str:
    if x is None or pd.isna(x):
        return ""
    if isinstance(x, (bool, np.bool_)):
        return str(bool(x))
    if isinstance(x, (int, np.integer)) or (isinstance(x, float) and float(x).is_integer()):
        return f"{int(x):,}"
    if abs(x) >= 10:
        return f"{int(math.floor(x + 0.5)):,}"  # round half up, so a median of 98.5 shows as 99
    return f"{x:,.2f}"


def md(df: pd.DataFrame, index: bool = False) -> str:
    """Render a DataFrame as a GitHub-flavoured markdown table."""
    d = df.reset_index() if index else df
    cols = [str(c) for c in d.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, row in d.iterrows():
        cells = []
        for v in row.tolist():
            cells.append(v.replace("|", "\\|").replace("\n", " ") if isinstance(v, str) else num(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def save(df: pd.DataFrame, name: str, index: bool = False) -> None:
    df.to_csv(OUTD / f"{name}.csv", index=index)


def row_share(ct: pd.DataFrame) -> pd.DataFrame:
    return ct.div(ct.sum(axis=1).replace(0, np.nan), axis=0)


def share_table(ct: pd.DataFrame, order_cols: list[str]) -> pd.DataFrame:
    cols = [c for c in order_cols if c in ct.columns]
    rs = row_share(ct[cols])
    out = pd.DataFrame(index=ct.index)
    out["n"] = ct[cols].sum(axis=1)
    for c in cols:
        out[c] = rs[c].map(lambda v: pct(v, 0))
    return out


def link(title: str, url: str) -> str:
    return f"[{title}]({url})"


def kappa_of(a: pd.Series, b: pd.Series) -> float:
    n = len(a)
    if not n:
        return float("nan")
    po = float((a.values == b.values).mean())
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / n**2
    return (po - pe) / (1 - pe) if pe < 1 else float("nan")


def dist(frame: pd.DataFrame, key: str, order: list[str] | None, n: int, tv: int, tl: int) -> pd.DataFrame:
    g = frame.groupby(key)
    t = pd.DataFrame(
        {"posts": g.size(), "views": g["v"].sum(), "likes": g["f"].sum(), "median_views": g["v"].median(), "median_likes": g["f"].median()}
    )
    if order is not None:
        t = t.reindex(order).fillna(0)
    t["share_posts"] = t["posts"] / n
    t["share_views"] = t["views"] / tv
    t["share_likes"] = t["likes"] / tl
    return t


def dist_md(t: pd.DataFrame, label: str) -> str:
    return md(
        pd.DataFrame(
            {
                label: t.index,
                "posts": t["posts"].astype(int).values,
                "share": [pct(v) for v in t["share_posts"]],
                "views": t["views"].astype(int).values,
                "share of views": [pct(v) for v in t["share_views"]],
                "likes": t["likes"].astype(int).values,
                "share of likes": [pct(v) for v in t["share_likes"]],
                "median views": t["median_views"].values,
                "median likes": t["median_likes"].values,
            }
        )
    )


# ---------------------------------------------------------------- load + join
raw = json.loads((DATA / "cards.json").read_text())
meta = raw["meta"]
cards = pd.DataFrame(raw["cards"])
cards["id"] = cards["id"].astype(str)
cards["v"] = cards["v"].fillna(0).astype(int)
cards["f"] = cards["f"].fillna(0).astype(int)
cards["ts"] = pd.to_datetime(cards["id"].map(lambda i: (int(i) >> 22) + 1288834974657), unit="ms", utc=True)
cards["day"] = cards["ts"].dt.strftime("%Y-%m-%d")
N_CARDS = len(cards)
N_AUTHORS = int(cards["sn"].nunique())
T_MIN, T_MAX = cards["ts"].min(), cards["ts"].max()


def window_text(t0: pd.Timestamp, t1: pd.Timestamp) -> str:
    """'16 to 23 September', or '30 September to 1 October' across a month end."""
    if (t0.year, t0.month) == (t1.year, t1.month):
        return f"{t0.day} to {t1.day} {t1:%B}"
    return f"{t0.day} {t0:%B} to {t1.day} {t1:%B}"


WINDOW = window_text(T_MIN, T_MAX)  # from the data: first and last post day (UTC)
LAST_DAY_PARTIAL = bool(T_MAX.hour < 23)  # the last day counts as partial unless posts run to its last hour

son2_rows = read_jsonl(LABELS_PATH)
son2 = pd.DataFrame(son2_rows)
son2_dups = int(son2.duplicated("id").sum()) if len(son2) else 0
son2 = son2.drop_duplicates("id", keep="first")
son1 = pd.DataFrame(read_jsonl(DATA / "classified-sonnet.jsonl")).drop_duplicates("id", keep="first")
son1 = son1[["id"] + LABEL_FIELDS].rename(columns={k: f"{k}_v1" for k in LABEL_FIELDS})
jev = pd.DataFrame(read_jsonl(DATA / "classified-jev.jsonl"))
jev_dups = int(jev.duplicated("id").sum()) if len(jev) else 0
jev = jev.drop_duplicates("id", keep="first").rename(
    columns={"family": "jev_family", "prob": "jev_prob", "latency_ms": "jev_latency_ms", "input_tokens": "jev_input_tokens"}
)
card_ids = set(cards["id"])
son2_stray = sorted(set(son2["id"]) - card_ids)

df = (
    cards.merge(son2, on="id", how="left")
    .merge(son1, on="id", how="left")
    .merge(jev[["id", "jev_family", "jev_prob", "jev_latency_ms", "jev_input_tokens"]], on="id", how="left")
)
son2_missing = int(df["family"].isna().sum())
df["has_repo"] = df["art"].map(lambda a: bool(a) and (a.get("k") == "repo" or "github.com" in (a.get("u") or "")))
for c in ["production_claim", "realtime_infra", "production_claim_v1", "realtime_infra_v1"]:
    df[c] = df[c].fillna(False).astype(bool)
df["vf"] = df["vf"].astype(int)
df["jev_prob"] = df["jev_prob"].astype(float).round(4)
# The first pass (v1) labelled the 23 Sep 10:42 UTC snapshot. Cards added by a refresh have no v1
# label, so every v1 figure below is a share of the cards v1 labelled, not of today's cards.
V1 = df[df["family_v1"].notna()]
N_V1 = int(len(V1))
V1_AUTHORS = int(V1["sn"].nunique())

# rule 3 for the Snake card
df["family_sonnet"] = df["family"]
snake_row = df.loc[df["id"] == SNAKE_ID].iloc[0]
snake = {
    "id": SNAKE_ID,
    "title": snake_row["t"],
    "url": snake_row["url"],
    "views": int(snake_row["v"]),
    "likes": int(snake_row["f"]),
    "family_v1": snake_row["family_v1"],
    "family_v2_sonnet": snake_row["family_sonnet"],
}
for cid, fam in RULE3_OVERRIDES.items():
    df.loc[(df["id"] == cid) & df["family"].notna() & (df["family"] != fam), "family"] = fam
snake["family_used"] = df.loc[df["id"] == SNAKE_ID, "family"].iloc[0]
snake["override_applied"] = bool(snake["family_used"] != snake["family_v2_sonnet"])

# dedupe (scripts/dedupe.py)
dd = find_duplicates(raw["cards"])
df["dup_of"] = df["id"].map(dd["merged_to"])
L = df[df["family"].notna()].copy()  # every card with a v2 label (agreement uses this)
D = L[L["dup_of"].isna()].copy()  # deduplicated
NJ = D[D["family"] == NOT_JEV].copy()
A = D[D["family"] != NOT_JEV].copy()  # the use-case base for every table below
N = len(A)
TOTAL_VIEWS = int(A["v"].sum())
TOTAL_LIKES = int(A["f"].sum())
ALL_VIEWS = int(cards["v"].sum())
ALL_LIKES = int(cards["f"].sum())
SUMMARY: dict = {
    "posts": N_CARDS,
    "authors": N_AUTHORS,
    "window_utc": [str(T_MIN), str(T_MAX)],
    "classified_sonnet_v2": int(len(L)),
    "duplicates_merged": len(dd["merged_to"]),
    "duplicate_groups": len(dd["groups"]),
    "after_dedupe": int(len(D)),
    "not_a_jev_build": int(len(NJ)),
    "use_case_base": int(N),
}
SUMMARY["window_days"] = [f"{T_MIN:%Y-%m-%d}", f"{T_MAX:%Y-%m-%d}"]
SUMMARY["window_text"] = WINDOW
SUMMARY["last_day_partial"] = LAST_DAY_PARTIAL
SUMMARY["feed"] = {k: meta[k] for k in ["updated", "analysed", "through", "pulled", "feed_cards", "kept_from_earlier", "cut_after_through", "snapshots"] if k in meta}
SUMMARY["v1_set"] = {"cards": N_V1, "authors": V1_AUTHORS}
SUMMARY["labels"] = {"file": LABELS_REL, "model": LABELS_MODEL, "short": LABELS_SHORT, "tag": LABELS_TAG, "audited": AUDITED,
                     "audited_model": AUDITED_MODEL}
sections: dict[str, str] = {}

# ---------------------------------------------------------------- 0. base, dedupe, not-Jev
dup_views = sum(g["dropped_views"] for g in dd["groups"])
dup_likes = sum(g["dropped_likes"] for g in dd["groups"])
loose = dd["loose_chip_sets"]
nj_stats = {
    "cards": int(len(NJ)),
    "share_of_deduped": len(NJ) / max(1, len(D)),
    "views": int(NJ["v"].sum()),
    "share_views": NJ["v"].sum() / max(1, D["v"].sum()),
    "likes": int(NJ["f"].sum()),
    "share_likes": NJ["f"].sum() / max(1, D["f"].sum()),
    "median_views": float(NJ["v"].median()) if len(NJ) else float("nan"),
}
SUMMARY["not_a_jev_build_stats"] = nj_stats
nj_top = NJ.sort_values("v", ascending=False).head(8)
sections["base"] = (
    f"- **Posts.** {N_CARDS:,} posts from {N_AUTHORS:,} authors, posted {T_MIN:%d %b %H:%M} to {T_MAX:%d %b %H:%M} UTC "
    f"(post times decoded from the X ids). No author has more than {int(cards['sn'].value_counts().max())} posts.\n"
    f"- **Duplicates** (`scripts/dedupe.py`). Rules: same post URL; or the same non-empty chip set and a near-identical title "
    f"(title token Jaccard ≥ 0.8 after lower-casing and removing punctuation); or, for cards with no chips, a near-identical title "
    f"and near-identical post text (character-trigram Jaccard ≥ 0.6). **{len(dd['merged_to'])} cards merged** into "
    f"{len(dd['groups'])} kept cards (the most-viewed of each group), dropping {dup_views:,} views and {dup_likes:,} likes. "
    f"No URL repeats. A looser rule, any shared set of two or more chips whatever the title, would merge up to "
    f"{sum(x['unmerged_extra_cards'] for x in loose)} more cards in {len(loose)} sets; it is not applied because about half of those "
    f"sets are coincidences (TypeSafe's own \"70 ms\" and \"500 ms\", \"1× cheaper, 1× faster\"), but it holds the cross-author and "
    f"cross-language reposts the title rule misses. Groups: `data/dedupe-groups.jsonl`.\n"
    f"- **Not a Jev build.** {LABELS_TAG} puts **{len(NJ):,} of the {len(D):,} remaining cards ({pct(nj_stats['share_of_deduped'])}) in "
    f"not_a_jev_build**, with {pct(nj_stats['share_views'])} of their views and {pct(nj_stats['share_likes'])} of their likes. "
    f"They are left out of every use-case table below.\n"
    f"- **Use-case base: {N:,} cards**, {TOTAL_VIEWS:,} views and {TOTAL_LIKES:,} likes. Every share below is of this base "
    f"unless it says otherwise."
)
sections["not_jev_top"] = md(
    pd.DataFrame(
        {
            "views": nj_top["v"].values,
            "likes": nj_top["f"].values,
            "v1 family": nj_top["family_v1"].values,
            f"{LABELS_TAG} reason": nj_top["reason"].values,
            "title": [link(t, u) for t, u in zip(nj_top["t"], nj_top["url"])],
        }
    )
)
save(NJ[["id", "v", "f", "family_v1", "reason", "t", "url"]].sort_values("v", ascending=False), "00_not_a_jev_build")

# ---------------------------------------------------------------- 1. families (+ Snake effect)
def family_table(frame: pd.DataFrame) -> pd.DataFrame:
    g = frame.groupby("family")
    t = pd.DataFrame(
        {
            "posts": g.size(),
            "views": g["v"].sum(),
            "likes": g["f"].sum(),
            "median_views": g["v"].median(),
            "median_likes": g["f"].median(),
            "p90_views": g["v"].quantile(0.9),
            "repo_cards": g["has_repo"].sum(),
            "production_claims": g["production_claim"].sum(),
        }
    )
    n, tv, tl = len(frame), frame["v"].sum(), frame["f"].sum()
    t["share_posts"] = t["posts"] / n
    t["share_views"] = t["views"] / tv
    t["share_likes"] = t["likes"] / tl
    t["views_index"] = t["share_views"] / t["share_posts"]
    t["likes_index"] = t["share_likes"] / t["share_posts"]
    return t.sort_values("posts", ascending=False)


t1 = family_table(A)
save(t1, "01_family_distribution", index=True)
m1 = pd.DataFrame(
    {
        "family": t1.index,
        "posts": t1["posts"].values,
        "share": [pct(v) for v in t1["share_posts"]],
        "views": t1["views"].values,
        "share of views": [pct(v) for v in t1["share_views"]],
        "likes": t1["likes"].values,
        "share of likes": [pct(v) for v in t1["share_likes"]],
        "views index": [f"{v:.2f}" for v in t1["views_index"]],
        "likes index": [f"{v:.2f}" for v in t1["likes_index"]],
        "median views": t1["median_views"].values,
        "median likes": t1["median_likes"].values,
        "repo": t1["repo_cards"].values,
        "production claims": t1["production_claims"].values,
    }
)
tot = pd.DataFrame(
    [
        {
            "family": "**all**",
            "posts": N,
            "share": "100%",
            "views": TOTAL_VIEWS,
            "share of views": "100%",
            "likes": TOTAL_LIKES,
            "share of likes": "100%",
            "views index": "1.00",
            "likes index": "1.00",
            "median views": A["v"].median(),
            "median likes": A["f"].median(),
            "repo": int(A["has_repo"].sum()),
            "production claims": int(A["production_claim"].sum()),
        }
    ]
)
sections["families"] = md(pd.concat([m1, tot], ignore_index=True))
SUMMARY["family"] = {
    f: {
        "posts": int(r.posts),
        "share_posts": round(r.share_posts, 4),
        "share_views": round(r.share_views, 4),
        "share_likes": round(r.share_likes, 4),
        "views_index": round(r.views_index, 3),
        "likes_index": round(r.likes_index, 3),
        "median_views": float(r.median_views),
    }
    for f, r in t1.iterrows()
}

# Snake effect: the same base with the card in other_or_meta (its v1 label) against games (rule 3)
alt = A.copy()
if SNAKE_ID in set(alt["id"]):
    alt.loc[alt["id"] == SNAKE_ID, "family"] = "other_or_meta"
t_alt = family_table(alt)
t_rule = t1
snake_effect = {}
for fam in [GAMES, "other_or_meta"]:
    snake_effect[fam] = {
        "share_views_meta": float(t_alt.loc[fam, "share_views"]),
        "share_views_rule3": float(t_rule.loc[fam, "share_views"]),
        "views_index_meta": float(t_alt.loc[fam, "views_index"]),
        "views_index_rule3": float(t_rule.loc[fam, "views_index"]),
        "share_likes_meta": float(t_alt.loc[fam, "share_likes"]),
        "share_likes_rule3": float(t_rule.loc[fam, "share_likes"]),
    }
snake["effect"] = snake_effect
SUMMARY["snake"] = snake
g_ = snake_effect[GAMES]
o_ = snake_effect["other_or_meta"]
sections["snake"] = (
    f"The [Laya-vs-Jev Snake benchmark]({snake['url']}) ({snake['views']:,} views, {snake['likes']:,} likes) was other_or_meta in v1. "
    f"Rubric rule 3 puts a benchmark on a named task in that task's family, so it belongs in games. {LABELS_TAG} labelled it "
    f"**{snake['family_v2_sonnet']}**"
    + (", so analyze.py applies rule 3 to it (`RULE3_OVERRIDES`)." if snake["override_applied"] else ", so no override was needed.")
    + f" Effect on this base: games go from {pct(g_['share_views_meta'])} to {pct(g_['share_views_rule3'])} of views "
    f"(views index {g_['views_index_meta']:.2f} → {g_['views_index_rule3']:.2f}) and from {pct(g_['share_likes_meta'])} to "
    f"{pct(g_['share_likes_rule3'])} of likes; other_or_meta goes from {pct(o_['share_views_meta'])} to {pct(o_['share_views_rule3'])} of views."
)

# ---------------------------------------------------------------- 2. tiers: the coarse under-300 ms split only
# The seven-level tier distribution is not published (a human calibration disagreed with both models on
# most cards); section 2 gives the audited under-300 ms share and the share of it that is games.
sub300 = A[A["tier"].isin(["frame", "feel", "turn"])]
sub300_stats = {
    "cards": int(len(sub300)),
    "share": len(sub300) / N,
    "games": int((sub300["family"] == GAMES).sum()),
    "games_share": float((sub300["family"] == GAMES).mean()) if len(sub300) else float("nan"),
}
SUMMARY["sub300"] = sub300_stats

# ---------------------------------------------------------------- 3. evidence
te = dist(A, "evidence", EVIDENCE, N, TOTAL_VIEWS, TOTAL_LIKES)
save(te, "03_evidence_overall", index=True)
sections["evidence"] = dist_md(te, "evidence")
ct_ef = pd.crosstab(A["family"], A["evidence"]).reindex(index=t1.index, columns=EVIDENCE, fill_value=0)
save(ct_ef, "03_evidence_by_family_counts", index=True)
save(row_share(ct_ef).round(4), "03_evidence_by_family_rowshare", index=True)
x = share_table(ct_ef, EVIDENCE)
x.index.name = "family"
sections["evidence_by_family"] = md(x, index=True)
SUMMARY["evidence"] = {k: int(v) for k, v in te["posts"].items()}

# ---------------------------------------------------------------- 4. framing: withdrawn
# No table rests on the framing field (see PUBLIC_FIELDS). Section 4 of landscape.md says why.

# ---------------------------------------------------------------- 5. baseline
tb = dist(A, "baseline", BASELINES, N, TOTAL_VIEWS, TOTAL_LIKES)
save(tb, "05_baseline_overall", index=True)
sections["baseline"] = dist_md(tb, "baseline")
ct_bf = pd.crosstab(A["family"], A["baseline"]).reindex(index=t1.index, columns=BASELINES, fill_value=0)
save(ct_bf, "05_baseline_by_family_counts", index=True)
save(row_share(ct_bf).round(4), "05_baseline_by_family_rowshare", index=True)
x = share_table(ct_bf, BASELINES)
x.index.name = "family"
sections["baseline_by_family"] = md(x, index=True)
incumbent = A["baseline"].isin(["classic_classifier_or_ml", "rules_or_regex", "vendor_api"])
SUMMARY["baseline"] = {k: int(v) for k, v in tb["posts"].items()}
SUMMARY["baseline_shares"] = {
    "none": float((A["baseline"] == "none").mean()),
    "frontier_llm": float((A["baseline"] == "frontier_llm").mean()),
    "small_llm": float((A["baseline"] == "small_llm").mean()),
    "incumbent_classic_rules_vendor": float(incumbent.mean()),
}

# ---------------------------------------------------------------- 6. attention: views and likes
def concentration(values: np.ndarray) -> tuple[pd.DataFrame, np.ndarray]:
    vs = np.sort(values)[::-1]
    cum = np.cumsum(vs) / vs.sum()
    rows = []
    for p in [0.001, 0.01, 0.05, 0.10, 0.25, 0.50]:
        k = max(1, math.ceil(p * len(vs)))
        rows.append({"top": f"{p * 100:g}%", "cards": k, "total": int(vs[:k].sum()), "share": float(cum[k - 1]), "min_in_group": int(vs[k - 1])})
    return pd.DataFrame(rows), cum


def gini(values: np.ndarray) -> float:
    asc = np.sort(values)
    n_ = len(asc)
    return float((2 * np.arange(1, n_ + 1) - n_ - 1).dot(asc) / (n_ * asc.sum()))


def top1_share(values: np.ndarray) -> float:
    vs = np.sort(values)[::-1]
    k = max(1, math.ceil(0.01 * len(vs)))
    return float(vs[:k].sum() / vs.sum())


conc_v, cum_v = concentration(A["v"].to_numpy())
conc_l, _ = concentration(A["f"].to_numpy())
conc = pd.DataFrame(
    {
        "top share of cards": conc_v["top"],
        "cards": conc_v["cards"],
        "views": conc_v["total"],
        "share of views": [pct(v) for v in conc_v["share"]],
        "smallest card (views)": conc_v["min_in_group"],
        "likes": conc_l["total"],
        "share of likes": [pct(v) for v in conc_l["share"]],
    }
)
save(pd.concat([conc_v.add_prefix("views_"), conc_l.add_prefix("likes_")], axis=1), "06_attention_concentration")
lorenz = pd.DataFrame({"share_of_cards_top": np.arange(1, N + 1) / N, "share_of_views": cum_v})
save(lorenz.iloc[:: max(1, N // 500)], "06_lorenz_points")
A["like_rate"] = np.where(A["v"] > 0, A["f"] / A["v"].where(A["v"] > 0, 1), np.nan)
top_card = A.sort_values("v", ascending=False).iloc[0]
suspect = A[(A["v"] >= 100_000) & (A["like_rate"] < 0.002)]
stats6 = {
    "total_views": TOTAL_VIEWS,
    "total_likes": TOTAL_LIKES,
    "median_views": float(A["v"].median()),
    "median_likes": float(A["f"].median()),
    "mean_views": float(A["v"].mean()),
    "gini_views": round(gini(A["v"].to_numpy()), 3),
    "gini_likes": round(gini(A["f"].to_numpy()), 3),
    "cards_holding_half_of_views": int(np.searchsorted(cum_v, 0.5) + 1),
    "cards_under_100_views": int((A["v"] < 100).sum()),
    "top1pct_views": float(conc_v.loc[1, "share"]),
    "top1pct_likes": float(conc_l.loc[1, "share"]),
    "top10pct_views": float(conc_v.loc[3, "share"]),
    "top_card_id": str(top_card["id"]),
    "top_card_views": int(top_card["v"]),
    "top_card_likes": int(top_card["f"]),
    "top_card_share": float(top_card["v"] / TOTAL_VIEWS),
    "top_card_like_rate": float(top_card["like_rate"]),
    "median_like_rate_1k_plus": float(A.loc[A["v"] >= 1000, "like_rate"].median()),
    "top1pct_views_excl_top_card": top1_share(A.loc[A["id"] != top_card["id"], "v"].to_numpy()),
    "suspect_cards": int(len(suspect)),
    "suspect_share_views": float(suspect["v"].sum() / TOTAL_VIEWS),
    "top1pct_views_excl_suspect": top1_share(A.loc[~A["id"].isin(suspect["id"]), "v"].to_numpy()),
    "raw_all_cards_top1pct_views": top1_share(cards["v"].to_numpy()),
}
save(pd.DataFrame([stats6]), "06_attention_stats")
save(suspect[["id", "v", "f", "like_rate", "family", "t", "url"]].sort_values("v", ascending=False), "06_low_like_rate_cards")
sections["concentration"] = md(conc) + (
    f"\n\nViews: total {TOTAL_VIEWS:,}, median {stats6['median_views']:,.0f}, Gini {stats6['gini_views']}. "
    f"Likes: total {TOTAL_LIKES:,}, median {stats6['median_likes']:,.0f}, Gini {stats6['gini_likes']}. "
    f"{stats6['cards_under_100_views']:,} cards ({pct(stats6['cards_under_100_views'] / N)}) have under 100 views. "
    f"Sensitivity of the top-1% view share ({pct(stats6['top1pct_views'])}): without the single most-viewed card "
    f"({stats6['top_card_views']:,} views, like rate {pct(stats6['top_card_like_rate'], 2)}) it is {pct(stats6['top1pct_views_excl_top_card'])}; "
    f"without the {stats6['suspect_cards']} cards with 100k or more views and a like rate under 0.2% (median like rate for cards with 1k or more views: "
    f"{pct(stats6['median_like_rate_1k_plus'], 2)}; together {pct(stats6['suspect_share_views'])} of views; `06_low_like_rate_cards.csv`) it is "
    f"{pct(stats6['top1pct_views_excl_suspect'])}; measured by likes it is {pct(stats6['top1pct_likes'])}. On all {N_CARDS:,} raw cards "
    f"(before dedupe and the not-Jev exclusion) it is {pct(stats6['raw_all_cards_top1pct_views'])}."
)
top20 = A.sort_values("v", ascending=False).head(20)
top20_out = pd.DataFrame(
    {
        "rank": range(1, 21),
        "views": top20["v"].values,
        "likes": top20["f"].values,
        "family": top20["family"].values,
        "evidence": top20["evidence"].values,
        "title": top20["t"].values,
        "url": top20["url"].values,
    }
)
save(top20_out, "06_top20_cards")
sections["top20"] = md(top20_out.assign(title=[link(t, u) for t, u in zip(top20_out["title"], top20_out["url"])]).drop(columns=["url"]))
SUMMARY["concentration"] = stats6

# posting day (UTC, from the id): views and likes both depend on how long a post has been up
day = A.groupby("day").agg(
    posts=("id", "size"), views=("v", "sum"), likes=("f", "sum"), median_views=("v", "median"), median_likes=("f", "median")
)
day["share_views"] = day["views"] / TOTAL_VIEWS
day["share_likes"] = day["likes"] / TOTAL_LIKES
save(day, "06_attention_by_day", index=True)
early = A["day"] <= "2026-09-19"
sections["by_day"] = md(
    pd.DataFrame(
        {
            "day (UTC)": day.index,
            "posts": day["posts"].values,
            "median views": day["median_views"].values,
            "median likes": day["median_likes"].values,
            "share of views": [pct(v) for v in day["share_views"]],
            "share of likes": [pct(v) for v in day["share_likes"]],
        }
    )
) + (
    f"\n\nPosts from 16 to 19 September are {pct(early.mean())} of posts and hold {pct(A.loc[early, 'v'].sum() / TOTAL_VIEWS)} of views "
    f"and {pct(A.loc[early, 'f'].sum() / TOTAL_LIKES)} of likes. "
    + (f"{T_MAX.day} {T_MAX:%B} is a partial day (last post {T_MAX:%H:%M} UTC)." if LAST_DAY_PARTIAL
       else f"The last post is at {T_MAX:%H:%M} UTC on {T_MAX.day} {T_MAX:%B}.")
)
fam_day = A.pivot_table(index="family", columns="day", values="v", aggfunc="median").reindex(t1.index)
save(fam_day, "06_median_views_by_family_and_day", index=True)
SUMMARY["by_day"] = {d: {"posts": int(r.posts), "median_views": float(r.median_views), "median_likes": float(r.median_likes)} for d, r in day.iterrows()}

# ---------------------------------------------------------------- 7. realtime slice
R = A[A["realtime_infra"]]
nr = len(R)
RNG = R[R["family"] != GAMES]
AG = A[A["family"] != GAMES]
rt_stats = {
    "cards": nr,
    "share_posts": nr / N,
    "share_views": R["v"].sum() / TOTAL_VIEWS,
    "share_likes": R["f"].sum() / TOTAL_LIKES,
    "games_share_of_realtime": float((R["family"] == GAMES).mean()) if nr else float("nan"),
    "non_game_cards": int(len(RNG)),
    "non_game_share_of_all_posts": len(RNG) / N,
    "non_game_share_of_non_game_posts": len(RNG) / max(1, len(AG)),
    "non_game_share_views": RNG["v"].sum() / TOTAL_VIEWS,
    "measured_production": int((R["evidence"] == "measured_production").sum()),
    "measured_production_non_game": int((RNG["evidence"] == "measured_production").sum()),
    "production_claims": int(R["production_claim"].sum()),
    "v1_share_all_cards": float(V1["realtime_infra_v1"].mean()),
}
# the same 120 hand-labelled cards
hand = load_hand()
H = L[L["id"].isin(hand)].copy()
H["hand_rt"] = H["id"].map(lambda i: hand[i]["realtime_infra"])
H["hand_fam"] = H["id"].map(lambda i: hand[i]["family"])
ng_hand = H["hand_fam"] != GAMES
rt_hand = {
    "n": int(len(H)),
    "hand": float(H["hand_rt"].mean()),
    "v1": float(H["realtime_infra_v1"].mean()),
    "v2": float(H["realtime_infra"].mean()),
    "hand_non_game": float((H["hand_rt"] & ng_hand).mean()),
    "v1_non_game": float((H["realtime_infra_v1"] & (H["family_v1"] != GAMES)).mean()),
    "v2_non_game": float((H["realtime_infra"] & (H["family"] != GAMES)).mean()),
}
# hand-calibrated estimate: P(hand) = P(label) P(hand | label) + P(no label) P(hand | no label)
def _calibrated(label_pos: pd.Series, hand_pos: pd.Series, full_share: float) -> dict:
    ppv = float(hand_pos[label_pos].mean()) if label_pos.any() else float("nan")
    fomr = float(hand_pos[~label_pos].mean()) if (~label_pos).any() else float("nan")
    k = int(hand_pos.sum())
    lo, hi = wilson(k, len(hand_pos))
    return {"label_share": full_share, "ppv_on_sample": ppv, "hand_pos_among_label_neg": fomr,
            "estimate": full_share * ppv + (1 - full_share) * fomr, "hand_share": k / len(hand_pos), "hand_ci": (lo, hi)}


rt_cal_all = _calibrated(H["realtime_infra"], H["hand_rt"], nr / N)
rt_cal_ng = _calibrated(H["realtime_infra"] & (H["family"] != GAMES), H["hand_rt"] & ng_hand, len(RNG) / N)
rt_hand["calibrated_all"] = rt_cal_all
rt_hand["calibrated_non_game"] = rt_cal_ng
rt_stats["hand_sample"] = rt_hand
save(pd.DataFrame([{k: v for k, v in rt_stats.items() if k != "hand_sample"}]), "07_realtime_overall")
rf = R.groupby("family").agg(cards=("id", "size"), views=("v", "sum"), likes=("f", "sum"), median_views=("v", "median"))
rf["share_of_realtime"] = rf["cards"] / max(1, nr)
rf["share_of_family"] = rf["cards"] / A.groupby("family").size().reindex(rf.index)
rf = rf.sort_values("cards", ascending=False)
save(rf, "07_realtime_by_family", index=True)
rtop = R.sort_values("v", ascending=False).head(15)
rtop_out = pd.DataFrame(
    {
        "rank": range(1, len(rtop) + 1),
        "views": rtop["v"].values,
        "likes": rtop["f"].values,
        "family": rtop["family"].values,
        "evidence": rtop["evidence"].values,
        "title": rtop["t"].values,
        "url": rtop["url"].values,
    }
)
save(rtop_out, "07_realtime_top15")
sections["realtime"] = (
    f"realtime_infra = true: **{nr:,} cards ({pct(nr / N)} of posts)**, {pct(rt_stats['share_views'])} of views, {pct(rt_stats['share_likes'])} of likes "
    f"(v1, all cards: {pct(rt_stats['v1_share_all_cards'])}). Games are {pct(rt_stats['games_share_of_realtime'])} of them. Outside games: "
    f"**{len(RNG):,} cards, {pct(rt_stats['non_game_share_of_all_posts'])} of all posts** ({pct(rt_stats['non_game_share_of_non_game_posts'])} of non-game posts), "
    f"{pct(rt_stats['non_game_share_views'])} of views. {rt_stats['measured_production']} realtime cards are measured_production "
    f"({rt_stats['measured_production_non_game']} outside games).\n\n"
    f"On the 120 hand-labelled cards: hand {pct(rt_hand['hand'])}, Sonnet v1 {pct(rt_hand['v1'])}, {LABELS_TAG} {pct(rt_hand['v2'])}; "
    f"outside games: hand {pct(rt_hand['hand_non_game'])}, v1 {pct(rt_hand['v1_non_game'])}, v2 {pct(rt_hand['v2_non_game'])} (share of all 120). "
    f"On the sample, {pct(rt_cal_all['ppv_on_sample'], 0)} of v2's realtime flags hold up ({pct(rt_cal_ng['ppv_on_sample'], 0)} outside games) and v2 misses "
    f"{pct(rt_cal_all['hand_pos_among_label_neg'], 0)} of the cards it leaves unflagged. Corrected with those rates, the estimate is "
    f"**{pct(rt_cal_all['estimate'])} of posts, {pct(rt_cal_ng['estimate'])} outside games** (hand sample alone: {pct(rt_cal_all['hand_share'])}, 95% CI "
    f"{pct(rt_cal_all['hand_ci'][0])}–{pct(rt_cal_all['hand_ci'][1])}; outside games {pct(rt_cal_ng['hand_share'])}, CI {pct(rt_cal_ng['hand_ci'][0])}–{pct(rt_cal_ng['hand_ci'][1])}). "
    + "So the label counts are upper bounds.\n\n"
    + md(
        pd.DataFrame(
            {
                "family": rf.index,
                "realtime cards": rf["cards"].values,
                "share of realtime": [pct(v) for v in rf["share_of_realtime"]],
                "share of family": [pct(v) for v in rf["share_of_family"]],
                "views": rf["views"].values,
                "likes": rf["likes"].values,
                "median views": rf["median_views"].values,
            }
        )
    )
)
sections["realtime_top15"] = md(rtop_out.assign(title=[link(t, u) for t, u in zip(rtop_out["title"], rtop_out["url"])]).drop(columns=["url"]))
RF = A[A["family"].isin(RT_FAMILIES)]
rtfam = {
    "cards": int(len(RF)),
    "share_posts": len(RF) / N,
    "share_views": RF["v"].sum() / TOTAL_VIEWS,
    "share_likes": RF["f"].sum() / TOTAL_LIKES,
    "measured_production": int((RF["evidence"] == "measured_production").sum()),
    "measured_demo": int((RF["evidence"] == "measured_demo").sum()),
    "by_family": {k: int(v) for k, v in RF["family"].value_counts().items()},
    "v1_cards_all": int(df["family_v1"].isin(RT_FAMILIES).sum()),
}
sections["realtime_families"] = (
    f"Voice, live chat and collaboration together: **{rtfam['cards']} cards ({pct(rtfam['share_posts'])} of posts)**, "
    f"{pct(rtfam['share_views'])} of views and {pct(rtfam['share_likes'])} of likes; {rtfam['measured_production']} measured_production and "
    f"{rtfam['measured_demo']} measured demos. By family: "
    + ", ".join(f"{SHORT[k]} {v}" for k, v in rtfam["by_family"].items())
    + f". v1 had {rtfam['v1_cards_all']} such cards of {N_V1:,}; the first review's targeted re-read bounded the true count at about 150 to 200 (2.6 to 3.5%)."
)
SUMMARY["realtime"] = rt_stats
SUMMARY["realtime_families"] = rtfam

# ---------------------------------------------------------------- 8. the measurement ladder and the candidate builds
# v3: the noise / hype / demo / cost-only / material buckets failed the independent audit (claim 3 of
# review/critical-review-grok.md) and are withdrawn; their tables on these labels are kept for the record in
# report/v1/buckets-on-v2-labels.md (scripts/buckets-reviewed.py). In their place: a three-step ladder on the
# evidence label, which the audit found stable, with the audited shares from report/data/13_audit_*.csv.
AUD = audit_build(LABELS_PATH)
AE = AUD["estimates"]
SUMMARY["audit"] = AUD
if not AUD["snapshot_matches"]:
    print("WARNING: the audit describes an earlier snapshot of the Sonnet v2 labels; charts.mjs will not build the page until it is redone.")


def rng(lo: float, hi: float, d: int = 1, d_hi: int | None = None) -> str:
    """'29.7–40.3%': a 95% interval as shares."""
    return f"{100 * lo:.{d}f}–{100 * hi:.{d if d_hi is None else d_hi}f}%"


def ci(key: str, d: int = 1) -> str:
    """'34.7% (29.7–40.3%)': an audited estimate with its interval."""
    e = AE[key]
    return f"{pct(e['value'], d)} ({rng(e['lo'], e['hi'], d)})" if "lo" in e else pct(e["value"], d)


LADDER = [
    ("no_measurement", "No measurement", ["demo_no_numbers", "proposal_or_idea", "commentary_or_meme"]),
    ("measured_demo", "Measured demo", ["measured_demo"]),
    ("measured_production", "Measured production", ["measured_production"]),
]
STEP_OF = {e: k for k, _, evs in LADDER for e in evs}
A["ladder"] = A["evidence"].map(STEP_OF)
CENSUS = production_census()  # the audit re-read every card the Sonnet v2 labels call measured production
A["audit_production"] = [
    ("holds" if CENSUS[i] else "does_not_hold") if i in CENSUS else ("not_reread" if e == "measured_production" else "")
    for i, e in zip(A["id"], A["evidence"])
]
CANDIDATES = set(candidate_ids())
A["candidate"] = A["id"].isin(CANDIDATES)
tl = dist(A, "ladder", [k for k, _, _ in LADDER], N, TOTAL_VIEWS, TOTAL_LIKES)
tl.insert(0, "label", [lab for _, lab, _ in LADDER])
tl.insert(1, "evidence", [", ".join(evs) for _, _, evs in LADDER])
tl.index.name = "step"
save(tl, "08_ladder", index=True)
save(A[["id", "family", "evidence", "baseline", "realtime_infra", "ladder", "audit_production", "candidate"]], "08_ladder_per_card")
prod_confirmed = int(((A["ladder"] == "measured_production") & (A["audit_production"] == "holds")).sum())
SUMMARY["ladder"] = {k: {"posts": int(tl.loc[k, "posts"]), "share_posts": float(tl.loc[k, "share_posts"]),
                         "share_views": float(tl.loc[k, "share_views"]), "share_likes": float(tl.loc[k, "share_likes"])} for k, _, _ in LADDER}
SUMMARY["ladder"]["measured_production"]["confirmed_by_audit"] = prod_confirmed
H["hand_ev"] = H["id"].map(lambda i: hand[i]["evidence"])
over = {}
for tag, col in [("v1", "evidence_v1"), ("v2", "evidence")]:
    m_ = H[col].isin(MEASURED)
    over[tag] = {"measured": int(m_.sum()), "not_measured_by_hand": int((m_ & ~H["hand_ev"].isin(MEASURED)).sum())}
SUMMARY["measured_overgrading_on_120"] = over
pa_ = AUD["primary_agreement"]
ps_ = AE["production_strict"]
fp_ = AE["production_first_pass"]
MA_ = AUD.get("model_audit")  # review/estimate-opus.py's run when the labels are not the audited Sonnet v2 labels
META_RANGE = ("about a fifth of posts state no use case, benchmark the model itself, or wrap it" if MA_ else
              "posts that state no use case, benchmark the model itself, or wrap it")
EB_ = int(AE["estimate_base"]["value"])  # the base the audited shares are shares of
_prod_s = (MA_ or {}).get("production") or {}
PROD_RECOUNT = ("" if not _prod_s else
                f"{LABELS_TAG} labels {_prod_s['base']} posts measured production, but the audit agrees with only "
                f"{_prod_s['model_mp_audited_holds']} of the {_prod_s['model_mp_audited']} of them it read "
                f"({_prod_s['model_mp_on_holds']} on its re-read, {_prod_s['model_mp_audited_holds'] - _prod_s['model_mp_on_holds']} on first-pass "
                f"labels its estimate does not count) and never saw {_prod_s['model_mp_unaudited']}, so the published count is the audit's")


def ao(key: str, d: int = 1) -> str:
    """The audit-only variant of an estimate: the audit's random samples alone, neither model's word."""
    e = AE[key]
    return "" if e.get("audit_only") is None else (pct(e["audit_only"], d) + ("" if e.get("audit_only_lo") is None else
                                                                            f" ({rng(e['audit_only_lo'], e['audit_only_hi'], d)})"))


def _none_or(v) -> str:
    return "none" if int(v) == 0 else f"{int(v)}"


def inside(key: str) -> bool:
    e = AE[key]
    return e.get("lo") is not None and e.get("model") is not None and e["lo"] <= e["model"] <= e["hi"]
sections["ladder"] = (
    f"The bucket scheme of earlier versions (noise, hype, demo, cost-only, fast loop, material) is withdrawn: it failed the audit "
    f"(claim 3 in the Audit section). Its three tables on these labels are kept for the record in "
    f"[v1/buckets-on-v2-labels.md](v1/buckets-on-v2-labels.md). In its place is a three-step ladder on the evidence label, which agrees "
    f"with the audit on {pct(pa_['evidence'])} of the {AUD['labelled']:,} audited cards. The counts are {LABELS_TAG}'s labels; the last column "
    f"is the audit's estimate with its 95% interval.\n\n"
    + md(pd.DataFrame({
        "step": tl["label"].values,
        "evidence labels": tl["evidence"].values,
        "posts": tl["posts"].astype(int).values,
        "share of posts": [pct(v) for v in tl["share_posts"]],
        "share of views": [pct(v) for v in tl["share_views"]],
        "share of likes": [pct(v) for v in tl["share_likes"]],
        "audited": [
            (f"{ci('ladder_no_measurement')}: demos with no numbers {ci('ladder_demo_no_numbers')}; a cost, speed or accuracy claim "
             f"with no measurement {ci('ladder_claim_no_number')}"),
            ci("ladder_measured_demo"),
            (f"{ps_['k']} hold on the audit's re-read of the {ps_['n']} strict {AUDITED_MODEL} cards ({pct(ps_['value'], 2)}), at most "
             f"{pct(ps_['hi'])}; the first labelling pass said {pct(fp_['value'])} ({fp_['k']} of {fp_['n']:,} cards)"),
        ],
    }))
    + f"\n\n\"No measurement\" is a demo with no numbers, a claim with no measurement, a proposal or commentary. Its two audited parts are "
    f"defined without the framing field (section 4). A claim with no measurement is a post whose evidence is demo_no_numbers and whose card "
    f"carries a cost, speed or accuracy chip (a price, a multiple, a latency, a rate or an accuracy the feed extracted from the post): "
    f"{ci('ladder_claim_no_number')}. A demo with no numbers is any other demo_no_numbers post that is not meta: "
    f"{ci('ladder_demo_no_numbers')}. The rest of the step is meta posts, proposals and commentary. Measured production is "
    f"{prod_confirmed} post{'s' if prod_confirmed != 1 else ''} in this base on the audit's re-read; its interval runs to {pct(ps_['hi'])} "
    f"because two large samples with no misses still allow a few." + (f" {PROD_RECOUNT}." if PROD_RECOUNT else "")
)
_pop = {r.key: (int(r.population), int(r.reviewed)) for r in pd.read_csv(OUTD / "13_audit_sampling.csv").itertuples()}
_s3, _s3g = AE["sub300_set"], AE["sub300_games"]


def human_calibration() -> dict:
    """The author's own labels (review/human-labels.jsonl, the labeller export) against both models: a calibration, not a sample."""
    path = ROOT / "review" / "human-labels.jsonl"
    if not path.exists():
        return {"n": 0}
    last: dict[str, dict] = {}
    for line in path.read_text().splitlines():
        if line.strip():
            h = json.loads(line)
            last[str(h["id"])] = h
    son = {r["id"]: r for r in (json.loads(x) for x in (DATA / "classified-sonnet-v2.jsonl").read_text().splitlines() if x.strip())}
    opu_path = DATA / "classified-opus.jsonl"
    opu = {r["id"]: r for r in (json.loads(x) for x in opu_path.read_text().splitlines() if x.strip())} if opu_path.exists() else {}
    hs = [h for h in last.values() if not h.get("unsure") and h["id"] in son and h["id"] in opu]
    tier_both = [h for h in hs if h.get("tier") and h["tier"] != son[h["id"]]["tier"] and h["tier"] != opu[h["id"]]["tier"]]
    meta_both = [h for h in hs if son[h["id"]]["family"] == "other_or_meta" and opu[h["id"]]["family"] == "other_or_meta"]
    real = [h for h in meta_both if h["family"] != "other_or_meta"]
    return {"n": len(hs), "unsure_left_out": sum(1 for h in last.values() if h.get("unsure")),
            "tier_differs_from_both": len(tier_both),
            "tier_human_turn": sum(1 for h in tier_both if h["tier"] == "turn"),
            "meta_by_both_models": len(meta_both), "meta_given_real_use": len(real),
            "meta_real_families": dict(Counter(h["family"] for h in real)),
            "family_agree": {"sonnet": sum(1 for h in hs if h["family"] == son[h["id"]]["family"]),
                             "opus": sum(1 for h in hs if h["family"] == opu[h["id"]]["family"])},
            "file": "review/human-labels.jsonl"}


HC = human_calibration()
SUMMARY["human_calibration"] = HC


def hc_tier() -> str:
    return (f"a human calibration of {HC['n']} posts (the author's own labels) disagreed with both models on tier for "
            f"{HC['tier_differs_from_both']} of them" if HC["n"] else "no human calibration is in yet")


def hc_meta() -> str:
    if not HC["n"] or not HC["meta_by_both_models"]:
        return ""
    fam = max(HC["meta_real_families"], key=HC["meta_real_families"].get) if HC["meta_real_families"] else ""
    return (f"the author's own calibration labels gave a real use to {HC['meta_given_real_use']} of the {HC['meta_by_both_models']} posts in it "
            f"that both models call meta" + (f" (mostly {fam.replace('_', ' ')})" if fam else ""))
sections["tier_audit"] = (
    f"The rubric has seven latency tiers (frame under 16 ms, feel under 100 ms, turn 100 to 300 ms, interaction under 1 s, task, batch, unclear). "
    f"The seven-level distribution is not published: tier agrees with the audit on {pct(pa_['tier'])} of the audited cards "
    f"({pct(AUD['frame_agreement']['tier'])} for the {AUDITED_MODEL} labels), the lowest of any field, and {hc_tier()}"
    + (f", {HC['tier_human_turn']} of them per-move decisions the author calls \"turn\"" if HC.get("tier_human_turn") else "")
    + f". One coarse split survives the audit. It re-read {_s3['n']} of the posts the {AUDITED_MODEL} "
    f"labels put under 300 ms (frame, feel or turn) and {_s3['k']} still need a decision that fast"
    + (f": about {ci('sub300_set')} of all posts. " if MA_ is None else
       f". With the {int(AE['sub300_set']['plug'])} posts that {LABELS_TAG} alone puts under 300 ms taken on its word, that is about "
       f"{ci('sub300_set')} of posts, and {ao('sub300_set')} on the audit's samples alone; {LABELS_TAG}'s own {pct(AE['sub300_set']['model'])} "
       f"is outside both. ")
    + f"{ci('sub300_games')} of those are games."
)
sections["framing_withdrawn"] = (
    "The rubric also asked what each post leads with (framing: cost, latency, accuracy, capability or none). A human calibration showed that "
    "a single choice misrepresents the many posts that lead with cost and latency together, so no number in this report rests on framing. "
    "The ladder's \"claim with no measurement\" (section 8) uses the evidence label and the feed's claim chips instead."
)
sections["baseline_audit"] = (
    f"**Audited.** The audit re-read {_pop['baseline_none'][1]:,} of the {_pop['baseline_none'][0]:,} posts the {AUDITED_MODEL} labels say name no "
    f"comparison, and all {_pop['replacement_baseline'][0]:,} that name classic ML, rules or a vendor API. Corrected: nothing {ci('baseline_none')}, a frontier "
    f"LLM {ci('baseline_frontier_llm')}, a small LLM {ci('baseline_small_llm')}, and the tools Jev would replace {ci('baseline_replacement')}. "
    f"The posts with a frontier or small-LLM baseline were not sampled, so their share rests on "
    + ("the labels there being right." if AUDITED else
       f"the {LABELS_TAG} labels there ({int(AE['plug_frontier_small']['value']):,} posts). "
       + ("All four of the " + LABELS_TAG + " labels' own shares are inside their intervals."
          if all(inside(k) for k in ("baseline_none", "baseline_frontier_llm", "baseline_small_llm", "baseline_replacement")) else ""))
)
_ll, _lla, _rf = AE["live_loop_nongame"], AE["live_loop_all"], AE["rt_families"]
sections["realtime_audit"] = (
    f"**Audited.** The realtime flag agrees with the audit on {pct(pa_['realtime_infra'])} of the audited cards, but of the Sonnet v2 flags "
    f"outside games that the audit sampled, only {_ll['k']} of {_ll['n']} hold. A live loop outside games is {ci('live_loop_nongame')} of posts, against the model's "
    f"{pct(_ll['model'])}; with games (at the live-loop rate the audit found for the games in its under-300 ms sample) it is about "
    f"{pct(_lla['value'])}, about a fifth of posts. Voice, live chat and collaboration are {ci('rt_families')} of posts on the audit's census "
    f"and negative sample, with {_none_or(AE['rt_families_production']['value'])} measured in production"
    + ("" if MA_ is None else f" and {_none_or(AE['rt_families_production_claims']['value'])} claiming production without a measurement "
       f"on the audit's own labels (a live news feed and a Discord moderation bot)") + "."
)
sections["realtime_families"] += (
    f" The audit's census of the {int(_rf['n'])} cards (it keeps {int(_rf['k'])} in these families) and its negative sample put the three families at "
    f"{ci('rt_families')} of posts, with {_none_or(AE['rt_families_production']['value'])} measured in production"
    + ("" if MA_ is None else f" and {_none_or(AE['rt_families_production_claims']['value'])} claiming production without a measurement")
    + "."
)
_pc = pd.read_csv(OUTD / "13_audit_production.csv", dtype={"id": str}, keep_default_na=False)
_pc = _pc.sort_values(["holds", "views"], ascending=[False, False])
sections["production_audit"] = (
    f"**Measured production is {ps_['k']} posts on the audit's re-read, {pct(ps_['value'], 2)} of posts, and at most {pct(ps_['hi'])}.** "
    f"The audit re-read all {ps_['n']} cards the Sonnet v2 labels call measured_production, and {ps_['k']} hold. Its samples of 200 demos with "
    f"no numbers and 200 measured demos found no missed production card; the upper bound is the Wilson bound on those zero counts, not a pile "
    f"of found cases." + (f" {PROD_RECOUNT}." if PROD_RECOUNT else "") + " Card by card:\n\n"
    + md(pd.DataFrame({
        "holds": ["yes" if h else "no" for h in _pc["holds"]],
        "views": _pc["views"].astype(int).values,
        "audit's evidence": _pc["audit_evidence"].values,
        "audit's note": _pc["note"].values,
        "title": [link(t, u) if u else t for t, u in zip(_pc["title"], _pc["url"])],
    }))
)
_sb = pd.read_csv(OUTD / "13_audit_substance.csv")
_before = _sb[_sb["kind"] == "before"]
_jobs = _sb[_sb["kind"] == "job"].sort_values("posts", ascending=False)
_cand_ng = int((A["candidate"] & (A["family"] != GAMES)).sum())
SUMMARY["candidates"] = {
    "posts": len(CANDIDATES), "in_base": int(A["candidate"].sum()), "outside_games": _cand_ng,
    "before": {r.key: int(r.posts) for r in _before.itertuples()},
    "distinct": int(AE["substance_distinct"]["value"]), "unavailable": int(AE["substance_unavailable"]["value"]),
}
sections["candidates"] = (
    f"**The {len(CANDIDATES)} candidate builds.** These are the posts the Sonnet v2 labels call a measured decision inside a live "
    f"system, made while a person waits (turn or interaction tier, 100 ms to 1 s), compared with nothing, rules, classic ML or a "
    f"frontier LLM: the posts the withdrawn scheme called materially different. The audit read each one from its title and text "
    f"and asked what a team would have used for that job before Jev. \"Unavailable at any price\" is the bar for new.\n\n"
    + md(pd.DataFrame({"what would have done the job before": _before["label"].values, "posts": _before["posts"].astype(int).values}))
    + f"\n\n{int(AE['substance_n']['value'])} posts, {int(AE['substance_distinct']['value'])} distinct builds (the rest are a second post "
    f"about the same build). None did something that was unavailable before: every one is a cheaper or faster version of an existing "
    f"job. The largest jobs are "
    + ", ".join(f"{r.label.lower()} ({int(r.posts)})" for r in _jobs.head(2).itertuples())
    + " and " + ", ".join(f"{r.label.lower()} ({int(r.posts)})" for r in _jobs.iloc[2:3].itertuples())
    + f". On the audit's own labels, {int(AE['candidates_still_meeting']['value'])} of the {len(CANDIDATES)} still meet the selection test "
    f"({int(AE['candidates_still_meeting']['k'])} outside games); with the misses the audit found in its samples, posts that meet it are "
    f"{ci('candidates_combined')} of the base. Source: `review/work/substance.py` (`data/13_audit_substance.csv`)."
)

# ---------------------------------------------------------------- 8b. what the noise is made of
# Every noise card (other_or_meta, or commentary in a use-case family) has a
# sub-type from scripts/classify-noise.ts (rubric: report/rubric-noise.md) and, for hot takes, a stance.
NOISE_SUBTYPES = [
    "benchmark_of_the_model",
    "tooling_or_wrapper",
    "explainer_or_tutorial",
    "news_or_repost",
    "meme_or_joke",
    "hot_take_or_commentary",
    "unrelated_or_unclear",
]
NOISE_WORDS = {
    "benchmark_of_the_model": "benchmarks of the model",
    "tooling_or_wrapper": "tooling or wrappers",
    "explainer_or_tutorial": "explainers or tutorials",
    "news_or_repost": "news or reposts",
    "meme_or_joke": "memes or jokes",
    "hot_take_or_commentary": "hot takes or commentary",
    "unrelated_or_unclear": "unrelated or unclear posts",
    "not_subtyped": "posts not yet sub-typed",
}
HOT = "hot_take_or_commentary"
STANCES = ["bullish", "skeptical", "mixed", "neutral"]
noise_lab = pd.DataFrame(read_jsonl(DATA / "classified-noise.jsonl"), columns=["id", "subtype", "stance", "reason"])
noise_lab = noise_lab.drop_duplicates("id", keep="first").rename(columns={"reason": "noise_reason"})
NZ = A[(A["family"] == "other_or_meta") | (A["evidence"] == "commentary_or_meme")].merge(noise_lab, on="id", how="left")
NZ["subtype"] = NZ["subtype"].fillna("not_subtyped")
n_noise, noise_v, noise_l = len(NZ), int(NZ["v"].sum()), int(NZ["f"].sum())


def _group_rows(frame: pd.DataFrame, key: str, order: list[str], within_n: int, within_v: int) -> pd.DataFrame:
    out = []
    for k in order:
        g = frame[frame[key] == k]
        top = g.sort_values(["v", "id"], ascending=[False, True]).head(1)
        out.append({
            key: k,
            "posts": len(g),
            "share_of_group": len(g) / max(1, within_n),
            "share_of_all_posts": len(g) / N,
            "views": int(g["v"].sum()),
            "share_of_group_views": g["v"].sum() / max(1, within_v),
            "share_of_all_views": g["v"].sum() / TOTAL_VIEWS,
            "likes": int(g["f"].sum()),
            "median_views": float(g["v"].median()) if len(g) else float("nan"),
            "top_card_views": int(top["v"].iloc[0]) if len(top) else 0,
            "top_card_url": top["url"].iloc[0] if len(top) else "",
            "top_card_title": top["t"].iloc[0] if len(top) else "",
        })
    return pd.DataFrame(out)


sub_order = NOISE_SUBTYPES + (["not_subtyped"] if (NZ["subtype"] == "not_subtyped").any() else [])
nb_tab = _group_rows(NZ, "subtype", sub_order, n_noise, noise_v)
nb_tab = nb_tab.sort_values(["posts", "views"], ascending=[False, False], key=None).reset_index(drop=True)
nb_tab = pd.concat([nb_tab[nb_tab["subtype"] != "not_subtyped"], nb_tab[nb_tab["subtype"] == "not_subtyped"]], ignore_index=True)
nb_csv = nb_tab.rename(columns={"share_of_group": "share_of_noise", "share_of_group_views": "share_of_noise_views"})
save(nb_csv, "12_noise_breakdown")
HT = NZ[NZ["subtype"] == HOT].copy()
HT["stance"] = HT["stance"].fillna("none")
st_order = STANCES + (["none"] if (HT["stance"] == "none").any() else [])
st_tab = _group_rows(HT, "stance", st_order, len(HT), int(HT["v"].sum()))
st_csv = st_tab.rename(columns={"share_of_group": "share_of_hot_takes", "share_of_group_views": "share_of_hot_take_views"})
save(st_csv, "12b_noise_stance")
nz_top = NZ.sort_values(["v", "id"], ascending=[False, True]).iloc[0]
SUMMARY["noise"] = {
    "posts": n_noise,
    "share_posts": n_noise / N,
    "views": noise_v,
    "share_views": noise_v / TOTAL_VIEWS,
    "likes": noise_l,
    "share_likes": noise_l / TOTAL_LIKES,
    "median_views": float(NZ["v"].median()),
    "not_subtyped": int((NZ["subtype"] == "not_subtyped").sum()),
    "subtypes": {r["subtype"]: {"posts": int(r["posts"]), "share_noise": r["share_of_group"], "share_noise_views": r["share_of_group_views"],
                                "median_views": r["median_views"]} for r in nb_tab.to_dict("records")},
    "hot_takes": int(len(HT)),
    "stance": {r["stance"]: int(r["posts"]) for r in st_tab.to_dict("records")},
    "top_card": {"id": str(nz_top["id"]), "views": int(nz_top["v"]), "subtype": nz_top["subtype"], "title": nz_top["t"], "url": nz_top["url"]},
}
_ns = nb_tab[nb_tab["subtype"] != "not_subtyped"].reset_index(drop=True)
_w = lambda k: NOISE_WORDS[k]
_lead = _ns.iloc[0]
_byv = _ns.sort_values("share_of_group_views", ascending=False).iloc[0]
_med = _ns[_ns["posts"] > 0].sort_values("median_views")
_stn = SUMMARY["noise"]["stance"]
noise_obs = (
    f"{_w(_lead['subtype']).capitalize()} are the largest sub-type, {int(_lead['posts']):,} of the {n_noise:,} noise posts ({pct(_lead['share_of_group'])}), "
    f"followed by {_w(_ns.iloc[1]['subtype'])} ({int(_ns.iloc[1]['posts']):,}, {pct(_ns.iloc[1]['share_of_group'])}) and "
    f"{_w(_ns.iloc[2]['subtype'])} ({int(_ns.iloc[2]['posts']):,}, {pct(_ns.iloc[2]['share_of_group'])}). "
    f"{_w(_byv['subtype']).capitalize()} hold the largest share of the noise's views, {pct(_byv['share_of_group_views'])} from {pct(_byv['share_of_group'])} of its posts, "
    f"and median views run from {num(_med.iloc[0]['median_views'])} ({_w(_med.iloc[0]['subtype'])}) to {num(_med.iloc[-1]['median_views'])} "
    f"({_w(_med.iloc[-1]['subtype'])}), against {num(A['v'].median())} for all posts. "
    f"Of the {len(HT):,} hot takes, {_stn.get('bullish', 0)} are bullish, {_stn.get('skeptical', 0)} skeptical, {_stn.get('mixed', 0)} mixed "
    f"and {_stn.get('neutral', 0)} neutral."
)
_ms, _mv, _mm, _mh = AE["meta_still"], AE["meta_vague"], AE["meta_meme"], AE["meta_hot"]
_under_half = _mm["value"] < 0.005 and _mh["value"] < 0.005
sections["noise_audit"] = (
    f"**{META_RANGE.capitalize()}: {ci('meta_still')} on the audit, {ao('meta_still') or ci('meta_all_samples')} on its samples alone.** "
    f"The {LABELS_TAG} labels put {pct(_ms['model'])} of posts there. The audit re-read {_ms['n']} of the posts the {AUDITED_MODEL} labels call "
    f"other_or_meta and {_ms['k']} stay meta; the other {_ms['n'] - _ms['k']} moved to a real family (most often classification) or out of the "
    f"base. That re-read alone gives {pct(_ms['frame_value'])}, the audit's published figure, but it counts no meta post outside the "
    f"{AUDITED_MODEL} labels' meta posts, and the audit's own random samples find about as many there as the re-read removes. "
    + ("" if MA_ is None else f"With the {int(_ms['plug'])} posts outside that stratum that {LABELS_TAG} calls meta taken on its word, the share "
       f"is {ci('meta_still')}; {LABELS_TAG}'s own {pct(_ms['model'])} is just above that and inside the samples-only interval. ")
    + (f"A careful reader still gives some of these posts a use: {hc_meta()}. " if hc_meta() else "")
    + f"Posts that never say what Jev decides, or that benchmark or wrap the model, are about {pct(_mv['value'])} of posts on "
    f"the audit's re-read ({_mv['k']} of the {_mv['n']}). Memes are {pct(_mm['value'], 2)} of posts and hot takes {pct(_mh['value'], 2)}"
    + (": under half a percent each. " if _under_half else ". ")
    + "The \"share of noise\" column below is a share of the noise posts, not of all posts."
    + ("" if SUMMARY["noise"]["not_subtyped"] == 0 else
       f" The sub-types come from a Claude Sonnet 5 pass over the posts the first labels called noise, so {SUMMARY['noise']['not_subtyped']:,} of "
       f"the {n_noise:,} posts {LABELS_TAG} calls noise have no sub-type yet (`scripts/refresh.sh` sub-types them).")
)
sections["noise"] = (
    f"The model puts **{n_noise:,} posts, {pct(n_noise / N)} of the base,** in other_or_meta, or labels them commentary in a use-case family: "
    f"the noise, with {pct(noise_v / TOTAL_VIEWS)} of views and {pct(noise_l / TOTAL_LIKES)} of likes. Claude Sonnet 5 put each of them in one of seven sub-types, "
    f"with a stance for hot takes (rubric: [rubric-noise.md](rubric-noise.md); script: `scripts/classify-noise.ts`, batches of 40). After a 40-card pilot, "
    f"the wording was tightened so that an end-user app whose post does not say what Jev decides counts as unrelated_or_unclear, not tooling_or_wrapper; "
    f"the full run used that wording."
    + (f" {SUMMARY['noise']['not_subtyped']} noise posts have no sub-type yet." if SUMMARY["noise"]["not_subtyped"] else "")
    + "\n\n"
    + md(
        pd.DataFrame(
            {
                "sub-type": list(nb_tab["subtype"]) + ["**all noise**"],
                "posts": list(nb_tab["posts"]) + [n_noise],
                "share of noise": [pct(v) for v in nb_tab["share_of_group"]] + ["100%"],
                "share of all posts": [pct(v) for v in nb_tab["share_of_all_posts"]] + [pct(n_noise / N)],
                "views": list(nb_tab["views"]) + [noise_v],
                "share of noise views": [pct(v) for v in nb_tab["share_of_group_views"]] + ["100%"],
                "share of all views": [pct(v) for v in nb_tab["share_of_all_views"]] + [pct(noise_v / TOTAL_VIEWS)],
                "median views": list(nb_tab["median_views"]) + [NZ["v"].median()],
                "most-viewed card": [f"{link(t, u)} ({v:,})" if u else "" for t, u, v in zip(nb_tab["top_card_title"], nb_tab["top_card_url"], nb_tab["top_card_views"], strict=True)]
                + [f"{link(nz_top['t'], nz_top['url'])} ({int(nz_top['v']):,})"],
            }
        )
    )
    + "\n\nHot takes by stance:\n\n"
    + md(
        pd.DataFrame(
            {
                "stance": st_tab["stance"],
                "posts": st_tab["posts"],
                "share of hot takes": [pct(v) for v in st_tab["share_of_group"]],
                "views": st_tab["views"],
                "median views": st_tab["median_views"],
                "most-viewed card": [f"{link(t, u)} ({v:,})" if u else "" for t, u, v in zip(st_tab["top_card_title"], st_tab["top_card_url"], st_tab["top_card_views"], strict=True)],
            }
        )
    )
    + "\n\n"
    + noise_obs
)

# ---------------------------------------------------------------- 9. tinkering, longevity, production
disp = read_jsonl(DATA / "hand-labels-disputes.jsonl")
reread = pd.DataFrame([r for r in disp if r["check"] == "measured_production_reread"])
reread = reread.merge(df[["id", "family", "family_v1", "evidence", "production_claim", "realtime_infra", "realtime_infra_v1", "v", "f", "t", "url", "dup_of"]], on="id", how="left")
code_names = {"P": "production (holds up)", "B": "benchmark, test or one-off job", "T": "trading own money or promo", "U": "personal use", "X": "not Jev"}
prod = {
    "v1_measured_production": int((df["evidence_v1"] == "measured_production").sum()),
    "v1_share": float((V1["evidence_v1"] == "measured_production").mean()),
    "reread_holds": int((reread["hand"] == "P").sum()),
    "reread_share": float((reread["hand"] == "P").sum() / N_V1),
    "reread_codes": {code_names.get(k, k): int(v) for k, v in reread["hand"].value_counts().items()},
    "v2_measured_production": int((A["evidence"] == "measured_production").sum()),
    "v2_share": float((A["evidence"] == "measured_production").mean()),
    "v2_production_claims": int(A["production_claim"].sum()),
    "v2_production_claim_share": float(A["production_claim"].mean()),
    "v2_mp_among_reread_P": int(((reread["hand"] == "P") & (reread["evidence"] == "measured_production")).sum()),
    "v2_mp_among_reread_not_P": int(((reread["hand"] != "P") & (reread["evidence"] == "measured_production")).sum()),
    "v2_mp_outside_reread": int(len(set(A.loc[A["evidence"] == "measured_production", "id"]) - set(reread["id"]))),
    "reread_P_by_family_v2": {k: int(v) for k, v in reread.loc[reread["hand"] == "P", "family"].value_counts().items()},
    "reread_P_realtime_v1": int((reread.loc[reread["hand"] == "P", "realtime_infra_v1"]).sum()),
    "reread_realtime_v1": int(reread["realtime_infra_v1"].sum()),
}
P_ok = reread[reread["hand"] == "P"].sort_values("v", ascending=False)
ex = P_ok.head(12)
sections["production"] = (
    f"**The first pass.** v1 Sonnet labelled {prod['v1_measured_production']} of the {N_V1:,} cards it saw "
    f"measured_production ({pct(prod['v1_share'])}). The review re-read all {len(reread)}: {prod['reread_holds']} hold up ({pct(prod['reread_share'])} of those {N_V1:,} cards); "
    + ", ".join(f"{v} {k}" for k, v in prod["reread_codes"].items() if not k.startswith("production"))
    + f". With the v2 rubric (explicit users, customers or a running service), Sonnet labels {prod['v2_measured_production']} of the {N:,} use-case cards "
    f"measured_production ({pct(prod['v2_share'])}) and {prod['v2_production_claims']} ({pct(prod['v2_production_claim_share'])}) as claiming production. "
    f"Of the re-read cards, v2 keeps {prod['v2_mp_among_reread_P']} of the {prod['reread_holds']} that hold up and {prod['v2_mp_among_reread_not_P']} of the "
    f"{len(reread) - prod['reread_holds']} that do not; "
    + (f"all {prod['v2_measured_production']} v2 measured_production cards are among v1's 95. " if prod["v2_mp_outside_reread"] == 0
       else f"{prod['v2_mp_outside_reread']} v2 measured_production card{'s were' if prod['v2_mp_outside_reread'] != 1 else ' was'} not in v1's 95 and not in that re-read. ")
    + f"Among the {prod['reread_holds']} that hold up, by v2 family: "
    + ", ".join(f"{SHORT.get(k, k)} {v}" for k, v in prod["reread_P_by_family_v2"].items())
    + f". v1 flagged {prod['reread_realtime_v1']} of the 95 as realtime; {prod['reread_P_realtime_v1']} of those hold up.\n\n"
    "Production cards that held up on the first review's re-read of v1 (most viewed first; the audit did not repeat this re-read):\n\n"
    + md(
        pd.DataFrame(
            {
                "views": ex["v"].values,
                "likes": ex["f"].values,
                "family (v2)": ex["family"].fillna("").values,
                "title": [link(t, u) for t, u in zip(ex["t"], ex["url"])],
            }
        )
    )
)
save(reread[["id", "hand", "hand_meaning", "family", "family_v1", "evidence", "production_claim", "v", "f", "t", "url"]], "09_production_reread")
SUMMARY["production"] = prod
A["repo_label"] = np.where(A["has_repo"], "repo", "no repo")
A["prod_label"] = np.where(A["production_claim"], "prod claim", "no prod claim")
ct8 = pd.crosstab(A["evidence"], [A["repo_label"], A["prod_label"]]).reindex(EVIDENCE, fill_value=0)
ct8.columns = [f"{a} / {b}" for a, b in ct8.columns]
ct8["total"] = ct8.sum(axis=1)
save(ct8, "09_evidence_x_repo_x_production", index=True)
ct8.index.name = "evidence"
sections["tinkering_crosstab"] = md(ct8, index=True)
mp = A.groupby("family").agg(
    posts=("id", "size"),
    measured_production=("evidence", lambda s: int((s == "measured_production").sum())),
    measured_demo=("evidence", lambda s: int((s == "measured_demo").sum())),
    production_claims=("production_claim", "sum"),
    repo=("has_repo", "sum"),
    verified_share=("vf", "mean"),
).reindex(t1.index)
save(mp, "09_production_repo_verified_by_family", index=True)
sections["tinkering_by_family"] = md(
    pd.DataFrame(
        {
            "family": mp.index,
            "posts": mp["posts"].values,
            "measured_production": mp["measured_production"].values,
            "measured_demo": mp["measured_demo"].values,
            "production claims": mp["production_claims"].values,
            "repo": mp["repo"].values,
            "verified accounts": [pct(v, 0) for v in mp["verified_share"]],
        }
    )
)
ppd = pd.crosstab(A["family"], A["day"]).reindex(index=t1.index, fill_value=0)
ppd.loc["**all**"] = ppd.sum()
save(ppd, "09_posts_per_day_by_family", index=True)
ppd_md = ppd.copy()
ppd_md.columns = [c[5:] for c in ppd_md.columns]
ppd_md.index.name = "family"
sections["posts_per_day"] = md(ppd_md, index=True)

# ---------------------------------------------------------------- 10. language
lang = A["lang"].value_counts()
lang_df = pd.DataFrame({"posts": lang, "share": lang / N})
lang_df["views"] = A.groupby("lang")["v"].sum().reindex(lang_df.index)
lang_df["likes"] = A.groupby("lang")["f"].sum().reindex(lang_df.index)
lang_df["share_views"] = lang_df["views"] / TOTAL_VIEWS
lang_df["share_likes"] = lang_df["likes"] / TOTAL_LIKES
save(lang_df, "10_language_overall", index=True)
top_l = lang_df.head(8)
sections["language"] = md(
    pd.DataFrame(
        {
            "lang": top_l.index,
            "posts": top_l["posts"].values,
            "share": [pct(v) for v in top_l["share"]],
            "share of views": [pct(v) for v in top_l["share_views"]],
            "share of likes": [pct(v) for v in top_l["share_likes"]],
        }
    )
) + f"\n\n{len(lang_df) - 8} further language codes hold {int(lang_df['posts'][8:].sum())} posts."
A["lang_group"] = A["lang"].where(A["lang"].isin(["en", "ja", "zh"]), "other")
ct9 = pd.crosstab(A["family"], A["lang_group"]).reindex(index=t1.index, columns=["en", "ja", "zh", "other"], fill_value=0)
save(ct9, "10_language_by_family_counts", index=True)
x = share_table(ct9, ["en", "ja", "zh", "other"])
x.index.name = "family"
sections["language_by_family"] = md(x, index=True)
SUMMARY["language"] = {k: round(float((A["lang"] == k).mean()), 4) for k in ["en", "ja", "zh"]}

# ---------------------------------------------------------------- 11. chips: cost and speed multiples only
MULT = [("cost multiple (N× cheaper)", re.compile(r"^([\d.,]+)\s*×\s*cheaper$")), ("speed multiple (N× faster)", re.compile(r"^([\d.,]+)\s*×\s*faster$"))]
mult_vals: dict[str, list[tuple[str, float]]] = {n_: [] for n_, _ in MULT}
for cid, chips in zip(A["id"], A["chips"]):
    for ch in chips or []:
        for name, rx in MULT:
            m = rx.match(ch.strip())
            if m:
                mult_vals[name].append((cid, float(m.group(1).replace(",", ""))))
rows11 = []
for name, vals in mult_vals.items():
    arr = np.array([v for _, v in vals])
    arr_x1 = arr[arr != 1.0]
    rows11.append(
        {
            "claim": name,
            "chips": len(arr),
            "cards": len({c for c, _ in vals}),
            "median": float(np.median(arr)),
            "p25": float(np.quantile(arr, 0.25)),
            "p75": float(np.quantile(arr, 0.75)),
            "chips_reading_1x": int((arr == 1.0).sum()),
            "median_without_1x": float(np.median(arr_x1)),
        }
    )
t11 = pd.DataFrame(rows11)
save(t11, "11_chip_multiples")
pd.DataFrame([(n_, c, v) for n_, vals in mult_vals.items() for c, v in vals], columns=["claim", "id", "value"]).to_csv(OUTD / "11_chip_multiples_long.csv", index=False)
sections["chips"] = md(
    pd.DataFrame(
        {
            "claim": t11["claim"],
            "chips": t11["chips"],
            "cards": t11["cards"],
            "median": [f"{v:.3g}×" for v in t11["median"]],
            "p25 to p75": [f"{a:.3g}× to {b:.3g}×" for a, b in zip(t11["p25"], t11["p75"])],
            'chips reading "1×"': t11["chips_reading_1x"],
            'median without "1×"': [f"{v:.3g}×" for v in t11["median_without_1x"]],
        }
    )
) + (
    f"\n\nCross-check: OpenChamber's own survey of user reports gives [about 30× cheaper and 7× faster]({OPENCHAMBER_SURVEY}). "
    "The accuracy and latency medians of v1 are dropped: the review found that the accuracy chips mix Jev's accuracy with the baseline's, "
    "Jev's stated confidence and corpus coverage, and that a third of the latency chips are whole-batch times or baselines."
)
SUMMARY["chips"] = {r["claim"]: {k: r[k] for k in r if k != "claim"} for r in rows11}

# ---------------------------------------------------------------- 12. agreement: Jev against Sonnet v2 and against the hand labels
B = L[L["jev_family"].notna()].copy()  # all labelled cards (duplicates and not-Jev included: this is about the classifiers)
B["fam_c"] = B["family"].replace({NOT_JEV: "other_or_meta"})  # Jev had no not_a_jev_build option
nb = len(B)
B["agree"] = B["fam_c"] == B["jev_family"]
B["agree_v1"] = np.where(B["family_v1"].notna(), B["family_v1"] == B["jev_family"], np.nan)  # cards added after v1 have no v1 label
B1 = B[B["family_v1"].notna()]
agree = float(B["agree"].mean())
kappa = kappa_of(B["fam_c"], B["jev_family"])
agree_v1 = float(B1["agree_v1"].mean())
kappa_v1 = kappa_of(B1["family_v1"], B1["jev_family"])
Bx = B[B["family"] != NOT_JEV]
agree_excl = float(Bx["agree"].mean())
nonmeta = B[(B["fam_c"] != "other_or_meta") & (B["jev_family"] != "other_or_meta")]
agree_nonmeta = float(nonmeta["agree"].mean())
cm = pd.crosstab(B["fam_c"], B["jev_family"]).reindex(index=FAMILIES_V1, columns=FAMILIES_V1, fill_value=0)
save(cm, "12_confusion_sonnet_v2_rows_jev_cols", index=True)
pr_rows = []
for f in FAMILIES_V1:
    tp = int(cm.loc[f, f])
    sup = int(cm.loc[f].sum())
    pred = int(cm[f].sum())
    prec = tp / pred if pred else float("nan")
    rec = tp / sup if sup else float("nan")
    f1 = 2 * prec * rec / (prec + rec) if pred and sup and (prec + rec) else float("nan")
    top_conf = cm.loc[f].drop(f).sort_values(ascending=False)
    pr_rows.append(
        {
            "family": f,
            "sonnet_n": sup,
            "jev_n": pred,
            "agree": tp,
            "precision": prec,
            "recall": rec,
            "f1": f1,
            "jev_most_often_instead": f"{SHORT[top_conf.index[0]]} ({int(top_conf.iloc[0])})" if sup and top_conf.iloc[0] > 0 else "",
        }
    )
pr = pd.DataFrame(pr_rows).sort_values("sonnet_n", ascending=False)
save(pr, "12_agreement_by_family")
bins = [0, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99, 1.0001]
labels = ["<0.3", "0.3–0.4", "0.4–0.5", "0.5–0.6", "0.6–0.7", "0.7–0.8", "0.8–0.9", "0.9–0.95", "0.95–0.99", "≥0.99"]
B["pbin"] = pd.cut(B["jev_prob"], bins=bins, labels=labels, right=False)
cal = B.groupby("pbin", observed=False).agg(cards=("id", "size"), mean_prob=("jev_prob", "mean"), agreement_v2=("agree", "mean"), agreement_v1=("agree_v1", "mean"))
cal["share_of_cards"] = cal["cards"] / nb
save(cal, "12_calibration_fixed_bins", index=True)
B["pdec"] = pd.qcut(B["jev_prob"].rank(method="first"), 10, labels=[f"D{i}" for i in range(1, 11)])
cald = B.groupby("pdec", observed=False).agg(
    cards=("id", "size"), prob_min=("jev_prob", "min"), prob_max=("jev_prob", "max"), mean_prob=("jev_prob", "mean"), agreement_v2=("agree", "mean"), agreement_v1=("agree_v1", "mean")
)
save(cald, "12_calibration_equal_count_deciles", index=True)
top_bin = B[B["jev_prob"] >= 0.99]
top_bin_games_trading = float(top_bin["jev_family"].isin([GAMES, "trading_and_markets"]).mean()) if len(top_bin) else float("nan")

# against the 120 hand labels
HJ = H[H["jev_family"].notna()].copy()
HJ["hand_fam"] = HJ["id"].map(lambda i: hand[i]["family"])
HJ["jev_ok"] = HJ["jev_family"] == HJ["hand_fam"]
HJ["v1_ok"] = HJ["family_v1"] == HJ["hand_fam"]
HJ["v2_ok"] = HJ["family"].replace({NOT_JEV: "other_or_meta"}) == HJ["hand_fam"]
hb = pd.cut(HJ["jev_prob"], bins=[0, 0.7, 0.9, 0.99, 1.0001], labels=["<0.7", "0.7–0.9", "0.9–0.99", "≥0.99"], right=False)
hcal = HJ.groupby(hb, observed=False).agg(cards=("id", "size"), mean_prob=("jev_prob", "mean"), jev_right=("jev_ok", "sum"), jev_rate=("jev_ok", "mean"))
save(hcal, "12_calibration_against_hand_labels", index=True)
hk = len(HJ)
jev_hand = {
    "n": hk,
    "jev": int(HJ["jev_ok"].sum()),
    "sonnet_v1": int(HJ["v1_ok"].sum()),
    "sonnet_v2": int(HJ["v2_ok"].sum()),
    "jev_ci": wilson(int(HJ["jev_ok"].sum()), hk),
    "v2_ci": wilson(int(HJ["v2_ok"].sum()), hk),
    "jev_at_099": f"{int(HJ.loc[HJ['jev_prob'] >= 0.99, 'jev_ok'].sum())}/{int((HJ['jev_prob'] >= 0.99).sum())}",
}
lat = B["jev_latency_ms"].dropna().to_numpy()
jev_err = read_jsonl(DATA / "classified-jev.errors.jsonl")
jev_err_unresolved = len({e["id"] for e in jev_err} - set(jev["id"]))
JEV_RUNS = "the first pass" + (", plus the cards added by refreshes" if len(jev) > N_V1 else "")
lat_stats = {
    "calls_ok": int(len(jev)),
    "p50_ms": float(np.percentile(lat, 50)),
    "p95_ms": float(np.percentile(lat, 95)),
    "p99_ms": float(np.percentile(lat, 99)),
    "failed_calls": len(jev_err),
    "error_rate": len(jev_err) / max(1, len(jev) + len(jev_err)),
}
sections["agreement"] = (
    f"Jev's labels use the v1 family definitions (14 families; it had no not_a_jev_build option, so v2's not_a_jev_build counts as other_or_meta here). "
    f"All {nb:,} cards with both labels, duplicates included (this compares classifiers, not posts).\n\n"
    f"- **Against {LABELS_TAG}: {pct(agree)}** agreement, kappa {kappa:.2f} (against v1, on the {len(B1):,} cards v1 labelled: {pct(agree_v1)}, kappa {kappa_v1:.2f}). "
    f"Leaving out the {int((B['family'] == NOT_JEV).sum())} cards v2 calls not_a_jev_build: {pct(agree_excl)}. "
    f"When neither says other_or_meta: {pct(agree_nonmeta)} (n={len(nonmeta):,}).\n"
    f"- **Against the 120 hand labels** (the review's, v1 families): Jev {jev_hand['jev']}/{hk} ({pct(jev_hand['jev'] / hk)}, 95% CI "
    f"{pct(jev_hand['jev_ci'][0])}–{pct(jev_hand['jev_ci'][1])}), {LABELS_TAG} {jev_hand['sonnet_v2']}/{hk} ({pct(jev_hand['sonnet_v2'] / hk)}, CI "
    f"{pct(jev_hand['v2_ci'][0])}–{pct(jev_hand['v2_ci'][1])}), Sonnet v1 {jev_hand['sonnet_v1']}/{hk} ({pct(jev_hand['sonnet_v1'] / hk)}). "
    f"Jev at a stated probability of 0.99 or more: {jev_hand['jev_at_099']} right.\n"
    f"- Games or trading make up {pct(top_bin_games_trading)} of Jev's ≥ 0.99 calls.\n"
    f"- **Against the audit** (Audit section): on the {AE['jev_audit_p99']['n']} audited cards where Jev's stated probability is 0.99 or more, "
    f"Jev's family matches the audit's on {AE['jev_audit_p99']['k']} ({pct(AE['jev_audit_p99']['value'])}).\n\n"
    + md(
        pd.DataFrame(
            {
                f"family ({LABELS_TAG})": pr["family"],
                f"{LABELS_SHORT} n": pr["sonnet_n"],
                "Jev n": pr["jev_n"],
                "agree": pr["agree"],
                "precision": [pct(v, 0) for v in pr["precision"]],
                "recall": [pct(v, 0) for v in pr["recall"]],
                "F1": [f"{v:.2f}" if not pd.isna(v) else "" for v in pr["f1"]],
                "Jev's most common other answer": pr["jev_most_often_instead"],
            }
        )
    )
)
cm_md = cm.copy()
cm_md.index = [SHORT[i] for i in cm_md.index]
cm_md.columns = [SHORT[c] for c in cm_md.columns]
cm_md.index.name = f"{LABELS_TAG} ↓ / Jev →"
sections["confusion"] = md(cm_md, index=True)
sections["calibration"] = (
    "Equal-count deciles of Jev's stated probability (D1 lowest), all cards:\n\n"
    + md(
        pd.DataFrame(
            {
                "decile": cald.index.astype(str),
                "cards": cald["cards"].values,
                "prob range": [f"{a:.2f}–{b:.2f}" for a, b in zip(cald["prob_min"], cald["prob_max"])],
                "mean prob": [f"{v:.3f}" for v in cald["mean_prob"]],
                f"agreement with {LABELS_TAG}": [pct(v) for v in cald["agreement_v2"]],
                "agreement with Sonnet v1": [pct(v) for v in cald["agreement_v1"]],
            }
        )
    )
    + "\n\nFixed-width bins, all cards:\n\n"
    + md(
        pd.DataFrame(
            {
                "Jev probability": cal.index.astype(str),
                "cards": cal["cards"].values,
                "share of cards": [pct(v) for v in cal["share_of_cards"]],
                "mean probability": [f"{v:.3f}" if not pd.isna(v) else "" for v in cal["mean_prob"]],
                f"agreement with {LABELS_TAG}": [pct(v) for v in cal["agreement_v2"]],
                "agreement with Sonnet v1": [pct(v) for v in cal["agreement_v1"]],
            }
        )
    )
    + "\n\nAgainst the 120 hand labels (coarse bins; the sample is small):\n\n"
    + md(
        pd.DataFrame(
            {
                "Jev probability": hcal.index.astype(str),
                "cards": hcal["cards"].values,
                "mean probability": [f"{v:.3f}" if not pd.isna(v) else "" for v in hcal["mean_prob"]],
                "Jev right": [f"{int(a)}/{int(b)}" for a, b in zip(hcal["jev_right"], hcal["cards"])],
                "rate": [pct(v) for v in hcal["jev_rate"]],
            }
        )
    )
)
sections["jev_latency"] = (
    f"{lat_stats['calls_ok']:,} successful calls ({JEV_RUNS}). Wall time per evaluate() call from a laptop through the Gateway: "
    f"p50 {lat_stats['p50_ms']:,.0f} ms, p95 {lat_stats['p95_ms']:,.0f} ms, p99 {lat_stats['p99_ms']:,.0f} ms. "
    f"{lat_stats['failed_calls']} failed calls ({pct(lat_stats['error_rate'], 2)}), "
    + ("all retried successfully." if jev_err_unresolved == 0 else f"{jev_err_unresolved} still unlabelled.")
)
cw = pd.crosstab(A["cat"], A["family"]).reindex(columns=[f for f in FAMILIES_V1], fill_value=0)
save(cw, "12_openchamber_cat_x_family", index=True)
cw_rows = []
for cat, row in cw.iterrows():
    tot_c = row.sum()
    top = row.sort_values(ascending=False).head(3)
    cw_rows.append({"OpenChamber category": cat, "cards": int(tot_c), "our top families": "; ".join(f"{SHORT[f]} {pct(v / tot_c, 0)}" for f, v in top.items() if v > 0)})
sections["crosswalk"] = md(pd.DataFrame(cw_rows).sort_values("cards", ascending=False))
SUMMARY["agreement"] = {
    "n": nb,
    "jev_vs_v2": round(agree, 4),
    "kappa_v2": round(kappa, 3),
    "jev_vs_v1": round(agree_v1, 4),
    "kappa_v1": round(kappa_v1, 3),
    "jev_vs_v2_excluding_not_jev": round(agree_excl, 4),
    "jev_vs_v2_excluding_other": round(agree_nonmeta, 4),
    "top_bin_share": float((B["jev_prob"] >= 0.99).mean()),
    "top_bin_agreement_v2": float(top_bin["agree"].mean()),
    "top_bin_games_trading": top_bin_games_trading,
    "hand": jev_hand,
    "deciles": {str(k): {"prob_min": float(r.prob_min), "prob_max": float(r.prob_max), "agreement_v2": float(r.agreement_v2), "agreement_v1": float(r.agreement_v1)} for k, r in cald.iterrows()},
    "jev_latency": lat_stats,
}

# ---------------------------------------------------------------- 13. hand-label check: v1 against v2, per field
pilots = {p.stem.replace("classified-sonnet-", ""): p for p in sorted((DATA / "pilot").glob("classified-sonnet-v2.pilot*.jsonl"))}
label_sets = {"v1 (full run)": {r["id"]: r for r in read_jsonl(DATA / "classified-sonnet.jsonl")}}
for k, p in pilots.items():
    label_sets[f"{k} (pilot)"] = {r["id"]: r for r in read_jsonl(p)}
SON2_HISTORY = read_jsonl(DATA / "classified-sonnet-v2.jsonl")  # the history below is Sonnet v1 against Sonnet v2, whatever the reference labels
label_sets["v2 (full run)"] = {r["id"]: r for r in SON2_HISTORY}
if not AUDITED:
    label_sets[f"{LABELS_TAG} (full run)"] = {r["id"]: r for r in son2_rows}
scores = {k: hand_score(v, hand) for k, v in label_sets.items()}
HAND_PUBLIC = [f for f in HAND_FIELDS if f != "framing"]  # framing is withdrawn
hrow = []
for f in HAND_PUBLIC:
    row = {"field": f, "review's v1 figure": f"{V1_REVIEW[f]}%" if f in V1_REVIEW else ""}
    for k, s in scores.items():
        row[k] = f"{pct(s[f]['rate'])} (κ {s[f]['kappa']:.2f})" if s["n"] else ""
    hrow.append(row)
hand_tab = pd.DataFrame(hrow)
save(hand_tab, "13_hand_label_agreement_by_field")
# stability: the final pilot and the full run labelled the same 120 cards with the same rubric
last_pilot = list(pilots)[-1] if pilots else None
stab = {}
if last_pilot:
    lp = label_sets[f"{last_pilot} (pilot)"]
    full = label_sets["v2 (full run)"]
    common = [i for i in lp if i in full]
    stab = {f: f"{sum(lp[i][f] == full[i][f] for i in common)}/{len(common)}" for f in PUBLIC_FIELDS}
sections["hand_check"] = (
    "Per-field agreement with the review's 120 hand labels (the review agent's labels, blind to Sonnet and Jev, made against the v1 rubric). "
    "\"family\" counts v2's not_a_jev_build as other_or_meta, like for like with v1; \"family_v2\" scores the 7 cards the review noted as not Jev builds "
    "as not_a_jev_build. Pilot 1 was the first v2 wording; pilot 2 followed one adjustment (tier read from how the build is used, \"a previous limit is gone\" "
    "counted as capability, a before-and-after figure counted as a comparison); the full run used the pilot 2 wording.\n\n"
    + md(hand_tab)
    + (f"\n\nRun-to-run stability of v2 on the same 120 cards (pilot 2 against the full run; Sonnet 5 ignores temperature): "
       + ", ".join(f"{k} {v}" for k, v in stab.items()) + "." if stab else "")
)
SUMMARY["hand_check"] = {k: {f: {"rate": s[f]["rate"], "kappa": s[f]["kappa"]} for f in HAND_PUBLIC} for k, s in scores.items() if s["n"]}
SUMMARY["v2_stability_on_120"] = stab

# ---------------------------------------------------------------- v1 → v2 shifts on all cards
_s2h = pd.DataFrame(SON2_HISTORY).drop_duplicates("id", keep="first")[["id"] + LABEL_FIELDS]
both = df[["id"] + [f"{k}_v1" for k in LABEL_FIELDS]].merge(_s2h, on="id", how="inner")
both = both[both["family_v1"].notna()].copy()
both["family_sonnet"] = both["family"]  # Sonnet v2's own family, before the Snake rule
shift_rows = []
for fld, val in [
    ("family", "other_or_meta"),
    ("family", NOT_JEV),
    ("evidence", "measured_demo"),
    ("evidence", "measured_production"),
    ("evidence", "demo_no_numbers"),
    ("baseline", "none"),
    ("baseline", "frontier_llm"),
    ("realtime_infra", True),
    ("production_claim", True),
]:
    a1 = (both[f"{fld}_v1"] == val).mean()
    a2 = (both[fld] == val).mean() if fld != "family" else (both["family_sonnet"] == val).mean()
    shift_rows.append({"label": f"{fld} = {val}", "v1 share": pct(a1), "v2 share": pct(a2)})
same = {f: float((both[f] == both[f + "_v1"]).mean()) if f != "family" else float((both["family_sonnet"].replace({NOT_JEV: "other_or_meta"}) == both["family_v1"]).mean()) for f in PUBLIC_FIELDS}
shift = pd.DataFrame(shift_rows)
save(shift, "13_v1_to_v2_shifts")
sections["shifts"] = (
    f"On all {len(both):,} cards (Sonnet's own labels, before dedupe or the Snake rule):\n\n"
    + md(shift)
    + "\n\nShare of cards whose label is unchanged from v1 to v2: "
    + ", ".join(f"{k} {pct(v)}" for k, v in same.items())
    + ". Framing is left out: it is withdrawn (section 4)."
)
SUMMARY["v1_to_v2"] = {"unchanged": same, "shifts": shift_rows}

# ---------------------------------------------------------------- cost
def sonnet_cost(rows: list[dict]) -> dict:
    t = {k: sum(r.get(k, 0) for r in rows) for k in ["input", "noCache", "cacheRead", "cacheWrite", "output"]}
    t["usd"] = (t["noCache"] * SONNET_PRICE["input"] + t["cacheRead"] * SONNET_PRICE["cacheRead"] + t["cacheWrite"] * SONNET_PRICE["cacheWrite"] + t["output"] * SONNET_PRICE["output"]) / 1e6
    gw = [float(r["gatewayCost"]) for r in rows if r.get("gatewayCost") not in (None, "")]
    t["gateway_reported_usd"] = sum(gw) if gw else None
    t["calls"] = len(rows)
    return t


usage_v2 = read_jsonl(DATA / "usage-sonnet-v2.jsonl")
usage_v1 = read_jsonl(DATA / "usage-sonnet.jsonl")
pilot_v2_usage = [r for p in sorted((DATA / "pilot").glob("usage-sonnet-v2.pilot*.jsonl")) for r in read_jsonl(p)]
pilot_v1_usage = read_jsonl(DATA / "pilot" / "usage-sonnet.pilot1.jsonl")
sc_v2, sc_v2p, sc_v1, sc_v1p = sonnet_cost(usage_v2), sonnet_cost(pilot_v2_usage), sonnet_cost(usage_v1), sonnet_cost(pilot_v1_usage)
sc_nz = sonnet_cost(read_jsonl(DATA / "usage-noise.jsonl"))
sc_nzp = sonnet_cost([r for p_ in sorted((DATA / "pilot").glob("usage-noise.pilot*.jsonl")) for r in read_jsonl(p_)])
noise_usd = sc_nz["usd"] + sc_nzp["usd"]
nz_pilot_cards = sum(r.get("n", 0) for p_ in sorted((DATA / "pilot").glob("usage-noise.pilot*.jsonl")) for r in read_jsonl(p_))
jev_tokens = int(jev["jev_input_tokens"].fillna(0).sum())
jev_usd = jev_tokens * JEV_PRICE_INPUT / 1e6
cost_df = pd.DataFrame(
    [
        {"item": "v2 pass: Sonnet 5, full run (rubric v2)", **{k: sc_v2[k] for k in ["calls", "noCache", "cacheRead", "cacheWrite", "output", "usd", "gateway_reported_usd"]}},
        {"item": "v2 pass: Sonnet 5, two 120-card pilots", **{k: sc_v2p[k] for k in ["calls", "noCache", "cacheRead", "cacheWrite", "output", "usd", "gateway_reported_usd"]}},
        {"item": "v2 pass: Sonnet 5, noise sub-types", **{k: sc_nz[k] for k in ["calls", "noCache", "cacheRead", "cacheWrite", "output", "usd", "gateway_reported_usd"]}},
        {"item": "v2 pass: Sonnet 5, noise sub-type pilot", **{k: sc_nzp[k] for k in ["calls", "noCache", "cacheRead", "cacheWrite", "output", "usd", "gateway_reported_usd"]}},
        {"item": "v1 pass: Sonnet 5, main run", **{k: sc_v1[k] for k in ["calls", "noCache", "cacheRead", "cacheWrite", "output", "usd", "gateway_reported_usd"]}},
        {"item": "v1 pass: Sonnet 5, discarded pilot", **{k: sc_v1p[k] for k in ["calls", "noCache", "cacheRead", "cacheWrite", "output", "usd", "gateway_reported_usd"]}},
        {"item": "v1 pass: Jev (input only; output free)", "calls": len(jev), "noCache": jev_tokens, "cacheRead": 0, "cacheWrite": 0, "output": 0, "usd": jev_usd, "gateway_reported_usd": None},
    ]
)
save(cost_df, "00_gateway_cost")
v2_pass = sc_v2["usd"] + sc_v2p["usd"]
v1_pass = sc_v1["usd"] + sc_v1p["usd"] + jev_usd
usage_labels = usage_v2 if AUDITED else [r for f_ in usage_files(LABELS_PATH) for r in read_jsonl(f_)]
sc_lab = sc_v2 if AUDITED else sonnet_cost(usage_labels)
if not AUDITED:  # list prices above are Sonnet's; for another model use what the Gateway reported, if the usage file has it
    sc_lab["usd"] = sc_lab["gateway_reported_usd"]
SUMMARY["cost"] = {"v2_full": sc_v2, "v2_pilots": sc_v2p, "v2_pass_usd": v2_pass, "v1_pass_usd": v1_pass, "jev_usd": jev_usd,
                   "noise": sc_nz, "noise_pilot": sc_nzp, "noise_usd": noise_usd,
                   "labels_run": {"model": LABELS_MODEL, "file": LABELS_REL, "usd": sc_lab["usd"], "calls": sc_lab["calls"]}}

# ---------------------------------------------------------------- data quality
dq = {
    "cards": N_CARDS,
    "unique_ids": int(cards["id"].nunique()),
    "duplicate_urls": int(cards["url"].duplicated().sum()),
    "text_exactly_400_chars": int((cards["x"].str.len() == 400).sum()),
    "zero_views": int((cards["v"] == 0).sum()),
    "sonnet_v2_labelled": int(len(L)),
    "sonnet_v2_missing": son2_missing,
    "sonnet_v2_stray_ids": len(son2_stray),
    "sonnet_v2_duplicate_rows": son2_dups,
    "sonnet_v2_batches": len(usage_labels),
    "sonnet_v2_retry_round_batches": sum(1 for r in usage_labels if r.get("round", 1) > 1),
    "sonnet_v2_ids_missing_from_a_response": sum(r.get("missing", 0) for r in usage_labels),
    "sonnet_v2_stray_ids_in_responses": sum(r.get("stray", 0) for r in usage_labels),
    "jev_duplicate_rows": jev_dups,
    "day_field_matches_id_time": bool((cards["d"] == cards["day"]).all()),
}
save(pd.DataFrame([dq]), "00_data_quality")
SUMMARY["data_quality"] = dq
# ---------------------------------------------------------------- headline numbers (audited; generated, so a refresh updates them)
cs_ = SUMMARY["concentration"]
chip_c, chip_s = SUMMARY["chips"]["cost multiple (N× cheaper)"], SUMMARY["chips"]["speed multiple (N× faster)"]
def mult(v: float) -> str:
    return f"{v:.3g}×"


_cand = SUMMARY["candidates"]
_bf = _cand["before"]
_ms = AE["meta_still"]
REFUSED_NOTE = (f"; {LABELS_MODEL}'s safety filter refused {len(REFUSED)} post, which is left out" if len(REFUSED) == 1 else
                f"; {LABELS_MODEL}'s safety filter refused {len(REFUSED)} posts, which are left out" if REFUSED else "")
FILL_NOTE = ("" if AUDITED else
             f" The audit sampled from the {AUDITED_MODEL} labels; `review/estimate-opus.py` repeats its estimators with the {LABELS_MODEL} "
             f"labels as the model under test, which fill the regions the audit did not sample (Audit section).")



sections["summary"] = (
    f"**Headline numbers (audited).** Reference labels: {LABELS_MODEL} (`{LABELS_REL}`). Use-case base: {N:,} of the {N_CARDS:,} posts, "
    f"after {len(dd['merged_to'])} duplicates merged and {len(NJ):,} posts ({pct(nj_stats['share_of_deduped'])}) that do not use Jev left out"
    f"{REFUSED_NOTE}. An independent reviewer ({AUDITOR}) labelled {AUD['labelled']:,} posts blind to the model's labels (Audit section). Each "
    f"share below is an audited estimate with its 95% interval, a share of the {EB_:,} posts in the use-case base, unless it "
    f"says it is the model's count or a census.{FILL_NOTE}\n\n"
    f"1. **None of the most promising builds did something new.** Of the {_cand['posts']} candidate builds (a measured decision inside a live "
    f"system, made while a person waits), {_cand['unavailable']} did something that was unavailable before. A team would have used an LLM for "
    f"{_bf['llm']}, rules or heuristics for {_bf['rules']}, a vendor API for {_bf['vendor']} and a classic model for {_bf['classic']} "
    f"({_cand['distinct']} distinct builds).\n"
    f"2. **The measurement ladder.** No measurement {ci('ladder_no_measurement')}, of which demos with no numbers are "
    f"{ci('ladder_demo_no_numbers')} of all posts and a cost, speed or accuracy claim with no measurement {ci('ladder_claim_no_number')}; "
    f"measured demos {ci('ladder_measured_demo')}; measured production {ps_['k']} posts on the audit's re-read, {pct(ps_['value'], 2)}, at most "
    f"{pct(ps_['hi'])} (" + (f"the audit agrees with {_prod_s['model_mp_audited_holds']} of the {_prod_s['model_mp_audited']} {LABELS_TAG} "
                             f"production posts it read; " if _prod_s else "") + f"the first labelling pass said {pct(fp_['value'])}).\n"
    f"3. **Comparison baselines.** {ci('baseline_none')} of posts compare Jev with nothing, {ci('baseline_frontier_llm')} with a frontier LLM, "
    f"{ci('baseline_small_llm')} with a small LLM, and {ci('baseline_replacement')} with classic ML, rules or a vendor API, the tools Jev "
    f"would replace" + (f"; all four of the {LABELS_TAG} labels' own shares are inside these intervals"
                        if MA_ and all(inside(k) for k in ("baseline_none", "baseline_frontier_llm", "baseline_small_llm", "baseline_replacement")) else "")
    + ".\n"
    f"4. **Attention is a handful of posts (a census).** The top 1% of posts ({int(conc_v.loc[1, 'cards'])}) hold {pct(cs_['top1pct_views'])} "
    f"of views and {pct(cs_['top1pct_likes'])} of likes; without the {cs_['suspect_cards']} posts with 100k or more views and a like rate under "
    f"0.2%, {pct(cs_['top1pct_views_excl_suspect'])}. The most-viewed post alone is {pct(cs_['top_card_share'])} of views.\n"
    f"5. **Realtime.** Voice, live chat and collaboration are {ci('rt_families')} of posts, {_none_or(AE['rt_families_production']['value'])} "
    f"measured in production" + ("" if MA_ is None else f" and {_none_or(AE['rt_families_production_claims']['value'])} claiming production "
                                   f"without a measurement") + ". A live loop outside games is "
    f"{ci('live_loop_nongame')} of posts; with games, about a fifth ({pct(AE['live_loop_all']['value'])}).\n"
    f"6. **Under 300 ms.** About {ci('sub300_set')} of posts need a decision in under 300 ms, and {ci('sub300_games')} of those are games"
    + ("" if MA_ is None else f" ({LABELS_TAG}'s own {pct(AE['sub300_set']['model'])} is outside the interval)")
    + ". That coarse split is the only tier figure published (section 2).\n"
    f"7. **Meta posts.** {META_RANGE.capitalize()}: {ci('meta_still')} on the audit, {ao('meta_still') or ci('meta_all_samples')} on its "
    f"samples alone, {pct(_ms['model'])} on the {LABELS_TAG} labels (section \"What the noise is made of\"). Memes "
    f"({pct(AE['meta_meme']['value'], 2)}) and hot takes "
    f"({pct(AE['meta_hot']['value'], 2)}) are " + ("under half a percent of posts each.\n" if _under_half else "small.\n")
    + f"8. **Claims (a census of the claim chips).** The median cost claim is {mult(chip_c['median'])} cheaper ({mult(chip_c['median_without_1x'])} "
    f"without the \"1×\" chips) and the median speed claim {mult(chip_s['median'])} faster ({mult(chip_s['median_without_1x'])}). OpenChamber's "
    f"own survey gives 30× and 7×.\n"
    f"9. **Jev as a classifier.** Jev matches {LABELS_TAG} on {pct(agree)} of cards (kappa {kappa:.2f}), and {pct(float(top_bin['agree'].mean()))} "
    f"when its stated probability is 0.99 or more. On the {AE['jev_audit_p99']['n']} audited cards at 0.99 or more, it matches the audit's family "
    f"on {pct(AE['jev_audit_p99']['value'])}, and it is right on {jev_hand['jev_at_099'].replace('/', ' of the ')} such calls in the earlier 120 "
    f"hand labels."
)

# ---------------------------------------------------------------- the audit section
_samp = pd.read_csv(OUTD / "13_audit_sampling.csv")
_agr = pd.read_csv(OUTD / "13_audit_agreement.csv")
_clm = pd.read_csv(OUTD / "13_audit_claims.csv")
_pag = pd.read_csv(OUTD / "13_audit_primary_agreement.csv")
_vc = AUD["verdicts"]
_lf, _ls, _lr = AE["limits_frontier_stratum"], AE["limits_small_stratum"], AE["limits_unsampled_remainder"]
_lc, _lo = AE["limits_numeric_chip"], AE["limits_prior_overlap"]
FIELD_NAMES = {"family": "family", "tier": "tier", "evidence": "evidence", "baseline": "baseline", "realtime_infra": "realtime",
               "production_claim": "production"}
_agr_p = _agr[_agr["labels"] == LABELS_REL]
EST_ROWS = [
    ("baseline_none", "Compare Jev with nothing", 1), ("baseline_frontier_llm", "Compare it with a frontier LLM", 1),
    ("baseline_small_llm", "Compare it with a small LLM", 1), ("baseline_replacement", "Compare it with the tools it would replace", 1),
    ("ladder_no_measurement", "No measurement", 1), ("ladder_demo_no_numbers", "Demos with no numbers", 1),
    ("ladder_claim_no_number", "A cost, speed or accuracy claim with no measurement", 1), ("ladder_measured_demo", "Measured demos", 1),
    ("production_strict", "Measured production", 2), ("rt_families", "Voice, live chat or collaboration", 1),
    ("live_loop_nongame", "A live loop outside games", 1), ("live_loop_all", "A live loop, games included", 1),
    ("sub300_set", "Need a decision in under 300 ms", 1), ("sub300_games", "Games, among those under 300 ms", 1),
    ("meta_still", "Meta posts, on a re-read of the model's meta posts", 1),
    ("meta_all_samples", "Meta posts, across all the audit's samples", 1), ("meta_vague", "Never say what Jev decides, or benchmark or wrap it", 1),
    ("meta_meme", "Memes", 2), ("meta_hot", "Hot takes", 2),
]


def _ci_of(e: dict, lo: str = "lo", hi: str = "hi", d: int = 1) -> str:
    return "" if e.get(lo) is None else rng(e[lo], e[hi], d)


sections["audit"] = (
    f"An independent reviewer ({AUDITOR}, another AI model, not a person) labelled {AUD['labelled']:,} of the {AUD['use_case_base']:,} use-case "
    f"posts blind to the model's labels, against the same rubric: every post in the rare strata (a census) and seeded random samples of the "
    f"rest (seed {int(AE['seed']['value'])}, `review/sample.py`). It sampled from the {AUDITED_MODEL} labels (rubric v2), so its strata are "
    f"groups of posts as those labels drew them. Each sample is scaled to its stratum with a 95% Wilson interval; where two sampled strata are "
    f"added, the bounds are the sum of the stratum bounds, which is wider than a joint interval. The review is "
    f"[review/critical-review-grok.md](../review/critical-review-grok.md) and its labels are "
    f"[review/hand-labels-grok.jsonl](../review/hand-labels-grok.jsonl); its scripts are `review/sample.py`, `review/estimate.py`, "
    f"`review/arithmetic.py` and `review/work/substance.py`. The tables here are `data/13_audit_*.csv`, written from those scripts by "
    f"`scripts/audit.py`.\n\n"
    + ("" if AUDITED else
       f"This report's reference labels are {LABELS_MODEL}'s, so `review/estimate-opus.py` ([review/audit-opus.md](../review/audit-opus.md)) "
       f"repeats the audit's estimators with those labels as the model under test, and `scripts/audit.py` copies its tables into "
       f"`data/13_audit_*.csv`. The audit's labels stay the reference. Shares are of {LABELS_TAG}'s own use-case base ({EB_:,} posts), each "
       f"stratum cut to that base. The regions the audit did not sample (the frontier and small-LLM baselines, the games left out of the "
       f"realtime-family check, the realtime-flagged games, the proposal and commentary posts, and the posts outside the under-300 ms and meta "
       f"strata) take the {LABELS_TAG} labels, and each estimate says how many posts that is. A samples-only variant takes neither model's word "
       f"there. Run with the {AUDITED_MODEL} labels, the same code reproduces the audit's own numbers exactly, and it stops if it does not.\n\n")
    + "### Sampling\n\n"
    + md(pd.DataFrame({
        "stratum": list(_samp["stratum"]) + ["**unique cards audited**"],
        "how": list(_samp["kind"]) + [""],
        "population": [f"{int(v):,}" for v in _samp["population"]] + [""],
        "audited": [f"{int(v):,}" for v in _samp["reviewed"]] + [f"{AUD['labelled']:,} ({int(AE['census_unique']['value'])} in census strata)"],
    }))
    + "\n\nA post can sit in more than one stratum, so the audited column sums to more than the unique cards.\n\n"
    "### Agreement with the audit\n\n"
    + ("Share of the audited cards where each label file matches the audit, field by field (framing is withdrawn and not scored here). "
       "The strata are not a random sample of posts, so this is agreement on the audited cards, not on the base.\n\n"
       + md(pd.DataFrame({
           "labels": [f"{AUDITED_MODEL} (the labels the audit sampled from)"] + ([] if AUDITED else [f"{LABELS_MODEL} (this report)"]),
           **{FIELD_NAMES[f]: [pct(AUD["frame_agreement"][f], 0)] + ([] if AUDITED else [pct(AUD["primary_agreement"][f], 0)]) for f in FIELD_NAMES},
       }))
       + f"\n\nBy stratum, for the {LABELS_MODEL} labels:\n\n"
       + md(pd.DataFrame({"stratum": _agr_p["stratum"], "n": _agr_p["n"], **{FIELD_NAMES[f]: [pct(v, 0) for v in _agr_p[f]] for f in FIELD_NAMES}})))
    + "\n\n### The estimates this report uses\n\n"
    + (f"Shares of the {AUD['use_case_base']:,} posts the audit sampled from, with the 95% interval, and the model's own share.\n\n" if MA_ is None
       else f"Shares of {LABELS_TAG}'s use-case base ({EB_:,} posts) from `review/estimate-opus.py` ([review/audit-opus.md](../review/audit-opus.md)), "
            f"with the 95% interval. \"On {LABELS_TAG}'s word\" is how many posts the estimate takes from {LABELS_TAG}'s labels where the audit did "
            f"not sample; \"samples only\" replaces those with the audit's random samples; \"as the audit ran it\" is the audit's own estimate "
            f"with the {AUDITED_MODEL} labels.\n\n")
    + md(pd.DataFrame({
        "posts that": [label for _, label, _ in EST_ROWS],
        "estimate": [pct(AE[k]["value"], d) for k, _, d in EST_ROWS],
        "95% interval": [_ci_of(AE[k], d=d) for k, _, d in EST_ROWS],
        **({} if MA_ is None else {
            f"on {LABELS_TAG}'s word": ["" if AE[k].get("plug") is None else f"{int(AE[k]['plug'])}" for k, _, _ in EST_ROWS],
            "samples only": [ao(k, d) for k, _, d in EST_ROWS],
            "as the audit ran it": [pct(AE[k].get("frame_value", AE[k]["value"]), d) for k, _, d in EST_ROWS]}),
        f"{LABELS_TAG} labels": [pct(AE[k]["model"], d) if AE[k].get("model") is not None else "" for k, _, d in EST_ROWS],
    }))
    + "\n\n### The ten claims\n\n"
    f"The claims the audit tested, as first published, with its corrected value and 95% interval, as the audit ran them on the {AUDITED_MODEL} "
    f"labels. {_vc.get('Holds', 0)} hold, {_vc.get('Holds with correction', 0)} hold with a correction and {_vc.get('Fails', 0)} fail; the failed "
    f"ones are withdrawn and this report uses the estimates above.\n\n"
    + md(pd.DataFrame({"#": _clm["claim"].astype(str), "claim": _clm["topic"], "published": _clm["published"], "corrected": _clm["corrected"],
                       "95% interval": _clm["interval"], "verdict": _clm["verdict"],
                       **({} if MA_ is None else {f"with {LABELS_TAG} labels": _clm["labels_audit"].fillna(""),
                                                  f"verdict with {LABELS_TAG}": _clm["labels_verdict"].fillna("")})}))
    + ("" if MA_ is None else
       f"\n\nTwo of the audit's fails, claims 1 and 7, rest on its estimator taking the posts outside its sampled strata as correctly labelled. "
       f"Estimated from its own random samples instead, the {AUDITED_MODEL} labels' {pct(AE['baseline_none']['frame_model'])} with no comparison "
       f"and {pct(AE['meta_still']['frame_model'])} meta posts sit inside the intervals "
       f"({rng(AE['baseline_none']['frame_audit_only_lo'], AE['baseline_none']['frame_audit_only_hi'])} and "
       f"{rng(AE['meta_still']['frame_audit_only_lo'], AE['meta_still']['frame_audit_only_hi'])}). That is why every figure in this report is a "
       f"range: the point estimate depends on what is assumed where the audit did not look.")
    + "\n\n### What the audit could not check\n\n"
    + (f"The {int(_lf['value']):,} posts with a frontier-LLM baseline and the {int(_ls['value']):,} with a small-LLM baseline (on the {AUDITED_MODEL} "
       f"labels) were not sampled, so those two shares rest on the labels there being right"
       if MA_ is None else
       f"The strata were drawn on the {AUDITED_MODEL} labels, which is a valid design for {LABELS_TAG}'s labels but a less efficient one. "
       f"The {int(AE['plug_frontier_small']['value']):,} posts the {AUDITED_MODEL} labels say compare Jev with a frontier or small LLM were not "
       f"sampled, so those shares rest on the {LABELS_TAG} labels there")
    + f"; the cards from them that the audit labelled for other reasons agree with {AUDITED_MODEL} {_lf['k']} of {_lf['n']} and {_ls['k']} of "
    f"{_ls['n']}, and that slice is not a random sample. The first review's re-read of the first pass's 95 production cards (51 held) was not "
    f"repeated. Games were left out of the negative sample for the three realtime families. The "
    f"{int(_lr['value']) if MA_ is None else int(AE['plug_remainder']['value'])} proposal and commentary posts "
    f"were not sampled. Post text is cut at 400 characters and a claim chip can invent a number: {_lc['k']} of the {_lc['n']:,} cards the audit "
    f"calls demos with no numbers still carry a numeric chip. The audit's re-read of production covered the {AUDITED_MODEL} labels' "
    f"{AE['production_strict']['n']} production posts; its first-pass labels call {int(AE['production_audit_unconfirmed']['value'])} more "
    f"posts measured production, which its estimate does not count" + ("" if AUDITED else
    f" ({LABELS_TAG} labels {AE['production_audit_unconfirmed']['k']} of them production too)") + ", and "
    + ("" if AUDITED else f"of the {int(AE['production_primary_other']['value'])} {LABELS_TAG} production posts outside its re-read it "
       f"labelled {AE['production_primary_other']['n']} in its samples and called {AE['production_primary_other']['k']} production; ")
    + f"the interval's upper end, {pct(AE['production_strict']['hi'])}, allows for posts like these. "
    f"The overlap with the earlier 120 hand labels is {int(_lo['value'])} cards (family "
    f"agrees on {_lo['k']} of {_lo['n']}). The auditor is another AI model, so human labels are still the missing check"
    + (f"; the author's own {HC['n']} calibration labels are too few to be one." if HC.get("n") else ".")
)

# The observation paragraphs (scripts/observations.md) are hand-written for one run. Its "written-for" line
# names that run; when the data differ, landscape.md says so at the top and the run prints a warning.
# a label file can have its own observations (scripts/observations-<labels stem>.md, e.g. observations-sonnet-v2.md for the
# Sonnet record); otherwise scripts/observations.md, written for the reference labels
_obs_path = ROOT / "scripts" / f"observations-{LABELS_PATH.stem.replace('classified-', '')}.md"
if not _obs_path.exists():
    _obs_path = ROOT / "scripts" / "observations.md"
_stamp = (re.search(r"^written-for: posts=(\d+) base=(\d+) feed=(.+?)(?: labels=(\S+))?\s*$", _obs_path.read_text(), re.MULTILINE)
          if _obs_path.exists() else None)
OBS_FOR = ({"posts": int(_stamp.group(1)), "base": int(_stamp.group(2)), "feed": _stamp.group(3), "labels": _stamp.group(4)}
           if _stamp else None)
OBS_STALE = bool(OBS_FOR and (OBS_FOR["posts"] != N_CARDS or OBS_FOR["base"] != N
                              or (OBS_FOR["labels"] is not None and OBS_FOR["labels"] != LABELS_REL)))
SUMMARY["observations"] = {"written_for": OBS_FOR, "stale": OBS_STALE}
stale_note = ""
if OBS_STALE:
    stale_note = (
        f"> **Note.** The tables, the headline numbers and the noise section are from this run ({N_CARDS:,} posts, feed updated {meta['updated']}). "
        f"The observation paragraphs under the other tables were written for the {OBS_FOR['feed']} snapshot ({OBS_FOR['posts']:,} posts, base "
        f"{OBS_FOR['base']:,}" + (f", labels `{OBS_FOR['labels']}`" if OBS_FOR.get("labels") else "") + ") and quote its numbers; where they "
        "differ, the tables are current.\n\n"
    )
    print(f"WARNING: scripts/observations.md was written for {OBS_FOR['posts']:,} posts (base {OBS_FOR['base']:,}); this run has {N_CARDS:,} "
          f"(base {N:,}). landscape.md says so at the top; re-read the observation paragraphs before publishing.")

(REPORT / "summary.json").write_text(json.dumps(SUMMARY, indent=1, default=lambda o: float(o) if isinstance(o, (np.floating, np.integer)) else str(o)))

# ---------------------------------------------------------------- observations + markdown
obs: dict[str, str] = {}
obs_path = _obs_path
if obs_path.exists():
    cur = None
    buf: list[str] = []
    for line in obs_path.read_text().splitlines():
        m = re.match(r"^## (\S+)\s*$", line)
        if m:
            if cur:
                obs[cur] = "\n".join(buf).strip()
            cur, buf = m.group(1), []
        else:
            buf.append(line)
    if cur:
        obs[cur] = "\n".join(buf).strip()


def O(key: str) -> str:
    return obs.get(key, "_Observation pending._")


def f_usd(v) -> str:
    return "n/a" if v is None else f"${v:,.2f}"


TITLE = f"What people built with Jev in launch week: {N_CARDS:,} posts from {N_AUTHORS:,} authors, {WINDOW} (UTC)"
feed_note = ""
if meta.get("kept_from_earlier"):
    feed_note += (f" It also keeps the {meta['kept_from_earlier']} posts that an earlier snapshot of the feed held and the latest one dropped "
                  f"(`scripts/build_cards.py`; snapshots in `data/snapshots/`).")
if meta.get("cut_after_through"):
    feed_note += f" {meta['cut_after_through']} posts after {meta['through']} (UTC) are left out."

_fa = AUD["frame_agreement"]
THREE_PASSES = (
    f"**Three passes.** First, Claude Sonnet 5 labelled every post against a written rubric (v1). Second, a critical review of those labels "
    f"tightened the rubric (v2) and every post was labelled again. Third, an independent reviewer ({AUDITOR}, another AI model) labelled "
    f"{AUD['labelled']:,} posts blind to the model's labels: every rare case, and seeded random samples of the rest (Audit section). "
    + (f"The model and the audit agree on the use-case family for {pct(pa_['family'], 0)} of the audited posts and on the evidence level for "
       f"{pct(pa_['evidence'], 0)}. So the headline numbers are given as audited ranges, not as the model's counts."
       if AUDITED else
       f"Sonnet and the audit agree on the use-case family for {pct(_fa['family'], 0)} of the audited posts and on the evidence level for "
       f"{pct(_fa['evidence'], 0)}. Then {LABELS_MODEL} labelled every post again with the v2 rubric, and it agrees with the audit more on every "
       f"field: family {pct(pa_['family'], 0)}, evidence {pct(pa_['evidence'], 0)}, baseline {pct(pa_['baseline'], 0)}, realtime "
       f"{pct(pa_['realtime_infra'], 0)}. The tables use its labels (`{LABELS_REL}`), and the headline numbers are given as audited ranges, "
       f"not as the model's counts.")
)
_opus_bullet = (
    f"- **Reference labels: {LABELS_MODEL}** (`{LABELS_REL}`, `scripts/classify-model.ts --model anthropic/claude-opus-5.5`), with adaptive "
    f"thinking, through Vercel AI Gateway with `generateObject`, batches of 40 cards, the v2 rubric as a cached system prompt. It labelled "
    f"{len(son2_rows):,} of the {N_CARDS:,} posts" + (f"; its safety filter refused {len(REFUSED)} ({', '.join(REFUSED)}), which is left out of "
                                                      f"every table" if REFUSED else "")
    + ". The first labelling passes (v1 and v2) were Claude Sonnet 5; the Sonnet v2 labels (`data/classified-sonnet-v2.jsonl`) are the ones "
    "the audit sampled from, and the Sonnet version of this report is kept in [v2/](v2/). Temperature 0 is requested but the Gateway ignores it "
    "for both models, so both runs were sampled at the default and are not deterministic (Sonnet's run-to-run stability is in section 13)."
)
REF_BULLET = (
    "- **Reference labels: Claude Sonnet 5** (`anthropic/claude-sonnet-5`) through Vercel AI Gateway with `generateObject`, batches of 40 cards "
    "(id, English title, post text, chips, OpenChamber category as a hint), concurrency 5, the rubric as a cached system prompt, thinking "
    "disabled. Temperature 0 is requested but Sonnet 5 ignores it, so runs are not deterministic (stability figures in section 13). Script: "
    "`scripts/classify-sonnet.ts` (`RUBRIC_VERSION=v2`)."
    if AUDITED else _opus_bullet if "Opus" in LABELS_MODEL else
    f"- **Reference labels: {LABELS_MODEL}** (`{LABELS_REL}`, set with `--labels`), the v2 rubric and the same fields as the Sonnet v2 labels "
    f"(`data/classified-sonnet-v2.jsonl`), which are the labels the audit sampled from."
)
WITHDRAWN = (
    f"- **What is not published, and why.** Framing (what a post leads with) is withdrawn: a human calibration showed that one choice "
    f"misrepresents posts that lead with cost and latency together, so no number rests on it (section 4). Latency tier is published only as the "
    f"audited under-300 ms split: the seven levels agree with the audit on {pct(pa_['tier'], 0)} of audited posts, and {hc_tier()} (section 2). "
    f"The other_or_meta share is published with its interval, {ci('meta_still')}, not as the label's count: a careful reader moves many of the "
    f"model's meta posts to a real use (the audit moved {_ms['n'] - _ms['k']} of {_ms['n']}" + (f"; {hc_meta()}" if hc_meta() else "")
    + "), and the audit also finds meta posts among the model's real builds (section \"What the noise is made of\")."
)
method = f"""## Method

{THREE_PASSES}

- **Disclosure.** Ably, where the author is CEO, is a realtime infrastructure company.
- **Data.** OpenChamber's Jev feed data file (`data/cards.json`, meta `updated {meta['updated']}`): {N_CARDS:,} posts from {N_AUTHORS:,} authors, which OpenChamber selected from {meta['analysed']:,} posts it analysed ({pct(N_CARDS / meta['analysed'])}) with its own filter for what counts as a build.{feed_note} Post times decoded from the X ids run from {T_MIN:%d %b %H:%M} to {T_MAX:%d %b %H:%M} UTC; TypeSafe's launch post was 15 Sep 18:17 UTC, so the first six hours after launch are missing. Views (`v`) are X impressions and `f` is likes, both as recorded on the card; both favour older posts (section 6).
- **Rubric v2.** [rubric.md](rubric.md): 15 families (v1's 14 plus not_a_jev_build), 7 latency tiers, 5 evidence levels, 5 framings, 6 baselines, two booleans and a reason. v1 is kept as [rubric-v1.md](rubric-v1.md). The changes are listed under "What changed, and why".
{REF_BULLET}
{WITHDRAWN}
- **Second classifier: Jev** (`typesafe-ai/jev`), labelled once per card ({JEV_RUNS}; no card is labelled twice): one `experimental_evaluate` call per card, a single choice over the 14 v1 family definitions, no examples and no OpenChamber hint. Script: `scripts/classify-jev.ts`.
- **Hand labels.** The review agent (Claude Opus 5.5) labelled 120 random cards blind to both classifiers (`data/hand-labels-120.jsonl`) and re-read disputed cards (`data/hand-labels-disputes.jsonl`). These are a careful reader's labels, from the same model family as Sonnet, not a human's. A sheet for 120 human labels is in [human-labels-120.csv](human-labels-120.csv).
- **Audit.** {AUDITOR} labelled {AUD['labelled']:,} posts blind to the model's labels ([review/critical-review-grok.md](../review/critical-review-grok.md), labels in [review/hand-labels-grok.jsonl](../review/hand-labels-grok.jsonl)); `scripts/audit.py` runs its scripts and writes `data/13_audit_*.csv`. The Audit section below has its sampling, its agreement and its verdicts.
- **Base.** Duplicates merged, not_a_jev_build left out (section 0). Scripts: `scripts/dedupe.py`, `scripts/analyze.py` (`--labels` picks the reference labels), `scripts/audit.py`, `scripts/hand_agreement.py`. Every table is also a CSV in [data/](data/).
- **Cost (Gateway list prices × usage tokens).** {'' if AUDITED else f"{LABELS_MODEL} labels: {f_usd(sc_lab['usd'])} (Gateway-reported, {sc_lab['calls']} calls). "}Sonnet v2 labels ({'the full run plus refreshes' if len(L) > N_V1 else 'full run'}) {sc_v2['calls']} calls, {sc_v2['noCache']:,} uncached input, {sc_v2['cacheRead']:,} cache-read, {sc_v2['cacheWrite']:,} cache-write and {sc_v2['output']:,} output tokens = **{f_usd(sc_v2['usd'])}** (Gateway-reported {f_usd(sc_v2['gateway_reported_usd'])}); two pilots {f_usd(sc_v2p['usd'])}; **this pass {f_usd(v2_pass)}**. Noise sub-types {f_usd(noise_usd)} ({sc_nz['calls']} calls, plus a {nz_pilot_cards}-card pilot). v1 pass: {f_usd(v1_pass)} (Sonnet {f_usd(sc_v1['usd'])}, discarded pilot {f_usd(sc_v1p['usd'])}, Jev {f_usd(jev_usd)}).
- **Limits.** One model's reading of a post of at most 400 characters plus a one-line summary, not a check of what was built. Claims are the authors' own and are not reproduced. Views are not verified; section 6 gives likes and the sensitivity to suspect cards.
"""

changes = f"""## What changed, and why

**v3 (24 September): the audit.** The blind audit of {AUD['labelled']:,} posts (Audit section) tested ten published claims: {AUD['verdicts'].get('Holds', 0)} hold, {AUD['verdicts'].get('Holds with correction', 0)} hold with a correction and {AUD['verdicts'].get('Fails', 0)} fail. v3 makes these changes:

1. **The bucket scheme is withdrawn** (claim 3). "Cost-only" described a residual bin (the audit puts the posts its words fit at {ci('cost_only_as_described')}, not {pct(AE['cost_only_as_described']['model'])}), and none of the {SUMMARY['candidates']['posts']} "materially different" candidates did anything that was unavailable before. The three bucket tables on these labels are kept for the record in [v1/buckets-on-v2-labels.md](v1/buckets-on-v2-labels.md).
2. **A measurement ladder replaces it** (section 8): no measurement, measured demo, measured production. The evidence label it rests on agrees with the audit on {pct(pa_['evidence'])} of audited cards.
3. **The substance test** of the {SUMMARY['candidates']['posts']} candidate builds is section 8's second table.
4. **Headline numbers are the audited estimates** with 95% intervals; the model's counts stay in the tables, labelled as such.
5. **The audit's sampling, agreement and verdict tables are published** (Audit section), with its labels and scripts.
6. **Every number that changed** is listed in [audit-changes.md](audit-changes.md), where it appeared, old and new.

**v2 (23 September).** The critical review of v1 ({REVIEW_NOTE}) found four problems: "hype is 37%" rested on Sonnet calling any build "capability"; the bucket rules applied were not the pre-registered ones; the accuracy and latency chip medians mixed Jev's numbers with baselines and confidence; and the headline said "5,782 people". v2 makes these changes:

1. **Counts.** "{N_CARDS:,} posts from {N_AUTHORS:,} authors, {WINDOW} (UTC)", not "{N_V1:,} people" (v1's headline; its {N_V1:,} posts came from {V1_AUTHORS:,} authors).
2. **Rubric v2** (review item 9). not_a_jev_build is a new family, separate from other_or_meta. measured_demo and measured_production need a number that the author's own run produced; TypeSafe's launch numbers (20 to 200× faster, 40 to 400× cheaper, 70 to 500 ms, the list price) and other posts' numbers are named as not measurements. capability needs an explicit "not possible or affordable before". A frontier_llm baseline needs a named or clearly implied comparison. production_claim needs an explicit statement of users, customers or a running service. realtime_infra needs a described live loop, stream, channel, voice pipeline or live session, not the word "real-time". tier unclear is allowed and preferred to a guess. One wording adjustment followed the first pilot (section 13).
3. **Duplicates and non-Jev posts** (item 8): {len(dd['merged_to'])} duplicate cards merged; {len(NJ):,} not_a_jev_build cards left out of the use-case tables.
4. **Snake card** (item 10): the Laya-vs-Jev Snake benchmark is in games under rule 3 (section 1).
5. **Buckets** (item 2): three tables, pre-registered, as first applied and corrected, with the deviation stated. Withdrawn in v3 (above).
6. **Chips** (item 3): the accuracy and latency medians are dropped; the cost and speed multiples stay, with OpenChamber's survey as a cross-check (section 11).
7. **Production** (item 4): examples come from the re-read; "at most 1.6 percent, 0.9 percent on re-read" (section 9). The audit corrects this in v3 (claim 2).
8. **Likes and post age** (item 7): likes are shown next to views, with medians by posting day and likes by family (sections 1 and 6).
9. **realtime_infra** (item 12): restated against the hand sample (section 7).
10. **Disclosure** (item 5): in the method section.

Item 6 of the review (100 human labels) is prepared, not done: [human-labels-120.csv](human-labels-120.csv) and [human-labels-README.md](human-labels-README.md).

### Per-field agreement with the 120 hand labels, v1 and v2

{sections['hand_check']}

### How the labels moved

{sections['shifts']}

{O('changes')}
"""

dq_md = f"""## Data quality

- Cards {dq['cards']:,}; unique ids {dq['unique_ids']:,}; duplicate URLs {dq['duplicate_urls']}; cards with 0 views {dq['zero_views']}. The card date field matches the UTC day decoded from the id: {dq['day_field_matches_id_time']}.
- Post text is capped at 400 characters in the feed: {dq['text_exactly_400_chars']:,} cards ({pct(dq['text_exactly_400_chars'] / N_CARDS)}) are cut. The chips come from the full post, so some numbers are visible only as chips.
- Duplicates: {len(dd['merged_to'])} merged by the rules in section 0; the looser chips-only rule would merge up to {sum(x['unmerged_extra_cards'] for x in loose)} more, so double counting is reduced, not removed.
- The most-viewed card ([{stats6['top_card_id']}](https://x.com/i/status/{stats6['top_card_id']}), {stats6['top_card_views']:,} views, {pct(stats6['top_card_share'])} of views) has a like rate of {pct(stats6['top_card_like_rate'], 2)}, and fxtwitter returned 404 for it on 23 September. {stats6['suspect_cards']} cards have 100k or more views and a like rate under 0.2%; they hold {pct(stats6['suspect_share_views'])} of views. That pattern looks like promoted posts.
- {LABELS_TAG} (`{LABELS_REL}`): {dq['sonnet_v2_labelled']:,} of {N_CARDS:,} cards labelled; {dq['sonnet_v2_missing']} unlabelled; {dq['sonnet_v2_stray_ids']} results for ids not in the feed; {dq['sonnet_v2_duplicate_rows']} duplicate rows. Across {dq['sonnet_v2_batches']} batch calls, {dq['sonnet_v2_ids_missing_from_a_response']} ids were missing from a response and re-queued ({dq['sonnet_v2_retry_round_batches']} retry-round batch{'es' if dq['sonnet_v2_retry_round_batches'] != 1 else ''}); {dq['sonnet_v2_stray_ids_in_responses']} returned ids were not in their batch and were dropped.
- Jev: {lat_stats['calls_ok']:,} labels ({JEV_RUNS}); {lat_stats['failed_calls']} failed calls, {'all retried' if jev_err_unresolved == 0 else f'{jev_err_unresolved} still unlabelled'}.
"""

doc = f"""# {TITLE}

Generated {pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%d %H:%M UTC')} by `scripts/analyze.py` (reference labels: {LABELS_TAG}, `{LABELS_REL}`; audit: `{AUD['document']}`). OpenChamber feed updated {meta['updated']}.

{stale_note}{sections['summary']}

{method}
## Audit

{sections['audit']}

{changes}
## 0. Base: duplicates and posts that do not use Jev

{sections['base']}

The most-viewed not_a_jev_build cards:

{sections['not_jev_top']}

{O('base')}

## 1. Families

{sections['families']}

"views index" and "likes index" are the family's share of views or likes divided by its share of posts.

{O('families')}

**The Snake card.** {sections['snake']}

## What the noise is made of

{sections['noise_audit']}

{sections['noise']}

## 2. Latency tier: the under-300 ms split only

{sections['tier_audit']}

## 3. Evidence

{sections['evidence']}

{O('evidence')}

Evidence by family (row shares):

{sections['evidence_by_family']}

{O('evidence_by_family')}

## 4. Framing: withdrawn

{sections['framing_withdrawn']}

## 5. Baseline

{sections['baseline']}

{sections['baseline_audit']}

{O('baseline')}

Baseline by family (row shares):

{sections['baseline_by_family']}

{O('baseline_by_family')}

## 6. Attention: views and likes

{sections['concentration']}

{O('concentration')}

By posting day (UTC):

{sections['by_day']}

{O('by_day')}

The 20 most-viewed cards:

{sections['top20']}

{O('top20')}

## 7. Realtime

{sections['realtime']}

{sections['realtime_audit']}

{O('realtime')}

{sections['realtime_families']}

{O('realtime_families')}

The 15 most-viewed realtime cards:

{sections['realtime_top15']}

## 8. The measurement ladder and the {SUMMARY['candidates']['posts']} candidate builds

{sections['ladder']}

{O('ladder')}

{sections['candidates']}

## 9. Production, repos and longevity

{sections['production_audit']}

{sections['production']}

{O('production')}

Evidence × repo link × production claim (counts):

{sections['tinkering_crosstab']}

By family:

{sections['tinkering_by_family']}

Posts per day by family (UTC):

{sections['posts_per_day']}

{O('posts_per_day')}

## 10. Language

{sections['language']}

Language by family (row shares):

{sections['language_by_family']}

{O('language')}

## 11. Claims on the cards: cost and speed multiples

{sections['chips']}

{O('chips')}

## 12. Jev as a classifier

{sections['agreement']}

{O('agreement')}

Confusion matrix (rows {LABELS_TAG}, columns Jev):

{sections['confusion']}

Calibration:

{sections['calibration']}

{O('calibration')}

{sections['jev_latency']}

OpenChamber category against our family (top three per category):

{sections['crosswalk']}

## 13. Hand-label check

{sections['hand_check']}

{O('hand_check')}

{dq_md}
"""
(REPORT / "landscape.md").write_text(doc)
print(f"wrote report/landscape.md, {len(list(OUTD.glob('*.csv')))} CSVs, summary.json")
print(json.dumps({"use_case_base": N, "not_jev": len(NJ), "merged": len(dd["merged_to"]), "noise": n_noise, "noise_not_subtyped": SUMMARY["noise"]["not_subtyped"],
                  "jev_vs_v2": round(agree, 4), "v2_pass_usd": round(v2_pass, 3), "noise_usd": round(noise_usd, 3)}, indent=1))
