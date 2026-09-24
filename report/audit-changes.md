# Numbers that changed (report v3, 24 September 2026)

Every number that changed when the independent audit ([review/critical-review-grok.md](../review/critical-review-grok.md)) was integrated and the page moved to the Claude Opus 5.5 labels, with where it appeared, the old value, the value the page and report now use, and the 95% interval. Use it to correct the launch copy (Brain `work/content/drafts/2026-09-jev/copy/launch-copy-2026-09-24.md` and the narrative in `jev-launch-plan-2026-09-24.md`), the findings note and anything already drafted.

- **New** is what `report/site/index.html` and `report/landscape.md` now say. Every audited number comes from `report/data/13_audit_*.csv`. For the Opus labels, `scripts/audit.py` copies those from `review/estimate-opus.py` ([review/audit-opus.md](../review/audit-opus.md)), which repeats the audit's estimators with Opus as the model under test: the audit's 1,681 labels stay the reference, shares are of Opus's own base, and the regions the audit did not sample take Opus's labels (each estimate states how many posts that is). A "samples only" variant takes neither model's word there.
- **Intervals** are 95% Wilson intervals. Where two sampled strata are added, the bounds are summed, which is wider than a joint interval.
- **Where** uses these short names: *page* (`report/site/index.html` and its charts), *report* (`report/landscape.md`), *copy* (the launch copy draft), *plan* (the launch plan narrative), *findings* (Brain `jev-landscape-findings.md`).
- **The base changed.** The page now uses the Claude Opus 5.5 labels (`data/classified-opus.jsonl`): 5,949 of 5,950 posts labelled (its safety filter refused one, which is left out), 7 duplicates merged, 347 posts that do not use Jev left out, so the use-case base is **5,595** (it was 5,709 on the Sonnet v2 labels). Feed updated 23 Sep 18:47 UTC. The copy still quotes the older 10:42 UTC snapshot (5,782 posts from 4,469 authors); those counts are in the last table. The Sonnet version of the whole report is kept in [v2/](v2/).
- **Rule for launch copy:** quote the audited value with its range. Never quote Opus's own production count (37): the audit agrees with only 11 of the 20 Opus production posts it read.

## Headline claims

| # | What | Where it appeared | Old | New | 95% interval | Why |
|---|---|---|---|---|---|---|
| 1 | Builds that did something new ("materially different") | page fig 1 title, lead, short version, chips; report; findings; copy (LinkedIn "1.6% did something that wasn't possible before. Most of that is games."); plan | 1.6% of posts (90 or 91 posts) | None. Of the 91 candidate builds, 0 did something unavailable before at any price. A team would have used an LLM for 64, rules or heuristics for 12, a vendor API for 11 and a classic model for 4 (85 distinct builds). New figure 1c | posts meeting the selection test, misses included: 2.0% (1.2 to 4.6) | audit claim 3, fails. "Most of that is games" was wrong too: 88 of the 91 are outside games |
| 2 | Cost-only: "measured, and a small model, a batch job or an incumbent already did the job" | page fig 1, chips; report; findings; copy (LinkedIn "A quarter is real, measured, and a saving on something a small model or a batch job already did"); plan | 23.3%, a quarter | Withdrawn with the bucket scheme. The description fits 12.5% of posts | 9.7 to 16.6 | audit claim 3, fails |
| 3 | Posts that compare Jev with nothing | page fig 3 title and lead, short version; report; findings; copy (LinkedIn bullet 1, X post 1, seed reply 2); plan | 81.5% (copy, findings); 81.4% (Sonnet labels) | 80% (80.0%); Opus's own 80.4% is inside | 77 to 82 (77.4 to 81.6) | audit claim 1 fails on the Sonnet labels, holds on Opus's (below) |
| 4 | Compare with a frontier LLM | report; findings | 11.9% | 11.3% | 10.5 to 13.1 | claim 1; not sampled, Opus's labels fill it |
| 5 | Compare with a small LLM | report; findings; copy (seed reply 9, "3.0% compared against a small model at all") | 3.0% | 5.0% | 4.2 to 6.9 | claim 1; not sampled, Opus's labels fill it |
| 6 | Compare with the tools Jev would replace (classic ML, rules, vendor API) | page fig 3 title ("fewer than 1 in 20"), lead, short version; report; findings; copy (LinkedIn bullet 1, X post 1, seed reply 2); plan | 3.6% (copy); "fewer than 1 in 20" | 3.7%, about 1 in 30; Opus's own 4.1% is inside | 3.0 to 5.4 | claim 1 |
| 7 | Measured production | page fig 1, fig 4 title, note and lead, short version; report; findings; copy (LinkedIn "Production: at most 1.6%", X post 4 "at most 1.6% ... Re-read by hand, 0.9%", seed replies 3 and 6); plan ("0.9 to 1.6 percent") | at most 1.6%; 0.9% on a re-read | **8 posts, 0.14%, at most 2%.** The audit re-read the 15 posts the Sonnet labels called production and 8 hold. Opus labels those 8 production too, but it labels 37 in all and the audit agrees with only 11 of the 20 it read, so Opus's count is not published | 0.14 to 2.0 | audit claim 2, holds with correction |
| 8 | Which posts are in production | page fig 4 lead; findings; copy (LinkedIn "mostly classification", X post 4, seed reply 6) | mostly classification (from the first re-read of 95) | The 8 that hold: a task router, a deploy approval gate, a news pipeline, a search reranker, an episode recommender, a fleet-wide decision layer and two public Q&A sites (AskJev.ai, AskJev.net). None is a realtime build | n/a | claim 2 |
| 9 | Voice, live chat and collaboration | page fig 7 subtitle and lead; report; findings; copy (X post 5 "2.8% of everything posted", seed reply 5); plan ("2.8 percent, no production") | 2.8%, no production | **4.0%**; Opus's own 3.7% is inside. **None measured in production, two claim it without a number** (a live news feed and a Discord moderation bot, on the audit's own labels) | 2.9 to 6.6 | claim 4, holds |
| 10 | A live loop outside games | page fig 7 title, note and lead; report; findings | 5 to 10 percent (5.3% on the 120-card sample) | about 8% (8.1%); Opus's own 6.7% is inside | 6.0 to 11.4 | claim 5, holds |
| 11 | A live loop, games included | page fig 7; report; findings | about a fifth (22.0%) | about a fifth (22.4%) | samples only 17.1 to 28.4 | claim 5, holds |
| 12 | Posts that need a decision in under 300 ms | copy (X post 5 "19% of Jev posts", seed reply 4 "of the 1,045 posts"); findings (1,045, 18.8%); page fig 6 | 19% (1,045 or 1,064 posts as labelled) | **about 11% (11.0%)**; Opus's own 14.5% is outside the interval | 9.5 to 12.5 (samples only 8.2 to 14.3) | claim 6: the games share holds, the set is smaller |
| 13 | Games, among the under-300 ms posts | page fig 6 title; findings; copy (X post 5, seed reply 4) | 91% | 91% (90.8%) | 82.2 to 95.5 | claim 6, holds |
| 14 | Meta posts: never say what Jev decides, or benchmark or wrap the model | copy note ("a fifth never says what it decides"), LinkedIn ("A fifth never says what Jev actually decides, or is a benchmark or wrapper"); plan; findings; page fig 1b | a fifth (21%) | **about a fifth, 21% (20.9%)**; 20.7% on the audit's samples alone; Opus's own 22.4% | 19.4 to 22.2 (samples only 16.9 to 25.9) | claim 7. The audit's own 14.9% (a fail) counted no meta post outside the Sonnet labels' meta posts; with Opus it holds with correction. A careful human reader gives some of these posts a use (the author gave all 4 that both models call meta one) |
| 15 | Memes and hot takes | copy note ("1 percent each"); plan; findings noise table | about 1% of posts each | under half a percent each: memes 0.29%, hot takes 0.44% | none in the audit | claim 7: "1% each" fails; it was a share of the noise |
| 16 | A claim with no number ("hype") | page fig 1 lead ("one in ten"); report; findings; copy (LinkedIn "A tenth is a claim with no number"); plan | 11.5%, a tenth | **Withdrawn**: it rested on the framing field. Restated from evidence and the claim chips: a cost, speed or accuracy claim with no measurement is **2.5%** of posts. The interim 16% (the audit's framing rule) is withdrawn too | 1.3 to 5.4 | framing withdrawn (below) |
| 17 | Demos with no numbers | page fig 1 lead; report; findings; copy (LinkedIn "A third is a demo with no numbers"); plan | 37.7%, a third | 46.6% (evidence demo_no_numbers, no claim chip, not meta). The interim 34.7% used the framing rule and is withdrawn | 41.8 to 51.6 | claim 3's first clause, restated without framing |
| 18 | Measured nothing / measured a demo (the ladder) | page fig 1 title, subtitle, lead, chips | a third measured a demo (Sonnet labels 33.8%) | no measurement 67%, measured demo 33% (Opus labels: 68.5% and 30.8%) | 63.5 to 70.5; 29.4 to 36.3 | new audited estimates |
| 19 | Share of views on the top 1% of posts | page fig 2; report | 53.4% (58 posts) | 53.3% (56 posts, Opus base); 49.8% without the 9 suspect posts; 47.0% of likes; the top post 7.8% | a census | claim 8, holds; the audit's recount on its own base is 53.4% |
| 20 | Posts that hold half of all views | copy (X post 2 "48 posts"); report | 48 | 47 | a census | base change |
| 21 | Median views per post | copy (X post 2 "139 views"); findings | 139 | 133 | a census | base change |
| 22 | Jev's agreement with the labelling model | page fig 9, short version; report; copy (X post 3, seed replies 8 and 10) | 77% with Sonnet (76.8%) | 78.4% with Opus (kappa 0.75); 98.0% in the surest tenth; 27 of 28 right at 0.99 or more on the 120-card sample; 98.1% (455 of 464) against the audit | a census | claim 9, holds |
| 23 | Claim multiples | page fig 5; report; copy (seed reply 8) | 28× cheaper, 6× faster; without "1×" chips 34× and 8.5× (Sonnet base) or 5.75× and 8.1× (older base) | 28× and 6×; without "1×" chips 34× and 8.1× | a census | claim 10, holds |

## Withdrawn fields

| What | Where it appeared | Old | Now | Why |
|---|---|---|---|---|
| Framing (what a post leads with: cost, latency, accuracy, capability, none) | page fig 8 ("what the framing buys") and its lead, method; report section 4; findings; copy ("half make no claim", capability numbers) | fig 8 and every framing share (for example half of posts make no claim; cost and latency lead 30% of posts and draw 58% of views; capability fell from 39.2% to 9.3% in v2) | No number rests on framing. Fig 8 is now "What measuring buys": views per post by evidence level (measured demos averaged 12,755 views against 5,752 for demos with no numbers; medians 143 and 130). The old chart files are in `data/withdrawn-tables/charts/` | A human calibration showed that one choice misrepresents the many posts that lead with cost and latency together |
| Latency tier at seven levels | page fig 6 heat map and lead; report section 2; findings (tier tables); copy | the family-by-tier heat map and every tier distribution (for example task 29%, interaction 19%; data and telemetry 95% batch) | Only the audited split: under 300 ms about 11% of posts (9.5 to 12.5), 91% of them games. Fig 6 is now a single bar. The tier tables are in `data/withdrawn-tables/` | Tier agrees with the audit on 75% (Opus) and 62% (Sonnet), and the author's own labels disagreed with both models on 8 of 13 posts, 4 of them per-move decisions he calls "turn" |

## Agreement with the audit (1,681 posts)

The page used to cite a 120-card check by one reader, then the audit's agreement with the Sonnet labels. It now leads with Opus's agreement and shows Sonnet's beside it.

| Field | Sonnet v2 (was on the page) | Opus 5.5 (now) |
|---|---|---|
| family | 71% (κ 0.67) | 82% (κ 0.79) |
| tier | 62% | 75% |
| evidence | 89% | 93% |
| baseline | 89% | 94% |
| realtime flag | 86% | 95% |
| production claim | 98% | 98% |

These are the audit's own agreement rates on the 1,681 posts. `review/audit-opus.md` also gives design-weighted rates (Sonnet family 72.3%, baseline 91.5%), which is where a "72 against 82" and "90 against 94" reading comes from.

## Page structure

| What | Old | New |
|---|---|---|
| Fig 1 (waffle) tint and header chips | six buckets | the measurement ladder on Opus's labels: no measurement 3,835, measured demo 1,723, labelled production not confirmed 29, production confirmed 8 |
| Fig 1 title | "Only 91 of the week's 5,709 builds, 1.6%, were materially different" | "About a third of the week's posts measured a demo, and 8 of 5,595 measured production" |
| Fig 1b title | "Unrelated or unclear posts, benchmarks of the model and tooling or wrappers make up 89% of the noise" | "About a fifth of posts are meta, and memes and hot takes are under half a percent each" |
| Fig 1c | none | "Of the 91 most promising builds, none did something that was unavailable before" |
| Fig 3 title | "Four in five posts compared Jev with nothing, and fewer than 1 in 20 with what it would replace" | "About four in five posts compared Jev with nothing, and about 1 in 30 with what it would replace" (bars: Opus's labels; markers: the audit) |
| Fig 4 | "Two thirds of builds showed no numbers, and 15 of 5,709 reported them from production" | "Two thirds of builds showed no numbers, and 8 of 5,595 measured production on a blind re-read"; the call-out gives only the audit's 8 |
| Fig 6 | family-by-tier heat map, "Nine in ten posts that need a decision in under 300 ms are games" | a single audited bar: "About 11 percent of posts need a decision in under 300 ms, and about 9 in 10 of those are games" |
| Fig 7 | "Outside games, realtime builds were demos: 2 of 720 reported numbers from production" | "Outside games, about 8 percent of posts have a live loop, and none of them is in production" (Opus flags 376 posts) |
| Fig 8 | "what the framing buys" | "Measured demos averaged twice the views of demos with no numbers, but the typical post gained little" (file `08-what-measuring-buys`) |
| Intro | three passes | four passes: Sonnet, the critical review and Sonnet again, the audit, then Opus |
| Audit section | Sonnet agreement and the ten verdicts | also: the Opus rerun, a Sonnet/Opus agreement table, "The numbers this page uses" (audited, samples only, Opus labels, the audit on Sonnet), the verdicts on Opus, and the note that two fails were an artefact of the estimator |
| Method | Sonnet as the labelling model | Opus with adaptive thinking; Sonnet as the first passes; both sampled at the Gateway default (it ignores temperature); the refused post; "Two labels I dropped"; the public repo link (github.com/mattheworiordan/jev-landscape) |

## Two of the audit's fails were an artefact

The audit's claims 1 (81.5% compare with nothing) and 7 (a fifth are meta) failed because its estimator took the posts outside its sampled strata as correctly labelled. Estimated from its own random samples instead, the Sonnet labels' 81.4% with no comparison and 21.1% meta posts sit inside the intervals (76.9 to 84.9, and 16.1 to 25.2). That is why every figure is now published as a range. With Opus as the model under test, claim 1 holds and claim 7 holds with correction (`review/audit-opus.md`).

## Counts from the refresh and the Opus labels (not the audit)

| What | Where it appeared | Old | New |
|---|---|---|---|
| Posts and authors | copy (LinkedIn, X post 1, post 3, seed replies, Temporal email, team ask); plan; findings | 5,782 posts from 4,469 people | 5,950 posts from 4,593 authors |
| Use-case base | page, report, findings | 5,709 (Sonnet v2; 234 not Jev) | 5,595 (Opus; 347 not Jev, 1 refused) |
| Opus labelling cost | page method, report method | n/a | $27.98 (Gateway-reported, 169 calls) |
| Noise posts (other_or_meta or commentary) | page fig 1b | 1,206 | 1,265 (326 not yet sub-typed: the sub-types come from a Sonnet pass over the Sonnet noise; `scripts/refresh.sh` fills them with the Gateway) |
| Posts flagged realtime | page fig 7 | 1,738 (30.4% of the Sonnet base), 720 outside games | 1,152 (20.6%), 376 outside games |
| Japanese posts | page fig 10 | 19.7% | 19.6% |
| Posting peak | page fig 10 | 1,047 posts on 19 Sep | 1,027 |

## Notes on this pass

- Two values differ from the coordinator's brief: the page prints the audited point estimates for the realtime families (4.0%, not Opus's own 3.7%) and the live loop outside games (8.1%, not Opus's own 6.7%), with the audit's intervals (2.9 to 6.6, 6.0 to 11.4), because every other audited figure on the page is the audit's point estimate. Opus's own shares are named as inside the intervals. The games share of the under-300 ms set prints as 82 to 95, since 95.47 rounds to 95.
- `scripts/audit.py` reruns `review/estimate-opus.py` (half a second, deterministic) on every analysis run with non-Sonnet labels, checks that its agreement and the labels' own shares match the analysis, and stops if they do not. With the Sonnet labels it still reproduces `review/estimate.py` exactly.
- Report section 12 said Jev agrees with the v1 labels on 75.0%; on the 5,782 cards v1 labelled it is 77.2% (fixed earlier in this pass).
