# Noise sub-types: what the other_or_meta posts are

Jev is TypeSafe AI's typed-decision model, launched 2026-09-15. It answers typed questions (choice, score, yes/no) about a state; it does not write prose. Each input card is one X post about Jev, collected by the OpenChamber feed, that an earlier pass (rubric v2) put in the noise: family other_or_meta (about Jev, but no concrete use of it that fits a use-case family) or commentary. Say what kind of post it is. Judge only what the post says. Do not guess beyond it.

Input fields per card: id; t (an English one-line summary, present even when the post is in Japanese or Chinese); x (the post text, often truncated at 400 characters, links shortened to t.co); chips (claims extracted automatically from the full post; they can be wrong); oc (OpenChamber's category / subcategory, a hint only; it is often wrong).

## subtype (exactly one of 7, in order of precedence)

- benchmark_of_the_model: tests how Jev itself performs rather than using it for a task: latency, throughput, price, calibration, accuracy suites, robustness (prompt injection, option order), trick questions (letter counting), comparisons with Laya, clones or LLMs on no particular application. Not a use case.
- tooling_or_wrapper: software whose purpose is to help people call, run, host or try Jev, with no use case of its own: SDKs, libraries, ports, clients, CLIs, MCP servers, plugins, API proxies and gateways, playgrounds, deployment scripts, skill packs, templates and generic interfaces for asking Jev a question. An app for end users (an input method, a clipboard tool, a chat assistant, a video workflow) is not tooling, even when the post calls it a tool.
- explainer_or_tutorial: explains what Jev is or how to call it: docs, guides, code snippets, courses, setup notes, threads that explain typed decisions. No use case of the author's own.
- news_or_repost: relays news rather than the author's own work: launch, pricing or funding announcements, Jev listed on a gateway, provider or platform ("Jev is now on X"), roundups, lists, directories, galleries, surveys of other people's builds or repos, event or hackathon announcements, and reposts or summaries of other people's builds.
- meme_or_joke: a joke, meme, parody or playful stunt whose point is the humour.
- hot_take_or_commentary: an opinion about Jev, TypeSafe AI, typed-decision models or the category: praise, criticism, predictions, reactions, arguments about where it fits or what it replaces.
- unrelated_or_unclear: not really about Jev; or the author's own app, demo or workflow built with Jev where the post does not say what Jev decides or the use fits no use-case family (for example "I built a clipboard tool with Jev"); or too vague to tell what the post is.

Rules:
1. Pick the post's main purpose. If two subtypes fit equally, use the one listed first.
2. The author's own SDK, client, port or integration is tooling_or_wrapper, even when the post announces it. An announcement by TypeSafe AI, a gateway, a provider or another platform that Jev is available there is news_or_repost.
3. A test that measures Jev and not an application is benchmark_of_the_model, even when it is framed as a joke or an opinion.
4. The author's own app, demo or workflow built with Jev is unrelated_or_unclear unless its main purpose fits an earlier subtype: a demo whose point is Jev's speed or accuracy is benchmark_of_the_model; an SDK, starter template or playground is tooling_or_wrapper; a how-to is explainer_or_tutorial.

## stance (hot_take_or_commentary only)

For hot_take_or_commentary, exactly one of:
- bullish: positive about Jev or the category: its value, quality or prospects.
- skeptical: doubtful or critical: questions the value, the claims, the accuracy, the price, the hype or the need.
- mixed: both are clearly present.
- neutral: an observation or a question with no clear lean.
For every other subtype, stance is none.

## reason

At most 10 words, in English: why this subtype.

Return exactly one result per input card, using the card's id unchanged.
