/**
 * Step 1: classify every OpenChamber Jev card with Claude Sonnet 5 against the
 * written rubric (./rubric.ts), through Vercel AI Gateway.
 *
 *   pnpm dlx tsx --env-file=.env.local scripts/classify-sonnet.ts
 *
 * Env knobs:
 *   RUBRIC_VERSION  v2 (default) or v1. v1 reproduces the first run
 *                   (data/classified-sonnet.jsonl, report/rubric-v1.md); v2 writes
 *                   data/classified-sonnet-v2.jsonl, data/usage-sonnet-v2.jsonl and
 *                   report/rubric.md.
 *   OUT, USAGE, ERRORS  override the output paths (used for pilots under data/pilot/).
 *   IDS             a .jsonl file whose rows carry "id": classify only those cards
 *                   (the v2 pilot used data/hand-labels-120.jsonl).
 *   LIMIT           classify at most N new cards.
 *   MAX_USD         stop launching batches once the spend recorded in the USAGE
 *                   file (including earlier runs into the same file) passes this;
 *                   default 8.5.
 *
 * Resumable: ids already in OUT are skipped. Each batch appends its results and
 * one usage row to USAGE as soon as it returns. Ids missing from a response are
 * re-queued for up to three rounds; ids still missing after that go to ERRORS.
 * Auth comes from the env file; the key is never printed.
 */
import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { generateObject } from 'ai';
import { z } from 'zod';
import { BASELINES, EVIDENCE, FRAMINGS, RUBRICS, TIERS } from './rubric';

const MODEL = 'anthropic/claude-sonnet-5';
const PRICE = { input: 2, output: 10, cacheRead: 0.2, cacheWrite: 2.5 }; // $ per million tokens (Gateway list)
const BATCH = 40;
const CONCURRENCY = 5;
const ROUNDS = 3;
const CALL_TIMEOUT_MS = 300_000;
const TEXT_CHARS = 700;
const MAX_USD = Number(process.env.MAX_USD ?? 8.5);
const LIMIT = process.env.LIMIT ? Number(process.env.LIMIT) : Infinity;

const VERSION = (process.env.RUBRIC_VERSION ?? 'v2') as keyof typeof RUBRICS;
if (!(VERSION in RUBRICS)) throw new Error(`RUBRIC_VERSION must be one of ${Object.keys(RUBRICS).join(', ')}`);
const { families: FAMILIES, rubric: RUBRIC } = RUBRICS[VERSION];
const SUFFIX = VERSION === 'v1' ? '' : `-${VERSION}`;
const OUT = process.env.OUT ?? `data/classified-sonnet${SUFFIX}.jsonl`;
const USAGE = process.env.USAGE ?? `data/usage-sonnet${SUFFIX}.jsonl`;
const ERRORS = process.env.ERRORS ?? `data/classified-sonnet${SUFFIX}.errors.jsonl`;
const RUBRIC_MD = VERSION === 'v1' ? 'report/rubric-v1.md' : 'report/rubric.md';
const IDS = process.env.IDS;

interface Card {
  id: string;
  t: string;
  x: string;
  chips: string[] | null;
  cat: string;
  u: string;
}

/**
 * What the model returns. Keys are abbreviated to cut output tokens (output is
 * about 70% of the cost); toResult() expands them to the rubric's field names
 * before anything is written.
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

function costOf(u: Omit<UsageRow, 'at' | 'n' | 'returned' | 'usd' | 'gatewayCost'>): number {
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

async function classifyBatch(batch: Card[]): Promise<{ results: Result[]; usage: UsageRow }> {
  const lines = batch.map((c) => JSON.stringify(cardForPrompt(c))).join('\n');
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
    maxOutputTokens: 12000,
    // A batch normally returns in about 2 minutes. On 2026-09-23 a network drop left five
    // requests hanging for 30 minutes with no error, so each call now has a hard deadline;
    // an aborted batch is re-queued like any other failure.
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
    results: res.object.results.map(toResult),
    usage: {
      at: new Date().toISOString(),
      n: batch.length,
      returned: res.object.results.length,
      ...tokens,
      usd: costOf(tokens),
      gatewayCost: gw?.cost,
    },
  };
}

function chunk<T>(xs: T[], n: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < xs.length; i += n) out.push(xs.slice(i, i + n));
  return out;
}

async function main(): Promise<void> {
  console.log(`auth: ${authMode()} (name only); rubric ${VERSION}; out ${OUT}; usage ${USAGE}`);
  if (authMode() === 'NONE') throw new Error('No Gateway credentials in the environment.');

  mkdirSync('report', { recursive: true });
  writeFileSync(RUBRIC_MD, RUBRIC);

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

  const only = IDS ? new Set(readJsonl<{ id: string }>(IDS).map((r) => r.id)) : null;
  let pending = cards.filter((c) => !done.has(c.id) && (!only || only.has(c.id))).map((c) => c.id);
  if (Number.isFinite(LIMIT)) pending = pending.slice(0, LIMIT);
  console.log(
    `${cards.length} cards, ${done.size} already classified, ${pending.length} to do; prior spend $${tot.usd.toFixed(3)}; cap $${MAX_USD}`,
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
          finished += 1;
          console.log(
            `r${round} batch ${i + 1}/${batches.length}: ${good.length}/${ids.length} ok, ${miss.length} missing, ${stray.length} stray | ` +
              `classified ${done.size}/${cards.length} | tokens in ${tot.input} (cache read ${tot.cacheRead}, write ${tot.cacheWrite}) out ${tot.output} | $${tot.usd.toFixed(3)}`,
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
    console.log(`${pending.length} ids unclassified; logged to ${ERRORS}`);
  }
  console.log(
    `DONE: ${done.size}/${cards.length} classified | tokens in ${tot.input} (cache read ${tot.cacheRead}, write ${tot.cacheWrite}) out ${tot.output} | Sonnet spend $${tot.usd.toFixed(3)}`,
  );
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : err);
  process.exit(1);
});
