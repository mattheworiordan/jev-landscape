# Critical review: the Jev launch-week claims

Reviewer: Grok. Population: the deduped use-case base, 5,709 posts (7 duplicate ids dropped, 234 `not_a_jev_build` left out). Seed `20260924`, `random.Random.sample` on sorted ids, in the order in `review/sample.py`. Labels: `review/hand-labels-grok.jsonl` (1,681 cards). Estimates: `review/estimate.py`. Rule arithmetic: `review/arithmetic.py`. Substance of the 91: `review/work/substance.py`.

Intervals are 95% Wilson intervals. Where two sampled strata are added, the bounds are the sum of the stratum bounds, which is wider than a joint interval. The 15 `measured_production` cards were re-read here and those labels override the batch labels.

## Sampling

| Stratum | Population | Reviewed |
|---|---:|---:|
| measured_production | 15 | 15 |
| material + material_vs_frontier | 91 | 91 |
| voice, live chat, collaboration | 156 | 156 |
| classic ML, rules, or vendor baseline | 201 | 201 |
| baseline = none | 4,647 | 300 |
| demo_no_numbers | 3,681 | 200 |
| measured_demo | 1,928 | 200 |
| not a realtime family, not games | 4,475 | 200 |
| realtime_infra false | 3,971 | 200 |
| realtime_infra true, not games | 720 | 100 |
| other_or_meta | 1,203 | 150 |
| tier in {frame, feel, turn} | 1,064 | 150 |

Exhaustive strata are 422 unique cards. With the samples, 1,681 unique cards, in 43 batches. The corrected bucket on the v2 labels is noise 1,206, hype 655, demo 2,154, cost_only 1,329, fast_loop 274, material 77, material_vs_frontier 14. `scripts/buckets-reviewed.py` still points at `classified-sonnet.jsonl` (v1). The counts above are the v2 recompute.

## Agreement with the model, by stratum

Rates are percent agreement. Columns: family, tier, evidence, framing, baseline, realtime_infra, production_claim.

| Stratum | n | fam | tier | evi | fra | base | rt | prod |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| measured_production | 15 | 67 | 40 | 53 | 80 | 80 | 93 | 67 |
| material | 91 | 59 | 69 | 79 | 79 | 92 | 68 | 97 |
| realtime families | 156 | 58 | 58 | 92 | 76 | 97 | 81 | 99 |
| replacement baseline | 201 | 72 | 59 | 89 | 70 | 62 | 90 | 98 |
| baseline none | 300 | 75 | 64 | 89 | 79 | 95 | 89 | 100 |
| demo_no_numbers | 200 | 75 | 58 | 89 | 80 | 94 | 87 | 98 |
| measured_demo | 200 | 73 | 64 | 88 | 74 | 86 | 88 | 98 |
| not realtime family, not games | 200 | 69 | 64 | 90 | 75 | 90 | 88 | 98 |
| realtime_infra false | 200 | 63 | 64 | 92 | 72 | 90 | 98 | 96 |
| realtime_infra true, not games | 100 | 71 | 62 | 92 | 70 | 92 | 55 | 97 |
| other_or_meta | 150 | 71 | 80 | 85 | 81 | 94 | 97 | 99 |
| tier under 300 ms | 150 | 91 | 49 | 97 | 78 | 94 | 76 | 99 |
| all labelled | 1,681 | 71 | 62 | 89 | 76 | 89 | 86 | 98 |

Family agreement is weakest on the realtime families (58%) and the material set (59%). The replacement-baseline field agrees on 62% of that stratum: 50 of the 201 are no comparison. Tier agreement on the under-300 ms sample is 49%. Evidence and production_claim are the stable fields, except on the 15 production cards (evidence 53%, production_claim 67%).

## The ten claims

**1. Baselines: 81.5% none, 11.9% frontier, 3.0% small, 3.6% the thing Jev would replace. Fails.**

The table, before any re-label, is 81.4% none (4,647), 12.1% frontier (690), 3.0% small (171), 3.5% replacement (201 = 77 classic + 94 rules + 30 vendor). The prose 81.5 / 11.9 / 3.6 does not match that table.

Re-label, keeping the unsampled frontier and small counts and adding what the none sample and the replacement census move:

| Baseline | Corrected | 95% interval |
|---|---:|---:|
| none | 78.2% | 75.7–79.8 |
| frontier LLM | 13.5% | 12.8–15.3 |
| small LLM | 4.8% | 3.9–6.7 |
| classic, rules, or vendor | 3.5% | 2.8–5.2 |

81.5% with no comparison is outside the interval. Of the 300 model-none cards, 15 name a comparison (5 frontier, 6 small, 2 rules, 2 classic). Of the 201 replacement cards, 50 are no comparison, 9 are a small LLM and 5 are a frontier LLM; 137 stay in the replacement group. The 3.6% replacement share holds (3.5%, 2.8–5.2). The frontier and small intervals assume every unsampled card in those strata is correctly labelled. Cards from those strata that happened to be labelled elsewhere agreed 115/151 (frontier) and 27/40 (small). That slice is not a random sample of either stratum.

**2. Production with numbers: at most 1.6%; 0.9% on a re-read; strict label 0.3%. Holds with correction.**

Corrected strict count: **8 / 5,709 = 0.14%**. No missed `measured_production` in the 200 demo-no-numbers cards or the 200 measured-demo cards. The conservative interval is **0.14–2.0%**. The top of that interval is the Wilson upper bound on a zero count in two large strata, not a pile of found cases.

Eight of the 15 strict cards survive a re-read: the task router, the deploy gate, the episode recommender, the Portuguese news pipeline, the Korean search reranker, the fleet note that states production and 250 ms, and the two public AskJev sites with visitor or question counts. The other seven are a labelled test, a test on "real production data", a workflow that was tested rather than shipped, a Flash replacement that is not stated as shipped, a latency measured in dev, a live news feed with no number in the text, and a "$127,000 in 11 hours" line that is hyperbole.

v1's 95 `measured_production` rows are 95/5,782 = 1.64%. The 51/5,782 = 0.88% re-read was not repeated here. The strict model rate 15/5,709 = 0.26% is a true description of the model. It is not the re-read rate.

**3. About 38% demos with no numbers; about 12% hype; about 23% cost-only; 1.6% (90 posts) materially different, 87 outside games. Fails.**

| Clause | Published | Corrected | 95% interval | Verdict |
|---|---:|---:|---:|---|
| Demos with no numbers | 37.7% | 34.7% under the published rule; 35.7% for other unmeasured cards | 29.7–40.3; 30.6–41.3 | holds |
| Cost, speed or accuracy claim, no number | 11.5% | 16.1% | 11.9–21.5 | holds with correction |
| Measured, and a batch or an incumbent already did it | 23.3% | 12.5% | 9.8–16.6 | fails |
| Materially different | 1.6% (91 in the table, 90 in the prose) | 38 of those 91 still meet the rule, 0.67%; with misses, 2.0% | 1.2–4.6 | fails |

The published "hype" rule also counts any named baseline. Restricted to a cost, speed or accuracy lead with no number, the re-label is 16.1% (11.9–21.5). "About 12%" is the bottom of that interval.

The 23% figure is the residual measured bin in the code (1,329 posts). On the model's own labels, 831 of those 1,329 have baseline none. The words "a small model, a batch job or an incumbent already did the job" fit 10.2% of posts on the model labels and 12.5% (9.8–16.6) after the re-label.

Of the 91 materially-different cards, 38 still fall in `material` or `material_vs_frontier` on these labels (32 and 6). Thirty-six are outside games. The other 53 move to cost_only (26), fast_loop (10), hype (9), demo (7) or noise (1). Misses outside that set: 6/192 measured demos and 1/200 unmeasured demos. Scaled, the combined estimate is 2.0% (1.2–4.6), about 114 posts. That interval includes 1.6%. The count "90 posts, 87 outside games" does not survive the census of those posts.

**4. Voice, live chat and collaboration are 2.8% of posts and none is in production. Holds with correction.**

Corrected share **3.8% (2.7–6.3)**. 104 of the 156 stay in those three families. The negative sample (not those families, not games) has 5 misses in 200, which scales to about 112 further posts. 2.8% sits at the bottom of the interval. Measured production inside the 156: 0. Production claims inside the 156: 0. One card in the negative sample says a Discord mod bot was "launched" and offers to add it to servers. That is not a statement that it serves users, and the 100× figure is a round multiple. It is not counted as production.

**5. About a fifth of posts involve a live loop; 5 to 10 percent outside games. Holds.**

Outside games: **7.8% (5.8–11.1)**. The point is inside 5 to 10. The top of the interval is 11.1. The model's 12.6% outside games does not hold: 51 of 100 model-true non-game cards stay true and non-game, and 4 of 200 model-false cards flip to a non-game live loop.

All posts: the model says 30.4%. Keeping the model's 1,018 realtime games and adding the non-game estimate gives 26%. In the under-300 ms sample, 100 of 136 games are a live loop on this read. Applied to all 1,078 games, that is about 790 games plus the 447 non-game estimate, 21.7% of posts. That is the "about a fifth".

**6. Of posts that need a decision in under 300 ms, about 91% are games. Holds.**

The model counts 1,064 such posts (frame 13, feel 979, turn 72), of which 966 are games (90.8%). The prose "1,045" and "948" does not match that table. On the re-label, 76 of the 150 sampled cards still have a budget under 300 ms, and 69 of those 76 are games: **90.8% (82.2–95.5)**. The set is smaller than the model says. 76/150 scaled to 1,064 is about 539 posts, 9.4% of all posts (8.0–10.9). The games share of that smaller set is still about 91%.

**7. A fifth of posts never say what Jev decides, or are benchmarks or wrappers; memes and hot takes are about 1% each. Fails.**

`other_or_meta` is 1,203 / 5,709 = 21.1% on the model. On the re-label, 106 of 150 stay there: **14.9% of posts (13.3–16.3)**. Forty-four move to a real family, most often classification (14) or `not_a_jev_build` (10).

Unrelated, benchmark, or wrapper, among those 150: 41 + 28 + 19 = 88, which is **12.4% of posts**. Memes: 2/150, **0.28% of posts**. Hot takes: 3/150, **0.42% of posts**. The model's own counts are 14 memes and 14 hot takes, 0.25% of posts each. One percent of posts would be about 57. The 1.2% figures in the noise table are shares of the noise bucket, not of posts.

**8. Half of all views sit on 1% of posts. Holds with correction.**

The top 1% is 58 posts and holds **53.4%** of views. Half of views sit on 49 posts (0.86% of posts). Nine posts have at least 100,000 views and a like rate under 0.2%; together they are 12.3% of views. Drop them and the top 1% holds **49.6%**. The top 1% of posts holds 47.5% of likes. One card (3,491,422 views, 1,963 likes, like rate 0.056%) is 7.7% of all views by itself.

**9. Jev agreed with the model on 77% of cards, and was right 27 of 28 times at probability 0.99 or higher. Holds.**

Jev matches Sonnet v2's family on 4,561 / 5,943 = **76.7%**, with `not_a_jev_build` counted as `other_or_meta`. At stated probability ≥ 0.99, Jev matches Sonnet on 1,611 / 1,653 = 97.5%. Against the earlier 120-card file, Jev's family matches that file on **27 of the 28** cards at ≥ 0.99. Nine of those 28 are in this label set; Jev matches these labels on all 9. Across the 464 cards in this set where Jev's probability is ≥ 0.99, the family matches on 455 (98.1%).

**10. The median claim is about 28× cheaper and 6× faster. Holds.**

On the use-case base, 126 cost chips have median **28×** and 299 speed chips have median **6×**. Eight cost chips and 52 speed chips read 1×. Without those, the medians are 34× and 8.5×. The values are spread out (cost mode is not a single launch number; the most common cost chip is 1×, then 100×, 200× and 10×). This is a median of extractor chips, which the rubric says can be the baseline's number or a launch figure.

## Substance of the 91

Read from title and text. What a team would have used before Jev:

| Prior method | Posts |
|---|---:|
| An LLM | 64 |
| Rules or heuristics | 12 |
| A vendor API | 11 |
| A classic model | 4 |
| Unavailable at any price | 0 |

All 91 are cheaper or faster versions of an existing job. Six are a second post about the same build (85 distinct builds). The largest jobs are feed or comment filters (22), voice commands (13) and typing or form fill (13). Sponsor skipping, comment moderation, voice endpointing, notification muting and form autofill already have a vendor or a ruleset. The rest are classifications, routes, guards and trading decisions an LLM or a small classifier already did, at higher latency or higher cost.

## Are the corrected rules fair?

Splitting frame and feel into `fast_loop` is a fair latency point: a 200–400 ms model is outside a sub-100 ms budget, and those cards are mostly games. The deviation paragraph is right that the pre-registered tests place only a quarter of the cards, so the scheme was finished after the data.

Two published shares move by more than two points under a rule that matches the sentences in the claim.

Hype, if it requires a cost, speed or accuracy lead and ignores a named baseline on its own: 185 of the 655 hype cards have framing `capability` (111) or `none` (74). Hype falls from 11.5% to **8.2%**. Demo rises from 37.7% to **41.0%**.

Cost-only, if it means a measured batch or a comparison with a small LLM, a vendor, rules or classic ML: **10.2%**, not 23.3%. The other 13.0% of posts are measured and fit neither description (`measured_other` in `review/arithmetic.py`). The material test itself does not move under that change (still 1.35% + 0.25%).

## What a hostile reader would lead with

1. The "materially different" posts did not do something that was unavailable before. Zero of the 91. Sixty-four are jobs an LLM already did. The census of the bucket keeps 38, not 90.
2. "Cost-only, 23%, a small model or a batch or an incumbent already did the job" describes 10–12% of posts. The 23% bin is where every other measured card went, and 831 of the 1,329 have no comparison.
3. A fifth of posts are not "no decision, or a benchmark, or a wrapper", and memes and hot takes are not 1% of posts. The re-label puts still-meta at 14.9% and the vague-or-benchmark-or-wrapper group at 12.4%. Memes are 0.25–0.28% of posts. Hot takes are 0.25–0.42%.

## What this review could not check

The frontier stratum (690) and the small-LLM stratum (171) were not in the sample design. Their false-positive rate is only the opportunistic slice above. The v1 re-read that produced 51 of 95 production cards was not repeated. Games were excluded from the negative sample for the three realtime families. Proposal and commentary cards (85) were left on the model bucket in the bucket scaling. Post text is cut at 400 characters, and a chip can invent a number. Of 1,023 cards labelled demo-no-numbers, 48 still have a numeric chip. Some of those chips are rightly ignored (launch ranges, hyperbole, a single decision's probability). The overlap with the earlier 120-card file is 32 cards, not 120. Family agrees on 27/32 (84%), tier 23/32 (72%), evidence 30/32 (94%), framing 20/32 (62%), baseline 25/32 (78%), realtime 30/32 (94%), production 32/32.
