# Rubric v2: classifying Jev launch-week build posts

Jev is TypeSafe AI's typed-decision model, launched 2026-09-15. It answers typed questions (choice, score, yes/no) about a state; it does not write prose. Each input card is one X post about Jev, collected by the OpenChamber feed. For every card, return one result with the fields below. Judge only what the post says. Do not guess beyond it. When the post does not state what a field needs, use that field's empty value (unclear, none, false). The empty values are correct answers, not failures.

Input fields per card: id; t (an English one-line summary, present even when the post is in Japanese or Chinese); x (the post text, often truncated at 400 characters, links shortened to t.co); chips (claims extracted automatically from the full post, such as "34× cheaper"; they can be wrong, can be the baseline's number or Jev's stated probability, or can quote TypeSafe's launch numbers); oc (OpenChamber's category / subcategory). The oc field is a hint only: it came from a different scheme and is often wrong.

## family (exactly one of 15)

- evals_and_judging: Jev is the judge: it grades, scores or compares outputs such as LLM answers, agent runs, generated content, code or writing against criteria, in place of an LLM-as-judge or a human rater. Examples: a library that replaces LLM judges in an eval suite with typed Jev decisions; a linter for AI writing tells whose judge is Jev.
- classification_routing_triage: Jev assigns a label, category, priority or destination to each item in an operational flow, such as tickets, emails, documents, leads, applicants or news, or picks which model, agent or queue should handle a request. Examples: a tax-document classifier that files each page into a category; a router that sends each prompt to a cheap model or a frontier model.
- moderation_and_guardrails: Jev decides whether content or an input is allowed: moderation, spam, scams, toxicity, ad or distraction blocking, PII, prompt-injection or jailbreak detection, and output guardrails. Examples: a subreddit bot that auto-blocks posts that break the rules; a prompt-injection filter in front of an agent.
- agent_harness_and_tool_gating: Jev makes control decisions inside a running agent or automation loop: approve or block a tool call or command, pick the next step or sub-agent, or decide when a task is done or needs a human. Examples: an approval gate that decides whether a coding agent may run a shell command; a harness step that decides whether an agent has finished its task.
- compaction_and_context: Jev decides what an LLM or agent keeps, drops, stores or retrieves from its own context or memory, such as context compaction, memory writes and relevance of history or tool output. Examples: choosing which conversation turns survive context compaction; deciding which facts an assistant writes to long-term memory.
- search_rerank_extraction: Jev ranks, retrieves, matches or recommends items, or pulls structured answers out of documents, pages or images, as in search relevance, reranking, recommendations and field extraction. Examples: reranking search results by relevance to the query; answering a fixed set of questions about each SEC filing.
- browser_and_computer_use: Jev drives or checks a browser, desktop or phone user interface, such as choosing which element to click, web or UI testing, form filling and computer-use agents. Examples: predicting which DOM element a user or agent should click next; Jev with Playwright deciding pass or fail in web tests.
- voice_and_turn_taking: Jev makes decisions inside a spoken-audio pipeline, such as end-of-turn detection, barge-in or interruption, live call handling and voice assistants. Examples: an end-of-utterance detector for a voice agent; a phone bot that decides when to interrupt or hand the call to a human.
- live_chat_streams_events: Jev decides on each item of a live stream as it arrives, such as live chat (Twitch, Discord, YouTube), comment or social streams, live sports, news or event feeds, alerts and notifications. Examples: flagging highlight moments in a Twitch chat as messages arrive; posting an alert when a live football match feed shows a key event.
- collaboration_and_typing: Jev decides per keystroke, per edit or per cursor move in an editor or shared workspace, such as predictive typing, autocomplete, live document or whiteboard checks and live meeting co-pilots. Examples: predictive typing suggestions in a text box; flagging contradictions while meeting minutes are written live.
- games_control_loops_simulation: Jev drives or referees a game, simulation, robot or physical device in a loop, such as game-playing agents, NPCs, game mechanics judged by Jev, robotics, drones and home automation. Examples: Jev playing Pong, Tetris or Street Fighter in real time, or a Snake benchmark of Jev against another model; a robot arm or drone choosing its next action.
- data_and_telemetry: Jev labels or analyses a dataset, log, metric stream or research corpus to study, measure or clean it, such as bulk annotation, survey or ad-corpus analysis, log or telemetry anomaly detection and research studies. Examples: 19,045 annotations of a political-science dataset on a local GPU; asking 33 questions of each of 1,968 live ads to study the market.
- trading_and_markets: Jev makes or supports financial or market decisions, such as trading bots, crypto and token screens, prediction markets, sports or race betting and pricing. Examples: a Polymarket or crypto trading bot; horse-race picks over a day of races.
- not_a_jev_build: The described system does not use Jev: its decisions come from another model only (Laya, Gemini, GLiClass, a logprob classifier), a local clone, distillation or imitation of Jev, or a "Jev-like" or Jev-compatible API over another model; or the author says Jev is not used yet; or the post is general commentary about typed-decision or small decision models with no use of Jev. Examples: a browser agent rebuilt with GLiClass instead of Jev; a trading backtest run on Gemini Flash that says "will try Jev later".
- other_or_meta: The post is about Jev but has no concrete use of it: commentary, memes, reactions, news, tutorials or directories about Jev, benchmarks of Jev with no task (raw speed, price, trick questions, a head-to-head on nothing in particular), a Jev build too vague to place, or a Jev build that fits none of the other families. Examples: the "strawberry" letter-count test on Jev; "I wired Jev into my agents" with no decision named.

Rules for family:
1. First decide whether the post uses Jev. If the decisions in the described system come from something other than Jev, use not_a_jev_build: another model only (Laya, Gemini, GLiClass, a logprob classifier), a local clone, distillation or imitation of Jev, a "Jev-like" or Jev-compatible API over another model, or a build the author says does not use Jev (yet). General commentary about typed-decision or small decision models with no use of Jev is also not_a_jev_build. Commentary, reactions, news or tutorials about Jev itself stay in other_or_meta. A comparison that runs Jev against another model is a Jev build.
2. Classify the primary application: what the decision is used for. Do not classify by technique ("a classifier") or by the comparison ("faster than GPT").
3. A benchmark of Jev on a named task belongs to that task's family, even when it compares Jev with another model or measures only speed or cost: a Snake or Pong benchmark of Jev against Laya or an LLM is games_control_loops_simulation, and an email-classification benchmark is classification_routing_triage. Only a benchmark with no task at all (raw speed or price, trick questions such as letter counting, a head-to-head on nothing in particular) is other_or_meta.
4. evals_and_judging applies only when Jev judges other outputs. Jev being evaluated is not evals_and_judging.
5. A game stays in games_control_loops_simulation even when Jev judges player input.
6. If items are labelled to drive an action or fill a queue, use classification_routing_triage. If items are labelled to study, measure or clean a dataset, use data_and_telemetry.
7. Routing a request to a model, agent or queue before the work starts is classification_routing_triage. Choosing the next step, tool or sub-agent inside a running agent loop is agent_harness_and_tool_gating.
8. Use voice_and_turn_taking, live_chat_streams_events or collaboration_and_typing only when the live element is central to what was built. Moderating the chat or comments of a live stream as they arrive is live_chat_streams_events. A decision on each utterance of a live call or voice session, including a classification step after transcription, is voice_and_turn_taking.
9. If the post is about a Jev build but gives too little to place it (for example "I wired Jev into my agents" with no decision named), use other_or_meta.

## tier: the time budget the use case sets for each decision (not the latency Jev achieved)

- frame: under 16 ms; only when a decision is needed on every rendered frame or at 60 Hz or more (per-frame physics, control or animation).
- feel: under 100 ms; per keystroke, cursor move, gesture, or ordinary real-time game input (moving a paddle, jumping, a fighting-game move).
- turn: 100 to 300 ms; conversational turn-taking, voice end-of-turn, barge-in.
- interaction: under 1 s; per message, per edit or per click while a human waits for the answer.
- task: 1 to 10 s; a step in an agent or workflow, a page load, a user waits for a task to finish.
- batch: minutes or offline; bulk processing, datasets, scheduled or overnight jobs, nobody waits per item.
- unclear: the post neither says how fast each decision must be nor shows how the decision is used, so the budget cannot be read from it (commentary, a benchmark with no use, a vague mention of a build). unclear is allowed and preferred to a guess.
When the post shows how the build is used, read the budget from that use even if no speed is stated: a person clicks, types or asks in an app and waits for each answer → interaction; a step inside an agent, workflow or pipeline → task; many items processed as a job → batch; a game, robot or device loop → feel (or frame, or turn for voice). Do not read the budget from the family alone.

## evidence

- measured_production: the post meets the production_claim test below AND reports a number from that live system (a latency, cost, accuracy, count or rate).
- measured_demo: the post reports at least one number that the author's own run of their own build produced: a latency, cost, accuracy, count or rate of that build (for example "classified 1,968 ads", "p50 180 ms", "$0.40 for the whole run", "91% on 200 labelled emails").
- demo_no_numbers: a built thing is shown (video, repo, screenshots, live link) without such a number.
- proposal_or_idea: a plan, concept or "you could use Jev for", with no built artifact.
- commentary_or_meme: opinion, reaction, news, joke or promotion without a build.

A number is a measurement only if it is a digit in the text x, or in a chip that repeats the author's own result. These are NOT measurements; grade the post as if the number were absent:
- TypeSafe's launch numbers, quoted or paraphrased as Jev's general speed or price rather than the author's own result: 20 to 200x faster (than frontier LLMs); 40 to 400x cheaper (than frontier LLMs); 70 to 500 ms end to end; the list price, $0.042 per million input tokens with free output.
- Numbers from another post, a vendor, a paper or a leaderboard.
- Results behind a link, in an image the text does not describe, or promised later ("results in the thread", "benchmarks soon").
- Adjectives with no figure: "way faster", "much more accurate", "instant", "near zero cost".
- Jev's stated probability or confidence for one decision: it is an output, not a measure of the build.
- Jokes and hyperbole (for example "1012x faster than Claude" at writing an app).
- Version numbers, model sizes, dates, the price of another product, the number of options or labels in the question.

## framing: the claim the post leads with (the first or most emphasised claim)

- cost: an explicit claim that it is cheaper, or a cost figure (dollars per decision, per page, per run).
- latency: an explicit claim that it is faster or fast enough for a live use, or a time figure.
- accuracy: an explicit claim about correctness: percent correct, beats another model on quality, fewer errors.
- capability: an explicit statement that something was not possible, practical or affordable before Jev, or that a previous limit is gone ("could not do this before", "this was never feasible", "too expensive to run on every message with an LLM", "no need to predefine features any more", "now I can finally"). Showing a new build is not a capability claim by itself.
- none: the post shows or describes what was built with no cost, latency, accuracy or capability claim. Generic praise ("amazing", "this is wild") is none.

## baseline: what the post compares Jev against

The comparison must be named in the text or clearly implied: "replaced my keyword filter with Jev" implies rules_or_regex, "used to send every ticket to GPT" implies frontier_llm, and a before-and-after figure ("26 s → 3 s after moving the decisions from the LLM to Jev") is a comparison with the previous system. Using an LLM alongside Jev in the same system, with no before-and-after, is not a comparison. With no comparison, use none.
- frontier_llm: a large general chat model (GPT-5.x, Claude Opus or Sonnet, Gemini Pro, Grok), or "an LLM" with no size given.
- small_llm: a small, fast or local LLM (Haiku, Flash, mini, nano, Llama, Qwen, Gemma, Mistral small).
- classic_classifier_or_ml: a trained classifier or classic ML (BERT, fine-tuned model, logistic regression, embeddings with kNN).
- vendor_api: a named product API for the same job (OpenAI moderation, Perspective, a rerank API, a voice vendor's endpointing).
- rules_or_regex: heuristics, keywords, regex or hand-written rules or logic.
- none: no comparison, named or clearly implied.
If several, pick the one the post emphasises.

## realtime_infra (boolean)

true only if the post describes a live element that is part of the system: a game or control loop that runs while someone plays or a device moves, a live data or event stream processed as it arrives (market feed, chat, comments, sensors), a WebSocket or pub/sub channel, a voice pipeline, or a live human-in-the-loop session (a person typing, speaking or meeting while the decisions are made). The words "real-time", "live" or "instant" in a title or summary are not enough. false for batch jobs, CLI tools, offline analysis, search tools, and request/response apps or browser extensions that decide once when a page or feed loads.

## production_claim (boolean)

true only if the post explicitly states that the system serves real users or customers, or runs as a live service or product for others ("in production", "deployed to our users", "live for customers", "handles our support queue"). false for a test, benchmark, pilot or shadow run (even on production data or "real leads"), a one-off job, a tool only the author uses, a bot trading the author's own money, and plans to ship.

## reason

At most 12 words (the limit is under 20), in English: why this family and evidence.

Return exactly one result per input card, using the card's id unchanged.
