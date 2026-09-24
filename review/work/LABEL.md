# Blind labelling instructions

You are labelling X posts about Jev (TypeSafe AI's typed-decision model, launched 2026-09-15). Jev answers typed questions (choice, score, yes/no). It does not write prose.

Judge only what the card says. Do not guess. When the post does not state what a field needs, use the empty value (unclear, none, false). Empty values are correct.

You will be given one JSONL file of cards. Each line has only: id, t (English one-line summary), x (post text, often truncated at 400 characters), chips (auto-extracted claim strings; they can be wrong, can be someone else's number, or can be TypeSafe's launch numbers), lang.

Do not read any other file. Do not look up the post. Do not use labels you remember from anywhere else.

## How to read a card

- Use t and x together. t is a summary, including for Japanese and Chinese posts. If x is not English, lean on t, and say "title-led" in the note.
- A number counts as a measurement only if it is a digit in x, or in a chip that repeats the author's own result. A number that appears only in t does not count.
- These are NOT measurements. Grade the post as if that number were absent:
  - TypeSafe's launch numbers, quoted as Jev's general speed or price: 20 to 200× faster than frontier LLMs; 40 to 400× cheaper; 70 to 500 ms end to end; list price $0.042 per million input tokens, free output.
  - Numbers from another post, a vendor, a paper or a leaderboard.
  - Results behind a link, in an image the text does not describe, or promised later.
  - Adjectives with no figure: "way faster", "instant", "near zero cost".
  - Jev's stated probability or confidence for one decision.
  - Jokes and hyperbole.
  - Version numbers, model sizes, dates, the price of another product, the number of options or labels in the question.
- Chips like "24/s" or "72/s" are often mis-parsed counts, not rates. Read x.

## family (exactly one)

- evals_and_judging: Jev grades, scores or compares other outputs (LLM answers, agent runs, content, code, writing). Jev being evaluated is not this family.
- classification_routing_triage: Jev assigns a label, category, priority or destination (tickets, emails, documents, leads, pages), or picks which model, agent or queue handles a request before the work starts.
- moderation_and_guardrails: allow or block content or an input (spam, toxicity, scams, PII, prompt-injection, jailbreak, output guardrails, ad blocking).
- agent_harness_and_tool_gating: control decisions inside a running agent loop: approve or block a tool call or command, pick the next step or sub-agent, decide when a task is done or needs a human.
- compaction_and_context: what an LLM or agent keeps, drops, stores or retrieves from its own context or memory.
- search_rerank_extraction: rank, retrieve, match, recommend, or pull structured fields out of documents, pages or images.
- browser_and_computer_use: drive or check a browser, desktop or phone UI (click, form fill, web test, computer-use).
- voice_and_turn_taking: decisions inside a spoken-audio pipeline (end-of-turn, barge-in, live calls, voice assistants), including a classification step on each utterance of a live call.
- live_chat_streams_events: a decision on each item of a live stream as it arrives (Twitch, Discord, YouTube, comments, sports, news, alerts). Moderating a live chat as messages arrive is this family, not moderation.
- collaboration_and_typing: per keystroke, per edit or per cursor move (predictive typing, autocomplete, live doc or whiteboard checks, live meeting co-pilots).
- games_control_loops_simulation: game, simulation, robot or physical device in a loop, including a benchmark of Jev playing a named game. A game stays here even if Jev judges player input.
- data_and_telemetry: label or analyse a dataset, log, metric stream or corpus to study, measure or clean it (bulk annotation, surveys, research). Labelling to drive an action or fill a queue is classification, not this.
- trading_and_markets: trading, crypto screens, prediction markets, betting, pricing.
- not_a_jev_build: the decisions come from another model only (Laya, Gemini, GLiClass, a logprob classifier), a local clone or imitation, a "Jev-like" API over another model, the author says Jev is not used yet, or the post is general commentary about small decision models with no use of Jev. A comparison that runs Jev against another model is a Jev build.
- other_or_meta: about Jev but no concrete use: commentary, memes, news, tutorials, directories, a benchmark with no task (raw speed, price, trick questions, a head-to-head on nothing), or a build too vague to place ("I wired Jev into my agents" with no decision named).

Family rules:
1. Decide first whether the post uses Jev. Commentary about Jev itself stays other_or_meta. Commentary about the category with no Jev use is not_a_jev_build.
2. Classify the primary application, not the technique and not the comparison.
3. A benchmark on a named task belongs to that task's family. Only a benchmark with no task is other_or_meta.
4. Routing before the work starts is classification. Choosing the next step inside a running loop is agent_harness.
5. Use voice, live chat or collaboration only when the live element is central.
6. Too little to place a real build: other_or_meta.

## tier (the time budget the use case sets, not the latency Jev achieved)

- frame: under 16 ms. Only a decision on every rendered frame or at 60 Hz or more.
- feel: under 100 ms. Per keystroke, cursor, gesture, or ordinary real-time game input (paddle, jump, a fighting-game move).
- turn: 100 to 300 ms. Conversational turn-taking, voice end-of-turn, barge-in.
- interaction: under 1 s. Per message, per edit or per click while a human waits.
- task: 1 to 10 s. A step in an agent or workflow, a page load, a user waits for a task to finish.
- batch: minutes or offline. Bulk processing, datasets, scheduled jobs, nobody waits per item.
- unclear: the post does not show how the decision is used, so the budget cannot be read. Prefer unclear to a guess.

Read the budget from the use when the post shows the use, even with no speed stated:
- a person clicks, types or asks and waits for each answer → interaction
- a step inside an agent, workflow or pipeline → task
- many items processed as a job → batch
- a live game, robot or device loop while someone plays or the device moves → feel (frame if per-frame, turn if voice)
- Do NOT mark a post feel or turn just because the family is games or voice. A turn-based board game, an offline game benchmark, or a voice demo with no turn-taking budget is whatever the use shows (often task, batch or unclear).

## evidence

- measured_production: production_claim is true AND the post reports a number from that live system (latency, cost, accuracy, count or rate of the system).
- measured_demo: at least one number the author's own run of their own build produced (latency, cost, accuracy, count or rate of that build). "Classified 1,968 ads", "p50 180 ms", "$0.40 for the whole run", "91% on 200 labelled emails" count. A count of items the author processed counts.
- demo_no_numbers: a built thing is shown (video, repo, screenshots, live link, or a described working build) without such a number.
- proposal_or_idea: a plan or "you could use Jev for", no built artifact.
- commentary_or_meme: opinion, reaction, news, joke or promotion without a build.

## framing (the claim the post leads with)

- cost: explicit cheaper claim, or a cost figure.
- latency: explicit faster claim, or a time figure, or "fast enough for a live use".
- accuracy: explicit correctness claim (percent correct, beats another model on quality, fewer errors).
- capability: explicit statement that something was not possible, practical or affordable before Jev, or that a previous limit is gone. Showing a new build is not a capability claim by itself.
- none: no cost, latency, accuracy or capability claim. Generic praise is none.

If several claims appear, pick the one the post emphasises first.

## baseline (what the post compares Jev against)

The comparison must be named or clearly implied. "Replaced my keyword filter" implies rules_or_regex. "Used to send every ticket to GPT" implies frontier_llm. A before-and-after figure is a comparison with the previous system. Using an LLM alongside Jev, with no before-and-after, is not a comparison.

- frontier_llm: a large general chat model (GPT-5.x, Claude Opus or Sonnet, Gemini Pro, Grok), or "an LLM" / "GPT" / "Claude" with no size given.
- small_llm: a small, fast or local LLM (Haiku, Flash, mini, nano, Llama, Qwen, Gemma, Mistral small, Astra-low if described as small).
- classic_classifier_or_ml: a trained classifier or classic ML (BERT, fine-tune, logistic regression, embeddings with kNN, alpha-beta is NOT this; alpha-beta is search).
- vendor_api: a named product API for the same job (OpenAI moderation, Perspective, a rerank API, Cohere rerank, a voice vendor's endpointing, Instantly's classifier).
- rules_or_regex: heuristics, keywords, regex, hand-written rules or logic, a system-prompt rule they replaced.
- none: no comparison.

If several, pick the one the post emphasises. Alpha-beta / minimax for a game is classic search, not classic_classifier_or_ml and not rules. Use none unless they clearly frame it as the incumbent method Jev replaces. If they report Jev versus alpha-beta as the thing a game AI would have used, use classic_classifier_or_ml only when it is a trained model; otherwise rules_or_regex is also wrong. Game-tree search has no bucket: use none, and say so in the note. Do not force it into classic ML.

## realtime_infra (boolean)

true only if the post describes a live element that is part of the system: a game or control loop that runs while someone plays or a device moves; a live data or event stream processed as it arrives (market feed, chat, comments, sensors); a WebSocket or pub/sub channel; a voice pipeline; or a live human-in-the-loop session (a person typing, speaking or meeting while decisions are made).

The words "real-time", "live" or "instant" are not enough. false for batch jobs, CLI tools, offline analysis, search tools, and request/response apps or extensions that decide once when a page or feed loads.

## production_claim (boolean)

true only if the post explicitly states that the system serves real users or customers, or runs as a live service or product for others ("in production", "deployed to our users", "live for customers", "handles our support queue"). false for a test, benchmark, pilot, shadow run, a one-off job, a tool only the author uses, a bot trading the author's own money, and plans to ship.

## noise (only when family is other_or_meta; otherwise null)

Pick one, first match wins:
- benchmark_of_the_model: tests Jev itself (speed, price, calibration, trick questions) with no application task.
- tooling_or_wrapper: SDK, client, proxy, playground, template, MCP, skill pack, with no end-user use case. An end-user app is not tooling.
- explainer_or_tutorial: docs, guides, how to call Jev. No use case of the author's own.
- news_or_repost: launch news, "Jev is now on X", roundups, reposts of other people's builds.
- meme_or_joke: the point is the humour.
- hot_take_or_commentary: an opinion about Jev or the category.
- unrelated_or_unclear: not really about Jev, or the author's own app where the post does not say what Jev decides.

## Output

Write JSONL, one object per input card, same ids, same order, no extra lines:

{"id":"...","family":"...","tier":"...","evidence":"...","framing":"...","baseline":"...","realtime_infra":false,"production_claim":false,"noise":null,"note":"at most 12 words"}

note says why this family and this evidence. Booleans are JSON booleans. noise is null unless family is other_or_meta.
