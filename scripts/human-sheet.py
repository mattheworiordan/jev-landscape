#!/usr/bin/env python3
"""Step 5: the human-labelling sheet for review item 6.

    python3 scripts/human-sheet.py        (from the jev-landscape folder)

Writes report/human-labels-120.csv (the review's 120 random cards, in sample order,
with empty label columns) and report/human-labels-README.md (a one-page instruction
block, then the rubric definitions quoted from report/rubric.md, so the sheet always
carries the rubric that ran). The sample is the review's:
random.Random(20260923).sample(range(5782), 120) over the cards sorted by id.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LABEL_COLS = ["family", "tier", "evidence", "framing", "baseline", "realtime_infra", "production_claim"]

cards = {c["id"]: c for c in json.loads((ROOT / "data" / "cards.json").read_text())["cards"]}
ids = [json.loads(l)["id"] for l in (ROOT / "data" / "hand-labels-120.jsonl").read_text().splitlines() if l.strip()]
out = ROOT / "report" / "human-labels-120.csv"
with open(out, "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["id", "url", "title", "text", "chips"] + LABEL_COLS)
    for i in ids:
        c = cards[i]
        w.writerow([i, c["url"], c["t"], c["x"], "; ".join(c.get("chips") or [])] + [""] * len(LABEL_COLS))

rubric = (ROOT / "report" / "rubric.md").read_text()
start = rubric.index("## family")
end = rubric.index("## reason")
quoted = "\n".join(("> " + line) if line.strip() else ">" for line in rubric[start:end].rstrip().splitlines())

readme = f"""# Human labels for 120 Jev cards: instructions

**What this is for.** The landscape report's labels come from Claude Sonnet 5, and the only check so far is a second AI reader (Claude Opus 5.5). {len(ids)} labels from a person settle how accurate Sonnet and Jev really are. The cards are the review's random sample, so the results compare directly with it.

**What to do (about an hour, 30 seconds a card).**
1. Open `human-labels-120.csv` in a spreadsheet. Each row is one X post about Jev: `title` is OpenChamber's English one-line summary, `text` is the post (cut at 400 characters), `chips` are numbers extracted from the full post and can be wrong.
2. Fill the seven empty columns for every row, using only the values in the table below, spelled exactly. Judge only what the row says. Do not open the URL unless you cannot decide at all; the classifiers saw only what is in the row.
3. When the post does not say, use the empty value: `unclear` for tier, `none` for framing and baseline, `false` for the two booleans. These are correct answers, not failures.
4. Do not look at the Sonnet or Jev labels before you finish.
5. Save as CSV with the same name and columns. Then `python3 scripts/hand_agreement.py --reference report/human-labels-120.csv` scores Sonnet v1 and v2 against your labels, field by field.

| column | allowed values |
|---|---|
| family | evals_and_judging, classification_routing_triage, moderation_and_guardrails, agent_harness_and_tool_gating, compaction_and_context, search_rerank_extraction, browser_and_computer_use, voice_and_turn_taking, live_chat_streams_events, collaboration_and_typing, games_control_loops_simulation, data_and_telemetry, trading_and_markets, not_a_jev_build, other_or_meta |
| tier | frame, feel, turn, interaction, task, batch, unclear |
| evidence | measured_production, measured_demo, demo_no_numbers, proposal_or_idea, commentary_or_meme |
| framing | cost, latency, accuracy, capability, none |
| baseline | frontier_llm, small_llm, classic_classifier_or_ml, vendor_api, rules_or_regex, none |
| realtime_infra | true, false |
| production_claim | true, false |

**The four calls people get wrong most often.** (1) A number counts as a measurement only if the author's own run produced it; TypeSafe's launch figures (20 to 200× faster, 40 to 400× cheaper, 70 to 500 ms) do not count. (2) capability needs an explicit "this was not possible or affordable before"; showing a new build is `none`. (3) A baseline needs a comparison named or clearly implied in the post; using an LLM next to Jev is not one. (4) realtime_infra needs a described live loop, stream, channel, voice pipeline or live session; the word "real-time" in a title is not enough.

## The rubric definitions (quoted from report/rubric.md, rubric v2)

{quoted}
"""
(ROOT / "report" / "human-labels-README.md").write_text(readme)
print(f"wrote {out.relative_to(ROOT)} ({len(ids)} rows) and report/human-labels-README.md")
