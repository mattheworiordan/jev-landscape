#!/usr/bin/env python3
"""Empty every field that can carry words from an X post, so a data file can be published.

    python3 publish/strip_text.py SRC DEST          format from the extension: .jsonl, .json or .csv
    python3 publish/strip_text.py --drop SRC DEST   JSON and JSONL: remove the fields instead
    python3 publish/strip_text.py --report FILE SRC DEST   also append a JSON line of counts to FILE

A field is text when its name is in TEXT_FIELDS, or when it ends in "title", "reason" or "note"
after a space or an underscore (CSV headers such as "top_card_title" or "audit's note"):

    t, x, text     the feed's title and the post text
    title, titles  the feed's title, copied into tables
    reason, note   a labeller's one-line rationale about one post; it often repeats the post's words

JSONL files and CSV tables have one row per post, so every text field is emptied. A JSON file is
a document (summary.json, the audit's estimates): only t, x, text, title and titles are emptied
there, and its notes stay, because they describe the method, not a post. The leak check
(publish/check_leaks.py) is the backstop for both.

The value is emptied ("" for a string, and a list keeps its length with "" in each slot). Numbers
and booleans stay, so a count in a column such as "empty_title" is kept. The key or column stays,
so every script that reads these files still runs. With --drop the JSON key is removed; CSV
columns always stay.

One value is kept as a fixed marker: a note that starts "NOT a Jev", "NOT Jev" or "built WITHOUT
Jev" keeps only those words, because scripts/hand_agreement.py reads them to mark a card
not_a_jev_build. The marker is the labeller's code word, not text from the post.

Everything else (ids, labels, numbers, booleans, timestamps, URLs, handles, error messages) is
copied unchanged, and a JSONL line or CSV file with nothing to empty is copied byte for byte.
Prints one line per file: rows and how many values were emptied, per field.
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path

TEXT_FIELDS = {"t", "x", "text", "title", "titles", "reason", "note", "notes"}
POST_FIELDS = {"t", "x", "text", "title", "titles"}  # the only text fields emptied in a JSON document
NUMBER = re.compile(r"^\s*(-?\d+(\.\d+)?([eE][-+]?\d+)?|True|False|true|false|nan|NaN)\s*$")
TEXT_SUFFIX = re.compile(r"[ _](title|titles|reason|note|notes)$", re.I)
NOT_JEV = re.compile(r"^(NOT (a )?Jev|built WITHOUT Jev)", re.I)  # the same pattern as scripts/hand_agreement.py


def is_text(name: str, document: bool = False) -> bool:
    n = name.strip().lower()
    if document:
        return n in POST_FIELDS
    return n in TEXT_FIELDS or bool(TEXT_SUFFIX.search(n))


def empty(key: str, value):
    """The published value of a text field."""
    if isinstance(value, str):
        m = NOT_JEV.match(value) if key.lower() in ("note", "notes") else None
        return m.group(0) if m else ""
    if isinstance(value, list):
        return [empty(key, v) if isinstance(v, (str, list)) else v for v in value]
    return value  # numbers, booleans and null carry no words


def strip_obj(obj, counts: Counter, drop: bool, path: str = "", document: bool = False):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            where = f"{path}.{k}" if path else k
            if is_text(k, document) and not isinstance(v, (dict, bool, int, float)) and v is not None:
                if drop:
                    counts[where] += 1  # removed
                    continue
                new = empty(k, v)
                if new != v:
                    counts[where] += 1
                out[k] = new
            else:
                out[k] = strip_obj(v, counts, drop, where, document)
        return out
    if isinstance(obj, list):
        return [strip_obj(v, counts, drop, path + "[]", document) for v in obj]
    return obj


def separators(line: str) -> tuple[str, str]:
    return (", ", ": ") if '": ' in line or '", "' in line else (",", ":")


def do_jsonl(src: Path, dest: Path, drop: bool) -> tuple[int, Counter]:
    counts: Counter = Counter()
    rows = 0
    out = []
    for line in src.read_text(encoding="utf-8").splitlines(keepends=True):
        body = line.rstrip("\r\n")
        if not body.strip():
            out.append(line)
            continue
        rows += 1
        obj = json.loads(body)
        before = sum(counts.values())
        new = strip_obj(obj, counts, drop)
        if new == obj and sum(counts.values()) == before and not (drop and set(new) != set(obj)):
            out.append(line)  # nothing to empty: keep the exact bytes
            continue
        ascii_only = "\\u" in body and not any(ord(ch) > 127 for ch in body)
        out.append(json.dumps(new, ensure_ascii=ascii_only, separators=separators(body)) + line[len(body):])
    dest.write_text("".join(out), encoding="utf-8")
    return rows, counts


def do_json(src: Path, dest: Path, drop: bool) -> tuple[int, Counter]:
    raw = src.read_text(encoding="utf-8")
    obj = json.loads(raw)
    counts: Counter = Counter()
    new = strip_obj(obj, counts, drop, document=True)
    if new == obj and not counts:
        dest.write_text(raw, encoding="utf-8")
        return 1, counts
    second = raw.splitlines()[1] if raw.count("\n") > 1 else ""
    indent = len(second) - len(second.lstrip(" ")) or None
    ascii_only = "\\u" in raw and not any(ord(ch) > 127 for ch in raw)
    text = json.dumps(new, ensure_ascii=ascii_only, indent=indent, separators=None if indent else separators(raw))
    dest.write_text(text + ("\n" if raw.endswith("\n") else ""), encoding="utf-8")
    return 1, counts


def do_csv(src: Path, dest: Path) -> tuple[int, Counter]:
    raw = src.read_text(encoding="utf-8")
    rows = list(csv.reader(io.StringIO(raw, newline="")))
    counts: Counter = Counter()
    if not rows:
        dest.write_text(raw, encoding="utf-8")
        return 0, counts
    header = rows[0]
    text_cols = [i for i, name in enumerate(header) if is_text(name)]
    if not text_cols or not any(i < len(r) and r[i] != "" and not NUMBER.match(r[i]) for r in rows[1:] for i in text_cols):
        dest.write_text(raw, encoding="utf-8")
        return len(rows) - 1, counts
    for row in rows[1:]:
        for i in text_cols:
            if i < len(row) and row[i] != "" and not NUMBER.match(row[i]):
                counts[header[i]] += 1
                row[i] = ""
    buf = io.StringIO(newline="")
    newline = "\r\n" if "\r\n" in raw else "\n"
    csv.writer(buf, lineterminator=newline).writerows(rows)
    dest.write_text(buf.getvalue(), encoding="utf-8")
    return len(rows) - 1, counts


def main(argv: list[str]) -> int:
    drop = "--drop" in argv
    report = None
    args = []
    it = iter(argv)
    for a in it:
        if a == "--report":
            report = next(it, None)
        elif a != "--drop":
            args.append(a)
    if len(args) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    src, dest = Path(args[0]), Path(args[1])
    dest.parent.mkdir(parents=True, exist_ok=True)
    suffix = src.suffix.lower()
    if suffix == ".jsonl":
        rows, counts = do_jsonl(src, dest, drop)
    elif suffix == ".json":
        rows, counts = do_json(src, dest, drop)
    elif suffix == ".csv":
        rows, counts = do_csv(src, dest)
    else:
        print(f"strip_text.py: unsupported file type {src}", file=sys.stderr)
        return 2
    emptied = ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) if counts else "nothing"
    print(f"{args[1]}: {rows} rows; {'removed' if drop else 'emptied'}: {emptied}")
    if report:
        with open(report, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"src": args[0], "dest": args[1], "rows": rows, "drop": drop,
                                 "fields": dict(sorted(counts.items()))}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
