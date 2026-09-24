# Critical review of the "A week of Jev, sorted" classification: does it hold under scrutiny?

You are an independent, skeptical reviewer. You have no stake in the result. Your job is to test whether the published statements below survive a properly sized, blind, hand-labelled audit of the data. Work sequentially; do not use any web access; everything you need is on disk. Never modify the input files. Write your own labels and scripts to the paths given. Be direct: "holds", "holds with correction", or "fails", with the corrected number and a confidence interval for every claim.

## The materials

All under `/Users/matthew.oriordan/Workshop/work/projects/jev-landscape/`:

- `data/cards.json`: `{meta, cards[]}`. Each card: `id` (X post id), `sn` (handle), `name`, `vf` (verified), `t` (an English one-line title, present for all languages), `x` (original post text, capped at 400 characters), `cat`/`u` (the source feed's own category and subcategory; ignore for labelling), `lang`, `d` (date), `v` (views), `f` (likes), `chips` (claim strings the feed extracted, e.g. "34× cheaper"), `url`.
- `data/classified-sonnet-v2.jsonl`: one line per card: the labels a model (Claude Sonnet 5) assigned under the rubric: `family`, `tier`, `evidence`, `framing`, `baseline`, `realtime_infra`, `production_claim`, `reason`.
- `data/classified-jev.jsonl`: Jev's own `family` choice per card with its stated probability.
- `data/classified-noise.jsonl`: sub-types for cards whose family is `other_or_meta`.
- `data/dedupe-groups.jsonl` and `data/hand-labels-120.jsonl`: a prior 120-card check done by another model (do not read it until you have finished your own labels; then compare).
- `report/rubric.md`: the rubric the model was given. Read it first and label against it exactly.
- `report/summary.json` and `report/data/*.csv`: the published numbers.
- `report/landscape.md`: the tables and the method, including the bucket rules and a "deviation from pre-registration" paragraph.
- `scripts/analyze.py`, `scripts/buckets-reviewed.py`: how the numbers were computed.

## The statements under test (each must get a verdict)

1. "81.5 percent of posts compare Jev with nothing; 11.9 percent with a frontier LLM; 3.0 percent with a small LLM; 3.6 percent with the thing Jev would replace (a classic classifier or ML model, rules or regex, or a vendor API)."
2. "At most 1.6 percent of posts show a production system with numbers from it; 0.9 percent on a hand re-read; the strict model label gives 0.3 percent."
3. "About 38 percent of posts are demos with no numbers; about 12 percent make a cost, speed or accuracy claim with no number ('hype'); about 23 percent are measured but a small model, a batch job or an incumbent already did the job ('cost-only'); 1.6 percent (90 posts) did something not possible before ('materially different'), 87 of them outside games."
4. "Voice, live chat and collaboration are 2.8 percent of posts and none is in production."
5. "About a fifth of posts involve a live loop (stream, channel, voice pipeline, game loop); 5 to 10 percent outside games."
6. "Of the posts needing a decision in under 300 ms, about 91 percent are games."
7. "A fifth of posts never say what Jev decides, or are benchmarks or wrappers of the model itself; memes and hot takes are about 1 percent each."
8. "Half of all views sit on 1 percent of posts" (a data statement; check the arithmetic and the effect of suspect view counts).
9. "Jev agreed with the model's family label on 77 percent of cards, and was right 27 of 28 times when its stated probability was 0.99 or higher."
10. "The median claim on the cards is about 28x cheaper and 6x faster."

## Sampling design (do this, do not shortcut it)

The rare categories are where the claims live, so a plain random sample is not enough. Use a seeded RNG (seed 20260924) and record every sampled id.

A. **Exhaustive review of the positives** for the rare labels: every card labelled `evidence = measured_production` (15), every card in the "materially different" bucket (recompute it with `scripts/buckets-reviewed.py` to get the ids), every card in the three realtime families (`voice_and_turn_taking`, `live_chat_streams_events`, `collaboration_and_typing`, about 150), and every card with `baseline` in {classic_classifier_or_ml, rules_or_regex, vendor_api} (about 210). Label each yourself.

B. **Random samples of the negatives** to estimate what the model missed: 300 cards from `baseline = none` (is there really no comparison?), 200 from `evidence = demo_no_numbers` (is there really no number of the author's own?), 200 from `evidence = measured_demo` (is the number really the author's own measurement, not the vendor's launch figures or someone else's?), 200 from `family` not in the three realtime families and not games (is any of them really voice, live chat or collaboration?), 200 from `realtime_infra = false` and 100 from `realtime_infra = true` outside games, 150 from `other_or_meta` (check the noise sub-type), and 150 from `tier` in {feel, frame, turn} (is the under-300 ms need real, and is it a game?).

C. **Blind labelling.** For every sampled card, label `family`, `tier`, `evidence`, `framing`, `baseline`, `realtime_infra`, `production_claim` from the title, text and chips only, WITHOUT looking at the model's labels for that card (write a small script that shows you the card fields only). Save to `review/hand-labels-<your-name>.jsonl` with one JSON object per card: `{id, family, tier, evidence, framing, baseline, realtime_infra, production_claim, note}`.

D. **Estimation.** For each claim, combine the exhaustive positives and the sampled negatives into a corrected estimate with a 95 percent Wilson interval (for a sample of n negatives with k found positives, scale to the stratum size). State the corrected proportion, the interval, and the verdict. Write the script to `review/estimate.py` (plain Python, no pandas) so the numbers reproduce.

E. **Substance check on the "materially different" cards.** For each of the 90, answer: what did the build do; what would a team have used before Jev (a trained classifier, rules, an incumbent API, an LLM); and is the capability genuinely unavailable at any price before, or merely cheaper or faster. Tally the three answers.

F. **Rule fairness.** Read the bucket rules in `scripts/buckets-reviewed.py` and the deviation paragraph in `report/landscape.md`. Say whether the corrected rules are fair, and whether any published bucket share would move by more than two points under a rule you consider fairer, with the number.

G. **Compare with the earlier 120-card check** (`data/hand-labels-120.jsonl`) only after you have finished: report agreement between your labels and those, on the overlap.

## Output

Write `review/critical-review-<your-name>.md` with: the sampling actually done (counts per stratum, seed); per-field agreement between your labels and the model's, per stratum; the ten verdicts, each with the corrected number and interval; the substance tally for the 90; the rule-fairness answer; the three findings a hostile reader would lead with; and what you could not check. Under 300 lines. Every number must come from your scripts. Do not soften; if a claim fails, say it fails.
