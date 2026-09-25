/**
 * Step 2: classify every card's family with Jev itself, as a second classifier.
 *
 *   pnpm dlx tsx --env-file=.env.local scripts/classify-jev.ts
 *
 * One `experimental_evaluate` call per card: a single choice question whose
 * options are the 14 families and whose criteria are the same one-sentence
 * definitions Sonnet saw (./rubric.ts FAMILY_DEFINITIONS, without the examples).
 * The state is {title, text (first 500 chars), chips}; OpenChamber's category
 * is not given to Jev.
 *
 * Resumable: ids already in data/classified-jev.jsonl are skipped. Failures go
 * to data/classified-jev.errors.jsonl and are retried on the next run.
 * latency_ms is the wall time of the evaluate() call from this laptop, so it
 * includes the network round trip to the Gateway and any SDK retry.
 * Env knob: LIMIT (at most N new cards, for a pilot).
 */
import { appendFileSync, existsSync, readFileSync } from 'node:fs';
import { experimental_evaluate as evaluate } from 'ai';
import { FAMILIES, FAMILY_DEFINITIONS } from './rubric';

const MODEL = 'typesafe-ai/jev';
const PRICE_INPUT = 0.042; // $ per million input tokens (Gateway list; output is free)
const CONCURRENCY = 8;
const TEXT_CHARS = 500;
const LIMIT = process.env.LIMIT ? Number(process.env.LIMIT) : Infinity;

const OUT = 'data/classified-jev.jsonl';
const ERRORS = 'data/classified-jev.errors.jsonl';

interface Card {
  id: string;
  t: string;
  x: string;
  chips: string[] | null;
}

const INSTRUCTIONS = [
  "The state is one X post about Jev, TypeSafe AI's typed-decision model: its English title, the start of its text and any claims extracted from it.",
  'Which family best describes the primary application the author built or proposes with Jev?',
  'Classify what the decision is used for, not the technique or the model comparison.',
  "A benchmark of Jev on a named task belongs to that task's family. A benchmark with no application, and commentary, memes, news or tutorials, belong to other_or_meta.",
].join(' ');

const QUESTIONS = {
  family: { type: 'choice', instructions: INSTRUCTIONS, criteria: FAMILY_DEFINITIONS },
} as const;

function readJsonl<T>(path: string): T[] {
  if (!existsSync(path)) return [];
  return readFileSync(path, 'utf8')
    .split('\n')
    .filter((l) => l.trim())
    .map((l) => JSON.parse(l) as T);
}

function pct(sorted: number[], p: number): number {
  if (sorted.length === 0) return NaN;
  const i = Math.min(sorted.length - 1, Math.max(0, Math.ceil((p / 100) * sorted.length) - 1));
  return sorted[i];
}

async function main(): Promise<void> {
  const mode = process.env.AI_GATEWAY_API_KEY ? 'AI_GATEWAY_API_KEY' : process.env.VERCEL_OIDC_TOKEN ? 'VERCEL_OIDC_TOKEN' : 'NONE';
  console.log(`auth: ${mode} (name only)`);
  if (mode === 'NONE') throw new Error('No Gateway credentials in the environment.');

  const { cards } = JSON.parse(readFileSync('data/cards.json', 'utf8')) as { cards: Card[] };
  const done = new Set(readJsonl<{ id: string }>(OUT).map((r) => r.id));
  let todo = cards.filter((c) => !done.has(c.id));
  if (Number.isFinite(LIMIT)) todo = todo.slice(0, LIMIT);
  console.log(`${cards.length} cards, ${done.size} already classified, ${todo.length} to do`);

  let next = 0;
  let ok = 0;
  let failed = 0;
  let inputTokens = 0;
  const latencies: number[] = [];
  const started = Date.now();

  const worker = async (): Promise<void> => {
    while (true) {
      const i = next;
      next += 1;
      if (i >= todo.length) return;
      const c = todo[i];
      const state = { title: c.t, text: c.x.slice(0, TEXT_CHARS), chips: c.chips ?? [] };
      const t0 = performance.now();
      try {
        const res = await evaluate({ model: MODEL, state, questions: QUESTIONS, maxRetries: 1 });
        const latency = performance.now() - t0;
        const a = res.answers.family;
        if (!(FAMILIES as readonly string[]).includes(a.choice)) throw new Error(`unknown choice ${String(a.choice)}`);
        const probs = a.probabilities ?? null;
        const row = {
          id: c.id,
          family: a.choice,
          prob: probs ? probs[a.choice] : null,
          latency_ms: Math.round(latency),
          input_tokens: res.usage.inputTokens ?? null,
          probs,
          at: new Date().toISOString(),
        };
        appendFileSync(OUT, `${JSON.stringify(row)}\n`);
        ok += 1;
        inputTokens += res.usage.inputTokens ?? 0;
        latencies.push(latency);
      } catch (err) {
        failed += 1;
        const latency = performance.now() - t0;
        const status = (err as { statusCode?: number } | null)?.statusCode ?? null;
        const msg = (err instanceof Error ? err.message : String(err)).slice(0, 300);
        appendFileSync(ERRORS, `${JSON.stringify({ id: c.id, status, error: msg, latency_ms: Math.round(latency), at: new Date().toISOString() })}\n`);
        if (status === 401 || status === 403 || status === 402) {
          console.error(`auth or budget failure (HTTP ${status}): ${msg}; stopping`);
          process.exit(1);
        }
      }
      const n = ok + failed;
      if (n % 200 === 0 || n === todo.length) {
        const s = [...latencies].sort((a, b) => a - b);
        console.log(
          `${n}/${todo.length} | ok ${ok} failed ${failed} | p50 ${pct(s, 50).toFixed(0)} ms p95 ${pct(s, 95).toFixed(0)} ms | input tokens ${inputTokens} ($${((inputTokens * PRICE_INPUT) / 1e6).toFixed(4)}) | ${((Date.now() - started) / 1000).toFixed(0)} s`,
        );
      }
    }
  };
  await Promise.all(Array.from({ length: CONCURRENCY }, worker));

  const s = [...latencies].sort((a, b) => a - b);
  console.log(
    `DONE: ok ${ok}, failed ${failed} (error rate ${((100 * failed) / Math.max(1, ok + failed)).toFixed(2)}%) | ` +
      `latency p50 ${pct(s, 50).toFixed(0)} ms, p95 ${pct(s, 95).toFixed(0)} ms | input tokens ${inputTokens}, Jev spend $${((inputTokens * PRICE_INPUT) / 1e6).toFixed(4)}`,
  );
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : err);
  process.exit(1);
});
