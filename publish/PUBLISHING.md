# Publishing: what is in the public repository, and why

The public repository has the labels, the tables, the code and the page. It does not have the text of any post. This file records the decision, the rules that apply it, and the checks. `publish/stage.sh` applies the rules and runs the checks every time it builds the tree.

## The decision

The source is OpenChamber's Jev feed (`https://jev.openchamber.dev/data/cards.json`). For each post, the feed holds the full text of the X post, a one-line title that the feed writes, the author's handle and name, an avatar, media links, views, likes and claim chips. OpenChamber collected it, and it is their dataset. We do not redistribute the text of some 6,000 posts in bulk without their consent. X's developer terms also restrict bulk datasets of post text, and they allow datasets of post ids.

So the repository publishes what we made, keyed by post id:

- every model's labels (`data/classified-*.jsonl`), the pilot runs, and the call logs (tokens, cost, latency, failures)
- the hand checks and the independent audit: the review agent's 120 labels and re-reads, the auditor's 1,681 labels, its sampling and its scripts, and the author's own blind labels (`review/human-labels.jsonl`)
- every table behind the page (`report/data/*.csv`, `report/summary.json`), and for the record the first pass (`report/v1/`), the tables on the Sonnet v2 labels that the audit sampled (`report/v2/`) and the withdrawn tables (`data/withdrawn-tables/`)
- the rubrics, the prompts and the audit documents
- all the code
- the report and its charts at the root of the repository (`index.html`, `charts/`), so that GitHub Pages serves it from the root of `main`, and the first edition of the page with every chart under `technical/`
- the data read at source on 24 September 2026 for the report: the two gateways (`data/gateway-openrouter-2026-09-24.json`, `data/gateway-vercel-2026-09-24.json`, the latter from Vercel's CC BY 4.0 export), list prices (`data/gateway-prices-2026-09-24.json`) and the rivals (`data/rivals-2026-09-24.json`, `data/alternatives-posts-2026-09-24.json`, ids and links only)
- `manifest.json`: the feed snapshot time, the card count, the SHA-256 of the two raw pulls, and every text field that was emptied

Anyone can get the text again from the feed (README.md, step 1), or open a post at `https://x.com/i/status/<id>`.

## What stays out, and why

| Path | Why it stays out |
|---|---|
| `data/cards.json` | The feed working set: full post text, titles, names, media. `scripts/build_cards.py` builds it from the feed. |
| `data/snapshots/` | The raw pulls of the feed, as they came. `manifest.json` names them with their SHA-256. |
| `data/*.log`, `data/refresh-logs/` | Run logs. The refresh logs print titles of new posts. |
| `review/blind/` | The auditor's input batches: the text of 1,681 posts. |
| `review/fxtwitter-150.json`, `review/human-sample-150.json` | The 150 posts for the human check, with full text. |
| `review/labeller.html` | The labeling page. It embeds the text of the same 150 posts. `scripts/human-sample.py` builds it again from the feed. We do not ship a text-free copy, because a labeler with no text has nothing to label. `review/human-sample-150-strata.json` (ids and strata) and `review/human-labels.jsonl` (the labels) are in the repository. |
| `review/work/material-cards-*.jsonl`, `review/work/production-cards.jsonl` | Post text that the audit read for the substance test and the production census. |
| `report/landscape.md`, `report/v1/landscape.md`, `report/v2/landscape.md` | The long tables with the method. They quote about 70 titles as links. `scripts/analyze.py` writes the current one again from the feed. |
| `report/human-labels-120.csv`, `report/human-labels-README.md` | An unused 120-post labeling sheet with the post text in it. The labeler replaced it. |
| `report/site/index.html`, `report/site/charts/` | Not left out: they are published under `technical/`. |
| `report/site/v3/` | Not left out: the report, published at the root as `index.html` and `charts/`, rebuilt by `stage.sh` with its published links. |
| `report/site/video/` | Screen recordings of the page for social posts. The page does not use them, and they are about 40 MB. |
| `data/snapshots-after-audit/` | A later pull of the feed (24 September), with full post text. Its 239 later posts are labelled in `data/labels-after-audit/` (shipped, text emptied) and left out of the analysis because the audit predates them. |
| `report/site/summary/`, `report/site/jev-week-sorted.pdf`, `report/site/assets/` | The internal team brief, the PDF of the first edition and an image for the brief. Internal review material, not part of the record. |
| `data/withdrawn-tables/charts/` | The chart of a withdrawn table. Its tables are in the repository; a picture of a withdrawn claim is not, so that nobody shares it as a finding. |
| `publish/publish.sh`, `publish/SUBSTACK.md` | The author's release tools: the `gh` commands for this account and the notes for the Substack post. |
| `node_modules/`, `__pycache__/`, `.ruff_cache/`, `.DS_Store` | Local tools and caches. |

`.gitignore` in the repository lists the same files, so that a run of the pipeline in a clone does not add them.

## How the text comes out of the data files

`publish/strip_text.py` reads every JSONL, JSON and CSV file before it goes in the tree.

- In a JSONL file or a CSV table, each row is one post. Every free-text field is emptied: `t`, `x`, `text`, `title`, `titles`, `reason`, `note`, and any column that ends in `title`, `reason` or `note`. A labeler's `reason` or `note` is one line about one post, and it often repeats the post's words: the reasons in the Sonnet v2 label file repeat 24 characters or more of 954 feed titles.
- A JSON file is a document (`report/summary.json`, the audit's estimates). Only `t`, `x`, `text`, `title` and `titles` are emptied. Its notes describe the method, so they stay.
- Numbers and booleans are never emptied.
- The key or column stays with an empty value. `scripts/analyze.py` selects `reason` from the label file, so a file without the key stops the analysis. With `--drop`, `strip_text.py` removes the key instead.
- One value stays as a fixed marker. A labeler's note that starts "NOT a Jev", "NOT Jev" or "built WITHOUT Jev" keeps only those words, because `scripts/hand_agreement.py` reads them to mark a post `not_a_jev_build`. Seven of the 120 hand labels carry the marker.
- Everything else is copied as it is: ids, labels, probabilities, latencies, token counts, timestamps, post URLs and handles in the tables, and error messages.

The label files then carry only the id, the labels and Jev's numbers (probability per family, latency, tokens). `reason` is present and empty.

## Code: one change in the copy

Four audit scripts (`review/arithmetic.py`, `review/estimate.py`, `review/sample.py`, `review/work/substance.py`) set `ROOT` to the author's project folder. `stage.sh` changes that line in the published copy to `Path(__file__).resolve().parents[N]`, which is the same folder on the author's machine and the clone folder anywhere else. It is the only change to any published code. Other local paths stay as they are: they are in comments, in prompts that record how the audit ran, and in the default `ENV_FILE`, which you replace with your own.

## The checks

`publish/stage.sh` stops with a failure when one of these fails:

1. **Leak check** (`publish/check_leaks.py`). It cuts the text and the title of every post in `data/cards.json` into overlapping windows: 40 characters for post text, 24 for titles. It removes windows that three or more posts share, then looks for every other window in every text file of the tree: raw, HTML-unescaped, tag-stripped and JSON-decoded. A copy of about 47 characters of a post, or 27 characters of a title, is found. Data files and charts may quote nothing. The page may quote up to 15 titles, each with a link to its post: it names the most-viewed post of each noise sub-type. A document or a script may quote up to 3 titles as worked examples, and a `.mjs` file up to 6: the copy checks in `charts.mjs` name 4 posts. One file is a reviewed false positive: `scripts/classify-jev.ts` imports the AI SDK with the same line of code that one post quotes.
2. **Grep.** A literal search for the three most-viewed titles, two titles from the middle of the feed and a line of a Japanese post. The log prints the number of files only, so it carries no feed text.
3. **Label keys.** Every `classified-*.jsonl` has only the known label keys, and its text fields are empty.
4. **Secrets.** No API keys, tokens or private keys.
5. **Paths.** No script sets `ROOT` to the author's folder.
6. **Excluded files.** None of the files in the table above is in the tree, and every file in the project is either shipped or excluded on purpose. A new file in a new folder is reported until someone adds it to a list in `stage.sh`.
7. **Size.** The tree is under 50 MB.
8. **Reproduction** (`publish/check_repro.sh`). In a temporary copy of the tree with `data/cards.json` and nothing else, `scripts/analyze.py`, `charts.mjs` and `page-v3.mjs` must give every table, `summary.json`, the audit's files, both pages and every SVG byte for byte (after `strip_text.py` on the new tables). On macOS the run cannot read the project folder, so each input comes from the tree. This check also fails when `report/` was rebuilt after staging.

## Publish

```sh
publish/stage.sh                 # build publish/repo/ and run the checks
publish/publish.sh --dry-run     # print every command; run nothing
publish/publish.sh               # stage again, commit, create the public repository, push, turn on Pages
```

`publish.sh` stages first and stops at a failed check, before anything leaves the machine. It stops if `gh` is logged in as another account, or if the repository exists and `publish/repo/` is not its clone. On a later run, it pushes an update to the same repository.

## Limits

- The feed is live. A later pull has the same posts up to 23 September 2026, with more views and likes and a few cards dropped. Labels reproduce closely, and view figures do not. The exact snapshot is not public. If OpenChamber agrees to its publication, `data/snapshots/` is the file to add.
- The page quotes feed titles, and the rubric and prompts quote a few. They are short quotations with links, not the dataset.
- The page and the charts are © Matthew O'Riordan, not under MIT or CC BY. To open them too, change the License section of `publish/templates/README.md` and the scope in `publish/templates/LICENSE-DATA`.
