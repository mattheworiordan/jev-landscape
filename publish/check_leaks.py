#!/usr/bin/env python3
"""Scan a directory tree for text copied from the OpenChamber feed (post text and card titles).

    python3 publish/check_leaks.py TREE [--cards data/cards.json] [--allow-titles GLOB[:MAX]] ...

The feed file (data/cards.json) holds, for every card, the full text of the X post (field "x")
and a one-line title written by the feed (field "t"). This script finds either of them in TREE:

  1. It normalises every post text and title (Unicode NFKC, straight quotes, collapsed white
     space, lower case) and cuts it into overlapping windows ("shingles"): 40 characters every
     8 characters for post text, 24 characters every 4 characters for titles of 24 or more
     characters. A copied span of about 47 characters of post text, or 27 characters of a
     title, always contains one whole shingle.
  2. It drops shingles that 3 or more cards share (retweets, quoted taglines, boilerplate).
  3. For every text file in TREE it builds four views (raw, HTML-unescaped, tag-stripped, and
     the decoded JSON string literals), slides a window over each, and records every card with
     a matching shingle.

Binary files (PNG and other non-UTF-8 files) are skipped and listed.

A post-text match that lies inside the same card's title counts as a title (the feed often
builds the title from the post's own words).

Exit status: 0 when no post text is found and titles appear only in files allowed with
--allow-titles (GLOB is matched against the path relative to TREE; MAX caps the number of
distinct titles allowed in each matching file, default 0 = unlimited). --allow-text does the
same for reviewed false positives, such as a script that shares a line of SDK code with a post
that quoted it. 1 otherwise.
"""
from __future__ import annotations

import argparse
import fnmatch
import html
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

TEXT_L, TEXT_STEP = 40, 8
TITLE_L, TITLE_STEP = 24, 4
COMMON = 3  # a shingle shared by this many cards or more is boilerplate, not evidence

QUOTES = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "–": "-", "—": "-", "−": "-", " ": " ", " ": " ",
})
ZERO_WIDTH = re.compile("[​‌‍⁠﻿]")
SPACE = re.compile(r"\s+")
TAG = re.compile(r"<[^>]{0,2000}>")
JSON_STR = re.compile(r'"((?:[^"\\\n]|\\.){8,})"')
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".ruff_cache"}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).translate(QUOTES)
    s = ZERO_WIDTH.sub("", s)
    return SPACE.sub(" ", s).strip().lower()


def shingles(s: str, length: int, step: int) -> list[str]:
    if len(s) < length:
        return []
    starts = list(range(0, len(s) - length + 1, step))
    if starts[-1] != len(s) - length:
        starts.append(len(s) - length)  # always cover the tail
    return [s[i:i + length] for i in starts]


def build_index(cards: list[dict]) -> tuple[dict[str, str], dict[str, str]]:
    text_owner: dict[str, set[str]] = defaultdict(set)
    title_owner: dict[str, set[str]] = defaultdict(set)
    for c in cards:
        cid = str(c.get("id"))
        for sh in shingles(norm(c.get("x") or ""), TEXT_L, TEXT_STEP):
            text_owner[sh].add(cid)
        t = norm(c.get("t") or "")
        for sh in shingles(t, TITLE_L, TITLE_STEP):
            title_owner[sh].add(cid)
    text = {sh: next(iter(ids)) for sh, ids in text_owner.items() if len(ids) < COMMON}
    title = {sh: next(iter(ids)) for sh, ids in title_owner.items() if len(ids) < COMMON}
    return text, title


def views(raw: str) -> list[str]:
    unescaped = html.unescape(raw)
    out = [raw, unescaped, TAG.sub(" ", unescaped), raw.replace('""', '"')]
    decoded = []
    for m in JSON_STR.finditer(raw):
        try:
            decoded.append(json.loads('"' + m.group(1) + '"'))
        except (json.JSONDecodeError, ValueError):
            continue
    if decoded:
        joined = "\n".join(decoded)
        out += [joined, TAG.sub(" ", html.unescape(joined))]
    return [norm(v) for v in out]


def scan(hay: str, index: dict[str, str], length: int) -> dict[str, str]:
    """card id -> first matching snippet"""
    found: dict[str, str] = {}
    get = index.get
    for i in range(len(hay) - length + 1):
        cid = get(hay[i:i + length])
        if cid is not None and cid not in found:
            found[cid] = hay[i:i + length]
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tree")
    ap.add_argument("--cards", default=str(Path(__file__).resolve().parent.parent / "data" / "cards.json"))
    ap.add_argument("--allow-titles", action="append", default=[], metavar="GLOB[:MAX]",
                    help="files that may quote card titles (the page, the rubric), at most MAX titles each")
    ap.add_argument("--allow-text", action="append", default=[], metavar="GLOB[:MAX]",
                    help="reviewed false positives: files that share a post-text shingle for another reason")
    ap.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                    help="paths (relative to TREE) not to scan, e.g. the feed file itself")
    ap.add_argument("--quiet", action="store_true", help="print only files with findings and the verdict")
    ap.add_argument("--json-out", metavar="FILE", help="write every finding (file, verdict, card ids) as JSON")
    a = ap.parse_args()

    feed = json.loads(Path(a.cards).read_text())
    cards = feed["cards"] if isinstance(feed, dict) else feed
    text_idx, title_idx = build_index(cards)
    title_of = {str(c.get("id")): c.get("t") or "" for c in cards}
    norm_title = {cid: norm(t) for cid, t in title_of.items()}

    def caps(specs: list[str]) -> list[tuple[str, int]]:
        out = []
        for spec in specs:
            glob, _, cap = spec.partition(":")
            out.append((glob, int(cap) if cap else 0))
        return out

    allow, allow_text = caps(a.allow_titles), caps(a.allow_text)

    root = Path(a.tree).resolve()
    failures, skipped, scanned = [], [], 0
    findings: dict[str, dict] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        rel = str(path.relative_to(root))
        if any(fnmatch.fnmatch(rel, g) for g in a.exclude):
            continue
        try:
            raw = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            skipped.append(rel)
            continue
        scanned += 1
        text_hits: dict[str, str] = {}
        title_hits: dict[str, str] = {}
        for v in views(raw):
            for cid, snip in scan(v, text_idx, TEXT_L).items():
                text_hits.setdefault(cid, snip)
            for cid, snip in scan(v, title_idx, TITLE_L).items():
                title_hits.setdefault(cid, snip)
        # A post-text hit that lies inside the same card's title is the title quoted, not the post
        for cid, snip in list(text_hits.items()):
            if snip in norm_title.get(cid, ""):
                title_hits.setdefault(cid, snip)
                del text_hits[cid]
        title_only = {k: v for k, v in title_hits.items() if k not in text_hits}
        text_caps = [cap for g, cap in allow_text if fnmatch.fnmatch(rel, g)]
        verdict = "ok"
        if text_hits and text_caps and (not text_caps[0] or len(text_hits) <= text_caps[0]):
            verdict = "text allowed"
        elif text_hits:
            verdict = "POST TEXT"
        elif title_only:
            title_caps = [cap for g, cap in allow if fnmatch.fnmatch(rel, g)]
            if not title_caps:
                verdict = "TITLES"
            elif title_caps[0] and len(title_only) > title_caps[0]:
                verdict = f"TITLES OVER CAP ({title_caps[0]})"
            else:
                verdict = "titles allowed"
        if verdict not in ("ok", "titles allowed", "text allowed"):
            failures.append(rel)
        if verdict != "ok":
            findings[rel] = {"verdict": verdict, "post_text_cards": sorted(text_hits), "title_cards": sorted(title_only)}
        if not a.quiet or verdict != "ok":
            print(f"{verdict:22s} {rel}  (post text: {len(text_hits)} cards, titles: {len(title_only)} cards)")
            for cid, snip in list(text_hits.items())[:3]:
                print(f"{'':25s}post text of {cid}: \"{snip}\"")
            for cid in list(title_only)[:3]:
                print(f"{'':25s}title of {cid}: \"{title_of.get(cid, '')[:80]}\"")
    print(f"\nscanned {scanned} text files; skipped {len(skipped)} binary files"
          + (f" ({', '.join(sorted({Path(s).suffix or s for s in skipped}))})" if skipped else ""))
    print(f"index: {len(text_idx):,} post-text shingles and {len(title_idx):,} title shingles from {len(cards):,} cards")
    if a.json_out:
        Path(a.json_out).write_text(json.dumps({"scanned": scanned, "skipped_binary": skipped, "failures": failures,
                                                "findings": findings}, indent=1) + "\n")
    if failures:
        print(f"FAIL: {len(failures)} file(s) carry feed text: " + ", ".join(failures))
        return 1
    print("PASS: no post text; titles only where allowed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
