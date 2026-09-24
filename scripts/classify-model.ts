/**
 * Classify every OpenChamber Jev card with any Gateway model against the written
 * rubric (./rubric.ts). Generalises classify-sonnet.ts: with no flags it runs the
 * Sonnet v2 path exactly as before (same model, prompt, thinking setting and
 * output files).
 *
 *   pnpm dlx tsx --env-file=/Users/matthew.oriordan/Workshop/work/projects/jev-pong/.env.local scripts/classify-model.ts \
 *     --model anthropic/claude-opus-5.5 --out data/classified-opus.jsonl
 *
 * Flags (env knob in brackets, flag wins):
 *   --model <gateway id>   default anthropic/claude-sonnet-5
 *   --out <path>           [OUT] default: Sonnet data/classified-sonnet-v2.jsonl,
 *                          other models data/classified-<model-short>.jsonl
 *   --usage <path>         [USAGE] default: Sonnet data/usage-sonnet-v2.jsonl,
 *                          other models data/usage-<model-short>.jsonl
 *   --errors <path>        [ERRORS] default: <out without .jsonl>.errors.jsonl
 *   --batch <n>            cards per call; default 40. Smaller batches only to isolate
 *                          a card that makes the whole batch fail (see ERRORS).
 *   --concurrency <n>      default 8
 *   --max-usd <n>          [MAX_USD] stop launching batches once the USAGE file's
 *                          recorded spend passes this; default 8.5
 *   --thinking <mode>      disabled | adaptive | omit. Default: disabled for Sonnet
 *                          (as before); omit for other models. Claude Opus 5.5
 *                          rejects "disabled" with a 400, so it runs adaptive.
 *   --effort <level>       low | medium | high | xhigh | max. Sent only when set;
 *                          default medium for non-Sonnet models (Opus 5.5's default).
 *   --max-output <n>       default 12000 for Sonnet, 32000 otherwise (thinking
 *                          tokens count toward this cap).
 *   --ids <file.jsonl>     [IDS] classify only the ids in this file
 *   --limit <n>            [LIMIT] classify at most N new cards
 *   RUBRIC_VERSION         v2 (default) or v1
 *
 * Temperature 0 is sent as before. The Gateway ignores it for claude-sonnet-5
 * and the newer Claude models (it logs "temperature is not supported"), so runs
 * on those models are sampled at the provider default.
 *
 * Resumable: ids already in OUT are skipped. Each batch appends its results and
 * one usage row (tokens, list-price cost, Gateway-reported cost, latency) to
 * USAGE as soon as it returns. Ids missing from a response are re-queued for up
 * to three rounds; ids still missing after that go to ERRORS. Progress is logged
 * every 10 batches; failures are logged as they happen. Prices come from the
 * Gateway model list (id and pricing fields only). Auth comes from the env file;
 * the key is never printed.
 */
import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { generateObject } from 'ai';
import { z } from 'zod';
import { BASELINES, EVIDENCE, FRAMINGS, RUBRICS, TIERS } from './rubric';

const SONNET = 'anthropic/claude-sonnet-5';
const SONNET_PRICE = { input: 2, output: 10, cacheRead: 0.2, cacheWrite: 2.5 }; // fallback if the model list is unreachable

function flag(name: string): string | undefined {
  const i = process.argv.indexOf(`--${name}`);
  if (i === -1) return undefined;
  const v = process.argv[i + 1];
  if (v === undefined || v.startsWith('--')) throw new Error(`--${name} needs a value`);
  return v;
}

const MODEL = flag('model') ?? SONNET;
const IS_SONNET_DEFAULT = MODEL === SONNET;
/** anthropic/claude-opus-5.5 -> opus-5.5 */
const MODEL_SHORT = MODEL.replace(/^[^/]+\//, '').replace(/^claude-/, '');

const BATCH = Number(flag('batch') ?? 40);
const CONCURRENCY = Number(flag('concurrency') ?? 8);
const ROUNDS = 3;
const CALL_TIMEOUT_MS = 300_000;
const TEXT_CHARS = 700;
const PROGRESS_EVERY = 10;
const MAX_USD = Number(flag('max-usd') ?? process.env.MAX_USD ?? 8.5);
const LIMIT_RAW = flag('limit') ?? process.env.LIMIT;
const LIMIT = LIMIT_RAW ? Number(LIMIT_RAW) : Infinity;
const THINKING = (flag('thinking') ?? (IS_SONNET_DEFAULT ? 'disabled' : 'omit')) as 'disabled' | 'adaptive' | 'omit';
if (!['disabled', 'adaptive', 'omit'].includes(THINKING)) throw new Error('--thinking must be disabled, adaptive or omit');
const EFFORT = flag('effort') ?? (IS_SONNET_DEFAULT ? undefined : 'medium');
const MAX_OUTPUT = Number(flag('max-output') ?? (IS_SONNET_DEFAULT ? 12000 : 32000));

const VERSION = (process.env.RUBRIC_VERSION ?? 'v2') as keyof typeof RUBRICS;
if (!(VERSION in RUBRICS)) throw new Error(`RUBRIC_VERSION must be one of ${Object.keys(RUBRICS).join(', ')}`);
const { families: FAMILIES, rubric: RUBRIC } = RUBRICS[VERSION];
const SUFFIX = VERSION === 'v1' ? '' : `-${VERSION}`;
const OUT =
  flag('out') ??
  process.env.OUT ??
  (IS_SONNET_DEFAULT ? `data/classified-sonnet${SUFFIX}.jsonl` : `data/classified-${MODEL_SHORT}${VERSION === 'v2' ? '' : SUFFIX}.jsonl`);
const USAGE =
  flag('usage') ??
  process.env.USAGE ??
  (IS_SONNET_DEFAULT ? `data/usage-sonnet${SUFFIX}.jsonl` : `data/usage-${MODEL_SHORT}${VERSION === 'v2' ? '' : SUFFIX}.jsonl`);
const ERRORS = flag('errors') ?? process.env.ERRORS ?? OUT.replace(/\.jsonl$/, '.errors.jsonl');
const RUBRIC_MD = VERSION === 'v1' ? 'report/rubric-v1.md' : 'report/rubric.md';
const IDS = flag('ids') ?? process.env.IDS;

interface Card {
  id: string;
  t: string;
  x: string;
  chips: string[] | null;
  cat: string;
  u: string;
}

/**
 * What the model returns. Keys are abbreviated to cut output tokens; toResult()
 * expands them to the rubric's field names before anything is written.
 */
const wireSchema = z.object({
  id: z.string().describe('the card id, unchanged'),
  fam: z.enum(FAMILIES as unknown as [string, ...string[]]).describe('family'),
  tier: z.enum(TIERS).describe('tier'),
  ev: z.enum(EVIDENCE).describe('evidence'),
  frm: z.enum(FRAMINGS).describe('framing'),
  base: z.enum(BASELINES).describe('baseline'),
  rt: z.boolean().describe('realtime_infra'),
  prod: z.boolean().describe('production_claim'),
  why: z.string().describe('reason, at most 12 words'),
});
const batchSchema = z.object({ results: z.array(wireSchema) });
type Wire = z.infer<typeof wireSchema>;

interface Result {
  id: string;
  family: Wire['fam'];
  tier: Wire['tier'];
  evidence: Wire['ev'];
  framing: Wire['frm'];
  baseline: Wire['base'];
  realtime_infra: boolean;
  production_claim: boolean;
  reason: string;
}

function toResult(w: Wire): Result {
  return {
    id: w.id,
    family: w.fam,
    tier: w.tier,
    evidence: w.ev,
    framing: w.frm,
    baseline: w.base,
    realtime_infra: w.rt,
    production_claim: w.prod,
    reason: w.why,
  };
}

const KEY_NOTE =
  'Output keys are abbreviated: fam = family, tier = tier, ev = evidence, frm = framing, base = baseline, rt = realtime_infra, prod = production_claim, why = reason.';

function gatewayToken(): string | undefined {
  return process.env.AI_GATEWAY_API_KEY ?? process.env.VERCEL_OIDC_TOKEN;
}

function authMode(): string {
  if (process.env.AI_GATEWAY_API_KEY) return 'AI_GATEWAY_API_KEY';
  if (process.env.VERCEL_OIDC_TOKEN) return 'VERCEL_OIDC_TOKEN';
  return 'NONE';
}

type Price = typeof SONNET_PRICE;

/** $ per million tokens for MODEL, from the Gateway model list (id + pricing only). */
async function fetchPrice(): Promise<Price> {
  try {
    const res = await fetch('https://ai-gateway.vercel.sh/v1/models', {
      headers: { Authorization: `Bearer ${gatewayToken()}` },
      signal: AbortSignal.timeout(30_000),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const body = (await res.json()) as { data?: Array<{ id: string; pricing?: Record<string, unknown> }> };
    const m = (body.data ?? []).find((x) => x.id === MODEL);
    if (!m?.pricing) throw new Error(`model ${MODEL} not in the Gateway list`);
    const perM = (k: string): number => Number(m.pricing?.[k] ?? Number.NaN) * 1e6;
    const p = { input: perM('input'), output: perM('output'), cacheRead: perM('input_cache_read'), cacheWrite: perM('input_cache_write') };
    if (Object.values(p).some((v) => !Number.isFinite(v))) throw new Error(`incomplete pricing for ${MODEL}`);
    return p;
  } catch (err) {
    if (IS_SONNET_DEFAULT) return SONNET_PRICE;
    throw err;
  }
}

let PRICE: Price = SONNET_PRICE;

function readJsonl<T>(path: string): T[] {
  if (!existsSync(path)) return [];
  return readFileSync(path, 'utf8')
    .split('\n')
    .filter((l) => l.trim())
    .map((l) => JSON.parse(l) as T);
}

interface UsageRow {
  at: string;
  model: string;
  n: number;
  returned: number;
  input: number;
  noCache: number;
  cacheRead: number;
  cacheWrite: number;
  output: number;
  reasoning?: number;
  usd: number;
  gatewayCost?: unknown;
  ms: number;
}

function costOf(u: { noCache: number; cacheRead: number; cacheWrite: number; output: number }): number {
  return (
    (u.noCache * PRICE.input + u.cacheRead * PRICE.cacheRead + u.cacheWrite * PRICE.cacheWrite + u.output * PRICE.output) /
    1e6
  );
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

function anthropicOptions(): Record<string, unknown> {
  const o: Record<string, unknown> = {};
  if (THINKING === 'disabled') o.thinking = { type: 'disabled' };
  if (THINKING === 'adaptive') o.thinking = { type: 'adaptive' };
  if (EFFORT) o.effort = EFFORT;
  return o;
}

async function classifyBatch(batch: Card[]): Promise<{ results: Result[]; usage: UsageRow }> {
  const lines = batch.map((c) => JSON.stringify(cardForPrompt(c))).join('\n');
  const started = Date.now();
  const res = await generateObject({
    model: MODEL,
    schema: batchSchema,
    schemaName: 'JevCardClassifications',
    schemaDescription: 'One classification per input card, keyed by the card id.',
    // The rubric is identical for every batch, so it is marked for Anthropic prompt caching.
    instructions: {
      role: 'system',
      content: RUBRIC,
      providerOptions: { anthropic: { cacheControl: { type: 'ephemeral' } } },
    },
    messages: [
      {
        role: 'user',
        content: `Classify these ${batch.length} cards (one JSON object per line). Return exactly ${batch.length} results. ${KEY_NOTE}\n\n${lines}`,
      },
    ],
    temperature: 0,
    maxRetries: 2,
    maxOutputTokens: MAX_OUTPUT,
    // A batch normally returns in about 2 minutes. On 2026-09-23 a network drop left five
    // requests hanging for 30 minutes with no error, so each call has a hard deadline;
    // an aborted batch is re-queued like any other failure.
    abortSignal: AbortSignal.timeout(CALL_TIMEOUT_MS),
    providerOptions: { anthropic: anthropicOptions() } as never,
  });
  const ms = Date.now() - started;
  const u = res.usage as typeof res.usage & { outputTokenDetails?: { reasoningTokens?: number }; reasoningTokens?: number };
  const input = u.inputTokens ?? 0;
  const cacheRead = u.inputTokenDetails?.cacheReadTokens ?? 0;
  const cacheWrite = u.inputTokenDetails?.cacheWriteTokens ?? 0;
  const noCache = u.inputTokenDetails?.noCacheTokens ?? Math.max(0, input - cacheRead - cacheWrite);
  const output = u.outputTokens ?? 0;
  const reasoning = u.outputTokenDetails?.reasoningTokens ?? u.reasoningTokens;
  const tokens = { input, noCache, cacheRead, cacheWrite, output };
  const gw = (res.providerMetadata as Record<string, Record<string, unknown>> | undefined)?.gateway;
  return {
    results: res.object.results.map(toResult),
    usage: {
      at: new Date().toISOString(),
      model: MODEL,
      n: batch.length,
      returned: res.object.results.length,
      ...tokens,
      reasoning,
      usd: costOf(tokens),
      gatewayCost: gw?.cost,
      ms,
    },
  };
}

function chunk<T>(xs: T[], n: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < xs.length; i += n) out.push(xs.slice(i, i + n));
  return out;
}

function median(xs: number[]): number {
  if (xs.length === 0) return Number.NaN;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

async function main(): Promise<void> {
  console.log(
    `auth: ${authMode()} (name only); model ${MODEL}; rubric ${VERSION}; thinking ${THINKING}; effort ${EFFORT ?? 'default'}; ` +
      `max output ${MAX_OUTPUT}; concurrency ${CONCURRENCY}; out ${OUT}; usage ${USAGE}`,
  );
  if (authMode() === 'NONE') throw new Error('No Gateway credentials in the environment.');
  PRICE = await fetchPrice();
  console.log(`price $/M: input ${PRICE.input}, output ${PRICE.output}, cache read ${PRICE.cacheRead}, cache write ${PRICE.cacheWrite}`);

  // The rubric file is part of the Sonnet v2 record; other models leave it alone.
  if (IS_SONNET_DEFAULT) {
    mkdirSync('report', { recursive: true });
    writeFileSync(RUBRIC_MD, RUBRIC);
  }

  const { cards } = JSON.parse(readFileSync('data/cards.json', 'utf8')) as { cards: Card[] };
  const byId = new Map(cards.map((c) => [c.id, c]));
  const done = new Set(readJsonl<Result>(OUT).map((r) => r.id));
  const priorUsage = readJsonl<UsageRow>(USAGE);
  const tot = { input: 0, cacheRead: 0, cacheWrite: 0, output: 0, usd: 0 };
  for (const u of priorUsage) {
    tot.input += u.input;
    tot.cacheRead += u.cacheRead;
    tot.cacheWrite += u.cacheWrite;
    tot.output += u.output;
    tot.usd += u.usd;
  }
  const latencies: number[] = [];

  const only = IDS ? new Set(readJsonl<{ id: string }>(IDS).map((r) => r.id)) : null;
  let pending = cards.filter((c) => !done.has(c.id) && (!only || only.has(c.id))).map((c) => c.id);
  if (Number.isFinite(LIMIT)) pending = pending.slice(0, LIMIT);
  console.log(
    `${cards.length} cards, ${done.size} already classified, ${pending.length} to do; prior spend $${tot.usd.toFixed(3)}; cap $${MAX_USD}`,
  );
  const t0 = Date.now();

  let stopped = false;
  for (let round = 1; round <= ROUNDS && pending.length > 0 && !stopped; round += 1) {
    const batches = chunk(pending, BATCH);
    const missing: string[] = [];
    let next = 0;
    let finished = 0;
    let attempted = 0;
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
        const batch = ids.map((id) => byId.get(id)!);
        const wanted = new Set(ids);
        try {
          const { results, usage } = await classifyBatch(batch);
          const seen = new Set<string>();
          const good: Result[] = [];
          const stray: string[] = [];
          for (const r of results) {
            if (!wanted.has(r.id)) stray.push(r.id);
            else if (!seen.has(r.id) && !done.has(r.id)) {
              seen.add(r.id);
              good.push(r);
            }
          }
          if (good.length > 0) appendFileSync(OUT, `${good.map((r) => JSON.stringify(r)).join('\n')}\n`);
          for (const r of good) done.add(r.id);
          const miss = ids.filter((id) => !seen.has(id));
          missing.push(...miss);
          appendFileSync(USAGE, `${JSON.stringify({ ...usage, round, stray: stray.length, missing: miss.length })}\n`);
          tot.input += usage.input;
          tot.cacheRead += usage.cacheRead;
          tot.cacheWrite += usage.cacheWrite;
          tot.output += usage.output;
          tot.usd += usage.usd;
          latencies.push(usage.ms);
          finished += 1;
          if (miss.length > 0 || stray.length > 0) {
            console.log(`r${round} batch ${i + 1}: ${good.length}/${ids.length} ok, ${miss.length} missing, ${stray.length} stray`);
          }
        } catch (err) {
          missing.push(...ids);
          const msg = err instanceof Error ? err.message : String(err);
          const status = (err as { statusCode?: number } | null)?.statusCode;
          // NoObjectGeneratedError carries the finish reason and usage; a refusal shows up here.
          const e = err as { finishReason?: string; usage?: { inputTokens?: number; outputTokens?: number; inputTokenDetails?: { cacheReadTokens?: number; cacheWriteTokens?: number; noCacheTokens?: number } } };
          if (e.usage) {
            const input = e.usage.inputTokens ?? 0;
            const cacheRead = e.usage.inputTokenDetails?.cacheReadTokens ?? 0;
            const cacheWrite = e.usage.inputTokenDetails?.cacheWriteTokens ?? 0;
            const noCache = e.usage.inputTokenDetails?.noCacheTokens ?? Math.max(0, input - cacheRead - cacheWrite);
            const output = e.usage.outputTokens ?? 0;
            const t = { input, noCache, cacheRead, cacheWrite, output };
            const usd = costOf(t);
            appendFileSync(
              USAGE,
              `${JSON.stringify({ at: new Date().toISOString(), model: MODEL, n: ids.length, returned: 0, ...t, usd, round, failed: true, finishReason: e.finishReason })}\n`,
            );
            tot.input += input;
            tot.cacheRead += cacheRead;
            tot.cacheWrite += cacheWrite;
            tot.output += output;
            tot.usd += usd;
          }
          console.error(
            `r${round} batch ${i + 1} failed${status ? ` (HTTP ${status})` : ''}${e.finishReason ? ` (finish ${e.finishReason})` : ''}` +
              `${e.usage ? ` (tokens in ${e.usage.inputTokens ?? 0}, out ${e.usage.outputTokens ?? 0})` : ''}: ${msg.slice(0, 300)}`,
          );
          if (status === 401 || status === 403 || status === 402) {
            stopped = true;
            console.error('auth or budget failure; stopping');
          }
        }
        attempted += 1;
        if (attempted % PROGRESS_EVERY === 0 || attempted === batches.length) {
          const mins = (Date.now() - t0) / 60000;
          console.log(
            `r${round} progress: ${attempted}/${batches.length} batches (${finished} ok) | classified ${done.size}/${cards.length} | ` +
              `tokens in ${tot.input} (cache read ${tot.cacheRead}, write ${tot.cacheWrite}) out ${tot.output} | $${tot.usd.toFixed(3)} | ` +
              `p50 batch ${(median(latencies) / 1000).toFixed(1)}s | ${mins.toFixed(1)} min elapsed`,
          );
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
    console.log(`${pending.length} ids unclassified; logged to ${ERRORS}`);
  }
  console.log(
    `DONE: ${done.size}/${cards.length} classified | tokens in ${tot.input} (cache read ${tot.cacheRead}, write ${tot.cacheWrite}) out ${tot.output} | ` +
      `${MODEL} spend $${tot.usd.toFixed(3)} | p50 batch ${(median(latencies) / 1000).toFixed(1)}s this run`,
  );
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : err);
  process.exit(1);
});
