#!/usr/bin/env python3
"""Draw the 150-card human-labelling sample and embed it in review/labeller.html.

The population matches scripts/analyze.py and review/sample.py: drop the ids
listed as merged in data/dedupe-groups.jsonl, then drop the cards whose Sonnet
v2 family is not_a_jev_build. From that base the script draws, with seed
20260924b:

  random           100 cards, uniform from the base
  rare_live         20 cards whose Sonnet family is voice_and_turn_taking,
                    live_chat_streams_events or collaboration_and_typing
  rare_production   15 cards whose Sonnet evidence is measured_production or
                    whose Sonnet production_claim is true
  rare_baseline     15 cards whose Sonnet baseline is classic_classifier_or_ml,
                    rules_or_regex or vendor_api

Each rare stratum is drawn after the random 100 and after the strata before
it, so no card appears twice. The page shows the 100 random cards first
(shuffled), then the 50 rare-strata cards (shuffled together), so the labeller
can stop after card 100. The page does not show which rare stratum a card
came from.

Post text: with --fetch, the script gets the full post text, the quoted
post's text and the media from the FxTwitter API
(https://api.fxtwitter.com/<screen_name>/status/<id>) and caches them in
review/fxtwitter-150.json. A card without a good cache entry uses the feed's
text (capped at 400 characters) and the feed's media; its text_source is
"feed". Run --fetch again to retry only the failed cards.

Outputs:
  review/human-sample-150.json         the cards as the page shows them
  review/human-sample-150-strata.json  the stratum of each card (keep it out
                                       of the labeller)
  review/labeller.html                 the cards and the rubric definitions
                                       (report/rubric.md), embedded in the page.
                                       No model labels go into the page.

Usage:
  python3 scripts/human-sample.py            # sample, then embed (uses the cache if present)
  python3 scripts/human-sample.py --fetch    # also fetch missing post text (needs network)
  python3 scripts/human-sample.py --no-html  # sample files only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARDS = ROOT / "data/cards.json"
SONNET = ROOT / "data/classified-sonnet-v2.jsonl"
DEDUPE = ROOT / "data/dedupe-groups.jsonl"
RUBRIC = ROOT / "report/rubric.md"
OUT_SAMPLE = ROOT / "review/human-sample-150.json"
OUT_STRATA = ROOT / "review/human-sample-150-strata.json"
FX_CACHE = ROOT / "review/fxtwitter-150.json"
HTML = ROOT / "review/labeller.html"

SEED = "20260924b"
N_RANDOM = 100
FEED_CAP = 400
FULL_CAP = 6000
MAX_HTML_BYTES = 400 * 1024
FX_URL = "https://api.fxtwitter.com/{sn}/status/{id}"
FX_UA = "jev-landscape-labeller/1.0 (one-off sample of 150 public posts)"

LIVE_FAMILIES = {"voice_and_turn_taking", "live_chat_streams_events", "collaboration_and_typing"}
RARE_BASELINES = {"classic_classifier_or_ml", "rules_or_regex", "vendor_api"}
RARE_STRATA = [
    ("rare_live", 20, lambda r: r.get("family") in LIVE_FAMILIES),
    (
        "rare_production",
        15,
        lambda r: r.get("evidence") == "measured_production" or r.get("production_claim") is True,
    ),
    ("rare_baseline", 15, lambda r: r.get("baseline") in RARE_BASELINES),
]

# The page's fields, in the order it shows them. framing is optional (last).
FIELDS = [
    (
        "family",
        [
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
            "not_a_jev_build",
        ],
    ),
    ("tier", ["frame", "feel", "turn", "interaction", "task", "batch", "unclear"]),
    (
        "evidence",
        ["commentary_or_meme", "proposal_or_idea", "demo_no_numbers", "measured_demo", "measured_production"],
    ),
    (
        "baseline",
        ["none", "frontier_llm", "small_llm", "classic_classifier_or_ml", "rules_or_regex", "vendor_api"],
    ),
    ("realtime_infra", ["yes", "no"]),
    ("production_claim", ["yes", "no"]),
    ("framing", ["cost", "latency", "accuracy", "capability", "none"]),
]
OPTIONAL_FIELDS = {"framing"}
BOOLEAN_FIELDS = {"realtime_infra", "production_claim"}
DATA_TAG = re.compile(r'(<script id="labeller-data" type="application/json">)(.*?)(</script>)', re.S)


def read_jsonl(path: Path) -> dict[str, dict]:
    """Rows by id; a later row for the same id replaces an earlier one."""
    rows: dict[str, dict] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                row = json.loads(line)
                rows[str(row["id"])] = row
    return rows


def merged_ids(path: Path) -> set[str]:
    merged: set[str] = set()
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                merged.update(str(i) for i in json.loads(line).get("merged", []))
    return merged


def draw(base: list[str], sonnet: dict[str, dict]) -> dict[str, str]:
    """Return {id: stratum} in draw order."""
    rng = random.Random(SEED)
    stratum: dict[str, str] = {cid: "random" for cid in rng.sample(base, N_RANDOM)}
    for name, k, keep in RARE_STRATA:
        pool = [cid for cid in base if cid not in stratum and keep(sonnet[cid])]
        if len(pool) < k:
            sys.exit(f"stratum {name} has {len(pool)} cards left; it needs {k}")
        stratum.update({cid: name for cid in rng.sample(pool, k)})
    return stratum


def page_order(stratum: dict[str, str]) -> list[str]:
    """The 100 random cards first, then the 50 rare-strata cards; each block shuffled."""
    rng = random.Random(SEED + ":order")
    first = [cid for cid, s in stratum.items() if s == "random"]
    rest = [cid for cid, s in stratum.items() if s != "random"]
    rng.shuffle(first)
    rng.shuffle(rest)
    return first + rest


# ---- FxTwitter ------------------------------------------------------------------


def fx_media(tweet: dict | None) -> list[dict]:
    out = []
    for m in ((tweet or {}).get("media") or {}).get("all") or []:
        kind = {"photo": "image", "video": "video", "gif": "video"}.get(m.get("type"))
        thumb = m.get("thumbnail_url") or (m.get("url") if kind == "image" else None)
        if kind and thumb:
            out.append({"type": kind, "thumb": thumb})
    return out


def parse_fx(doc: dict) -> dict:
    tweet = doc.get("tweet") if isinstance(doc, dict) else None
    if not isinstance(tweet, dict) or not isinstance(tweet.get("text"), str):
        return {"ok": False, "error": f"{doc.get('code')} {doc.get('message')}" if isinstance(doc, dict) else "bad body"}
    quote = tweet.get("quote") if isinstance(tweet.get("quote"), dict) else None
    article = tweet.get("article") if isinstance(tweet.get("article"), dict) else None
    return {
        "ok": True,
        "text": tweet["text"],
        "quote_text": quote.get("text") if quote else None,
        "quote_sn": ((quote or {}).get("author") or {}).get("screen_name"),
        "media": fx_media(tweet),
        "quote_media": fx_media(quote),
        "article_title": (article or {}).get("title"),
        "article_preview": (article or {}).get("preview_text"),
    }


def fetch_one(sn: str, cid: str) -> dict:
    url = FX_URL.format(sn=sn, id=cid)
    entry: dict = {"ok": False, "error": "not tried"}
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": FX_UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                return parse_fx(json.loads(resp.read().decode("utf-8")))
        except urllib.error.HTTPError as e:
            try:
                entry = parse_fx(json.loads(e.read().decode("utf-8")))
            except (ValueError, UnicodeDecodeError):
                entry = {"ok": False, "error": f"HTTP {e.code}"}
            if e.code in (401, 403, 404):
                return entry
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
            entry = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        time.sleep(2 * (attempt + 1))
    return entry


def fetch_all(cards: list[dict], cache: dict[str, dict]) -> None:
    todo = [c for c in cards if not cache.get(c["id"], {}).get("ok")]
    print(f"fetching {len(todo)} posts from FxTwitter ({len(cards) - len(todo)} already cached)")
    for i, c in enumerate(todo, 1):
        sn = c.get("sn") or c["url"].split("/")[3]
        cache[c["id"]] = fetch_one(sn, c["id"])
        cache[c["id"]]["fetched"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if i % 25 == 0 or i == len(todo):
            FX_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            print(f"  {i}/{len(todo)}")
        time.sleep(0.4)


# ---- page cards ---------------------------------------------------------------------


def small(url: str) -> str:
    return url + "?name=small" if "pbs.twimg.com/media/" in url and "?" not in url else url


def page_card(c: dict, fx: dict | None) -> dict:
    card = {"id": c["id"], "url": c["url"], "t": c.get("t") or "", "lang": c.get("lang"), "chips": c.get("chips") or []}
    media: list[dict] = []
    media_in = "post"
    if fx and fx.get("ok"):
        text = fx.get("text") or ""
        if fx.get("article_title"):
            text = f"{text}\n\n[X article] {fx['article_title']}\n{fx.get('article_preview') or ''}".strip()
        card.update(
            x=text[:FULL_CAP],
            text_source="fxtwitter",
            truncated=len(text) > FULL_CAP,
            quote=(fx.get("quote_text") or None),
            quote_sn=fx.get("quote_sn"),
        )
        media = fx.get("media") or []
        if not media and fx.get("quote_media"):
            media, media_in = fx["quote_media"], "quoted post"
    else:
        x = c.get("x") or ""
        card.update(x=x, text_source="feed", truncated=len(x) >= FEED_CAP - 5, quote=None, quote_sn=None)
    if not media:
        m = c.get("m") or {}
        if m.get("kind") and m.get("thumb"):
            media = [{"type": "image" if m["kind"] == "photo" else "video", "thumb": m["thumb"]}]
            media_in = "post"
    kinds = {m["type"] for m in media}
    card["media_type"] = "video" if "video" in kinds else ("image" if "image" in kinds else "none")
    card["media_in"] = media_in if media else None
    card["thumbs"] = [small(m["thumb"]) for m in media[:4]]
    art = c.get("art") or None
    card["art"] = {"k": art.get("k"), "l": art.get("l"), "u": art.get("u")} if art else None
    return card


# ---- rubric -----------------------------------------------------------------------


def parse_rubric(text: str) -> dict:
    """Split report/rubric.md into the intro and, per field, the option definitions and notes."""
    parts = re.split(r"^## ", text, flags=re.M)
    intro = "\n".join(line for line in parts[0].splitlines() if not line.startswith("# ")).strip()
    options = dict(FIELDS)
    fields: dict[str, dict] = {}
    for part in parts[1:]:
        heading, _, body = part.partition("\n")
        key = re.match(r"[a-z_]+", heading).group(0)
        if key not in options:
            continue
        defs: dict[str, str] = {}
        notes: list[str] = []
        if key in BOOLEAN_FIELDS:
            para = " ".join(body.split())
            cut = para.find(" false for ")
            if cut < 0:
                sys.exit(f"rubric: cannot split the {key} paragraph into true and false")
            defs = {"yes": para[:cut].strip(), "no": para[cut:].strip()}
        else:
            for line in body.splitlines():
                m = re.match(r"^- ([a-z_]+): (.*)$", line)
                if m and m.group(1) in options[key]:
                    defs[m.group(1)] = m.group(2).strip()
                else:
                    notes.append(line)
        lost = [o for o in options[key] if o not in defs]
        if lost:
            sys.exit(f"rubric: no definition for {key} options {lost}")
        fields[key] = {
            "heading": heading.strip(),
            "defs": defs,
            "short": {o: d.split(" Examples:")[0].strip() for o, d in defs.items()},
            "notes": "\n".join(notes).strip(),
        }
    lost_fields = [k for k in options if k not in fields]
    if lost_fields:
        sys.exit(f"rubric: no section for {lost_fields}")
    return {"intro": intro, "fields": fields}


def embed(payload: dict) -> int:
    html = HTML.read_text(encoding="utf-8")
    if not DATA_TAG.search(html):
        sys.exit(f"{HTML} has no labeller-data script tag")
    # Escape "<" so no string in the data can close the script element.
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    html = DATA_TAG.sub(lambda m: m.group(1) + blob + m.group(3), html, count=1)
    size = len(html.encode("utf-8"))
    if size > MAX_HTML_BYTES:
        sys.exit(f"labeller.html would be {size:,} bytes; the limit is {MAX_HTML_BYTES:,}")
    HTML.write_text(html, encoding="utf-8")
    return size


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true", help="fetch full post text from FxTwitter for uncached cards")
    ap.add_argument("--no-html", action="store_true", help="write the sample files only")
    args = ap.parse_args()

    cards = json.loads(CARDS.read_text(encoding="utf-8"))["cards"]
    by_id = {c["id"]: c for c in cards}
    sonnet = read_jsonl(SONNET)
    merged = merged_ids(DEDUPE)
    base = sorted(
        c["id"] for c in cards if c["id"] not in merged and sonnet.get(c["id"], {}).get("family") != "not_a_jev_build"
    )
    unlabelled = [cid for cid in base if cid not in sonnet]
    if unlabelled:
        sys.exit(f"{len(unlabelled)} base cards have no Sonnet v2 label, e.g. {unlabelled[:3]}")

    stratum = draw(base, sonnet)
    order = page_order(stratum)
    sample_hash = hashlib.sha1(",".join(order).encode()).hexdigest()[:10]

    cache: dict[str, dict] = json.loads(FX_CACHE.read_text(encoding="utf-8")) if FX_CACHE.exists() else {}
    if args.fetch:
        fetch_all([by_id[cid] for cid in order], cache)
        FX_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    sample = [page_card(by_id[cid], cache.get(cid)) for cid in order]
    ok = sum(1 for c in sample if c["text_source"] == "fxtwitter")
    print(f"full text from FxTwitter: {ok}/{len(sample)} ({100 * ok / len(sample):.0f}%); the rest use the feed text")

    OUT_SAMPLE.write_text(json.dumps(sample, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    counts: dict[str, int] = {}
    for s in stratum.values():
        counts[s] = counts.get(s, 0) + 1
    strata_doc = {
        "seed": SEED,
        "sample_hash": sample_hash,
        "base_size": len(base),
        "counts": counts,
        "note": (
            "position = the card's place in the labeller (1-100 random, 101-150 rare). stratum = the draw the card "
            "came from. also_in = the other rare strata its Sonnet v2 label matches. Keep this file out of the labeller."
        ),
        "cards": [
            {
                "position": pos,
                "id": cid,
                "stratum": stratum[cid],
                "also_in": [name for name, _, keep in RARE_STRATA if keep(sonnet[cid]) and name != stratum[cid]],
            }
            for pos, cid in enumerate(order, 1)
        ],
    }
    OUT_STRATA.write_text(json.dumps(strata_doc, indent=1) + "\n", encoding="utf-8")
    print(f"base {len(base)} cards; drew {len(order)}: {counts}; sample hash {sample_hash}")
    print(f"wrote {OUT_SAMPLE.relative_to(ROOT)} and {OUT_STRATA.relative_to(ROOT)}")

    if not args.no_html:
        payload = {
            "meta": {"seed": SEED, "n": len(sample), "n_random": N_RANDOM, "sample_hash": sample_hash, "feed_cap": FEED_CAP},
            "fields": [{"key": k, "options": o, "optional": k in OPTIONAL_FIELDS} for k, o in FIELDS],
            "rubric": parse_rubric(RUBRIC.read_text(encoding="utf-8")),
            "cards": sample,
        }
        size = embed(payload)
        print(f"embedded {len(sample)} cards in {HTML.relative_to(ROOT)} ({size:,} bytes)")


if __name__ == "__main__":
    main()
