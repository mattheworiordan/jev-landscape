# Rubric: classifying Jev launch-week build posts

Jev is TypeSafe AI's typed-decision model, launched 2026-09-15. It answers typed questions (choice, score, yes/no) about a state; it does not write prose. Each input card is one X post about Jev, collected by the OpenChamber feed. For every card, return one result with the fields below. Judge only what the post says. Do not guess beyond it.

Input fields per card: id; t (an English one-line summary, present even when the post is in Japanese or Chinese); x (the post text, often truncated at 400 characters, links shortened to t.co); chips (claims extracted automatically from the text, such as "34× cheaper"; they can be wrong or can quote TypeSafe's own marketing); oc (OpenChamber's category / subcategory). The oc field is a hint only: it came from a different scheme and is often wrong.

## family (exactly one of 14)

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
- games_control_loops_simulation: Jev drives or referees a game, simulation, robot or physical device in a loop, such as game-playing agents, NPCs, game mechanics judged by Jev, robotics, drones and home automation. Examples: Jev playing Pong, Tetris or Street Fighter in real time; a robot arm or drone choosing its next action.
- data_and_telemetry: Jev labels or analyses a dataset, log, metric stream or research corpus to study, measure or clean it, such as bulk annotation, survey or ad-corpus analysis, log or telemetry anomaly detection and research studies. Examples: 19,045 annotations of a political-science dataset on a local GPU; asking 33 questions of each of 1,968 live ads to study the market.
- trading_and_markets: Jev makes or supports financial or market decisions, such as trading bots, crypto and token screens, prediction markets, sports or race betting and pricing. Examples: a Polymarket or crypto trading bot; horse-race picks over a day of races.
- other_or_meta: The post has no concrete use of Jev: commentary, memes, reactions, news, tutorials or directories with no use case, benchmarks of Jev itself (speed, price, trick questions, head-to-head with no application), or a build that fits none of the other families. Examples: the "strawberry" letter-count test on Jev; a latency and price benchmark of Jev against Opus with no application.

Rules for family:
1. Classify the primary application: what the decision is used for. Do not classify by technique ("a classifier") or by the comparison ("faster than GPT").
2. A benchmark of Jev on a named task belongs to that task's family. A benchmark with no application (raw speed, price, trick questions, a model head-to-head) is other_or_meta.
3. evals_and_judging applies only when Jev judges other outputs. Jev being evaluated is not evals_and_judging.
4. A game stays in games_control_loops_simulation even when Jev judges player input.
5. If items are labelled to drive an action or fill a queue, use classification_routing_triage. If items are labelled to study, measure or clean a dataset, use data_and_telemetry.
6. Use voice_and_turn_taking, live_chat_streams_events or collaboration_and_typing only when the live element is central to what was built.
7. If the post is about a build but gives too little to place it, use other_or_meta.

## tier: the time budget the use case sets for each decision (not the latency Jev achieved)

- frame: under 16 ms; only when a decision is needed on every rendered frame or at 60 Hz or more (per-frame physics, control or animation).
- feel: under 100 ms; per keystroke, cursor move, gesture, or ordinary real-time game input (moving a paddle, jumping, a fighting-game move).
- turn: 100 to 300 ms; conversational turn-taking, voice end-of-turn, barge-in.
- interaction: under 1 s; per message, per edit or per click while a human waits for the answer.
- task: 1 to 10 s; a step in an agent or workflow, a page load, a user waits for a task to finish.
- batch: minutes or offline; bulk processing, datasets, scheduled or overnight jobs, nobody waits per item.
- unclear: commentary, or the post does not say enough.

## evidence

- measured_production: numbers (latency, accuracy, cost, volume) from a system the author says is live with real users, customers or traffic.
- measured_demo: numbers from a demo, prototype, benchmark or experiment the author ran themselves.
- demo_no_numbers: a built thing is shown (video, repo, screenshots, live link) with no measurement.
- proposal_or_idea: a plan, concept or "you could use Jev for", with no built artifact.
- commentary_or_meme: opinion, reaction, news, joke or promotion without a build.
Numbers that only repeat TypeSafe's own launch claims do not count as measurement.

## framing: the claim the post leads with (the first or most emphasised)

- cost: cheaper, dollars per decision or per page.
- latency: faster, milliseconds, "realtime".
- accuracy: percent correct, beats another model on quality, fewer errors.
- capability: something that was not possible or practical before, a new product or interaction the model enables.
- none: no claim.

## baseline: what the post compares Jev against

- frontier_llm: a large general chat model (GPT-5.x, Claude Opus or Sonnet, Gemini Pro, Grok), or "an LLM" with no size given.
- small_llm: a small, fast or local LLM (Haiku, Flash, mini, nano, Llama, Qwen, Gemma, Mistral small).
- classic_classifier_or_ml: a trained classifier or classic ML (BERT, fine-tuned model, logistic regression, embeddings with kNN).
- vendor_api: a named product API for the same job (OpenAI moderation, Perspective, a rerank API, a voice vendor's endpointing).
- rules_or_regex: heuristics, keywords, regex or hand-written rules.
- none: no comparison.
If several, pick the one the post emphasises.

## realtime_infra (boolean)

true if a live stream, a WebSocket or pub/sub channel, a voice pipeline, a game loop or a live human-in-the-loop session is part of the described system. false for batch jobs, CLI tools, offline analysis and request/response apps with no live element.

## production_claim (boolean)

true only if the author says it runs in production or on real users or customers.

## reason

At most 12 words (the limit is under 20), in English: why this family and evidence.

Return exactly one result per input card, using the card's id unchanged.
