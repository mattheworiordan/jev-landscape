/**
 * Step 1b: sub-classify the noise. Every card that the v2 labels put in the noise
 * bucket (family other_or_meta, or evidence commentary_or_meme in a use-case family)
 * gets one of seven sub-types, and a stance when it is a hot take, from Claude
 * Sonnet 5 through Vercel AI Gateway.
 *
 *   pnpm dlx tsx --env-file=.env.local scripts/classify-noise.ts
 *
 * Env knobs:
 *   LABELS          the label file whose noise posts to sub-type (default data/classified-sonnet-v2.jsonl)
 *   OUT, USAGE, ERRORS  override the output paths (default data/classified-noise.jsonl,
 *                   data/usage-noise.jsonl, data/classified-noise.errors.jsonl).
 *   LIMIT           classify at most N new cards (used for the pilot).
 *   MAX_USD         stop launching batches once the spend recorded in the USAGE file
 *                   (including earlier runs into the same file) passes this; default 3.
 *
 * Resumable: ids already in OUT are skipped. Each batch appends its results and one
 * usage row to USAGE as soon as it returns. Ids missing from a response, and hot takes
 * returned without a stance, are re-queued for up to three rounds; ids still missing
 * after that go to ERRORS. The rubric is written to report/rubric-noise.md at start-up,
 * so the published rubric is always the one that ran. Auth comes from the env file;
 * the key is never printed.
 */
import { appendFileSync, existsSync, readFileSync, writeFileSync } from 'node:fs';
import { generateObject } from 'ai';
import { z } from 'zod';

const MODEL = 'anthropic/claude-sonnet-5';
const PRICE = { input: 2, output: 10, cacheRead: 0.2, cacheWrite: 2.5 }; // $ per million tokens (Gateway list)
const BATCH = 40;
const CONCURRENCY = 5;
const ROUNDS = 3;
const CALL_TIMEOUT_MS = 300_000;
const TEXT_CHARS = 700;
const MAX_USD = Number(process.env.MAX_USD ?? 3);
const LIMIT = process.env.LIMIT ? Number(process.env.LIMIT) : Infinity;
const OUT = process.env.OUT ?? 'data/classified-noise.jsonl';
const USAGE = process.env.USAGE ?? 'data/usage-noise.jsonl';
const ERRORS = process.env.ERRORS ?? 'data/classified-noise.errors.jsonl';
const LABELS = process.env.LABELS ?? 'data/classified-sonnet-v2.jsonl'; // the labels whose noise posts get sub-typed (refresh.sh passes the reference labels)
const RUBRIC_MD = 'report/rubric-noise.md';

// In order of precedence: when two fit equally, the first one listed wins.
export const SUBTYPES = [
  'benchmark_of_the_model',
  'tooling_or_wrapper',
  'explainer_or_tutorial',
  'news_or_repost',
  'meme_or_joke',
  'hot_take_or_commentary',
  'unrelated_or_unclear',
] as const;
export const STANCES = ['bullish', 'skeptical', 'mixed', 'neutral'] as const;
const STANCE_OPTIONS = ['bullish', 'skeptical', 'mixed', 'neutral', 'none'] as const;
const HOT = 'hot_take_or_commentary';

export const RUBRIC_NOISE = `# Noise sub-types: what the other_or_meta posts are

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
`;

interface Card {
  id: string;
  t: string;
  x: string;
  chips: string[] | null;
  cat: string;
  u: string;
}
interface Label {
  id: string;
  family: string;
  evidence: string;
}

const wireSchema = z.object({
  id: z.string().describe('the card id, unchanged'),
  sub: z.enum(SUBTYPES).describe('subtype'),
  st: z.enum(STANCE_OPTIONS).describe('stance: one of the four for hot_take_or_commentary, none otherwise'),
  why: z.string().describe('reason, at most 10 words'),
});
const batchSchema = z.object({ results: z.array(wireSchema) });
type Wire = z.infer<typeof wireSchema>;

interface Result {
  id: string;
  subtype: Wire['sub'];
  stance: (typeof STANCES)[number] | null;
  reason: string;
}

const KEY_NOTE = 'Output keys are abbreviated: sub = subtype, st = stance, why = reason.';

function authMode(): string {
  if (process.env.AI_GATEWAY_API_KEY) return 'AI_GATEWAY_API_KEY';
  if (process.env.VERCEL_OIDC_TOKEN) return 'VERCEL_OIDC_TOKEN';
  return 'NONE';
}

function readJsonl<T>(path: string): T[] {
  if (!existsSync(path)) return [];
  return readFileSync(path, 'utf8')
    .split('\n')
    .filter((l) => l.trim())
    .map((l) => JSON.parse(l) as T);
}

interface UsageRow {
  at: string;
  n: number;
  returned: number;
  input: number;
  noCache: number;
  cacheRead: number;
  cacheWrite: number;
  output: number;
  usd: number;
  gatewayCost?: unknown;
}

function costOf(u: { noCache: number; cacheRead: number; cacheWrite: number; output: number }): number {
  return (u.noCache * PRICE.input + u.cacheRead * PRICE.cacheRead + u.cacheWrite * PRICE.cacheWrite + u.output * PRICE.output) / 1e6;
}

function cardForPrompt(c: Card) {
  return {
    id: c.id,
    t: c.t,
    x: c.x.length > TEXT_CHARS ? `${c.x.slice(0, TEXT_CHARS)}…` : c.x,
    chips: c.chips ?? [],
    oc: `${c.cat} / ${c.u}`,
  };
}

/** The noise bucket as scripts/buckets-reviewed.py defines it, on the use-case families. */
function isNoise(l: Label): boolean {
  return l.family === 'other_or_meta' || (l.evidence === 'commentary_or_meme' && l.family !== 'not_a_jev_build');
}

async function classifyBatch(batch: Card[]): Promise<{ results: Wire[]; usage: UsageRow }> {
  const lines = batch.map((c) => JSON.stringify(cardForPrompt(c))).join('\n');
  const res = await generateObject({
    model: MODEL,
    schema: batchSchema,
    schemaName: 'JevNoiseSubtypes',
    schemaDescription: 'One sub-type per input card, keyed by the card id.',
    instructions: {
      role: 'system',
      content: RUBRIC_NOISE,
      providerOptions: { anthropic: { cacheControl: { type: 'ephemeral' } } },
    },
    messages: [
      {
        role: 'user',
        content: `Sub-classify these ${batch.length} cards (one JSON object per line). Return exactly ${batch.length} results. ${KEY_NOTE}\n\n${lines}`,
      },
    ],
    maxRetries: 2,
    maxOutputTokens: 8000,
    abortSignal: AbortSignal.timeout(CALL_TIMEOUT_MS),
    providerOptions: { anthropic: { thinking: { type: 'disabled' } } },
  });
  const u = res.usage;
  const input = u.inputTokens ?? 0;
  const cacheRead = u.inputTokenDetails?.cacheReadTokens ?? 0;
  const cacheWrite = u.inputTokenDetails?.cacheWriteTokens ?? 0;
  const noCache = u.inputTokenDetails?.noCacheTokens ?? Math.max(0, input - cacheRead - cacheWrite);
  const output = u.outputTokens ?? 0;
  const tokens = { input, noCache, cacheRead, cacheWrite, output };
  const gw = (res.providerMetadata as Record<string, Record<string, unknown>> | undefined)?.gateway;
  return {
    results: res.object.results,
    usage: { at: new Date().toISOString(), n: batch.length, returned: res.object.results.length, ...tokens, usd: costOf(tokens), gatewayCost: gw?.cost },
  };
}

function chunk<T>(xs: T[], n: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < xs.length; i += n) out.push(xs.slice(i, i + n));
  return out;
}

async function main(): Promise<void> {
  console.log(`auth: ${authMode()} (name only); out ${OUT}; usage ${USAGE}`);
  if (authMode() === 'NONE') throw new Error('No Gateway credentials in the environment.');
  writeFileSync(RUBRIC_MD, RUBRIC_NOISE);

  const { cards } = JSON.parse(readFileSync('data/cards.json', 'utf8')) as { cards: Card[] };
  const byId = new Map(cards.map((c) => [c.id, c]));
  const labels = new Map<string, Label>();
  for (const l of readJsonl<Label>(LABELS)) if (!labels.has(l.id)) labels.set(l.id, l);
  const noiseIds = cards.filter((c) => labels.has(c.id) && isNoise(labels.get(c.id)!)).map((c) => c.id);
  const done = new Set(readJsonl<Result>(OUT).map((r) => r.id));
  const tot = { input: 0, cacheRead: 0, output: 0, usd: 0 };
  for (const u of readJsonl<UsageRow>(USAGE)) {
    tot.input += u.input;
    tot.cacheRead += u.cacheRead;
    tot.output += u.output;
    tot.usd += u.usd;
  }
  let pending = noiseIds.filter((id) => !done.has(id));
  if (Number.isFinite(LIMIT)) pending = pending.slice(0, LIMIT);
  console.log(
    `${cards.length} cards, ${noiseIds.length} in the noise, ${noiseIds.length - pending.length} already sub-typed, ${pending.length} to do; prior spend $${tot.usd.toFixed(3)}; cap $${MAX_USD}`,
  );

  let stopped = false;
  for (let round = 1; round <= ROUNDS && pending.length > 0 && !stopped; round += 1) {
    const batches = chunk(pending, BATCH);
    const missing: string[] = [];
    let next = 0;
    let finished = 0;
    console.log(`round ${round}: ${pending.length} ids in ${batches.length} batches`);

    const worker = async (): Promise<void> => {
      while (!stopped) {
        const i = next;
        next += 1;
        if (i >= batches.length) return;
        if (tot.usd >= MAX_USD) {
          stopped = true;
          console.log(`budget cap reached ($${tot.usd.toFixed(3)} >= $${MAX_USD}); stopping`);
          return;
        }
        const ids = batches[i];
        const wanted = new Set(ids);
        try {
          const { results, usage } = await classifyBatch(ids.map((id) => byId.get(id)!));
          const seen = new Set<string>();
          const good: Result[] = [];
          let stray = 0;
          let noStance = 0;
          for (const r of results) {
            if (!wanted.has(r.id)) {
              stray += 1;
              continue;
            }
            if (seen.has(r.id) || done.has(r.id)) continue;
            if (r.sub === HOT && r.st === 'none') {
              noStance += 1; // re-queued: a hot take needs a stance
              continue;
            }
            seen.add(r.id);
            good.push({ id: r.id, subtype: r.sub, stance: r.sub === HOT ? (r.st as Result['stance']) : null, reason: r.why });
          }
          if (good.length > 0) appendFileSync(OUT, `${good.map((r) => JSON.stringify(r)).join('\n')}\n`);
          for (const r of good) done.add(r.id);
          const miss = ids.filter((id) => !seen.has(id));
          missing.push(...miss);
          appendFileSync(USAGE, `${JSON.stringify({ ...usage, round, stray, missing: miss.length, no_stance: noStance })}\n`);
          tot.input += usage.input;
          tot.cacheRead += usage.cacheRead;
          tot.output += usage.output;
          tot.usd += usage.usd;
          finished += 1;
          console.log(
            `r${round} batch ${i + 1}/${batches.length}: ${good.length}/${ids.length} ok, ${miss.length} missing (${noStance} hot takes without a stance), ${stray} stray | ` +
              `tokens in ${tot.input} (cache read ${tot.cacheRead}) out ${tot.output} | $${tot.usd.toFixed(3)}`,
          );
        } catch (err) {
          missing.push(...ids);
          const msg = err instanceof Error ? err.message : String(err);
          const status = (err as { statusCode?: number } | null)?.statusCode;
          console.error(`r${round} batch ${i + 1} failed${status ? ` (HTTP ${status})` : ''}: ${msg.slice(0, 300)}`);
          if (status === 401 || status === 403 || status === 402) {
            stopped = true;
            console.error('auth or budget failure; stopping');
          }
        }
      }
    };
    await Promise.all(Array.from({ length: CONCURRENCY }, worker));
    console.log(`round ${round} done: ${finished}/${batches.length} batches returned, ${missing.length} ids to retry`);
    pending = missing;
  }

  if (pending.length > 0) {
    appendFileSync(
      ERRORS,
      `${pending.map((id) => JSON.stringify({ id, at: new Date().toISOString(), error: stopped ? 'stopped' : 'missing after retries' })).join('\n')}\n`,
    );
    console.log(`${pending.length} ids not sub-typed; logged to ${ERRORS}`);
  }
  const covered = noiseIds.filter((id) => done.has(id)).length;
  console.log(`DONE: ${covered}/${noiseIds.length} noise cards sub-typed | tokens in ${tot.input} (cache read ${tot.cacheRead}) out ${tot.output} | noise spend $${tot.usd.toFixed(3)}`);
  if (covered < noiseIds.length) process.exitCode = 2;
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : err);
  process.exit(1);
});
