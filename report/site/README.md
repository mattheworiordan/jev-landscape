# A week of Jev, sorted: page and charts

The visual layer for the Jev landscape report: twelve charts as standalone SVG files, and `index.html`, a self-contained report page with every chart inlined and an Audit section. Everything is generated from the analysis in `../data/*.csv` and `../summary.json`, and every audited number from `../data/13_audit_*.csv`. `scripts/audit.py` writes those tables: for the audited Sonnet v2 labels from the independent audit's own scripts (`../../review/estimate.py` and friends), and for any other label file, such as the Claude Opus 5.5 labels the page uses, from `../../review/estimate-opus.py`, which repeats the audit's estimators with that file as the model under test (`../../review/audit-opus.md`).

## Regenerate

To pull the latest feed, label the new posts and rebuild everything (data, report, charts, page), run one command:

```sh
~/Workshop/work/projects/jev-landscape/scripts/refresh.sh
```

It keeps each pull in `../../data/snapshots/`, labels only the posts not yet labelled (Sonnet v2, the reference labels' model, Jev, and the noise sub-types), reruns the analysis and this generator, and prints what changed: cards before and after, new cards by day, and the headline numbers before and after. Posts after `THROUGH` (default 2026-09-23, UTC) are left out. `REFRESH_MAX_USD` caps new spend per label file (0 spends nothing), and `OFFLINE=1` skips labelling altogether. The log is in `../../data/refresh-logs/`.

To rebuild only the charts and the page from the current CSVs:

```sh
cd ~/Workshop/work/projects/jev-landscape
node report/site/scripts/charts.mjs
```

Node 18 or later. No dependencies, no network. The script:

1. Reads the CSVs, `summary.json` and the audit tables (`13_audit_*.csv`).
2. Cross-checks them against each other: family totals against the use-case base, the per-card ladder (`08_ladder_per_card.csv`) against `08_ladder.csv` and the audit's production census, the noise sub-types against figure 1's Other or meta posts, the top-1% shares against the audit's recount, the realtime slice, the chip medians, the decile agreement, the costs; and for the audit, every estimate against `summary.json`, every interval around its estimate, the labels' own shares against the model audit's, the substance counts against the 91 candidates, and the sampling and agreement tables against each other. If the audit no longer matches the base (`snapshot_matches = 0`), or any check fails, it prints the mismatch and writes nothing.
3. Writes 72 SVG files and `index.html`.
4. Runs the copy checks. Some sentences state a fact in words ("about four in five", "about a fifth", "none did something unavailable before", which production posts hold, which realtime posts claim production). They were written for the 23 September data, the 24 September audit and the Opus labels. When one no longer holds, the script prints `COPY CHECK:` and the sentence. These are warnings: the page is still written, and the sentence needs a rewrite.

The page uses the Claude Opus 5.5 labels (`data/classified-opus.jsonl`), the default of `scripts/analyze.py`. To build it from another label file with the same rubric and fields, run the analysis with that file first; the page then names that model everywhere:

```sh
python3 scripts/analyze.py --labels data/classified-sonnet-v2.jsonl
node report/site/scripts/charts.mjs --labels data/classified-sonnet-v2.jsonl
```

`LABELS` and `LABELS_MODEL` in the environment do the same, and `scripts/refresh.sh` passes them through. The Sonnet version of the report is kept for the record in `../v2/`.

The page copy (the lead paragraph for each chart, the audit section, the method section) is in `scripts/charts.mjs`, in `SECTIONS` and the HTML template. Its numbers are read from the data, so a re-run with new CSVs updates the charts and the text together. The dates and counts come from the data too: the post window from `summary.json` `window_days` and `window_utc`, the snapshot time from `feed.updated`. The byline date is `PUBLISHED` at the top of the script (default 24 September 2026; override with the `PUBLISHED` environment variable). The public repo link, and the review files the audit section links to, come from `REPO_URL` (default `https://github.com/mattheworiordan/jev-landscape`; the files are linked at `review/critical-review-grok.md`, `review/audit-opus.md` and `review/hand-labels-grok.jsonl` in that repo).

## Files

| Path | What it is |
|---|---|
| `index.html` | The report page. Inline CSS, each chart inlined twice (640 px layout, and a 360 px layout shown below 560 px), a "Show the numbers" table under each chart, a small tooltip script. The only external request is Google Fonts (Manrope, IBM Plex Mono), with system fallbacks. Light and dark follow `prefers-color-scheme`, and a `data-theme="light"` or `"dark"` on `<html>` overrides it. |
| `charts/NN-name-light.svg` | Fixed light colors, written as presentation attributes. The most portable file. |
| `charts/NN-name-dark.svg` | Fixed dark colors, same structure. |
| `charts/NN-name.svg` | Adaptive: an embedded `<style>` switches light and dark with the reader's system setting. |
| `charts/narrow/...` | The same three files laid out for phone width (360 px). |
| `charts/png/NN-name.png` | 1600 px PNGs of the light files, for X, LinkedIn and Hacker News. |
| `scripts/charts.mjs` | The generator. |

Every SVG has a `<title>` (the chart's headline sentence) and a `<desc>` (subtitle and key values), a background rect, the source line and the disclosure line. The text asks for Manrope and falls back to the system sans; label positions allow for the wider fallback fonts.

## Which SVG to use where

| Where | Use |
|---|---|
| Markdown blog on a light background | `![Of the 91 most promising builds, none did something that was unavailable before](charts/12-what-would-have-done-the-job-light.svg)` |
| Markdown blog on a dark background | the `-dark.svg` file |
| Blog that follows the reader's system theme and allows HTML | a `<picture>` element, below |
| Site with its own light/dark toggle | inline the SVG markup from `index.html` (it reads the `--v-*` CSS variables, so define them as the page does), or swap `-light` and `-dark` with the site's theme logic. `<picture>` follows the OS setting, not a site toggle. |
| Posts on X, LinkedIn or Hacker News | these don't accept SVG: use `charts/png/`, rendered from the `-light.svg` files with `rsvg-convert -w 1600 -b white` |
| Phone-first layouts, email | `charts/narrow/...-light.svg` |

```html
<picture>
  <source media="(max-width: 480px) and (prefers-color-scheme: dark)" srcset="charts/narrow/01-week-in-one-picture-dark.svg">
  <source media="(max-width: 480px)" srcset="charts/narrow/01-week-in-one-picture-light.svg">
  <source media="(prefers-color-scheme: dark)" srcset="charts/01-week-in-one-picture-dark.svg">
  <img src="charts/01-week-in-one-picture-light.svg" alt="About a third of the week's posts measured a demo, and 8 of 5,595 measured production" width="640">
</picture>
```

The wide files are 640 units wide and stay legible from 600 px up. Below 480 px, use the narrow files. For alt text, use the chart's title; the subtitle is in `<desc>`.

## Color

One accent, one secondary, the rest neutral:

- **Orange** (`#eb6834` light, `#d95926` dark): production that holds on the audit's re-read in chart 1, the empty "unavailable at any price" slot in chart 12, and Jev in chart 9. Nothing else.
- **Blue** (`#2a78d6` / `#3987e5`, with lighter and darker steps): measured work, and the one series each chart is about.
- **Greys**: everything else.

Checked with the dataviz skill's `validate_palette.js`: the blue and orange pair passes every categorical check in both modes (worst CVD ΔE 24.7 light, 26.8 dark); the three blue steps pass the ordinal check in both modes. The lightest greys are below 3:1 against the surface by design, so every grey mark is also named in a legend or a label, and each chart has a table on the page.

## The twelve charts

On the page, charts 11 and 12 follow chart 1 as figures 1b and 1c: chart 11 breaks down figure 1's Other or meta posts, and chart 12, the substance test, reads the 91 most promising builds. Every other figure keeps the number of its chart file. Every chart subtitle carries the audit's estimate and 95% interval where the audit gave one. Audited shares are of Opus's 5,595-post base.

| # | File | What it shows | Data | Caveat on the chart |
|---|---|---|---|---|
| 1 | `01-week-in-one-picture` | Unit chart: every one of the 5,595 use-case posts as a square, grouped by family and tinted by the measurement ladder (no measurement 3,835; measured demo 1,723; Opus's production label split into 8 confirmed by the audit's re-read and 29 not confirmed). | `08_ladder_per_card.csv`, `08_ladder.csv`, `01_family_distribution.csv`, `13_audit_estimates.csv` | Tint is Opus's evidence label (93% agreement with the audit); audited: no measurement 67% (64 to 70), measured demo 33% (29 to 36), production 0.14%, at most 2%. |
| 12 | `12-what-would-have-done-the-job` | Figure 1c, the substance test. What a team would have used before Jev for each of the 91 candidate builds: an LLM 64, rules or heuristics 12, a vendor API 11, a classic model 4, unavailable at any price 0 (an empty dashed slot). | `13_audit_substance.csv`, `13_audit_estimates.csv` | Judged from title and text by the independent reviewer; 85 distinct builds; 38 of the 91 still meet the selection test on the reviewer's labels. The 91 were picked on the Sonnet v2 labels. |
| 2 | `02-attention-concentration` | Cumulative share of views and likes against share of posts, most-viewed first, log x-axis, with an equal-share reference. Top 1% (56 posts): 53.3% of views, 47.0% of likes. | `06_lorenz_points.csv`, `06_attention_concentration.csv`, `06_attention_stats.csv`, `06_attention_by_day.csv` | Views are unverified; the top post is 7.8% of views at a 0.06% like rate (49.7% without it, 49.8% without the 9 suspect posts); the audit's recount on its own base gives 53.4%; posts from 16 to 19 Sep hold 79% of views. |
| 3 | `03-what-they-compared-against` | Share of posts by named baseline as bars (Opus: nothing 80.4%, frontier LLM 11.3%, small LLM 4.3%, rules 2.5%, classic ML 1.1%, vendor API 0.6%; the last three bracketed, 4.1%), with the audit's estimate and 95% interval as a marker under each bar. | `05_baseline_overall.csv`, `13_audit_estimates.csv` | Audited: nothing 80% (77 to 82), frontier LLM 11.3% (10 to 13), small LLM 5.0% (4 to 7), the tools Jev would replace 3.7% (3 to 5); all four of Opus's shares are inside; frontier and small were not sampled. |
| 4 | `04-claims-without-numbers` | Evidence level by family as 100% bars, sorted by measured share. The darkest segment is Opus's production label, which the audit does not support (it agrees with 11 of the 20 it read); the call-out gives the audit's 8. | `03_evidence_by_family_counts.csv`, `03_evidence_overall.csv`, `13_audit_production.csv`, `13_audit_estimates.csv` | Production 0.14% on the audit, at most 2%; the first pass said 1.6%. Evidence agrees with the audit on 93%. |
| 5 | `05-what-people-claimed` | Histograms of the cost and speed multiples on the claim chips, in log bins, with the median line, OpenChamber's survey and the measured small-model band marked. Median 28× (34× without "1×" chips) and 6× (8.1×). | `11_chip_multiples_long.csv`, `11_chip_multiples.csv`, `14_small_model_reference.csv` | Authors' claims, unverified; "1×" chips are an extractor artifact; accuracy and latency medians are withdrawn and not drawn. |
| 6 | `06-who-needs-it-fast` | One audited bar: the posts that need a decision in under 300 ms (frame, feel or turn), 11.0% (9.5 to 12.5), split into games (90.8%) and the rest, with the interval marked. Replaces the family-by-tier heat map. | `13_audit_estimates.csv`, `summary.json` sub300 and Jev latency, `13_audit_primary_agreement.csv` | The seven-level tier distribution is withdrawn: tier agrees with the audit on 75% and the author's own labels disagreed with both models on 8 of 13; Opus's own 14.5% is outside the interval; Jev's own p50 is 412 ms. |
| 7 | `07-realtime-slice` | The 376 posts Opus flags realtime outside games, by family and evidence. 2 are labeled production: the audit re-read one (a live news feed) and it does not hold; it never saw the other. | `08_ladder_per_card.csv`, `summary.json` realtime, `13_audit_estimates.csv`, `13_audit_production.csv` | Audited: a live loop outside games is 8.1% of posts (6.0 to 11.4), about a fifth with games; voice, live chat and collaboration 4.0% (2.9 to 6.6), none measured in production and two claiming it without a number. |
| 8 | `08-what-measuring-buys` | Median and mean views per post by evidence level (measured demo, demo with no numbers, proposal, commentary). Replaces the framing chart. | `03_evidence_overall.csv`, `06_attention_stats.csv` | Opus's measured-production posts are left out (the audit confirms 8 in all); views favor older posts; framing is withdrawn after a human calibration. |
| 9 | `09-jev-grading-jev` | Jev's calls in ten equal tenths by stated probability. Each column is the tenth's volume (595 cards); orange is the cards where Jev picked the reference labels' family; the black tick is Jev's average stated probability. 42.5% at D1 to 98.0% at D10. | `12_calibration_equal_count_deciles.csv`, `00_gateway_cost.csv`, `summary.json` agreement, `13_audit_estimates.csv` | Agreement with Opus, not accuracy; 27 of 28 right at 0.99 or above on the 120-card sample; on the audit's 464 high-confidence cards Jev matched 98.1%; 38% of the confident calls are games or trading; Jev $0.33 against Opus $27.98. |
| 10 | `10-where-the-builders-were` | Language of the post (Japanese 19.6%) and posts per day, 16 to 23 Sep, peak 1,027 on 19 Sep. | `10_language_overall.csv`, `06_attention_by_day.csv` | 16 Sep starts six hours after launch and 23 Sep ends at 18:44 UTC. |
| 11 | `11-what-the-noise-is-made-of` | Figure 1b. Opus's 1,265 noise posts (other_or_meta, or commentary in another family) by sub-type: a bar for each sub-type's share of the noise's posts (blue) and a thinner bar for its share of the noise's views (light blue). 326 are not yet sub-typed. | `12_noise_breakdown.csv`, `12b_noise_stance.csv`, `summary.json` noise, `13_audit_estimates.csv` | Bars are shares of the noise, not of all posts. Audited: about a fifth of posts are meta, 20.9% (19.4 to 22.2), 20.7% (16.9 to 25.9) on the audit's samples alone; memes and hot takes under half a percent of posts each. |

## Not drawn, and why

- **The measured small-model band on chart 5** (5 to 10× cost, 2 to 4× latency, from the Pong comparison) is drawn from `../data/14_small_model_reference.csv`, one band per row with its own legend entry. Delete the file to leave the bands out.
- **OpenChamber's survey marks on chart 5** (about 30× and 7×) are the one external reference on a chart. They come from `../landscape.md` section 11, which cites [OpenChamber's post](https://openchamber.dev/blog/jev-typesafe-ai/). They are constants in the script (`SURVEY`), not CSV values.
- **The noise sub-types for 326 of Opus's noise posts**: the sub-types come from a Sonnet pass over the Sonnet v2 noise posts. `scripts/refresh.sh` sub-types the rest (it needs the Gateway and about a dollar).
- **Chart 9's human-label variant** waits for human labels; the author's 13 calibration labels (`../../review/human-labels.jsonl`) are too few.
- **The labelling model's cost on chart 9** is the reference-label run in `summary.json` (`cost.labels_run`): $27.98 for the Opus run.
- **Withdrawn, not charted:** accuracy and latency chip medians (v2); the bucket tint and chips (the audit's claim 3 failed; tables kept in `../v1/buckets-on-v2-labels.md`); the framing chart and every framing number, and the family-by-tier heat map (a human calibration; the old files are in `../../data/withdrawn-tables/`).
