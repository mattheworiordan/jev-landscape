# Audit estimates with Claude Opus 5.5 as the model under test

Written by `review/estimate-opus.py` (the script also writes every number to `review/work/estimate-opus.json` and the tables to `review/data/audit-opus-*.csv`). Reference labels: Grok's 1,681 blind labels (`review/hand-labels-grok.jsonl`), with the 15 production re-reads. Model under test: Claude Opus 5.5 (`data/classified-opus.jsonl`, rubric v2). Comparison: Claude Sonnet 5 (`data/classified-sonnet-v2.jsonl`), the labels the audit sampled from. Estimators: `review/estimate.py`'s, unchanged.

## Bottom line

- Opus agrees with the audit more often than Sonnet on every field: family 81.6% against 71.0% (kappa 0.79 against 0.67), tier 75.2% against 61.9%, evidence 93.1% against 89.2%, baseline 93.6% against 89.5%, realtime flag 94.7% against 85.6%.
- Of the 19 figures in the side-by-side table that have an interval, 17 Opus figures are inside the audit's 95% interval, against 11 for Sonnet. The Opus figures outside: the under-300 ms set (Opus 14.5%, audit 11.0%, 9.5–12.5%; audit-only 8.2–14.3%); meta posts (Opus 22.4%, audit 20.9%, 19.4–22.2%; audit-only 16.9–25.9%).
- Do not publish Opus's measured-production count as it stands. Opus labels 37 posts; the audit's census and samples give 8 posts, 0.14% (0.14–2.01%), and the audit agrees with 11 of the 20 Opus production posts it read.
- Two of the review's estimators take the posts outside their sampled strata as correctly labelled. The audit's own random samples of demos say they are not. Estimated from those samples instead, Sonnet's base has 80.8% (76.9–84.9%) of posts with no comparison and 20.0% (16.1–25.2%) meta posts. Sonnet's own 81.4% and 21.1% are inside those intervals (so are its three other baseline shares), so the review's "Fails" on claims 1 and 7 rests on that assumption. The "audit-only" column below gives these estimates wherever a claim has such a region.

## How the estimates are formed

1. **Strata and reference.** The strata stay as `review/sample.py` drew them from Sonnet's labels (seed 20260924). The script checks that Sonnet's labels still give the same stratum sizes and census lists, and stops if they do not. Grok's labels are the reference. Opus's labels on the same posts are the model under test.
2. **Estimators.** `wilson()`, `corrected()` and `scale_count()` are imported from `review/estimate.py`. Census strata are counted exactly, each sample is scaled to its stratum with a 95% Wilson interval, and where strata are added the bounds are summed (wider than a joint interval). Run with Sonnet as the model, the script reproduces `review/work/estimate.json` to 1e-9 on every claim and on the agreement table. It checks this on every run.
3. **Base.** Shares are of Opus's own use-case base, 5,595 posts: 5,949 labelled, 7 duplicates merged, 347 not_a_jev_build left out. 1 post was refused by Opus's safety filter and has no label. The audit's frame is Sonnet's base (5,709). 139 frame posts are outside Opus's base (138 Opus calls not_a_jev_build, and the refused post). Each stratum is cut to Opus's base. The audited posts left in a sampled stratum are still a simple random sample of what is left of it (domain estimation), so the scaling holds.
4. **Plug-ins.** Where `review/estimate.py` takes a region the audit did not sample from the model's own labels, this run takes Opus's labels. The regions, in Opus's base: the frontier and small-LLM strata (847 posts, claim 1); the proposal and commentary posts (78, claims 2 and 3); games, outside the realtime-family negative sample (1,051, claim 4); flagged games (994, claim 5); posts outside Sonnet's under-300 ms stratum (4,535, claim 6) and outside its meta stratum (4,438, claim 7). With Sonnet as the model these regions add nothing, or exactly what the review assumed. The 25 posts in Opus's base that Sonnet called not_a_jev_build were never in the frame; they enter at Opus's labels too. The column "on Opus's word" gives the size of these terms.
5. **Audit-only variant.** The evidence strata cover every frame post except the 85 proposal and commentary posts: the census of Sonnet's 15 measured-production posts and random samples of 200 demos with no numbers and 200 measured demos. Cut to a plug-in region, the samples that fall inside it are a random sample of that part of the region. "Audit-only" replaces each plug-in region by that estimate. It takes neither model's word except on the proposal, commentary and model-only posts. Its intervals are wide where few sampled posts fall in the region.
6. **Not a random sample.** The 1,681 audited posts over-represent the census strata (read in full) and are sampled at 3% to 65% elsewhere, on Sonnet's labels. Raw agreement on them is not a population rate. The "weighted" columns reweight each audited post by 1/(its inclusion probability) under the design (1 in a census stratum, else 1 − ∏(1 − n/N) over the sampled strata that hold it, treating the eight samples as independent draws). The weights sum to 5,721, against 5,709 frame posts.
7. **`scripts/audit.py`.** Its `reestimate()` (checked against the 24 Sep 09:23 version) gives shares of the frame, not of Opus's base. On claims 1 to 5 its numbers equal this script's frame-base variant (`model_frame_base` in the JSON) to 1e-9. It differs on claims 6 and 7, where it uses the samples only, and on the games' live-loop rate in claim 5, where it counts Sonnet's games in the under-300 ms sample. "Samples only" keeps Sonnet's assumption that no post outside Sonnet's meta or under-300 ms stratum belongs in it. With Opus's labels it prints 14.9% meta posts next to Opus's 22.4%.

## Agreement with the audit on the 1,681 audited posts

| field | Opus agrees | Opus kappa | Opus weighted | Opus weighted kappa | Sonnet agrees | Sonnet kappa | Sonnet weighted |
|---|---:|---:|---:|---:|---:|---:|---:|
| family | 1,371 (81.6%) | 0.79 | 82.0% | 0.79 | 1,193 (71.0%) | 0.67 | 72.3% |
| tier | 1,264 (75.2%) | 0.69 | 76.2% | 0.70 | 1,041 (61.9%) | 0.52 | 61.9% |
| evidence | 1,565 (93.1%) | 0.86 | 93.2% | 0.86 | 1,500 (89.2%) | 0.79 | 89.9% |
| framing | 1,482 (88.2%) | 0.82 | 89.1% | 0.83 | 1,275 (75.8%) | 0.65 | 75.9% |
| baseline | 1,574 (93.6%) | 0.83 | 94.9% | 0.85 | 1,504 (89.5%) | 0.73 | 91.5% |
| realtime_infra | 1,592 (94.7%) | 0.86 | 95.1% | 0.85 | 1,439 (85.6%) | 0.67 | 87.1% |
| production_claim | 1,655 (98.5%) | 0.64 | 98.2% | 0.53 | 1,646 (97.9%) | 0.52 | 98.0% |

The framing field is withdrawn from the rebuilt report; it is kept here because the review's bucket rule uses it. Kappa on production_claim is low for both models because the audit marks it true on only 26 of the 1,681 audited posts.

By stratum. Percent agreement, Opus / Sonnet. Strata are Sonnet-defined; within a sampled stratum the posts are a random sample.

| stratum | n | family | tier | evidence | framing | baseline | realtime | production |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| measured_production | 15 | 87 / 67 | 73 / 40 | 80 / 53 | 87 / 80 | 93 / 80 | 100 / 93 | 93 / 67 |
| material | 91 | 84 / 59 | 75 / 69 | 89 / 79 | 85 / 79 | 92 / 92 | 88 / 68 | 99 / 97 |
| realtime families | 156 | 79 / 58 | 75 / 58 | 97 / 92 | 87 / 76 | 97 / 97 | 93 / 81 | 99 / 99 |
| replacement baseline | 201 | 82 / 72 | 69 / 59 | 95 / 89 | 83 / 70 | 79 / 62 | 97 / 90 | 99 / 98 |
| baseline none | 300 | 82 / 75 | 75 / 64 | 93 / 89 | 92 / 79 | 96 / 95 | 96 / 89 | 98 / 100 |
| demo_no_numbers | 200 | 82 / 75 | 71 / 58 | 92 / 89 | 91 / 80 | 98 / 94 | 92 / 87 | 98 / 98 |
| measured_demo | 200 | 84 / 73 | 73 / 64 | 94 / 88 | 88 / 74 | 93 / 86 | 96 / 88 | 100 / 98 |
| not realtime family, not games | 200 | 82 / 69 | 80 / 64 | 91 / 90 | 88 / 75 | 96 / 90 | 97 / 88 | 98 / 98 |
| realtime_infra false | 200 | 76 / 63 | 80 / 64 | 95 / 92 | 88 / 72 | 92 / 90 | 98 / 98 | 98 / 96 |
| realtime_infra true, not games | 100 | 83 / 71 | 78 / 62 | 95 / 92 | 82 / 70 | 94 / 92 | 90 / 55 | 96 / 97 |
| other_or_meta | 150 | 79 / 71 | 83 / 80 | 89 / 85 | 91 / 81 | 95 / 94 | 97 / 97 | 99 / 99 |
| tier under 300 ms | 150 | 93 / 91 | 72 / 49 | 97 / 97 | 86 / 78 | 97 / 94 | 89 / 76 | 99 / 99 |
| all labelled | 1,681 | 82 / 71 | 75 / 62 | 93 / 89 | 88 / 76 | 94 / 89 | 95 / 86 | 98 / 98 |

## Recount by Opus's own label

Among the audited posts, grouped by Opus's label: how often the audit gives the same label. These posts are not a random sample of Opus's labels. The strata were drawn on Sonnet's labels, and rare strata were read in full. The weighted columns correct for the design (method, point 6); they estimate the rate over the frame, not over the audited posts. Sonnet's weighted precision is given for comparison.

| Opus label | Opus posts | audited | audit agrees | precision | weighted | Sonnet weighted | recall | weighted recall |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| family is voice, live chat or collaboration | 206 | 153 | 125 | 81.7% | 72.7% | 66.7% | 85.0% | 75.0% |
| family is games | 1,071 | 287 | 273 | 95.1% | 94.6% | 92.1% | 94.1% | 94.1% |
| family is other_or_meta | 1,254 | 385 | 296 | 76.9% | 78.3% | 70.5% | 83.4% | 83.3% |
| family is not_a_jev_build | 347 | 36 | 23 | 63.9% | 70.2% | n/a | 71.9% | 71.4% |
| evidence is measured_production | 37 | 20 | 11 | 55.0% | 43.1% | 53.3% | 100.0% | 100.0% |
| evidence is measured (demo or production) | 1,760 | 569 | 549 | 96.5% | 97.5% | 88.8% | 94.8% | 93.9% |
| evidence is demo_no_numbers, proposal or commentary | 3,835 | 1,112 | 1,082 | 97.3% | 97.2% | 96.8% | 98.2% | 98.9% |
| baseline is none | 4,498 | 1,296 | 1,265 | 97.6% | 97.5% | 95.4% | 95.8% | 97.3% |
| baseline is classic ML, rules or vendor API | 228 | 173 | 140 | 80.9% | 74.1% | 68.2% | 87.0% | 73.8% |
| tier is frame, feel or turn | 809 | 262 | 174 | 66.4% | 66.8% | 47.2% | 90.2% | 91.7% |
| realtime_infra true, not games | 376 | 215 | 192 | 89.3% | 83.3% | 46.5% | 85.3% | 77.0% |
| realtime_infra true | 1,152 | 427 | 379 | 88.8% | 87.0% | 61.9% | 90.2% | 89.2% |
| meets the material test (corrected bucket material) | 72 | 52 | 34 | 65.4% | 59.4% | 41.8% | 56.7% | 43.6% |
| production_claim true | 124 | 48 | 24 | 50.0% | 39.1% | 33.6% | 92.3% | 87.4% |

By field and value (every value Opus uses). Precision: of the audited posts Opus gives this value, the share the audit gives it too. Recall: of the audited posts the audit gives this value, the share Opus gives it too.

| field | Opus value | Opus posts | audited | agrees | precision | weighted | recall | weighted recall |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| family | agent_harness_and_tool_gating | 262 | 68 | 47 | 69.1% | 63.9% | 75.8% | 76.2% |
| family | browser_and_computer_use | 254 | 66 | 59 | 89.4% | 86.7% | 88.1% | 92.8% |
| family | classification_routing_triage | 781 | 200 | 183 | 91.5% | 92.7% | 62.5% | 65.3% |
| family | collaboration_and_typing | 66 | 50 | 41 | 82.0% | 70.8% | 74.5% | 57.9% |
| family | compaction_and_context | 87 | 15 | 12 | 80.0% | 74.4% | 85.7% | 95.7% |
| family | data_and_telemetry | 271 | 60 | 31 | 51.7% | 55.5% | 83.8% | 85.2% |
| family | evals_and_judging | 366 | 83 | 68 | 81.9% | 81.0% | 65.4% | 69.1% |
| family | games_control_loops_simulation | 1,071 | 287 | 273 | 95.1% | 94.6% | 94.1% | 94.1% |
| family | live_chat_streams_events | 68 | 45 | 34 | 75.6% | 64.0% | 77.3% | 70.5% |
| family | moderation_and_guardrails | 257 | 77 | 55 | 71.4% | 75.5% | 94.8% | 92.7% |
| family | not_a_jev_build | 0 | 36 | 23 | 63.9% | 70.2% | 71.9% | 71.4% |
| family | other_or_meta | 1,254 | 385 | 296 | 76.9% | 78.3% | 83.4% | 83.3% |
| family | search_rerank_extraction | 518 | 170 | 136 | 80.0% | 80.1% | 90.7% | 90.5% |
| family | trading_and_markets | 268 | 81 | 70 | 86.4% | 83.5% | 97.2% | 96.6% |
| family | voice_and_turn_taking | 72 | 58 | 43 | 74.1% | 64.8% | 89.6% | 82.5% |
| tier | batch | 781 | 201 | 168 | 83.6% | 84.7% | 66.7% | 72.6% |
| tier | feel | 756 | 221 | 148 | 67.0% | 67.2% | 91.4% | 93.3% |
| tier | frame | 3 | 0 | 0 | n/a | n/a | 0.0% | 0.0% |
| tier | interaction | 1,254 | 452 | 346 | 76.5% | 76.1% | 81.2% | 80.0% |
| tier | task | 1,453 | 369 | 248 | 67.2% | 69.5% | 73.6% | 75.0% |
| tier | turn | 50 | 41 | 24 | 58.5% | 52.9% | 82.8% | 73.6% |
| tier | unclear | 1,298 | 397 | 330 | 83.1% | 84.0% | 69.8% | 70.9% |
| evidence | commentary_or_meme | 142 | 43 | 27 | 62.8% | 63.0% | 40.3% | 41.7% |
| evidence | demo_no_numbers | 3,672 | 1,063 | 991 | 93.2% | 93.0% | 96.9% | 97.5% |
| evidence | measured_demo | 1,723 | 549 | 531 | 96.7% | 97.6% | 93.5% | 92.9% |
| evidence | measured_production | 37 | 20 | 11 | 55.0% | 43.1% | 100.0% | 100.0% |
| evidence | proposal_or_idea | 21 | 6 | 5 | 83.3% | 76.4% | 41.7% | 41.0% |
| framing | accuracy | 533 | 203 | 177 | 87.2% | 88.8% | 86.8% | 82.9% |
| framing | capability | 116 | 48 | 29 | 60.4% | 59.2% | 59.2% | 55.9% |
| framing | cost | 616 | 160 | 141 | 88.1% | 87.1% | 83.9% | 84.4% |
| framing | latency | 1,136 | 377 | 349 | 92.6% | 92.9% | 79.1% | 79.7% |
| framing | none | 3,194 | 893 | 786 | 88.0% | 89.2% | 96.0% | 97.1% |
| baseline | classic_classifier_or_ml | 59 | 51 | 38 | 74.5% | 66.2% | 90.5% | 72.5% |
| baseline | frontier_llm | 630 | 148 | 126 | 85.1% | 91.9% | 85.1% | 85.6% |
| baseline | none | 4,498 | 1,296 | 1,265 | 97.6% | 97.5% | 95.8% | 97.3% |
| baseline | rules_or_regex | 138 | 99 | 82 | 82.8% | 80.2% | 81.2% | 69.1% |
| baseline | small_llm | 239 | 64 | 48 | 75.0% | 77.3% | 94.1% | 98.5% |
| baseline | vendor_api | 31 | 23 | 15 | 65.2% | 51.9% | 83.3% | 86.6% |
| realtime_infra | False | 4,443 | 1,254 | 1,213 | 96.7% | 97.2% | 96.2% | 96.6% |
| realtime_infra | True | 1,152 | 427 | 379 | 88.8% | 87.0% | 90.2% | 89.2% |
| production_claim | False | 5,471 | 1,633 | 1,631 | 99.9% | 99.8% | 98.5% | 98.3% |
| production_claim | True | 124 | 48 | 24 | 50.0% | 39.1% | 92.3% | 87.4% |

"Opus posts" counts Opus's use-case base, so not_a_jev_build shows 0 there (347 after merging duplicates).

## The ten claims

**1. Baselines.** none Opus 80.4%, audit 80.0% (77.4–81.6%); frontier Opus 11.3%, audit 11.3% (10.5–13.1%); small Opus 4.3%, audit 5.0% (4.2–6.9%); replacement Opus 4.1%, audit 3.7% (3.0–5.4%). All four Opus shares are inside their intervals; Sonnet's none, frontier and small shares were outside theirs. The 847 frontier and small-LLM posts were not sampled, so the estimate takes Opus's word there (112 none, 548 frontier, 177 small, 10 replacement). The audit's own samples put that region at 151 none, 492 frontier, 194 small and 10 replacement, close to Opus's split and far from Sonnet's (690 frontier, 171 small, 0 none). Of those posts that happen to be audited, Opus's frontier label holds on 126 of 148 (Sonnet 115 of 151). Recount by Opus's label: replacement baseline 173 audited, the audit agrees on 140 (80.9%; weighted 74.1%); none 1,296 audited, the audit agrees on 1,265 (97.6%; weighted 97.5%).

**2. Production.** Opus: 37 posts, 0.66%. Audit: 8 posts, 0.14% (0.14–2.01%): 8 of Sonnet's 15 hold on the re-read, and neither sample of 200 demos has a production post. Opus's share is inside the interval only because the interval's top is the Wilson bound on zero misses in 400 sampled demos. The recount is direct: 20 of Opus's 37 production posts were audited and 11 hold (sanity check 1). Publish the audited count, not Opus's.

**3. The measurement ladder.** no measurement: Opus 68.5%, audit 67.3% (63.5–70.5%); measured demo: Opus 30.8%, audit 32.5% (29.4–36.3%); demos with no numbers, report rule (no claim chip, not meta): Opus 47.9%, audit 46.6% (41.8–51.6%); a claim chip with no measurement, report rule: Opus 2.1%, audit 2.5% (1.3–5.4%); demos with no numbers, review rule: Opus 36.5%, audit 35.0% (30.0–40.5%); a cost, speed or accuracy lead with no number, review rule: Opus 13.0%, audit 15.8% (11.6–21.3%); measured, and a batch or an incumbent already did it: Opus 11.9%, audit 12.5% (9.7–16.6%); posts that meet the material test, misses included: Opus 1.3%, audit 2.0% (1.2–4.6%). Every Opus figure is inside its interval. The ladder rests on the evidence field, where Opus's measured label holds on 97.5% (weighted) and its no-measurement label on 97.2%. The review-rule rows leave out the proposal and commentary posts, as `review/estimate.py` does. Opus's own count of posts that meet the material test is 72; 52 audited, the audit agrees on 34 (65.4%; weighted 59.4%).

**4. Voice, live chat and collaboration.** Opus: 206 posts, 3.7%. Audit: 4.0% (2.9–6.6%), 7 posts on Opus's word (6 games Opus moves into these families, and 1 model-only). Sonnet's 2.7% sat at the bottom of its interval; Opus's is near the centre. Recount: 153 audited, the audit agrees on 125 (81.7%; weighted 72.7%). Production: the audit has 0 of these posts in measured production (Opus labels 1, the live news feed the audit re-read as having no number). On the audit's own labels two of these posts claim production without a measurement: the Discord moderation bot in the negative sample, which the review read and did not count, and the same news feed, which Sonnet had in classification, so the census of 156 did not see it.

**5. A live loop.** Outside games: Opus 6.7%, audit 8.1% (6.0–11.4%), 11 posts on Opus's word. Sonnet's 12.6% was outside its interval. With games: Opus flags 20.6%; the review's rough construction gives 22.4%; the evidence strata alone give 22.2% (17.1–28.4%). Both halves of the claim (about a fifth; 5 to 10 percent outside games) fit Opus's figures. Recount: realtime flag true and not games, 215 audited, the audit agrees on 192 (89.3%; weighted 83.3%).

**6. Under 300 ms.** Opus puts 809 posts (14.5%) under 300 ms. Audit: 11.0% (9.5–12.5%): 76 of the 150 sampled posts in Sonnet's stratum stay under 300 ms, plus 91 posts that Opus alone puts there, on Opus's word. The audit's samples put 49 (12–192) such posts outside Sonnet's stratum, not 89; audit-only 10.3% (8.2–14.3%). Opus's share is outside both, though nearer than Sonnet's 18.6%. Recount: 262 audited, the audit agrees on 174 (66.4%; weighted 66.8%). The games share holds: Opus 87.4%, audit 69 of 76, 90.8% (82.2–95.5%).

**7. Meta posts.** Opus: 1,254 posts, 22.4%. Audit, same logic: 20.9% (19.4–22.2%), of which 318 posts on Opus's word (303 outside Sonnet's meta stratum, and 15 model-only). Audit-only: 20.7% (16.9–25.9%): the audit's samples put 292 (166–509) meta posts outside Sonnet's stratum, close to Opus's 303. Inside the stratum Opus calls 936 of 1,132 posts meta; the sample says 104 of 138 (75.4%), about 853. So Opus over-calls meta inside Sonnet's stratum and is about right outside it. Opus's share is just above the same-logic interval and inside the audit-only one. The review's 14.9% (13.3–16.3%) for Sonnet leaves out the same region; with it, Sonnet's base is 20.0% (16.1–25.2%) meta, and Sonnet's 21.1% is inside. "A fifth of posts" holds under both models once that region is counted. Memes 0.29% and hot takes 0.44% of posts (2 and 3 of 138 sampled): "about 1% each" still fails. Unrelated, a benchmark or a wrapper: 12.6% on the sample, 17.1% with the region outside the stratum. Opus has no noise sub-types of its own; its meme and hot-take counts use the noise file, which covers 1,254 of its 1,254 meta posts. Recount: 385 audited, the audit agrees on 296 (76.9%; weighted 78.3%).

**8. Attention (a census).** Only the base moves. Top 1% (56 posts; 58 on Sonnet's base) hold 53.3% of views (53.4%); 49.8% without the 9 low-like-rate posts (49.6%); 47.0% of likes (47.5%); 47 posts hold half of all views (49). The verdict does not change.

**9. Jev as a classifier.** Jev matches Opus's family on 4,660 of 5,942 posts (78.4%, kappa 0.75; Sonnet 76.7%, kappa 0.73), and on 97.0% of the 1,653 posts where Jev states 0.99 or more (Sonnet 97.5%). Against the audit, Jev at 0.99 or more matches on 455 of 464, and on 27 of the 28 such posts in the earlier 120 labels; neither depends on the model. Holds.

**10. Claimed multiples (a census of the chips).** Only the base moves: 126 cost chips (Sonnet's base 126), median 28× (34× without the 8 1× chips; 34× on Sonnet's base); 297 speed chips (299), median 6× (8.1× without the 51 1× chips; 8.5× on Sonnet's base). The headline medians hold; the speed figure without 1× chips needs updating if the report prints it.

## Side by side

Shares are of each model's own use-case base (Sonnet 5,709, Opus 5,595). "Audit" is the review's estimator with that model as the model under test. "On Opus's word" is the number of posts the Opus estimate takes from Opus's labels. "Audit-only" is on Opus's base; Sonnet's base gives nearly the same (CSV). ✓ = the model's own figure is inside the audit interval.

| claim | quantity | Sonnet labels | audit, Sonnet as model | Opus labels | audit, Opus as model | on Opus's word | audit-only | Sonnet ✓ | Opus ✓ |
|---:|---|---:|---:|---:|---:|---:|---:|:---:|:---:|
| 1 | Compared with nothing | 81.4% | 78.2% (75.7–79.8%) | 80.4% | 80.0% (77.4–81.6%) | 131 | 80.7% (76.8–84.8%) | ✗ | ✓ |
| 1 | Compared with a frontier LLM | 12.1% | 13.5% (12.8–15.3%) | 11.3% | 11.3% (10.5–13.1%) | 548 | 10.3% (6.9–14.2%) | ✗ | ✓ |
| 1 | Compared with a small LLM | 3.0% | 4.8% (3.9–6.6%) | 4.3% | 5.0% (4.2–6.9%) | 181 | 5.3% (2.9–9.9%) | ✗ | ✓ |
| 1 | Compared with classic ML, rules or a vendor API | 3.5% | 3.5% (2.8–5.1%) | 4.1% | 3.7% (3.0–5.4%) | 12 | 3.7% (2.9–7.3%) | ✓ | ✓ |
| 2 | Measured production that holds on the audit's reading | 0.26% | 0.14% (0.14–1.99%) | 0.66% | 0.14% (0.14–2.01%) | 0 |  | ✓ | ✓ |
| 3 | Ladder: no measurement | 66.0% | 67.2% (63.4–70.3%) | 68.5% | 67.3% (63.5–70.5%) | 97 |  | ✓ | ✓ |
| 3 | Ladder: measured demo | 33.8% | 32.7% (29.6–36.5%) | 30.8% | 32.5% (29.4–36.3%) | 6 |  | ✓ | ✓ |
| 3 | Ladder: measured production | 0.26% | 0.14% (0.14–1.99%) | 0.66% | 0.14% (0.14–2.01%) | 0 |  | ✓ | ✓ |
| 3 | Demos with no numbers (report rule: no claim chip, not meta) | 48.0% | 46.5% (41.6–51.4%) | 47.9% | 46.6% (41.8–51.6%) | 18 |  | ✓ | ✓ |
| 3 | A cost, speed or accuracy claim with no number (report rule: claim chip) | 1.2% | 2.4% (1.2–5.3%) | 2.1% | 2.5% (1.3–5.4%) | 4 |  | ✗ | ✓ |
| 3 | Demos with no numbers (review rule, framing field) | 37.7% | 34.7% (29.7–40.3%) | 36.5% | 35.0% (30.0–40.5%) | 17 |  | ✓ | ✓ |
| 3 | A cost, speed or accuracy lead with no number (review rule, framing field) | 9.6% | 16.1% (11.9–21.5%) | 13.0% | 15.8% (11.6–21.3%) | 0 |  | ✗ | ✓ |
| 3 | Measured, and a batch or an incumbent already did the job | 10.6% | 12.5% (9.8–16.6%) | 11.9% | 12.5% (9.7–16.6%) | 0 |  | ✓ | ✓ |
| 3 | Posts that meet the material test, misses included | 1.6% | 2.0% (1.2–4.6%) | 1.3% | 2.0% (1.2–4.6%) | 0 |  | ✓ | ✓ |
| 4 | Voice, live chat or collaboration | 2.7% | 3.8% (2.7–6.3%) | 3.7% | 4.0% (2.9–6.6%) | 7 | 3.9% (2.7–7.9%) | ✓ | ✓ |
| 5 | A live loop outside games | 12.6% | 7.8% (5.8–11.1%) | 6.7% | 8.1% (6.0–11.4%) | 11 | 8.3% (5.9–13.3%) | ✗ | ✓ |
| 5 | A live loop, games included (the review's rough construction) | 30.4% | 21.7% | 20.6% | 22.4% |  | 22.2% (17.1–28.4%) |  |  |
| 6 | Posts that need a decision in under 300 ms | 18.6% | 9.4% (8.0–10.9%) | 14.5% | 11.0% (9.5–12.5%) | 91 | 10.3% (8.2–14.3%) | ✗ | ✗ |
| 6 | Share of the under-300 ms posts that are games | 90.8% | 90.8% (82.2–95.5%) | 87.4% | 90.8% (82.2–95.5%) |  | 88.1% | ✓ | ✓ |
| 7 | Posts that are meta (never say what Jev decides, benchmark, wrapper, commentary) | 21.1% | 14.9% (13.3–16.3%) | 22.4% | 20.9% (19.4–22.2%) | 318 | 20.7% (16.9–25.9%) | ✗ | ✗ |
| 7 | Unrelated or unclear, a benchmark, or a wrapper | 18.8% | 12.4% | 20.0% | 12.6% |  | 17.1% |  |  |
| 7 | Memes | 0.25% | 0.28% | 0.27% | 0.29% |  | 0.29% |  |  |
| 7 | Hot takes | 0.21% | 0.42% | 0.32% | 0.44% |  | 0.44% |  |  |
| 8 | Share of views on the top 1% of posts |  | 53.4% |  | 53.3% |  |  |  |  |
| 8 | The same without the low-like-rate posts |  | 49.6% |  | 49.8% |  |  |  |  |
| 8 | Share of likes on the top 1% of posts |  | 47.5% |  | 47.0% |  |  |  |  |
| 9 | Jev picks the model's family |  | 76.7% |  | 78.4% |  |  |  |  |
| 9 | The same at a stated probability of 0.99 or more |  | 97.5% |  | 97.0% |  |  |  |  |
| 9 | Jev matches the audit's family at 0.99 or more |  | 98.1% |  | 98.1% |  |  |  |  |
| 10 | Median cost multiple on the claim chips |  | 28× |  | 28× |  |  |  |  |
| 10 | Median speed multiple on the claim chips |  | 6× |  | 6× |  |  |  |  |

Rows 3 use the evidence strata directly, so they have no audit-only variant. The review-rule "hype" row compares like with like: the model figure is the same rule on the model's labels (9.6% for Sonnet), not the review's published hype bucket (11.5%).

## Which claims are more or less supported under Opus

- **1. Comparison baselines.** Review: Fails. With Opus: Holds. More supported: 4 of 4 Opus shares inside their interval, 1 of 4 for Sonnet; on the audit-only estimate 4 of 4 and 4 of 4.
- **2. Production with numbers.** Review: Holds with correction. With Opus: Holds with correction. Less supported: inside only because the interval's top is the bound on zero misses; Opus's count is 4.6x the audit's point estimate of 8, against 1.9x for Sonnet.
- **3. The measurement ladder (was the bucket scheme).** Review: Fails (the bucket scheme, since withdrawn). With Opus: The ladder shares hold. Slightly more supported: 8 of 8 Opus figures inside, 6 of 8 for Sonnet (Sonnet's misses: the chip-rule claim share and the framing-rule hype share).
- **4. Voice, live chat and collaboration.** Review: Holds with correction. With Opus: Holds. More supported: Opus's share is near the centre of the interval; Sonnet's was at its bottom edge.
- **5. A live loop.** Review: Holds. With Opus: Holds. More supported: Opus's non-game share is inside the interval; Sonnet's was outside (on the audit-only estimate both are inside, and Opus's all-posts share is inside while Sonnet's is not).
- **6. Decisions under 300 ms.** Review: Holds. With Opus: Holds; the set's size does not. About the same on the claim: the games share holds under both (Sonnet's 90.8% equals the audit's point, Opus's 87.4% is inside). On the set's size Opus's 14.5% is nearer the audit than Sonnet's 18.6%, and still outside.
- **7. Meta posts.** Review: Fails. With Opus: Holds with correction: the fifth holds on the audit-only estimate; memes and hot takes are under half a percent each. More supported: Opus's share is inside the audit-only interval and just above the same-logic one; Sonnet's is far outside the same-logic interval and inside the audit-only one.
- **8. Attention.** Review: Holds with correction. With Opus: Holds with correction. Unchanged: a census, only the base moves (shares move by 0.5 point at most).
- **9. Jev as a classifier.** Review: Holds. With Opus: Holds. Unchanged.
- **10. The claimed multiples.** Review: Holds. With Opus: Holds. Unchanged medians; without the 1x chips the speed median moves from 8.5x to 8.1x.

In short: Opus's figures are better supported than Sonnet's on baselines, the realtime families, the live loop and meta posts, and nearer the audit on the size of the under-300 ms set. Two stay unsupported: measured production (publish the audited count, not Opus's 37) and the size of the under-300 ms set (14.5% against the audit's 11.0%, 9.5–12.5%). The census claims (8, 9, 10) do not depend on the model.

## Sanity checks

**1. Measured production: Opus's 37 against the audit's re-read.** Opus labels 37 posts measured production (37 in its base). 11 are among Sonnet's 15, which the audit re-read; 26 are posts Sonnet called measured demos. Of the 8 posts that hold on the re-read, Opus labels all 8 measured production. Opus drops 4 of Sonnet's 15, and the re-read rejects all 4 of them too. It keeps 3 that the re-read rejects (a $127,000 hyperbole, a latency measured in dev, a live news feed with no number). Of its other 26, the audit read 9 on first-pass labels: 3 measured production and 6 measured demos. 2 of those 9 fell in the random sample of measured demos, and the audit calls 0 of them production. 17 were never audited. Net: 11 of 20 audited Opus production posts hold (55.0%; weighted 43.1%). The audit's point estimate stays 8 posts (0.14%), at most 2.0%. At least 11 posts are production on the audit's own labels (the 3 beyond the re-read are first-pass labels from other strata, which the estimator does not add). Opus's 37 (0.66%) is 3.4 times the 11 the audit confirms and 4.6 times its point estimate.

**2. The three realtime families: Opus's 206 against the audit's census of 156.** 112 of Opus's 206 are in Sonnet's census, and 94 are outside it (Sonnet had 25 of those as meta, 21 as classification, 15 as moderation). Of the 104 census posts the audit keeps in these families, Opus keeps 100. Of the 52 the audit moves out, Opus still has 12. Of Opus's 94 outside the census, the audit read 41 and puts 25 in these families. In the random negative sample of 200, the audit finds 5 misses and Opus has 3 of them. Overall 125 of 153 audited Opus posts hold (81.7%; weighted 72.7%). The audit estimates 225 posts (4.0% (2.9–6.6%)); Opus's 206 is inside. Opus's extra posts are partly real (the misses Sonnet had) and partly not (12 census posts the audit rejects).

**3. not_a_jev_build: Opus's 349 against the audit's re-label.** 349 on the whole feed is 347 after merging duplicates. 209 of them Sonnet also calls not_a_jev_build; those were outside the audit's frame and were never read. The other 138 are in the frame: 71 Sonnet meta, 27 games, the rest spread. The audit read 36 of them and calls 23 not_a_jev_build; 7 more it keeps as meta. In the audit's re-label of 150 Sonnet meta posts (claim 7), it moved 10 to not_a_jev_build; Opus calls all 10 of those not_a_jev_build, and 2 more that the audit keeps as meta. Scaled, the audit puts 80 (44–142) of Sonnet's 1,203 meta posts outside Jev builds; Opus has 71. Across all audited posts, Opus catches 23 of the audit's 32 not_a_jev_build posts, and its own not_a_jev_build label holds on 63.9% (weighted 70.2%). Over the whole frame the evidence samples estimate 75 (25–228) posts the audit would call not_a_jev_build; Opus's 138 is inside that range, above the point. Opus's larger count agrees with the audit's re-label of meta posts; its not_a_jev_build calls on other posts hold about two times in three.

## Limits

- The strata were drawn on Sonnet's labels. For Opus they are a valid stratification, but less efficient: only 112 of Opus's 206 realtime-family posts are in the census, for example. An Opus-drawn sample would give tighter intervals where the two models disagree.
- The "same logic" estimate takes Opus's word on the regions the review did not sample; the "on Opus's word" column sizes that. The audit-only variant avoids it with few posts (for claim 1, 13 + 55 sampled posts fall in the 847-post region), so its intervals are wide.
- 25 model-only posts and 78 proposal and commentary posts enter at Opus's labels.
- Grok is another AI model, not a person. Agreement with it is not correctness; it is agreement with an independent reader using the same rubric.
- Summed Wilson bounds are conservative, and the weighted rates treat the eight samples as independent draws.
- The production re-read covered Sonnet's 15 posts. 17 of Opus's 37 were never audited.

## Files

- `review/estimate-opus.py`: the estimation (run: `python3 review/estimate-opus.py --model data/classified-opus.jsonl`).
- `review/work/estimate-opus.json`: every number, for Sonnet (`sonnet`), Opus on its own base (`model`) and on the frame (`model_frame_base`).
- `review/data/audit-opus-agreement.csv`: agreement and kappa per field, raw and weighted, both models.
- `review/data/audit-opus-agreement-strata.csv`: agreement per Sonnet-defined stratum, both models.
- `review/data/audit-opus-recount.csv` and `audit-opus-recount-groups.csv`: the recount by each model's own label.
- `review/data/audit-opus-estimates.csv`: the side-by-side table, with the audit-only and frame-base columns.
- `review/data/audit-opus-claims.csv`: one row per claim, with both verdicts.
- `review/data/audit-opus-sanity.csv`: the three sanity checks.
