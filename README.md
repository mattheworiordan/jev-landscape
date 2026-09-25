# A week of Jev, sorted

What people did with Jev, TypeSafe AI's decision model, in its first week: every post from the week, sorted and audited; the usage the two public gateways show; and the rivals that turned up. This repository holds the report, the labels, the tables, the data read at source and the code that rebuilds all of it. The piece: https://blog.mattheworiordan.com/p/jev-is-built-for-tinkerers

**The report: https://mattheworiordan.github.io/jev-landscape/** · The first edition, with every chart: https://mattheworiordan.github.io/jev-landscape/technical/

By [Matthew O'Riordan](https://www.linkedin.com/in/mattoriordan/). Disclosure: the author is CEO of [Ably](https://ably.com), a realtime infrastructure company.

## What the data says

- Jev is being called at scale, and the money is small. On 23 September it was a quarter of all requests on Vercel's AI Gateway and 2% of its tokens; on OpenRouter it served more requests that week than the busiest chat model, for an eighth of the spend. TypeSafe publishes no usage number, and 96% of the gateway volume is anonymous.
- The buzz is about using it, not about what it makes possible. About four in five posts compared Jev with nothing, and none of the 91 most promising builds did something that was unavailable before.
- TypeSafe announced 40 to 400x cheaper. The posts claimed 28x. Measured against the small models people would actually use, the median of the published head-to-heads is about 7x on cost and 5x on latency, often with better accuracy.
- Twenty rivals appeared within a week, mostly built by one person in days on open weights. None matches Jev's mix of cost, speed and accuracy yet, and no big provider has shipped a decision endpoint.

Every number on the report links to its source or to a table in this repository. Where a blind audit checked a number, the report gives the audit's range, not a model's count.

## Method in six lines

1. **Source.** Every card in OpenChamber's Jev feed ([jev.openchamber.dev](https://jev.openchamber.dev)) posted from 2026-09-16 to 2026-09-23 (UTC): 5,950 X posts from 4,593 authors, feed snapshot of 2026-09-23 18:47 UTC.
2. **Labels.** A model labeled every post against a written rubric ([report/rubric.md](report/rubric.md)): what Jev decides, how fast the decision must be, the evidence, the baseline, whether it sits in a live loop, and whether it is in production. The report uses the Claude Opus 5.5 labels (`data/classified-opus.jsonl`).
3. **Second pass.** A critical review of the first labels tightened the rubric (v1 to v2), and every post was labeled again. Duplicates were merged and 347 posts that are not Jev builds were set aside, which leaves 5,595 use-case posts.
4. **Audit.** Grok labeled 1,681 posts blind: every post in the rare groups, and seeded samples of the rest. The report gives the audit's estimates with 95% Wilson intervals ([review/critical-review-grok.md](review/critical-review-grok.md)). It sampled the Claude Sonnet 5 labels (`data/classified-sonnet-v2.jsonl`), and the page says so where it uses the Claude Opus 5.5 labels. The author hand-checked 13 posts, enough to catch problems, not a human audit.
5. **The gateways and the rivals.** OpenRouter's model page and rankings, Vercel's open leaderboard export, npm, pypistats, Discord, Hugging Face and JevBench were read at source on 24 September 2026. The files in `data/gateway-*.json` and `data/rivals-*.json` record what was read, where and when.
6. **The head-to-heads.** Every comparison found where someone put Jev against another model on the same task and published cost, latency or accuracy, including the author's own Jev Pong runs. They are listed with links in `report/site/scripts/page-v3.mjs` and on the report; each figure is the author's own, unreproduced.

Jev also chose a family for every post. That gives the agreement and calibration numbers in figure 9 of the technical page.

## What is in this repository

| Path | What it is |
|---|---|
| `index.html`, `charts/` | The report and its own charts. Each chart is an SVG in light, dark and adaptive versions, with phone-width versions in `charts/narrow/` and 1600-pixel PNGs in `charts/png/`. GitHub Pages serves the report from the root of `main`. |
| `technical/` | The first edition of the page, with every chart from the full analysis, including the ones the report leaves out. |
| `data/classified-*.jsonl` | The labels, one line per post, keyed by X post id. The table below lists each file. |
| `data/gateway-openrouter-2026-09-24.json`, `data/gateway-vercel-2026-09-24.json`, `data/gateway-prices-2026-09-24.json` | Jev's requests, tokens and billed usage a day on OpenRouter, its share of Vercel AI Gateway requests and tokens a day (from Vercel's CC BY 4.0 export), and the list prices used for the cost comparison. Each file names its source and read time. |
| `data/rivals-2026-09-24.json`, `data/alternatives-posts-2026-09-24.json` | New Hugging Face models named jev or laya a day, the JevBench axes, and the posts in the feed that show a model, port or endpoint that is not Jev (ids and links only). |
| `data/usage-*.jsonl`, `data/*.errors.jsonl`, `data/pilot/` | Tokens, cost and latency per call, the posts that failed or were refused, and the pilot runs. |
| `data/hand-labels-120.jsonl`, `data/hand-labels-disputes.jsonl`, `data/dedupe-groups.jsonl` | A 120-post check by a review agent, its re-reads of disputed posts, and the duplicate groups. |
| `review/` | The independent audit: its labels (`hand-labels-grok.jsonl`, `labels/`), its sampling (`work/strata.json`), its scripts, its instructions and its report. `human-labels.jsonl` holds the author's own blind labels. |
| `report/data/*.csv`, `report/summary.json` | Every table behind both pages. |
| `report/rubric.md`, `report/rubric-noise.md`, `report/rubric-v1.md` | The rubrics that the models labeled against. |
| `report/v1/` | The first pass and the withdrawn bucket tables, kept for the record. |
| `report/v2/` | The tables on the Claude Sonnet 5 v2 labels, which the audit sampled, kept for the record. |
| `data/withdrawn-tables/` | Tables that the page no longer uses, kept for the record. |
| `review/data/` | The audit's tables for each label file, from the audit's scripts. |
| `scripts/`, `report/site/scripts/` | The pipeline: pull the feed, label, analyze, draw the first edition (`charts.mjs`), draw the report (`page-v3.mjs`, with `lib.mjs`). |
| `manifest.json` | The feed snapshot (time, card count, hashes of the raw pulls) and the text fields that were emptied. |
| `publish/` | How this repository was made: the file list, the text filter and the leak check ([publish/PUBLISHING.md](publish/PUBLISHING.md)). |

The label files:

| File | Posts | Fields |
|---|---|---|
| `data/classified-jev.jsonl` | 5,950 | Jev (`typesafe-ai/jev`): its family, its stated probability for each family, latency: `id`, `family`, `prob`, `latency_ms`, `input_tokens`, `probs`, `at` |
| `data/classified-noise.jsonl` | 1,533 | Claude Sonnet 5: sub-type and stance of the noise posts (rubric-noise.md): `id`, `subtype`, `stance`, `reason` (empty) |
| `data/classified-opus.jsonl` | 5,949 | Claude Opus 5.5, rubric v2: `id`, `family`, `tier`, `evidence`, `framing`, `baseline`, `realtime_infra`, `production_claim`, `reason` (empty) |
| `data/classified-sonnet-v2.jsonl` | 5,950 | Claude Sonnet 5, rubric v2 (the labels the audit sampled): `id`, `family`, `tier`, `evidence`, `framing`, `baseline`, `realtime_infra`, `production_claim`, `reason` (empty) |
| `data/classified-sonnet.jsonl` | 5,782 | Claude Sonnet 5, rubric v1 (the first pass): `id`, `family`, `tier`, `evidence`, `framing`, `baseline`, `realtime_infra`, `production_claim`, `reason` (empty) |

## What is not in this repository

The text of the posts. OpenChamber's feed holds the full text of every post, a one-line title that the feed writes, the author's name and links to media. The feed belongs to OpenChamber, and X's terms restrict bulk copies of post text. So this repository has post ids and labels, and every text field in the data files is empty: `reason`, `note`, `title` and `text`. Each file keeps its fields, so every script still runs.

To read a post, open `https://x.com/i/status/<id>`. To get the text for every post, fetch the feed (step 1 below).

The pages quote a few feed titles, each with a link to its post, and the rubrics and prompts use a few titles as examples. `publish/check_leaks.py` checks every other file for post text and titles.

## Reproduce

You need Python 3.11 or later with pandas and numpy, Node.js 18 or later and pnpm. Step 2 also needs a [Vercel AI Gateway](https://vercel.com/ai-gateway) API key.

1. Fetch the feed and build `data/cards.json`:

   ```sh
   curl -fsS -o feed.json https://jev.openchamber.dev/data/cards.json
   python3 scripts/build_cards.py add feed.json
   python3 scripts/build_cards.py build --through 2026-09-23
   ```

2. Label every post with your own Gateway key. The full run cost $8.39 with Claude Sonnet 5, $29.26 with Claude Opus 5.5 and $0.33 for Jev's own labels.

   ```sh
   pnpm install
   echo 'AI_GATEWAY_API_KEY=<your key>' > .env.local
   pnpm dlx tsx --env-file=.env.local scripts/classify-model.ts --out data/classified-mine.jsonl --usage data/usage-mine.jsonl
   ```

   The default model is Claude Sonnet 5. For another model, add `--model <gateway id>`, for example `--model anthropic/claude-opus-5.5`.

3. Rebuild the tables in `report/data/` and `report/summary.json`. Give the name of the model that made your labels:

   ```sh
   python3 scripts/analyze.py --labels data/classified-mine.jsonl --labels-model "Claude Sonnet 5"
   ```

4. Rebuild the first edition and its charts, then the report:

   ```sh
   node report/site/scripts/charts.mjs --labels data/classified-mine.jsonl
   TECHNICAL_URL=technical/ node report/site/scripts/page-v3.mjs
   ```

   `charts.mjs` writes `report/site/index.html` and `report/site/charts/` (published under `technical/`). `page-v3.mjs` writes `report/site/v3/index.html` and `report/site/v3/charts/` (published at the root). It reads the gateway, price and rivals files in `data/` as they are; to update those, re-read the sources named in each file.

To check the published numbers without labeling, skip step 2 and use the labels that the pages use:

```sh
python3 scripts/analyze.py --labels data/classified-opus.jsonl --labels-model "Claude Opus 5.5"
node report/site/scripts/charts.mjs --labels data/classified-opus.jsonl
TECHNICAL_URL=technical/ node report/site/scripts/page-v3.mjs
```

With the feed snapshot of 2026-09-23 18:47 UTC, this rebuilds both pages and every published table byte for byte, once `publish/strip_text.py` has emptied the titles again. `publish/check_repro.sh` runs it in a temporary copy and compares each file.

`scripts/refresh.sh` does steps 1 to 4 for the first edition in one command. It labels only the posts that have no labels yet, with Claude Sonnet 5, Jev and the noise rubric. Set `ENV_FILE` to your `.env.local` first.

**What will not match.** The feed is live. A later pull has the same posts up to 2026-09-23, but views and likes go up, and the feed drops a few cards between updates. Label counts match closely, and view figures do not. The audit is fixed to the 5,950-card snapshot: if a pull changes the audited groups, `charts.mjs` reports `snapshot_matches = 0` and writes nothing. The gateway figures were read once, on 24 September 2026; OpenRouter and Vercel show different numbers today. `manifest.json` names the two raw pulls of the feed with their SHA-256. They are not published.

**Before you publish a fork.** A run writes feed titles back into `report/data/*.csv`, `report/summary.json` and `data/dedupe-groups.jsonl`. `.gitignore` keeps `data/cards.json` and the other text files out, but not these. Run `publish/stage.sh` to build a text-free copy in `publish/repo/` and check it.

## Corrections

If you think a label or a figure is wrong, open an issue with the post id or the source, the field and your reading of it. The report changes when the data does, and the change is recorded here.

## License

- **Code** (`scripts/`, `review/*.py`, `review/work/*.py`, `review/label-workflow.rhai`, `report/site/scripts/`, `publish/`): MIT, in [LICENSE](LICENSE).
- **Data and method** (the label files in `data/` and `review/`, the gateway, price and rivals files, the CSV files, `report/summary.json`, `manifest.json`, the rubrics and the audit documents): CC BY 4.0, in [LICENSE-DATA](LICENSE-DATA). Credit: Matthew O'Riordan, "A week of Jev, sorted" (2026), https://github.com/mattheworiordan/jev-landscape. The Vercel figures come from Vercel's AI Gateway leaderboard export, CC BY 4.0, credit Vercel.
- **The pages and the charts** (`index.html`, `charts/`, `technical/`): © 2026 Matthew O'Riordan. They are not under either license.
- **The posts** belong to their authors, and the feed belongs to OpenChamber. Neither is in this repository.

Staged 2026-09-25 11:43 UTC from the 2026-09-23 18:47 UTC feed snapshot.
