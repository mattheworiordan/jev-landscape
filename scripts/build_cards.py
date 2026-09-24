#!/usr/bin/env python3
"""Keep every pull of the OpenChamber feed, and build data/cards.json from them.

    python3 scripts/build_cards.py adopt              keep a raw pull in data/cards.json as a snapshot
    python3 scripts/build_cards.py add FILE           keep a new pull (FILE) as a snapshot
    python3 scripts/build_cards.py build [--through YYYY-MM-DD]
                                                      write data/cards.json from the snapshots

Run from the jev-landscape folder; scripts/refresh.sh runs all three in order.

Snapshots are the feed files exactly as pulled, in data/snapshots/cards-YYYYMMDD-HHMM.json,
named by the feed's own "updated" time (UTC), so pulling an unchanged feed twice keeps one file.

data/cards.json is the working set that every other script reads:
  - every card that any snapshot holds, in the version of the latest snapshot that holds it
    (views and likes as that snapshot recorded them);
  - posted on or before --through (UTC day; default 2026-09-23), with the post time decoded
    from the X id, so the report covers whole days;
  - a card that an earlier snapshot held and a later one dropped stays in. The feed drops a
    few cards between updates (6 of 5,782 on 23 September, one of them in the 120-card hand
    sample); keeping them keeps the labelled samples whole. The report counts them.
Its meta is the latest snapshot's meta plus: built, through, snapshots, latest_snapshot,
cards, feed_cards (cards from the latest snapshot), kept_from_earlier, cut_after_through.
A raw pull has no "built" key; that is how adopt tells a raw pull from a built file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SNAP = DATA / "snapshots"
CARDS = DATA / "cards.json"
MIN_CARDS = 1000  # a pull with fewer cards than this is treated as broken, not as the feed


def post_time(card_id: str) -> datetime:
    return datetime.fromtimestamp(((int(card_id) >> 22) + 1288834974657) / 1000, tz=timezone.utc)


def feed_time(meta: dict) -> datetime:
    """The feed's meta.updated, e.g. '2026-09-23 18:47 UTC'."""
    m = re.match(r"^(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2})", str(meta.get("updated", "")))
    if not m:
        raise SystemExit(f"feed meta has no usable 'updated' time: {meta.get('updated')!r}")
    return datetime.strptime(f"{m.group(1)} {m.group(2)}:{m.group(3)}", "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)


def snapshot_name(meta: dict) -> str:
    return f"cards-{feed_time(meta):%Y%m%d-%H%M}.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict) or "meta" not in raw or not isinstance(raw.get("cards"), list):
        raise SystemExit(f"{path}: not a feed file (needs meta and a cards list)")
    return raw


def keep(src: Path, *, move: bool = False) -> Path:
    """Store a raw pull under its feed name; an identical file already there is enough."""
    raw = load(src)
    if "built" in raw["meta"]:
        raise SystemExit(f"{src} is a built working set, not a raw pull")
    if len(raw["cards"]) < MIN_CARDS:
        raise SystemExit(f"{src} holds {len(raw['cards'])} cards (< {MIN_CARDS}); refusing it as a snapshot")
    SNAP.mkdir(parents=True, exist_ok=True)
    dest = SNAP / snapshot_name(raw["meta"])
    if dest.exists():
        if digest(dest) == digest(src):
            print(f"snapshot {dest.name} already kept (same content)")
            if move:
                src.unlink()
            return dest
        # same feed time, different content: keep both, the later pull with a suffix
        dest = SNAP / dest.name.replace(".json", f"-pulled-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.json")
    (shutil.move if move else shutil.copyfile)(str(src), str(dest))
    print(f"kept snapshot {dest.name}: {len(raw['cards']):,} cards, feed updated {raw['meta'].get('updated')}")
    return dest


def cmd_adopt(_: argparse.Namespace) -> None:
    if not CARDS.exists():
        print("no data/cards.json to adopt")
        return
    raw = load(CARDS)
    if "built" in raw["meta"]:
        print("data/cards.json is a built working set; its sources are already in data/snapshots/")
        return
    keep(CARDS)  # copied, so data/cards.json stays in place until build replaces it


def cmd_add(a: argparse.Namespace) -> None:
    keep(Path(a.file))


def snapshots() -> list[tuple[datetime, Path, dict]]:
    out = []
    for p in sorted(SNAP.glob("cards-*.json")):
        raw = load(p)
        out.append((feed_time(raw["meta"]), p, raw))
    out.sort(key=lambda t: (t[0], t[1].name))
    return out


def cmd_build(a: argparse.Namespace) -> None:
    snaps = snapshots()
    if not snaps:
        raise SystemExit("no snapshots in data/snapshots/; run adopt or add first")
    through = datetime.strptime(a.through, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = through + timedelta(days=1)
    latest_t, latest_p, latest = snaps[-1]
    version: dict[str, dict] = {}
    for _, _, raw in snaps:  # oldest first, so later snapshots overwrite
        for c in raw["cards"]:
            version[str(c["id"])] = c
    in_latest = {str(c["id"]) for c in latest["cards"]}
    cut = {i for i in version if post_time(i) >= end}
    order = [str(c["id"]) for c in latest["cards"]] + sorted((i for i in version if i not in in_latest), reverse=True)
    cards = [version[i] for i in order if i not in cut]
    kept = [c for c in cards if str(c["id"]) not in in_latest]
    meta = dict(latest["meta"])
    meta.update(
        {
            "built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "through": a.through,
            "snapshots": [p.name for _, p, _ in snaps],
            "latest_snapshot": latest_p.name,
            "cards": len(cards),
            "feed_cards": len(cards) - len(kept),
            "kept_from_earlier": len(kept),
            "cut_after_through": len(cut),
        }
    )
    tmp = CARDS.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"meta": meta, "cards": cards}, ensure_ascii=False))
    tmp.replace(CARDS)
    last = max(post_time(str(c["id"])) for c in cards)
    print(
        f"built data/cards.json: {len(cards):,} cards through {a.through} (UTC) from {len(snaps)} snapshot(s); "
        f"latest {latest_p.name} (feed updated {meta.get('updated')}) gives {meta['feed_cards']:,}, "
        f"{len(kept)} kept from earlier snapshots, {len(cut)} posted after {a.through} left out; last post {last:%Y-%m-%d %H:%M} UTC"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("adopt").set_defaults(fn=cmd_adopt)
    p_add = sub.add_parser("add")
    p_add.add_argument("file")
    p_add.set_defaults(fn=cmd_add)
    p_build = sub.add_parser("build")
    p_build.add_argument("--through", default="2026-09-23")
    p_build.set_defaults(fn=cmd_build)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
