#!/usr/bin/env node
// page-v3.mjs: "A week of Jev, sorted", restructured on 24 September 2026.
// Reads the CSVs and audit tables charts.mjs uses, plus four data files read at source on 24 Sep (the two
// gateways, list prices, the rivals) and the head-to-head results collected from the posts, draws the new
// figures with the helpers in lib.mjs, carries kept charts across from the current page with their number
// tables, and writes v3/index.html. charts.mjs and the current index.html are untouched.
// Run: node report/site/scripts/page-v3.mjs   (PUBLISHED and ARTICLE_URL in the environment set the byline date and the link to the opinion piece)
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { FOOTERS, THEMES, esc, fmt, pct, r1, sum, tw, wrap, tx, txs, lines, ln, rect, hbarD, vbarD, pathEl, legend, nice, frame } from './lib.mjs';

const SITE = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const REPORT = resolve(SITE, '..');
const PROJECT = resolve(REPORT, '..');
const DATA = join(REPORT, 'data');
const PDATA = join(PROJECT, 'data');
const OUT = join(SITE, 'v3');
const WIDE = 640, NARROW = 360;
const XML = '<?xml version="1.0" encoding="UTF-8"?>\n';

// ---------------------------------------------------------------- helpers
function parseCSV(text) {
  const rows = []; let row = [], field = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) { if (c === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else q = false; } else field += c; }
    else if (c === '"') q = true;
    else if (c === ',') { row.push(field); field = ''; }
    else if (c === '\n') { row.push(field); rows.push(row); row = []; field = ''; }
    else if (c !== '\r') field += c;
  }
  if (field || row.length) { row.push(field); rows.push(row); }
  const [h, ...rest] = rows.filter((r) => r.length > 1 || r[0] !== '');
  return rest.map((r) => Object.fromEntries(h.map((k, i) => [k, r[i] ?? ''])));
}
const csv = (name) => parseCSV(readFileSync(join(DATA, `${name}.csv`), 'utf8'));
const jsonf = (p) => JSON.parse(readFileSync(p, 'utf8'));
const num = Number;
const usd = (n) => `$${fmt(n)}`;
const usdShort = (n) => (n >= 1e6 ? `$${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)}M` : n >= 1e3 ? `$${(n / 1e3).toFixed(n >= 1e5 ? 0 : 1)}k` : `$${Math.round(n)}`);
const mShort = (n) => (n >= 1e12 ? `${(n / 1e12).toFixed(2)}T` : n >= 1e9 ? `${(n / 1e9).toFixed(0)}B` : n >= 1e6 ? `${(n / 1e6).toFixed(0)}M` : fmt(n));
const median = (xs) => { const s = [...xs].sort((a, b) => a - b); const m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
const xf = (v) => (v >= 100 ? `${Math.round(v)}x` : v >= 10 ? `${Math.round(v)}x` : `${v.toFixed(1).replace(/\.0$/, '')}x`);
const a = (href, text) => `<a href="${esc(href)}">${text}</a>`;
const tbl = (head, rows, cls = 'wrap') => `<div class="tablewrap"><table class="${cls}"><thead><tr>${head.map((h) => `<th scope="col">${h}</th>`).join('')}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c, i) => (i === 0 ? `<th scope="row">${c}</th>` : `<td>${c}</td>`)).join('')}</tr>`).join('')}</tbody></table></div>`;
const dayLabel = (iso) => `${Number(iso.slice(8, 10))} Sep`;
const problems = [];
const check = (cond, msg) => { if (!cond) problems.push(msg); };

// ---------------------------------------------------------------- data
const S = jsonf(join(REPORT, 'summary.json'));
const AE = Object.fromEntries(csv('13_audit_estimates').map((r) => [r.key, { value: num(r.value), lo: r.lo === '' ? null : num(r.lo), hi: r.hi === '' ? null : num(r.hi), k: r.k === '' ? null : num(r.k), n: r.n === '' ? null : num(r.n) }]));
const aud = (key, d = 0) => { const e = AE[key]; return e.lo === null ? pct(e.value, d) : `${pct(e.value, d)} (${(e.lo * 100).toFixed(d)} to ${(e.hi * 100).toFixed(d)})`; };
const BASE = S.use_case_base;
const perCard = csv('08_ladder_per_card');
check(perCard.length === BASE, `per-card rows ${perCard.length} should equal the use-case base ${BASE}`);
const tierOf = new Map();
for (const line of readFileSync(join(PDATA, 'classified-opus.jsonl'), 'utf8').split('\n')) { if (!line.trim()) continue; const r = JSON.parse(line); tierOf.set(String(r.id), r.tier); }
const stats = csv('06_attention_stats')[0];
const conc = csv('06_attention_concentration');
const top1 = conc.find((r) => r.views_top === '1%');
const chips = Object.fromEntries(csv('11_chip_multiples').map((r) => [r.claim.startsWith('cost') ? 'cost' : 'speed', r]));
const sub = csv('13_audit_substance');
const before = Object.fromEntries(sub.filter((r) => r.kind === 'before').map((r) => [r.key, num(r.posts)]));
const prodRows = csv('13_audit_production').filter((r) => r.holds === '1');
const OR = jsonf(join(PDATA, 'gateway-openrouter-2026-09-24.json'));
const VC = jsonf(join(PDATA, 'gateway-vercel-2026-09-24.json'));
const PR = jsonf(join(PDATA, 'gateway-prices-2026-09-24.json'));
const RV = jsonf(join(PDATA, 'rivals-2026-09-24.json'));
const LAST_DAY = '2026-09-23'; // 24 Sep is a partial day and is left out of every chart and sentence
const orDays = OR.days.filter((d) => d.date >= '2026-09-18' && d.date <= LAST_DAY);
const vcDays = VC.days.filter((d) => d.date >= '2026-09-17' && d.date <= LAST_DAY);
const orDay = (d) => OR.days.find((x) => x.date === d);
const vcDay = (d) => VC.days.find((x) => x.date === d);
const OR23 = orDay(LAST_DAY), OR18 = orDay('2026-09-18');
const V23 = vcDay(LAST_DAY), V17 = vcDay('2026-09-17');
const WK = OR['rankings_week_to_2026-09-23'];
const LUNA = WK['gpt-5.6-luna'], JEVWK = WK.jev;
const PUBLISHED = process.env.PUBLISHED || '25 September 2026';
const ARTICLE_URL = process.env.ARTICLE_URL || '#';
const TECHNICAL_URL = process.env.TECHNICAL_URL || '../index.html'; // publish/stage.sh sets technical/
const articleLink = ARTICLE_URL === '#' ? 'a separate piece' : a(ARTICLE_URL, 'a separate piece');
const L = {
  feed: 'https://jev.openchamber.dev', repo: 'https://github.com/mattheworiordan/jev-landscape', pong: 'https://jev-pong.ably.dev/how#other-models',
  or: 'https://openrouter.ai/typesafe/jev-1.13', orRank: 'https://openrouter.ai/rankings', vcExport: 'https://vercel.com/api/ai/leaderboard-export?dataset=models&modality=all&format=json',
  vcBlog: 'https://vercel.com/blog/ai-gateway-jev-model-launch', vcBoard: 'https://vercel.com/ai-gateway/leaderboards', vcPrice: 'https://vercel.com/ai-gateway/models/jev',
  orModels: 'https://openrouter.ai/api/v1/models', tsDocs: 'https://docs.typesafe.ai/models', tsStatus: 'https://status.typesafe.ai/incidents', launch: 'https://x.com/CompleteSkeptic/status/2099925682726002904',
  waitlist: 'https://x.com/CompleteSkeptic/status/2100454726462804333', noWaitlist: 'https://x.com/typesafeai/status/2101786156572823624', paused: 'https://x.com/typesafeai/status/2102281508950307159',
  npm: 'https://api.npmjs.org/downloads/point/last-week/@typesafe-ai/sdk', pypi: 'https://pypistats.org/packages/typesafe-sdk', gh: 'https://github.com/search?q=jev+created%3A%3E%3D2026-09-15&type=repositories',
  discord: 'https://discord.com/invite/typesafe', hn: 'https://news.ycombinator.com/item?id=49717558', awesome: 'https://github.com/yibie/awesome-jev', ship: 'https://www.shipwithjev.com',
  gitloom: 'https://gitloom.ai/blog/jev-in-production', unblocked: 'https://getunblocked.com/blog/jev-in-production-vs-cross-encoder/',
  survey: 'https://openchamber.dev/blog/jev-typesafe-ai/', a16z: 'https://a16z.com/llmflation-llm-inference-cost/', epoch: 'https://epoch.ai/data-insights/llm-inference-price-trends',
  jevbench: 'https://benchmarkheaven.com/jev-models', laya: 'https://huggingface.co/convaiinnovations/laya', layaMlx: 'https://github.com/mizorewww/laya-mlx', dabit: 'https://github.com/dabit3/jev-experiments',
  technical: TECHNICAL_URL, linkedin: 'https://www.linkedin.com/in/mattoriordan/', ably: 'https://ably.com',
  nearhere: 'https://nearhere.events/blog/typesafe-jev-mistral-gemini-event-validation', lindfors: 'https://lindfors.no/blog/a-first-look-at-typesafes-jev/', sniff: 'https://github.com/DanRWilloughby/snifftest',
  triage: 'https://dev.to/reachjalil/how-we-tuned-typesafe-jev-for-log-triage-without-alert-storms-1ei0', codealive: 'https://github.com/CodeAlive-AI/mastra-jev-moderation', rerank: 'https://github.com/anessbelbati/jev-rerank-bench',
  classmethod: 'https://dev.classmethod.jp/en/articles/jev-for-llm-model-routing/', hermes: 'https://github.com/anpicasso/hermes-jev-approvals', langwatch: 'https://langwatch.ai/instant-evals',
  every: 'https://every.to/also-true-for-humans/mini-vibe-check-typesafe-s-jev-judged-everything-i-ve-written-in-0-7-seconds', awlevin: 'https://github.com/awlevin/typesafe-computer-use',
  nutlope: 'https://x.com/nutlope/status/2100426999546184123', secbench: 'https://github.com/Gaurav-Gosain/jev-sec-bench', browseruse: 'https://github.com/browser-use/jev-ultrafast/blob/main/docs/performance.md', compaction: 'https://madewithjev.com/builds/instant-compaction',
  kwindla: 'https://x.com/kwindla/status/2101394993957274021', canvas: 'https://github.com/gaborishka/jev-canvas', livekit: 'https://github.com/livekit/agents/issues/7355',
};

// ---------------------------------------------------------------- the six groups
const GROUPS = [
  { key: 'data', name: 'Decisions about data', sub: 'classify, route, extract, rerank, judge, telemetry', fams: ['classification_routing_triage', 'search_rerank_extraction', 'evals_and_judging', 'data_and_telemetry'] },
  { key: 'games', name: 'Decisions inside games and control loops', sub: 'games, simulations, robots', fams: ['games_control_loops_simulation'] },
  { key: 'agents', name: 'Decisions inside agent loops', sub: 'gate a tool call, pick the next browser action, prune context', fams: ['agent_harness_and_tool_gating', 'browser_and_computer_use', 'compaction_and_context'] },
  { key: 'people', name: 'Decisions about what a person just said or typed', sub: 'moderation, voice, live chat, collaboration', fams: ['moderation_and_guardrails', 'voice_and_turn_taking', 'live_chat_streams_events', 'collaboration_and_typing'] },
  { key: 'money', name: 'Decisions about money', sub: 'trading bots', fams: ['trading_and_markets'] },
  { key: 'none', name: 'No decision stated', sub: 'meta, benchmarks of the model, wrappers', fams: ['other_or_meta'] },
];
const STEPS = [
  { key: 'no_measurement', label: 'No measurement', role: 'g2' },
  { key: 'measured_demo', label: 'Measured demo', role: 'blueLo' },
  { key: 'prod_not', label: 'Labeled production, not confirmed', role: 'blue' },
  { key: 'prod_ok', label: 'Production, confirmed by the audit', role: 'accent' },
];
const stepOf = (r) => (r.ladder === 'measured_production' ? (r.audit_production === 'holds' ? 'prod_ok' : 'prod_not') : r.ladder);
for (const g of GROUPS) {
  const rs = perCard.filter((r) => g.fams.includes(r.family));
  g.posts = rs.length; g.share = rs.length / BASE;
  g.steps = Object.fromEntries(STEPS.map((s) => [s.key, rs.filter((r) => stepOf(r) === s.key).length]));
  g.measured = (g.steps.measured_demo + g.steps.prod_not + g.steps.prod_ok) / g.posts;
  g.live = rs.filter((r) => r.realtime_infra === 'True').length / g.posts;
  g.fast = rs.filter((r) => ['frame', 'feel', 'turn'].includes(tierOf.get(String(r.id)))).length / g.posts;
}
check(sum(GROUPS.map((g) => g.posts)) === BASE, 'the six groups cover every post once');
const famsSeen = new Set(perCard.map((r) => r.family));
check([...famsSeen].every((f) => GROUPS.some((g) => g.fams.includes(f))), 'every family is in a group');
const stepTot = Object.fromEntries(STEPS.map((s) => [s.key, sum(GROUPS.map((g) => g.steps[s.key]))]));
check(stepTot.prod_ok === prodRows.length, 'confirmed production posts match the audit table');
check(before.unavailable === 0, 'none of the candidate builds did something unavailable before');
const G = Object.fromEntries(GROUPS.map((g) => [g.key, g]));

// ---------------------------------------------------------------- the head-to-heads: Jev against the model it was compared with, same task, numbers published
// Multiples are the comparison model's figure divided by Jev's, from each source as read; "small" is the vendor's small or cheap tier.
const H2H = [
  { who: 'Jev Pong (me)', task: 'the next paddle move, 30 states', vs: 'Ministral 3B', kind: 'small', cost: 7.0 / 2.5, lat: 396 / 222, acc: 'Jev 28 of 29, Ministral 26 of 30', link: L.pong },
  { who: 'Jev Pong (me)', task: 'the next paddle move, 30 states', vs: 'GPT-5.4 Nano', kind: 'small', cost: 25 / 2.5, lat: 799 / 222, acc: 'Jev 28 of 29, Nano 29 of 30', link: L.pong },
  { who: 'Jev Pong (me)', task: 'the next paddle move, 30 states', vs: 'Claude Haiku 4.5', kind: 'small', cost: 110 / 2.5, lat: 791 / 222, acc: 'Jev 28 of 29, Haiku 30 of 30', link: L.pong },
  { who: 'Jon Reed, Near Here', task: 'reject unsuitable event listings, 50 cases', vs: 'Mistral Small 4', kind: 'small', cost: 0.370 / 0.043, lat: 2.90 / 0.59, acc: 'Jev 96%, Mistral 84%', link: L.nearhere },
  { who: 'Jon Reed, Near Here', task: 'reject unsuitable event listings, 50 cases', vs: 'Gemini 3.5 Flash-Lite', kind: 'small', cost: 2.496 / 0.043, lat: 3.40 / 0.59, acc: 'Jev 96%, Gemini 86%', link: L.nearhere },
  { who: 'Emil Lindfors', task: '11 typed questions over 24 hearing responses', vs: 'DeepSeek V4.1 Flash', kind: 'small', cost: 1.31 / 0.22, lat: 2.7 / 0.32, acc: 'stance 20 of 24 each; substance Jev 19, DeepSeek 14', link: L.lindfors },
  { who: 'Dan Willoughby, Sniff Test', task: 'ten boolean questions a paragraph, 54 clean paragraphs', vs: 'Claude Haiku 4.5', kind: 'small', cost: 0.43 / 0.0129, lat: 1971 / 182, acc: 'false flags: Jev 1, Haiku 37', link: L.sniff },
  { who: 'Jalil Laaraichi, OpenWork', task: 'page, ticket or ignore over 8,000 log lines', vs: 'GPT-5.6 Luna', kind: 'small', cost: 0.320 / 0.062, lat: null, acc: 'Jev 100% recall and 0 false pages, Luna 96.2%', link: L.triage },
  { who: 'CodeAlive', task: 'block or allow agent input, 58 messages', vs: 'gpt-oss-120b', kind: 'small', cost: 4, lat: 1.97 / 0.415, acc: 'Jev 9 of 9 hostile blocked and 0 of 49 real blocked; gpt-oss 8 or 9 of 9', link: L.codealive },
  { who: 'anessbelbati, rerank bench', task: 'search reranking across 14 datasets', vs: 'Cohere Rerank 4 Pro', kind: 'small', cost: 2.51 / 0.45, lat: 844 / 422, acc: 'nDCG@10 0.692 against 0.691', link: L.rerank },
  { who: 'Taishi Morinaga, Classmethod', task: 'four-tier model routing, 40 calls', vs: 'Gemini 3.5 Flash', kind: 'small', cost: null, lat: 2.1 / 0.66, acc: 'Jev 10 of 10 on every pattern', link: L.classmethod },
  { who: 'anpicasso, Hermes approvals', task: 'approve, deny or escalate 153 real commands', vs: 'a small chat model', kind: 'small', cost: null, lat: 3968 / 405, acc: '10 escalations to a human instead of 42', link: L.hermes },
  { who: 'LangWatch', task: 'judge 300 support conversations against human labels', vs: 'Claude Opus 5', kind: 'frontier', cost: 31.13 / 0.32, lat: 600 / 73, acc: 'Jev 97% agreement, Opus 91%', link: L.langwatch },
  { who: 'Dan Shipper, Every', task: 'four writing checks over 12 passages', vs: 'Claude Fable 5.1', kind: 'frontier', cost: 580, lat: 8.83 / 0.35, acc: 'Jev 6 of 7 planted defects, Fable 7 of 7', link: L.every },
  { who: 'awlevin, computer use', task: 'the next action from an OCR of the screen', vs: 'Claude Opus 5', kind: 'frontier', cost: 0.032 / 0.0002, lat: 5.2 / 0.38, acc: 'not measured', link: L.awlevin },
  { who: 'Dan Willoughby, Sniff Test', task: 'ten boolean questions a paragraph, 54 clean paragraphs', vs: 'Claude Opus 5', kind: 'frontier', cost: 3.08 / 0.0129, lat: 6532 / 182, acc: 'false flags: Jev 1, Opus 0', link: L.sniff },
];
const small = H2H.filter((h) => h.kind === 'small'), frontier = H2H.filter((h) => h.kind === 'frontier');
const smallCost = small.filter((h) => h.cost).map((h) => h.cost), smallLat = small.filter((h) => h.lat).map((h) => h.lat);
const frontierCost = frontier.map((h) => h.cost), frontierLat = frontier.map((h) => h.lat);
const noPong = small.filter((h) => !h.who.startsWith('Jev Pong'));
const M = { smallCostMedNoPong: median(noPong.filter((h) => h.cost).map((h) => h.cost)), smallLatMedNoPong: median(noPong.filter((h) => h.lat).map((h) => h.lat)), smallCostMed: median(smallCost), smallLatMed: median(smallLat), smallCostLo: Math.min(...smallCost), smallCostHi: Math.max(...smallCost), smallLatLo: Math.min(...smallLat), smallLatHi: Math.max(...smallLat), frontierCostLo: Math.min(...frontierCost), frontierCostHi: Math.max(...frontierCost), frontierLatLo: Math.min(...frontierLat), frontierLatHi: Math.max(...frontierLat) };
const LAUNCH = { costLo: 40, costHi: 400, speedLo: 20, speedHi: 200 }; // TypeSafe's launch post, against frontier LLMs

// ---------------------------------------------------------------- footers: one line on the page, the full credit only in the files
const SOURCE_CORPUS = `Source: jev.openchamber.dev, ${fmt(S.posts)} posts 16 to 23 Sep 2026 (UTC), classified with Claude Opus 5.5, 1,681 posts audited blind by Grok; analysis by Matthew O'Riordan`;
const DISCLOSURE = 'Disclosure: the author is CEO of Ably, a realtime infrastructure company.';
FOOTERS.file.push('', DISCLOSURE);
FOOTERS.page.push('');
const withFooter = (fileSource, pageSource, fn) => { FOOTERS.file[0] = fileSource; FOOTERS.page[0] = pageSource; return fn(); };

// ---------------------------------------------------------------- panel helpers
const panelTitle = (T, x, y, s, narrow, maxW) => lines(T, x, y, s, maxW, { size: narrow ? 12 : 12.5, lh: 15, weight: 700 }).svg;
const panelTitleH = (s, narrow, maxW) => (wrap(s, maxW, narrow ? 12 : 12.5, 700).length - 1) * 15;
const dot = (T, cx, cy, r, role, title) => `<circle cx="${r1(cx)}" cy="${r1(cy)}" r="${r}" ${T.mode === 'vars' ? `style="fill:var(--v-${role})"` : `fill="${T[role]}"`}>${title ? `<title>${esc(title)}</title>` : ''}</circle>`;
const diamond = (T, cx, cy, r, role, title) => `<path d="M${r1(cx)} ${r1(cy - r)}l${r} ${r}l${-r} ${r}l${-r} ${-r}z" ${T.mode === 'vars' ? `style="fill:var(--v-${role})"` : `fill="${T[role]}"`}>${title ? `<title>${esc(title)}</title>` : ''}</path>`;
function vBarPanel(T, { x0, x1, y0, h, items, narrow, fmtVal, ymax, ticks, tickFmt, note }) {
  const out = []; const inner = x1 - x0; const n = items.length;
  const gap = narrow ? 6 : 10; const bw = (inner - 44 - (n - 1) * gap) / n; const xs = x0 + 44; const yb = y0 + h;
  for (const t of ticks) { const y = yb - (t / ymax) * h; out.push(ln(T, xs, y, x1, y, 'grid')); out.push(tx(T, xs - 6, y + 4, tickFmt(t), { size: 10.5, role: 'muted', anchor: 'end' })); }
  items.forEach((it, i) => {
    const x = xs + i * (bw + gap); const bh = (it.value / ymax) * h;
    out.push(pathEl(T, vbarD(x, yb, bw, bh, 3), 'blue', `${it.label}: ${fmtVal(it.value)}`));
    out.push(tx(T, x + bw / 2, yb - bh - 5, fmtVal(it.value), { size: narrow ? 10 : 11, weight: 600, anchor: 'middle' }));
    out.push(tx(T, x + bw / 2, yb + 14, it.label, { size: narrow ? 10 : 11, role: 'ink2', anchor: 'middle' }));
  });
  out.push(ln(T, xs, yb, x1, yb, 'axis'));
  let y = yb + 20;
  if (note) { const b = lines(T, xs, y + 2, note, x1 - xs, { size: 10.5, lh: 14, role: 'muted' }); out.push(b.svg); y += b.h + 6; }
  return { svg: out.join(''), y };
}

// ---------------------------------------------------------------- figure: the gateways
const chartGateways = {
  key: '13', file: '13-the-gateways',
  title: "Jev became a quarter of Vercel's gateway requests in a week, and 2% of its tokens",
  subtitle: 'OpenRouter requests a day, 18 to 23 Sep; Vercel AI Gateway share of all requests and of all tokens, 17 to 23 Sep',
  desc: `OpenRouter served ${mShort(OR23.requests)} Jev requests on 23 Sep. Jev was ${V23.requests_share_pct.toFixed(0)}% of Vercel AI Gateway requests and ${V23.tokens_share_pct.toFixed(1)}% of its tokens that day.`,
  body(T, { x0, x1, y0, narrow }) {
    const out = []; let y = y0;
    let t = 'OpenRouter: Jev requests a day, in millions';
    out.push(panelTitle(T, x0, y, t, narrow, x1 - x0)); y += 24 + panelTitleH(t, narrow, x1 - x0);
    const items = orDays.map((d) => ({ label: dayLabel(d.date), value: d.requests / 1e6 }));
    const nm = nice(Math.max(...items.map((i) => i.value)));
    const pnl = vBarPanel(T, { x0, x1, y0: y, h: narrow ? 120 : 150, items, narrow, fmtVal: (v) => `${Math.round(v)}M`, ymax: nm.max, ticks: [0, nm.step, nm.step * 2, nm.step * 3].filter((v) => v <= nm.max), tickFmt: (v) => `${v}M`, note: 'Requests are API calls, not decisions; one call can carry several questions.' });
    out.push(pnl.svg); y = pnl.y + 14;
    t = narrow ? "Vercel AI Gateway: Jev's share of requests and of tokens" : "Vercel AI Gateway: Jev's share of all requests, and of all tokens";
    out.push(panelTitle(T, x0, y, t, narrow, x1 - x0)); y += 24 + panelTitleH(t, narrow, x1 - x0);
    const days = vcDays; const h = narrow ? 110 : 130; const xs = x0 + 44; const xe = x1 - (narrow ? 84 : 104); const yb = y + h; const ymax = 30;
    for (const v of [0, 10, 20, 30]) { const yy = yb - (v / ymax) * h; out.push(ln(T, xs, yy, xe, yy, 'grid')); out.push(tx(T, xs - 6, yy + 4, `${v}%`, { size: 10.5, role: 'muted', anchor: 'end' })); }
    const px = (i) => xs + (i / (days.length - 1)) * (xe - xs); const py = (v) => yb - (v / ymax) * h;
    for (const [metric, role, label] of [['requests_share_pct', 'blue', 'of requests'], ['tokens_share_pct', 'g3', 'of tokens']]) {
      const d = days.map((dd, i) => `${i ? 'L' : 'M'}${r1(px(i))} ${r1(py(dd[metric]))}`).join('');
      out.push(`<path d="${d}" fill="none" stroke-width="2.5" stroke-linejoin="round" ${T.mode === 'vars' ? `style="stroke:var(--v-${role})"` : `stroke="${T[role]}"`}/>`);
      days.forEach((dd, i) => out.push(dot(T, px(i), py(dd[metric]), 3, role, `${dayLabel(dd.date)}: ${dd[metric].toFixed(1)}% ${label}`)));
      const last = days[days.length - 1];
      out.push(tx(T, xe + 6, py(last[metric]) + 4, `${last[metric].toFixed(metric === 'tokens_share_pct' ? 1 : 0)}% ${narrow ? label.replace('of ', '') : label}`, { size: narrow ? 10 : 11, weight: 600, role: role === 'g3' ? 'ink2' : 'ink' }));
    }
    days.forEach((dd, i) => { if (!narrow || i % 2 === 0) out.push(tx(T, px(i), yb + 14, dayLabel(dd.date), { size: narrow ? 10 : 11, role: 'ink2', anchor: 'middle' })); });
    out.push(ln(T, xs, yb, xe, yb, 'axis')); y = yb + 22;
    const b = lines(T, xs, y, 'Jev was free on Vercel until 25 Sep, which flatters its share there. Vercel publishes shares, not counts.', xe - xs + 40, { size: 10.5, lh: 14, role: 'muted' });
    out.push(b.svg); y += b.h;
    return { svg: out.join(''), y };
  },
};

// ---------------------------------------------------------------- figure: weighted by money
const promptTok = OR23.prompt_tokens; const reqs = OR23.requests; const OUT_TOK = 10;
const priced = Object.entries(PR.usd_per_million).map(([name, pr]) => ({ name, usd: name === 'Jev' ? OR23.usd : (promptTok * pr.prompt + reqs * OUT_TOK * pr.completion) / 1e6 })).sort((x, y) => x.usd - y.usd);
const jevBill = OR23.usd;
const pricedOf = (n) => priced.find((x) => x.name === n).usd;
const chartMoney = {
  key: '14', file: '14-weighted-by-money',
  title: 'More requests than GPT-5.6 Luna, for an eighth of the money',
  subtitle: "OpenRouter, week to 23 Sep: Jev against GPT-5.6 Luna; then one day's Jev tokens priced on other models",
  desc: `Jev ${mShort(JEVWK.requests)} requests, ${mShort(JEVWK.tokens)} tokens, ${usd(JEVWK.usd)}; GPT-5.6 Luna ${mShort(LUNA.requests)}, ${mShort(LUNA.tokens)}, ${usd(LUNA.usd)}. On 23 Sep Jev's ${mShort(promptTok)} prompt tokens cost ${usd(jevBill)}.`,
  body(T, { x0, x1, y0, narrow }) {
    const out = []; let y = y0;
    let t = 'Week to 23 Sep on OpenRouter: Jev (blue) against GPT-5.6 Luna (grey)';
    out.push(panelTitle(T, x0, y, t, narrow, x1 - x0)); y += 26 + panelTitleH(t, narrow, x1 - x0);
    const rowsM = [['Requests', JEVWK.requests, LUNA.requests, mShort], ['Tokens', JEVWK.tokens, LUNA.tokens, mShort], ['Spend', JEVWK.usd, LUNA.usd, usdShort]];
    const lw = narrow ? 64 : 80; const bx = x0 + lw; const bw = x1 - bx - (narrow ? 44 : 60); const bh = narrow ? 11 : 13;
    for (const [label, j, l, f] of rowsM) {
      const mx = Math.max(j, l);
      out.push(tx(T, x0, y + bh + 1, label, { size: 12, weight: 600 }));
      out.push(tx(T, x0, y + 2 * bh + 6, `Jev is ${(j / l) < 1 ? `${Math.round((j / l) * 100)}%` : `${(j / l).toFixed(1)}x`}`, { size: 10.5, role: 'muted' }));
      out.push(pathEl(T, hbarD(bx, y, (j / mx) * bw, bh, 3), 'blue', `Jev: ${f(j)}`));
      out.push(tx(T, bx + (j / mx) * bw + 6, y + bh - 2, f(j), { size: 11, weight: 600 }));
      y += bh + 3;
      out.push(pathEl(T, hbarD(bx, y, (l / mx) * bw, bh, 3), 'g2', `GPT-5.6 Luna: ${f(l)}`));
      out.push(tx(T, bx + (l / mx) * bw + 6, y + bh - 2, f(l), { size: 11, role: 'ink2' }));
      y += bh + (narrow ? 12 : 14);
    }
    y += 6;
    t = `What 23 Sep's Jev tokens (${mShort(promptTok)} prompt tokens) would cost on other models, at list price`;
    out.push(panelTitle(T, x0, y, t, narrow, x1 - x0)); y += 34 + panelTitleH(t, narrow, x1 - x0);
    const SHORT = { 'DeepSeek V4 Flash 0731': 'DeepSeek V4 Flash', 'Gemini 3.5 Flash-Lite': 'Gemini Flash-Lite', 'Claude Haiku 4.5': 'Haiku 4.5', 'Claude Fable 5.1': 'Fable 5.1' };
    const lw2 = narrow ? 104 : 132; const ax0 = x0 + lw2; const ax1 = x1 - (narrow ? 74 : 96);
    const lo = 1e4, hi = 1e7; const lx = (v) => ax0 + ((Math.log10(v) - Math.log10(lo)) / (Math.log10(hi) - Math.log10(lo))) * (ax1 - ax0);
    for (const [v, tl] of [[1e4, '$10k'], [1e5, '$100k'], [1e6, '$1M'], [1e7, '$10M']]) { out.push(ln(T, lx(v), y, lx(v), y + priced.length * 20 - 4, 'grid')); out.push(tx(T, lx(v), y - 6, tl, { size: 10.5, role: 'muted', anchor: 'middle' })); }
    for (const it of priced) {
      const yy = y + 8; const isJev = it.name === 'Jev';
      out.push(tx(T, ax0 - 8, yy + 4, narrow ? (SHORT[it.name] || it.name) : it.name, { size: narrow ? 10.5 : 11.5, weight: isJev ? 700 : 400, anchor: 'end' }));
      out.push(ln(T, ax0, yy, lx(Math.max(it.usd, lo)), yy, isJev ? 'accent' : 'blueLo', 2));
      out.push(dot(T, lx(Math.max(it.usd, lo)), yy, 5, isJev ? 'accent' : 'blue', `${it.name}: ${usd(it.usd)}, ${(it.usd / jevBill).toFixed(1)}x Jev's bill`));
      out.push(tx(T, lx(Math.max(it.usd, lo)) + 9, yy + 4, `${usdShort(it.usd)} · ${isJev ? 'billed' : xf(it.usd / jevBill)}`, { size: narrow ? 10 : 11, weight: isJev ? 700 : 400, role: isJev ? 'ink' : 'ink2' }));
      y += 20;
    }
    y += 4;
    const b = lines(T, ax0, y, `Same prompt tokens, plus ${OUT_TOK} output tokens a request for the chat models: a floor for models that think before answering. A price comparison only; nobody has run these tasks on those models.`, x1 - ax0, { size: 10.5, lh: 14, role: 'muted' });
    out.push(b.svg); y += b.h;
    return { svg: out.join(''), y };
  },
};

// ---------------------------------------------------------------- figure: the six groups
const chartGroups = {
  key: '15', file: '15-what-people-built-in-six-groups',
  title: 'A third of the posts are decisions about data, and a fifth are games',
  subtitle: `${fmt(BASE)} posts in six groups by what the decision is about, shaded by what each post measured`,
  desc: GROUPS.map((g) => `${g.name}: ${fmt(g.posts)} posts, ${pct(g.share, 0)}.`).join(' '),
  body(T, { x0, x1, y0, narrow }) {
    const out = []; let y = y0;
    const lg = legend(T, STEPS.map((s) => ({ label: s.label, role: s.role })), x0, x1, y, { size: 11 });
    out.push(lg.svg); y = lg.y + 8;
    const maxPosts = Math.max(...GROUPS.map((g) => g.posts)); const bh = narrow ? 16 : 18;
    const labelW = Math.max(...GROUPS.map((g) => tw(`${fmt(g.posts)} posts · ${pct(g.share, 0)} · ${pct(g.measured, 0)} measured`, narrow ? 10 : 11, 600))) + 12;
    for (const g of GROUPS) {
      if (narrow) { out.push(tx(T, x0, y + 12, g.name, { size: 11.5, weight: 700 })); out.push(tx(T, x0, y + 26, g.sub, { size: 10.5, role: 'muted' })); y += 32; }
      else { out.push(txs(T, x0, y + 12, [{ s: g.name, weight: 700 }, { s: `  ${g.sub}`, role: 'muted', size: 11 }], { size: 12.5 })); y += 18; }
      let x = x0; const w = (g.posts / maxPosts) * (x1 - x0 - labelW);
      for (const s of STEPS) { const sw = (g.steps[s.key] / g.posts) * w; if (sw > 0) { out.push(rect(T, x, y, sw, bh, s.role).replace('/>', `><title>${esc(`${g.name}, ${s.label.toLowerCase()}: ${fmt(g.steps[s.key])} posts`)}</title></rect>`)); x += sw; } }
      out.push(txs(T, x0 + w + 8, y + bh - 4, [{ s: `${fmt(g.posts)} posts`, weight: 600 }, { s: ` · ${pct(g.share, 0)} · ${pct(g.measured, 0)} measured`, role: 'ink2' }], { size: narrow ? 10 : 11 }));
      y += bh + (narrow ? 14 : 16);
    }
    return { svg: out.join(''), y };
  },
};

// ---------------------------------------------------------------- figure: announced, claimed, measured
function rangeRow(T, { y, x0, x1, lx, label, lo, hi, mid, role, narrow, note }) {
  const out = []; const lw = narrow ? 118 : 180; const yy = y + 9;
  const b = lines(T, x0, y + 1, label, lw - 10, { size: narrow ? 10.5 : 11.5, lh: 13, weight: 600 });
  out.push(b.svg);
  out.push(`<rect x="${r1(lx(lo))}" y="${r1(yy - 5)}" width="${r1(lx(hi) - lx(lo))}" height="10" rx="5" ${T.mode === 'vars' ? `style="fill:var(--v-${role})"` : `fill="${T[role]}"`}><title>${esc(`${label}: ${xf(lo)} to ${xf(hi)}${mid ? `, median ${xf(mid)}` : ''}`)}</title></rect>`);
  if (mid) out.push(dot(T, lx(mid), yy, 4.5, 'ink', `median ${xf(mid)}`));
  out.push(tx(T, lx(hi) + 8, yy + 4, `${xf(lo)} to ${xf(hi)}${mid ? `, median ${xf(mid)}` : ''}`, { size: narrow ? 10 : 11, role: 'ink2' }));
  if (note) out.push(tx(T, x0, y + 1 + b.h + 12, note, { size: 10, role: 'muted' }));
  return { svg: out.join(''), y: y + Math.max(b.h, 12) + (note ? 30 : 16) };
}
const chartClaims = {
  key: '17', file: '17-announced-claimed-measured',
  title: `TypeSafe's 40 to 400x cheaper is against frontier models. Against comparable small models, the measured median is ${xf(M.smallCostMed)}.`,
  subtitle: 'Cost and speed multiples: the launch claim, what the posts claimed, and what the published head-to-heads measured',
  desc: `Launch claim ${LAUNCH.costLo} to ${LAUNCH.costHi}x cheaper and ${LAUNCH.speedLo} to ${LAUNCH.speedHi}x faster against frontier models. Posts: median ${xf(num(chips.cost.median))} and ${xf(num(chips.speed.median))}. Head-to-heads against small models: cost ${xf(M.smallCostLo)} to ${xf(M.smallCostHi)}, median ${xf(M.smallCostMed)}; latency ${xf(M.smallLatLo)} to ${xf(M.smallLatHi)}, median ${xf(M.smallLatMed)}.`,
  body(T, { x0, x1, y0, narrow }) {
    const out = []; let y = y0;
    const lw = narrow ? 118 : 180; const ax0 = x0 + lw; const ax1 = x1 - (narrow ? 96 : 140);
    const lo = 1, hi = 1000; const lx = (v) => ax0 + ((Math.log10(Math.min(Math.max(v, lo), hi)) - Math.log10(lo)) / (Math.log10(hi) - Math.log10(lo))) * (ax1 - ax0);
    for (const [panel, rows] of [
      ['Cheaper by', [
        { label: 'TypeSafe, launch post', lo: LAUNCH.costLo, hi: LAUNCH.costHi, role: 'g2', note: 'against frontier LLMs' },
        { label: `The posts' claims (${chips.cost.chips} chips)`, lo: num(chips.cost.p25), hi: num(chips.cost.p75), mid: num(chips.cost.median), role: 'blueLo', note: 'middle half and median; mostly against frontier LLMs' },
        { label: `Measured, against a frontier model (${frontier.length})`, lo: M.frontierCostLo, hi: M.frontierCostHi, role: 'g3' },
        { label: `Measured, against a small model (${smallCost.length})`, lo: M.smallCostLo, hi: M.smallCostHi, mid: M.smallCostMed, role: 'blue' },
      ]],
      ['Faster by', [
        { label: 'TypeSafe, launch post', lo: LAUNCH.speedLo, hi: LAUNCH.speedHi, role: 'g2', note: 'against frontier LLMs' },
        { label: `The posts' claims (${chips.speed.chips} chips)`, lo: num(chips.speed.p25), hi: num(chips.speed.p75), mid: num(chips.speed.median), role: 'blueLo', note: 'middle half and median' },
        { label: `Measured, against a frontier model (${frontierLat.length})`, lo: M.frontierLatLo, hi: M.frontierLatHi, role: 'g3' },
        { label: `Measured, against a small model (${smallLat.length})`, lo: M.smallLatLo, hi: M.smallLatHi, mid: M.smallLatMed, role: 'blue' },
      ]],
    ]) {
      out.push(tx(T, x0, y + 12, panel, { size: narrow ? 12 : 12.5, weight: 700 })); y += 26;
      for (const v of [1, 10, 100, 1000]) { out.push(ln(T, lx(v), y - 4, lx(v), y + rows.length * 34, 'grid')); out.push(tx(T, lx(v), y - 8, `${v}x`, { size: 10, role: 'muted', anchor: 'middle' })); }
      y += 4;
      for (const r of rows) { const rr = rangeRow(T, { y, x0, x1, lx, narrow, ...r }); out.push(rr.svg); y = rr.y; }
      y += 10;
    }
    const b = lines(T, x0, y, 'The launch claim and most chips compare with frontier models; the measured rows are every head-to-head with published numbers I could find, listed under the chart. Accuracy is in the table: Jev was at or above the small model on most bounded questions.', x1 - x0, { size: 10.5, lh: 14, role: 'muted' });
    out.push(b.svg); y += b.h;
    return { svg: out.join(''), y };
  },
};

// ---------------------------------------------------------------- figure: Jev against the model it was compared with, by task
const chartH2H = {
  key: '18', file: '18-jev-against-the-model-it-was-compared-with',
  title: `Against small models the median gap is ${xf(M.smallCostMed)} on cost and ${xf(M.smallLatMed)} on latency; against frontier models it is 100x and more`,
  subtitle: 'Every published head-to-head found: how many times cheaper and faster Jev was than the model it was compared with, on the same task',
  desc: `${H2H.length} comparisons from ${new Set(H2H.map((h) => h.who)).size} sources. Blue: against a small model. Grey: against a frontier model.`,
  body(T, { x0, x1, y0, narrow }) {
    const out = []; let y = y0;
    const lg = legend(T, [{ label: 'cheaper by (against a small model)', role: 'blue', kind: 'dot' }, { label: 'faster by', role: 'blue', kind: 'diamond' }, { label: 'against a frontier model', role: 'g3', kind: 'dot' }], x0, x1, y, { size: 11 });
    out.push(lg.svg); y = lg.y + 10;
    const lw = narrow ? 128 : 210; const ax0 = x0 + lw; const ax1 = x1 - 12;
    const lo = 1, hi = 1000; const lx = (v) => ax0 + ((Math.log10(Math.min(Math.max(v, lo), hi)) - Math.log10(lo)) / (Math.log10(hi) - Math.log10(lo))) * (ax1 - ax0);
    const rows = [...H2H].sort((p, q) => (p.kind === q.kind ? (p.cost || p.lat) - (q.cost || q.lat) : p.kind === 'small' ? -1 : 1));
    const labelOf = (h) => `${h.who.split(',')[0]} vs ${h.vs}`;
    const rowH = (h) => Math.max(narrow ? 30 : 22, wrap(labelOf(h), lw - 10, narrow ? 9.5 : 10.5, 500).length * 12 + 10);
    const total = sum(rows.map(rowH));
    for (const v of [1, 10, 100, 1000]) { out.push(ln(T, lx(v), y, lx(v), y + total - 4, 'grid')); out.push(tx(T, lx(v), y - 6, `${v}x`, { size: 10, role: 'muted', anchor: 'middle' })); }
    y += 4;
    for (const h of rows) {
      const rh = rowH(h);
      const yy = y + rh / 2 - 2; const role = h.kind === 'small' ? 'blue' : 'g3';
      const b = lines(T, x0, y + 1, labelOf(h), lw - 10, { size: narrow ? 9.5 : 10.5, lh: 12, weight: 500 });
      out.push(b.svg);
      if (h.cost && h.lat) out.push(ln(T, lx(Math.min(h.cost, h.lat)), yy, lx(Math.max(h.cost, h.lat)), yy, 'grid', 1.5));
      if (h.cost) out.push(dot(T, lx(h.cost), yy, 4.5, role, `${h.who} vs ${h.vs}: ${xf(h.cost)} cheaper`));
      if (h.lat) out.push(diamond(T, lx(h.lat), yy, 5, role, `${h.who} vs ${h.vs}: ${xf(h.lat)} faster`));
      y += rh;
    }
    y += 6;
    const b = lines(T, x0, y, `Small: the vendor's small or cheap tier. Each multiple is the comparison model's figure divided by Jev's, as the source published it; the table under the chart has the accuracy and the links.`, x1 - x0, { size: 10.5, lh: 14, role: 'muted' });
    out.push(b.svg); y += b.h;
    return { svg: out.join(''), y };
  },
};

// ---------------------------------------------------------------- figure: the rivals
const chartRivals = {
  key: '16', file: '16-the-rivals',
  title: 'Twenty rivals in a week, and the rate is still rising',
  subtitle: 'New Hugging Face models named jev or laya a day, 17 to 23 Sep; posts in the feed showing a rival model, 16 to 23 Sep. The twenty are listed under the chart.',
  desc: `${RV.rivals_count} distinct models and endpoints plus ${RV.benchmarks_count} benchmarks by 22 Sep. Hugging Face: ${RV.hf_new_models_per_day.map((d) => d.models).join(', ')} a day.`,
  body(T, { x0, x1, y0, narrow }) {
    const out = []; let y = y0;
    let t = 'Hugging Face: new models named jev or laya, per day';
    out.push(panelTitle(T, x0, y, t, narrow, x1 - x0)); y += 24 + panelTitleH(t, narrow, x1 - x0);
    const items = RV.hf_new_models_per_day.map((d) => ({ label: dayLabel(d.date), value: d.models }));
    const nm = nice(Math.max(...items.map((i) => i.value)));
    let pnl = vBarPanel(T, { x0, x1, y0: y, h: narrow ? 110 : 130, items, narrow, fmtVal: (v) => String(v), ymax: nm.max, ticks: [0, nm.step, nm.step * 2, nm.step * 3, nm.step * 4].filter((v) => v <= nm.max), tickFmt: (v) => String(v), note: 'Models created that day whose name contains jev or laya.' });
    out.push(pnl.svg); y = pnl.y + 14;
    t = 'The feed: posts showing a model, port or endpoint that is not Jev, per day';
    out.push(panelTitle(T, x0, y, t, narrow, x1 - x0)); y += 24 + panelTitleH(t, narrow, x1 - x0);
    const items2 = RV.rival_posts_per_day.map((d) => ({ label: dayLabel(d.date), value: d.posts }));
    const nm2 = nice(Math.max(...items2.map((i) => i.value)));
    pnl = vBarPanel(T, { x0, x1, y0: y, h: narrow ? 100 : 120, items: items2, narrow, fmtVal: (v) => String(v), ymax: nm2.max, ticks: [0, nm2.step, nm2.step * 2, nm2.step * 3].filter((v) => v <= nm2.max), tickFmt: (v) => String(v), note: 'All Jev posting fell from 1,027 a day on 19 Sep to 336 on 23 Sep, so the rivals took a growing share of a shrinking conversation.' });
    out.push(pnl.svg); y = pnl.y;
    return { svg: out.join(''), y };
  },
};

// ---------------------------------------------------------------- render the new charts
mkdirSync(join(OUT, 'charts', 'narrow'), { recursive: true });
const written = [];
const PAGE_SOURCE = { corpus: `Source: jev.openchamber.dev, ${fmt(S.posts)} posts, 16 to 23 Sep 2026. Method and audit: see the end of this page.`, gateways: 'Source: OpenRouter and Vercel AI Gateway, read 24 Sep 2026. Method: see the end of this page.', prices: 'Source: OpenRouter rankings and list prices, read 24 Sep 2026. Method: see the end of this page.', h2h: 'Source: the linked write-ups and the Jev Pong runs. Method: see the end of this page.', rivals: 'Source: Hugging Face and jev.openchamber.dev, read 24 Sep 2026. Method: see the end of this page.' };
const FILE_SOURCE = { corpus: SOURCE_CORPUS, gateways: `Source: openrouter.ai/typesafe/jev-1.13 and Vercel's AI Gateway leaderboard export (CC BY 4.0), read 24 Sep 2026; analysis by Matthew O'Riordan`, prices: `Source: openrouter.ai/rankings and the Jev model page, list prices from openrouter.ai/api/v1/models and docs.typesafe.ai, read 24 Sep 2026; analysis by Matthew O'Riordan`, h2h: `Source: the linked write-ups (Near Here, Lindfors, Sniff Test, OpenWork, CodeAlive, rerank bench, Classmethod, Hermes, LangWatch, Every, awlevin) and the Jev Pong runs; TypeSafe's launch post; the feed's claim chips; analysis by Matthew O'Riordan`, rivals: `Source: huggingface.co model search by creation date and jev.openchamber.dev, read 24 Sep 2026; analysis by Matthew O'Riordan` };
const NEW = [[chartGateways, 'gateways'], [chartMoney, 'prices'], [chartGroups, 'corpus'], [chartClaims, 'h2h'], [chartH2H, 'h2h'], [chartRivals, 'rivals']];
const pageSVG = {};
for (const [c, src] of NEW) {
  pageSVG[c.key] = { wide: withFooter(FILE_SOURCE[src], PAGE_SOURCE[src], () => frame(THEMES.vars, c, WIDE, 'wauto', 'page')), narrow: withFooter(FILE_SOURCE[src], PAGE_SOURCE[src], () => frame(THEMES.vars, c, NARROW, 'nauto', 'page')) };
  for (const [dir, W, tag] of [[join(OUT, 'charts'), WIDE, 'w'], [join(OUT, 'charts', 'narrow'), NARROW, 'n']]) {
    for (const [name, svg] of [[`${c.file}.svg`, withFooter(FILE_SOURCE[src], PAGE_SOURCE[src], () => frame(THEMES.vars, c, W, `${tag}auto`, 'file'))], [`${c.file}-light.svg`, withFooter(FILE_SOURCE[src], PAGE_SOURCE[src], () => frame(THEMES.light, c, W, `${tag}light`, 'file'))], [`${c.file}-dark.svg`, withFooter(FILE_SOURCE[src], PAGE_SOURCE[src], () => frame(THEMES.dark, c, W, `${tag}dark`, 'file'))]]) {
      writeFileSync(join(dir, name), XML + svg + '\n'); written.push(join(dir, name));
    }
  }
}

// ---------------------------------------------------------------- kept charts, in their page variant, with their number tables
const OLD_HTML = readFileSync(join(SITE, 'index.html'), 'utf8');
function keptFigure(figId) {
  const m = OLD_HTML.match(new RegExp(`<section class="fig" id="${figId}"[\\s\\S]*?</section>`)); check(Boolean(m), `figure ${figId} found in the current page`);
  const s = m ? m[0] : '';
  const wide = (s.match(/<div class="fig-wide">([\s\S]*?)<\/div>\s*<div class="fig-narrow">/) || [, ''])[1];
  const narrow = (s.match(/<div class="fig-narrow">([\s\S]*?)<\/div>\s*<figcaption/) || [, ''])[1];
  const table = (s.match(/<details><summary>Show the numbers<\/summary>([\s\S]*?)<\/details>/) || [, ''])[1];
  check(wide.includes('<svg') && narrow.includes('<svg'), `figure ${figId} has both layouts`);
  return { svg: { wide, narrow }, table };
}
const CSS = OLD_HTML.match(/<style>([\s\S]*?)<\/style>/)[1];
const SCRIPT = OLD_HTML.match(/<script>[\s\S]*?<\/script>/)[0];
let AUDIT = (OLD_HTML.match(/<details class="audit-tables">[\s\S]*?<\/details>/) || [''])[0];
AUDIT = AUDIT.replace(/<h3>What the charts count<\/h3>\s*<ul>[\s\S]*?<\/ul>/, '').replace(/figure (\d+[abc]?)/g, 'figure $1 of the technical page').replace(/suspect posts/g, 'low like-rate posts').replace(/looks like promotion/g, 'has a like rate far below the median');
check(AUDIT.length > 2000, 'the audit tables were found in the current page');

// ---------------------------------------------------------------- markup
let figN = 0;
function figure({ svg, table }) {
  figN += 1;
  return `<figure><div class="fig-wide">${svg.wide}</div><div class="fig-narrow">${svg.narrow}</div>${table ? `<details><summary>Show the numbers</summary>${table}</details>` : ''}</figure>`;
}
const section = (id, eyebrow, title, body) => `<section class="fig" id="${id}">\n  <p class="eyebrow">${eyebrow}</p>\n  <h2>${title}</h2>\n${body}\n</section>`;
const why = (t) => `<p class="sowhat">${t}</p>`;

// ---------------------------------------------------------------- tables
const gatewayTable = tbl(['Day', 'OpenRouter requests', 'Prompt tokens', 'Billed', 'Vercel: share of requests', 'Vercel: share of tokens'],
  vcDays.map((d) => { const o = orDay(d.date); return [dayLabel(d.date), o && o.requests > 1e6 ? fmt(o.requests) : '', o && o.requests > 1e6 ? mShort(o.prompt_tokens) : '', o && o.requests > 1e6 ? usd(o.usd) : '', `${d.requests_share_pct.toFixed(1)}%`, `${d.tokens_share_pct.toFixed(2)}%`]; }));
const funnelTable = tbl(['Signal', 'Number', 'When', 'Source'], [
  ['People let off the waitlist', '140,000 in under 36 hours', '17 Sep', a(L.waitlist, 'Diogo Almeida, TypeSafe')],
  ['Waitlist removed', '"Jev is now available to everyone."', '20 Sep', a(L.noWaitlist, 'TypeSafe')],
  ['Signups paused', '"an immense swell of demand"; not reopened by 24 Sep', '22 Sep', a(L.paused, 'TypeSafe')],
  ['Vercel AI Gateway, day one', 'nearly 13% of paid teams by hour 24; every other recent launch under 7% after a day', '18 Sep', a(L.vcBlog, 'Vercel')],
  ['Vercel AI Gateway, latest day', 'used by 37.8% of teams, first; the primary model by tokens for 33.8% of teams', 'read 24 Sep', a(L.vcBoard, 'Vercel leaderboards')],
  ['SDK downloads, launch week', '298,412 JavaScript, 46,177 Vercel provider, 331,517 Python (automated installs included)', 'read 24 Sep', `${a(L.npm, 'npm')}, ${a(L.pypi, 'pypistats')}`],
  ['New GitHub repositories matching "jev"', '8,106 since 15 Sep, against 56 the week before', 'read 24 Sep', a(L.gh, 'GitHub search')],
  ['Discord members', '107,727', 'read 24 Sep', a(L.discord, 'Discord')],
  ['Named apps on OpenRouter', 'five apps hold 4.3% of Jev requests; a data-labeling app alone 12.9 million; the rest is anonymous', 'read 24 Sep', a(L.or, 'OpenRouter')],
  ['Incidents', 'API down 5, 18, 2 and 12 minutes on 17, 20, 21 and 23 Sep; none in July or August', 'read 24 Sep', a(L.tsStatus, 'TypeSafe status page')],
]);
const moneyTable = tbl(['Model', 'Prompt price, $ per million tokens', 'Output price', `Cost of 23 Sep's Jev tokens`, "Multiple of Jev's bill"],
  priced.map((it) => { const pr = PR.usd_per_million[it.name]; return [it.name, pr.prompt.toFixed(3), pr.completion.toFixed(2), usd(it.usd), it.name === 'Jev' ? 'billed' : xf(it.usd / jevBill)]; }));
const groupTable = tbl(['Group', 'Posts', 'Share', 'No measurement', 'Measured demo', 'Labeled production, not confirmed', 'Production, confirmed', 'In a live loop', 'Needs under 300 ms'],
  GROUPS.map((g) => [`${g.name} <span class="sub">(${g.sub})</span>`, fmt(g.posts), pct(g.share, 0), fmt(g.steps.no_measurement), fmt(g.steps.measured_demo), fmt(g.steps.prod_not), fmt(g.steps.prod_ok), pct(g.live, 0), pct(g.fast, 0)])
    .concat([['All posts', fmt(BASE), '100%', fmt(stepTot.no_measurement), fmt(stepTot.measured_demo), fmt(stepTot.prod_not), fmt(stepTot.prod_ok), '', '']]));
const h2hTable = tbl(['Who', 'The task', 'Against', 'Cheaper by', 'Faster by', 'Accuracy', 'Source'],
  H2H.map((h) => [h.who, h.task, `${h.vs} (${h.kind})`, h.cost ? xf(h.cost) : 'not published', h.lat ? xf(h.lat) : 'not published', h.acc, a(h.link, 'link')]));
const costTable = tbl(['Job', 'Who', 'What they measured', 'Source'], [
  ['Evals and judging', 'LangWatch', '97% agreement with human labels over 300 support conversations; 10,000 conversations judged for $0.32 in 73 seconds, against $31 and ten minutes on Opus 5', a(L.langwatch, 'langwatch.ai')],
  ['Evals and judging', 'Mike Taylor and Dan Shipper, Every', '777 judgments in under 0.7 seconds; 0.35 s a passage against 8.8 s on Fable 5.1, about 580 times cheaper', a(L.every, 'every.to')],
  ['Classification', 'Hassan, 1kpapers', '1,018 papers sorted into 24 topics for $0.08, 256 ms a paper', a(L.nutlope, 'X')],
  ['Classification', 'Emil Lindfors', '$0.22 per 1,000 documents; 0.32 s a document', a(L.lindfors, 'lindfors.no')],
  ['Triage', 'Jalil Laaraichi, OpenWork', 'log triage with 0 false pages; $0.062 against $0.32 per 3,000 logs', a(L.triage, 'dev.to')],
  ['Security screening', 'Gaurav Gosain', '96.5% on 662 blind prompt-injection and vulnerable-code cases; p50 325 ms', a(L.secbench, 'GitHub')],
  ['Agent approvals', 'anpicasso, Hermes', '153 real commands: 10 escalations to a human instead of 42; 405 ms against 3,968 ms', a(L.hermes, 'GitHub')],
  ['Computer use', 'awlevin', 'next action from an OCR of the screen: $0.0002 a step against $0.032; 0.13 to 0.38 s against 5.2 s', a(L.awlevin, 'GitHub')],
  ['Browser agents', 'Gregor Zunic, Browser Use', 'a real flight search 25% faster end to end; 101 protocol calls instead of 1,092', a(L.browseruse, 'GitHub')],
  ['Context pruning', 'tamara', 'score every tool call and result, drop the stale ones: 1M tokens to 86K', a(L.compaction, 'madewithjev')],
  ['Reranking', 'anessbelbati', 'parity with Cohere Rerank 4 Pro on nDCG at half the latency', a(L.rerank, 'GitHub')],
]);
const speedTable = tbl(['What', 'Who', 'What they measured', 'Source'], [
  ['Voice turn-end on every partial transcript', 'Nader Dabit', '108 ms round trip; the assistant replies 351 ms after the speaker stops instead of 1,000 ms', a(`${L.dabit}/tree/main/jev-voice-turn`, 'GitHub')],
  ['Hold every chat message before it renders', 'Nader Dabit', '45 messages a second held 124 ms each; 381 of 383 harmful messages caught, 0 of 958 clean ones blocked, on a labeled set', a(`${L.dabit}/tree/main/modstream`, 'GitHub')],
  ['Judge a draft between keystrokes', 'Nader Dabit', '105 ms end to end, 85 judgments a second while typing; 4 of 4 risky drafts caught, 0 false blocks', a(`${L.dabit}/tree/main/send-guard`, 'GitHub')],
  ['Nine questions per customer message, eight chats at once', 'Nader Dabit', 'panel refresh 93 ms', a(`${L.dabit}/tree/main/agent-assist`, 'GitHub')],
  ['Live minutes that flag a reversed decision', 'Nader Dabit', '131 ms from end of utterance to screen; action items 96% recall, 92% precision', a(`${L.dabit}/tree/main/live-minutes`, 'GitHub')],
  ['A 300-message-a-second stream, every message judged', 'Nader Dabit', '124 ms end to end, zero backlog, $37.86 an hour', a(`${L.dabit}/tree/main/jev-firehose`, 'GitHub')],
  ['Turn detection for voice agents', 'Kwindla Hultman Kramer', '92.6% at 296 ms, against an LLM at 81.3% and 1,008 ms', a(L.kwindla, 'X')],
  ['Voice and gesture on a canvas, eight questions per partial transcript', 'gaborishka', '300 to 550 ms a decision', a(L.canvas, 'GitHub')],
  ['Per-turn decisions as a LiveKit plugin', 'sidxh', 'a proposal; 0 comments, 0 reactions', a(L.livekit, 'GitHub')],
  ['The same shape, local, on a laptop', 'mizorewww, laya-mlx', '7 to 14 ms a decision on an M3 Max; no cloud in the path', a(L.layaMlx, 'GitHub')],
]);
const compoundTable = tbl(['Use case', 'How it was done before', 'What a decision model changes', 'Speed, cost, or both', 'Evidence so far'], [
  ['A voice control plane: speak now, is this a command, escalate', 'silence timers; a trained classifier per product; or an LLM at about a second', 'several product-specific questions on every partial transcript, about 300 ms, no training', 'speed', 'two head-to-heads (92.6% at 296 ms against 81.3% at 1,008 ms); demos'],
  ['A moderation policy per room, applied before fan-out', 'keyword filters; vendor taxonomies; an LLM per message at 0.5 to 3 s, so after the fact', 'a prose policy the room owner writes, several hazards per message, held about 120 ms', 'both', 'a synthetic set: 99.5% caught, 0 clean messages blocked'],
  ['Who is this for? Gating an assistant in a group', 'wake words, @-mentions, or an LLM at about a second', 'a decision on every utterance at about 340 ms', 'speed', 'demos, no accuracy numbers'],
  ['A human-takeover trigger on every turn', 'a trained escalation classifier, or an LLM judge adding 1 to 3 s', 'left on for every turn, before the reply streams', 'both', '10 escalations instead of 42, 405 ms against 3,968 ms; one measured demo'],
  ['A live audience board, every message scored', 'sampled or batch sentiment; an LLM per message at $140 to $950 an hour', 'every message, categories redefined as you go, $37.86 an hour at 300 messages a second', 'cost', 'a measured demo'],
  ['Live minutes that flag a reversed decision', 'a summary after the meeting', 'flagged in about 130 ms, while everyone is still in the room', 'cost, mostly', 'one repo, on replay'],
]);
const rivalsTable = tbl(['Name', 'Who', 'First seen', 'Type', 'Competes on', 'Independent check', 'Source'],
  RV.rivals.map((r) => [r.name, r.who, r.first_seen, r.type, r.competes_on, r.check, a(r.source, 'link')]));
const jb = RV['jevbench_v141_2026-09-23'];

// ---------------------------------------------------------------- the page
const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>A week of Jev, sorted</title>
<meta name="description" content="I sorted every post from Jev's first week, read the usage the gateways show, and counted the rivals. This is what the data says.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>${CSS}
.sowhat{margin:20px 0 0;padding:12px 18px;border-left:3px solid var(--accent);background:var(--bg-2);border-radius:0 8px 8px 0;font-size:16px;line-height:1.55;max-width:44em}
.prose ul{padding-left:1.1em;margin:0 0 14px}
.prose li{margin:0 0 6px}
table.wrap td .sub,table.wrap th .sub{color:var(--muted);font-weight:400;font-size:12px}
.numbers{margin-top:16px}
.numbers table.wrap td:nth-child(6){white-space:normal}
.numbers table.wrap th,.numbers table.wrap td{min-width:8em}
.numbers table.wrap th:first-child,.numbers table.wrap td:first-child{min-width:9em}
.watch li{margin:0 0 8px}
figure details{margin-top:8px}
@media print{.sowhat{break-inside:avoid}}
</style>
</head>
<body>
<main>
<header>
  <p class="kicker">Data · Jev's first week · 16 to 23 September 2026</p>
  <h1>A week of Jev, sorted</h1>
  <p class="dek">I sorted 5,950 posts from Jev's first week, read the usage the gateways show, and counted the rivals. This is what the data says. What I make of it is ${articleLink}.</p>
  <p class="byline"><strong>${a(L.linkedin, "Matthew O'Riordan")}</strong> · ${PUBLISHED} · Disclosure: I'm CEO of ${a(L.ably, 'Ably')}, a realtime infrastructure company.</p>
</header>

<div class="intro prose">
  <p>Jev is TypeSafe AI's decision model. It doesn't write text. You give it a state and a typed question, pick one of these, score this, yes or no, and it answers in a few hundred milliseconds with a probability. ${a(L.launch, 'TypeSafe\'s launch claim')} was 20 to 200x faster and 40 to 400x cheaper than an LLM for that kind of question; "100x cheaper, 10x faster" is the shorthand the week settled on.</p>
  <p>I built ${a('https://jev-pong.ably.dev', 'Pong on it')} the week it came out. The post did well, and nearly every comment asked the same thing: fine, you built a game, what's it for? I tried to answer and couldn't. Every use case I reached for was either already solved or harder than a cheaper yes-or-no. So I stopped guessing and measured: every post in OpenChamber's Jev feed for the first week, sorted and audited; the two gateways that publish usage; and the rivals that turned up. The ${a('#method', 'method and the audit')} are at the end.</p>
  <div class="short">
    <h2>The short version</h2>
    <ul>
      <li>Jev is being called at scale, and the money is small. On 23 September it was a quarter of all requests on Vercel's AI Gateway and 2% of its tokens; on OpenRouter it served more requests that week than GPT-5.6 Luna, for an eighth of the spend. TypeSafe publishes no usage number, and 96% of OpenRouter's Jev requests come from apps that don't say who they are.</li>
      <li>The buzz is about using it, not about what it makes possible. Four in five posts compared Jev with nothing, and none of the ${AE.candidates.value} builds most likely to show something new did something that was unavailable before.</li>
      <li>TypeSafe announced 40 to 400x cheaper than frontier models, and against frontier models it holds. The posts claimed ${xf(num(chips.cost.median))}. Measured against the small models you'd actually use, the median is ${xf(M.smallCostMed)} on cost and ${xf(M.smallLatMed)} on latency, often with better accuracy.</li>
      <li>Twenty rivals in a week, mostly built by one person in days on open weights. None matches Jev's mix yet, and no big provider has shipped one.</li>
    </ul>
  </div>
</div>

${section('s1', '1 · How big it really is', "A quarter of Vercel's gateway requests, 2% of its tokens, and nobody can say who's behind it", `
  <div class="prose">
    <p>TypeSafe hasn't published a usage number, so the ${a(L.or, 'gateways')} are the only view anyone has, and they show what the posts can't: Jev is being called at a scale that dwarfs the demos. What the chart can't show is who's calling it. Five named apps (a data-labeling app with 12.9 million requests, Magnific, mirasim, the Asian Development Bank's evidence portal, a Naver rubric judge) account for 4% of OpenRouter's Jev requests. The rest is anonymous. Demand outran TypeSafe: ${a(L.waitlist, '140,000 people')} were let off the waitlist in 36 hours, signups were ${a(L.paused, 'paused')} a week in, and the API had ${a(L.tsStatus, 'four short outages')}.</p>
  </div>
  ${figure({ svg: pageSVG['13'], table: gatewayTable + '<h3>Who is trying it</h3>' + funnelTable })}
  ${why(`The calls are real and tiny. A request isn't a decision, a gateway can't tell trying from using, and Jev was ${a(L.vcPrice, 'free on Vercel')} all week, so read the Vercel line as a ceiling.`)}`)}

${section('s2', '2 · Weighted by money', 'More requests than GPT-5.6 Luna, for an eighth of the money', `
  <div class="prose">
    <p>This is what 100x cheaper looks like on a bill. Priced on the same day's tokens, Jev sits with the cheapest small models, and one of them, DeepSeek V4 Flash, is cheaper per token. The ${xf(pricedOf('Claude Fable 5.1') / jevBill)} is only there if you assume the calls would have gone to a frontier model, and nobody sends yes-or-no questions to Fable. Most of these calls exist because they cost almost nothing, not because they replaced something expensive.</p>
  </div>
  ${figure({ svg: pageSVG['14'], table: moneyTable })}
  ${why('A price comparison, not a quality one: nobody has run these tasks on the other models.')}`)}

${section('s3', '3 · What people built', "We can't see what everyone runs. We can see what they show.", `
  <div class="prose">
    <p>The gateways show volume with no names. The posts show names with no volume. So the rest of this page is about the ${fmt(BASE)} posts: what people said Jev decides, what they measured, and what they compared it with. Two things stood out. Games are the biggest single family, not classification. And a fifth of the posts never say what the decision is at all.</p>
  </div>
  ${figure({ svg: pageSVG['15'], table: groupTable })}
  ${why(`Read everything below knowing the week was mostly demos: two thirds of posts measured nothing, and a third measured a demo. Production numbers in posts are rare (${prodRows.length} of ${fmt(BASE)} held up on the audit), which fits the gateway picture: the volume sits with apps that don't post.`)}`)}

${section('s4', '4 · Was any of it new?', 'The buzz is about using it, not about what it makes possible', `
  <div class="prose">
    <p>Four in five posts compared Jev with nothing. That matters because Jev is doing jobs that already had tools. If it were solving something nobody could solve before, there'd be nothing to compare with. It isn't, so the missing baseline is the tell.</p>
  </div>
  ${figure(keptFigure('figure-3'))}
  <div class="prose" style="margin-top:22px">
    <p>The audit went further. It took the ${AE.candidates.value} posts where the first-pass labels found a measured decision inside a live system with a person waiting on it, the builds most likely to need both the speed and the price, and asked what a team would have used before Jev. An LLM for ${before.llm}. Rules for ${before.rules}. A vendor API for ${before.vendor}. A classic model for ${before.classic}. None did something that was unavailable before. (${AE.substance_distinct.value} distinct builds; ${AE.candidates_still_meeting.value} still meet the test on the auditor's own labels.)</p>
  </div>
  ${figure(keptFigure('figure-1c'))}
  ${why('Faster and cheaper versions of jobs that had a tool. A real change to who can try them; one week in, not a change to what gets built.')}`)}

${section('s5', '5 · Announced, claimed, measured', `TypeSafe's 40 to 400x is against frontier models, and holds there. Against the small models you'd actually use, the median is ${xf(M.smallCostMed)}.`, `
  <div class="prose">
    <p>The ${a(L.launch, 'launch claim')} was against frontier models, and on the four published frontier comparisons it holds. The posts repeated it. Where someone put Jev against a small model on the same task and published the numbers (I found ${small.length} such comparisons, including my own Pong runs) the gap shrank to a median of ${xf(M.smallCostMed)} on cost and ${xf(M.smallLatMed)} on latency (${xf(M.smallCostMedNoPong)} and ${xf(M.smallLatMedNoPong)} without my own runs), with Jev at or above the small model on accuracy for most bounded questions. Against frontier models the multiples are real: ${xf(M.frontierCostLo)} to ${xf(M.frontierCostHi)} on cost.</p>
  </div>
  ${figure({ svg: pageSVG['17'] })}
  ${figure({ svg: pageSVG['18'], table: h2hTable + '<h3>The cost uses people measured</h3>' + costTable })}
  ${why(`The honest number for a build-or-buy is single digits against a small model. Worth having, and it moves the sweet spot from ten times the decisions at a tenth of the bill to a few times the decisions at a fraction of it. The jobs are evals, triage, extraction, reranking and agent gating, and small-model prices have been falling ${a(L.a16z, 'roughly 10x a year')} on their own.`)}`)}

${section('s6', '6 · Who needs it fast', 'Outside games, speed is a handful of demos, and they share one shape', `
  <div class="prose">
    <p>A tenth of posts need a decision in under 300 ms, and nine in ten of those are games. Voice, live chat and collaboration, where a person is waiting, are ${aud('rt_families')} of posts, and none is measured in production. The few live builds that exist mostly sit in one repo, ${a(L.dabit, "Nader Dabit's jev-experiments")}, and they share a shape: several of your own questions on every event, inside the turn, from a model you didn't train. That's the one pattern nothing served before for anyone without an ML team.</p>
  </div>
  ${figure(keptFigure('figure-6'))}
  ${figure({ ...keptFigure('figure-7'), table: keptFigure('figure-7').table + '<h3>The live builds, by name</h3>' + speedTable })}
  <h3>Where speed and cost compound</h3>
  <div class="prose"><p>The use cases people talked about, what they were done with before, and what a general decision model changes. Every one is a demo or a proposal.</p></div>
  <div class="numbers">${compoundTable}</div>
  ${why(`The latency story belongs to games and to local models: a ${a(L.layaMlx, 'local Laya')} answers in 7 to 14 ms on a laptop. The live human tier is where cost and speed compound into something new, and after a week it holds demos.`)}`)}

${section('s7', '7 · Who else is coming', 'Twenty rivals in a week, most built by one person in days', `
  <div class="prose">
    <p>The moat is smaller than the launch suggested. SemIf was up within a day. AutoJev was trained by agents in 20 hours on one H200 for $3,100. Reflex was one Shopify engineer over three days. JevK5, a week old, is second on ${a(L.jevbench, 'JevBench')}. Each rival moves one or two knobs (${jb.beat_jev_on_cost} of the other top-20 systems beat Jev on cost, ${jb.beat_jev_on_speed} on speed, ${jb.beat_jev_on_calibration} on calibration, none on intelligence), and none matches Jev's mix yet. No big provider has announced a decision endpoint. And people built local copies partly because they couldn't get in.</p>
  </div>
  ${figure({ svg: pageSVG['16'], table: rivalsTable })}
  ${why('What it took to get close: one person, a few days, open weights, and at most a few thousand dollars.')}`)}

${section('s8', '8 · Where it is', 'What the week adds up to', `
  <div class="prose">
    <ul>
      <li>Jev is being called at scale, mostly by apps that don't say who they are, and the money is small.</li>
      <li>Against comparable small models the gap is single digits, not 100x and 10x.</li>
      <li>The uses that can be named are decisions about data: labeling, routing, judging, extraction. Possible before, cheaper now, and getting cheaper regardless.</li>
      <li>Speed and cost compound in one place, decisions about a person's words in real time. It's ${pct(G.people.share, 0)} of posts, a few demos, and nothing measured in production.</li>
      <li>None of the ${AE.candidates.value} builds most likely to show something new did something that was unavailable before.</li>
      <li>Twenty rivals in a week, built cheaply, none matching the mix yet, and no big provider.</li>
    </ul>
    <h3>What to watch</h3>
    <ul class="watch">
      <li><b>2 October.</b> Jev stops being free on Vercel on 25 September. If its share of requests is still around a quarter a week later, the volume was use; if it halves, a lot of it was free-tier tinkering. I'll re-read ${a(L.vcExport, 'the same export')}, OpenRouter's daily curve, and whether the five named apps are still there.</li>
      <li>When TypeSafe reopens signups, and whether it publishes a usage number.</li>
      <li>The first decision endpoint from a big provider.</li>
      <li>The first production number in the live tier: a voice agent, a chat room, a takeover trigger, with a volume attached.</li>
    </ul>
    <p>What I think it means is ${articleLink}. This page is the data.</p>
  </div>`)}

<section class="method prose" id="method">
  <p class="eyebrow">Method</p>
  <h2>How this was measured</h2>
  <p>The posts come from ${a(L.feed, "OpenChamber's Jev feed")}, snapshot 23 September 18:47 UTC: ${fmt(S.posts)} posts from ${fmt(S.authors)} authors between 16 and 23 September, as OpenChamber selected them. Without ${S.duplicates_merged} duplicates, the ${S.not_a_jev_build} posts that don't use Jev and one post the labeling model refused, ${fmt(BASE)} remain. The feed is what people chose to show, not a sample of usage: it starts six hours after launch, the top 1% of posts held half of all views, and the median post got ${num(stats.median_views)} views.</p>
  <p>I used AI models to do the sorting, and I want to be plain about that. Claude Opus 5.5 labeled every post against a written rubric: what Jev decides, whether the author measured anything, what they compared it with, whether the decision sits in a live loop, and whether it's in production. Then a second model, Grok, labeled ${fmt(AE.labelled.value)} of those posts blind: every post in the rare groups the headlines rest on, and random samples of the rest. It produced its own estimates with 95% intervals, and wherever it checked a number this page uses its range, not the first model's count. It corrected several; the production count went from ${AE.production_model.value} to ${prodRows.length}. I hand-checked 13 posts myself, enough to catch problems, not enough to call it a human audit. A proper human sample is the check still missing. At Vercel AI Gateway list prices the labeling cost about $48.</p>
  <p>The gateway numbers were read at source on 24 September: ${a(L.or, "OpenRouter's model page")} and ${a(L.orRank, 'rankings')}, ${a(L.vcExport, "Vercel's open leaderboard export")} (CC BY 4.0), ${a(L.npm, 'npm')}, ${a(L.pypi, 'pypistats')} and ${a(L.discord, 'Discord')}. 24 September was a partial day and is left out everywhere. The head-to-heads are every comparison I could find where someone put Jev against another model on the same task and published cost, latency or accuracy; each is the author's own figure, unreproduced. The rivals were found from the feed, Hugging Face, GitHub and ${a(L.jevbench, 'JevBench')}; ranks move daily and are dated. Gateway requests are requests, not decisions, and can't separate production from testing. Vercel publishes shares, never counts.</p>
  <p>The labels, the tables behind every chart, the rubric and the code are at ${a(L.repo, 'github.com/mattheworiordan/jev-landscape')}, without the text of any post: code under MIT, data and method under CC BY 4.0. The posts belong to their authors. The ${a(L.technical, 'full technical page')} has every chart from the first edition, including the ones this page leaves out.</p>
  <p class="disclosure"><b>Disclosure.</b> I'm CEO of ${a(L.ably, 'Ably')}, a realtime infrastructure company. I looked at Jev because it sits in the low-latency part of the stack I work on. Read the numbers with that in mind. I'm ${a(L.linkedin, 'on LinkedIn')} if you want to argue with any of it.</p>
  ${AUDIT.replace('<summary>Show the audit tables</summary>', `<summary>Show the audit tables</summary><p class="eyebrow" style="margin-top:12px">The tables refer to the figure numbers of the ${a(L.technical, 'full technical page')}.</p>`)}
</section>
</main>
${SCRIPT}
</body>
</html>
`;

// ---------------------------------------------------------------- checks and write
check(!/—/.test(html), 'no em dashes on the page');
check(!/<text[^>]*>24 Sep/.test(html) && !/<th scope="row">24 Sep/.test(html), 'no 24 September data in any chart or table');
for (const w of ['game-changer', 'game changer', 'seamless', 'leverage', 'unlock', 'delve', 'moreover', 'furthermore']) check(!new RegExp(`\\b${w}\\b`, 'i').test(html.replace(/<[^>]+>/g, '')), `banned word on the page: ${w}`);
if (problems.length) { console.error(`Checks failed:\n- ${problems.join('\n- ')}`); process.exit(1); }
writeFileSync(join(OUT, 'index.html'), html);
written.push(join(OUT, 'index.html'));
const prose = html.replace(/<style>[\s\S]*?<\/style>|<script>[\s\S]*?<\/script>|<svg[\s\S]*?<\/svg>|<details[\s\S]*?<\/details>|<div class="numbers">[\s\S]*?<\/div>/g, ' ').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim().split(' ').length;
console.log(`Wrote ${written.length} files under ${OUT.replace(`${SITE}/`, '')}/ · visible prose about ${prose} words (charts, tables and the audit excluded)`);
console.log(`head-to-heads: small cost median ${xf(M.smallCostMed)} (${xf(M.smallCostLo)} to ${xf(M.smallCostHi)}), small latency median ${xf(M.smallLatMed)} (${xf(M.smallLatLo)} to ${xf(M.smallLatHi)}); frontier cost ${xf(M.frontierCostLo)} to ${xf(M.frontierCostHi)}, latency ${xf(M.frontierLatLo)} to ${xf(M.frontierLatHi)}`);
