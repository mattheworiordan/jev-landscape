#!/usr/bin/env node
// A week of Jev, sorted: chart and page generator.
//
// Reads ../../data/*.csv and ../../summary.json (the analysis, with the audit tables 13_audit_*.csv) and writes:
//   charts/NN-name.svg          adaptive: follows the reader's system light/dark setting
//   charts/NN-name-light.svg    fixed light colors
//   charts/NN-name-dark.svg     fixed dark colors
//   charts/narrow/...           the same three files laid out for phone width (360 px)
//   index.html                  the self-contained report page, every chart inlined
//   jev-week-sorted.pdf         with --pdf only: the page printed to A4, every <details> open
//
// The chart files travel without the page, so their footer is the full source line and the disclosure.
// The same charts inlined on the page carry one short source line that points to the method at the end
// of the page. That footer is the only difference (frame()'s footer option: 'file' or 'page').
//
// Run from anywhere: node report/site/scripts/charts.mjs   (Node 18+, no dependencies)
//   --labels data/classified-opus.jsonl (or LABELS=...) checks that summary.json was built from that label
//   file (python3 scripts/analyze.py --labels ...); the model's name on the page comes from summary.json.
//   --pdf also prints the page to jev-week-sorted.pdf with Playwright's Chromium (the project's dev
//   dependency: pnpm install, then pnpm exec playwright install chromium). Only --pdf loads it.
//
// Rule: every number drawn on a chart comes from the CSVs or summary.json. The script
// cross-checks the CSVs against summary.json and the audit tables, and stops if they disagree.

import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const SITE = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const REPORT = resolve(SITE, '..');
const DATA = join(REPORT, 'data');
const OUT = join(SITE, 'charts');

// ---------------------------------------------------------------- data loading
function parseCSV(text) {
  const rows = [];
  let row = [], field = '', quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else quoted = false; }
      else field += c;
    } else if (c === '"') quoted = true;
    else if (c === ',') { row.push(field); field = ''; }
    else if (c === '\n' || c === '\r') {
      if (c === '\r' && text[i + 1] === '\n') i++;
      row.push(field); rows.push(row); row = []; field = '';
    } else field += c;
  }
  if (field !== '' || row.length) { row.push(field); rows.push(row); }
  const [head, ...body] = rows.filter((r) => !(r.length === 1 && r[0] === ''));
  return body.map((r) => Object.fromEntries(head.map((h, j) => [h, r[j]])));
}
const csv = (name) => parseCSV(readFileSync(join(DATA, `${name}.csv`), 'utf8'));
const S = JSON.parse(readFileSync(join(REPORT, 'summary.json'), 'utf8'));
const num = Number;

const problems = [];
const check = (cond, msg) => { if (!cond) problems.push(msg); };
const near = (a, b, tol = 1e-6) => Math.abs(a - b) <= tol;

// ---------------------------------------------------------------- formatting
const fmt = (n) => Math.round(n).toLocaleString('en-US');
const pct = (x, d = 1) => `${(x * 100).toFixed(d)}%`;
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const r1 = (v) => Math.round(v * 10) / 10;
const sum = (a) => a.reduce((x, y) => x + y, 0);

// ---------------------------------------------------------------- the reference labels (one flag)
const argLabels = (() => { const i = process.argv.indexOf('--labels'); return i > -1 ? process.argv[i + 1] : process.env.LABELS; })();
const LB = S.labels || { file: 'data/classified-sonnet-v2.jsonl', model: 'Claude Sonnet 5', short: 'Sonnet', tag: 'Sonnet v2', audited: true, audited_model: 'Claude Sonnet 5' };
if (argLabels && resolve(REPORT, '..', argLabels) !== resolve(REPORT, '..', LB.file)) {
  console.error(`summary.json was built from ${LB.file}, not ${argLabels}. Run: python3 scripts/analyze.py --labels ${argLabels}`);
  process.exit(1);
}
const LABELS_MODEL = LB.model, LABELS_SHORT = LB.short, AUDITED = Boolean(LB.audited);
// the author's own calibration labels (review/human-labels.jsonl), summarised by analyze.py
const HC = S.human_calibration || { n: 0 };

// ---------------------------------------------------------------- the audit (report/data/13_audit_*.csv)
// scripts/audit.py writes these from the audit's own scripts (review/estimate.py, review/arithmetic.py,
// review/work/substance.py). Every audited number on the page comes from them, and the checks below tie
// them to summary.json and to the model's counts in the other CSVs.
const AUDIT_TABLES = ['13_audit_estimates', '13_audit_sampling', '13_audit_agreement', '13_audit_claims', '13_audit_substance',
  '13_audit_substance_cards', '13_audit_production', '13_audit_primary_agreement'];
const missingAudit = AUDIT_TABLES.filter((f) => !existsSync(join(DATA, `${f}.csv`)));
if (missingAudit.length) {
  console.error(`Missing ${missingAudit.join(', ')}: run python3 scripts/analyze.py, which runs scripts/audit.py.`);
  process.exit(1);
}
const optNum = (v) => (v === '' || v === undefined ? null : Number(v));
const AE = Object.fromEntries(csv('13_audit_estimates').map((r) => [r.key, {
  ...r, value: Number(r.value), lo: optNum(r.lo), hi: optNum(r.hi), model: optNum(r.model), k: optNum(r.k), n: optNum(r.n),
  frameValue: optNum(r.frame_value), frameLo: optNum(r.frame_lo), frameHi: optNum(r.frame_hi),
  ao: optNum(r.audit_only), aoLo: optNum(r.audit_only_lo), aoHi: optNum(r.audit_only_hi), plug: optNum(r.plug),
  frameModel: optNum(r.frame_model), frameAo: optNum(r.frame_audit_only), frameAoLo: optNum(r.frame_audit_only_lo), frameAoHi: optNum(r.frame_audit_only_hi),
}]));
const need = (key) => {
  if (!AE[key]) { console.error(`13_audit_estimates.csv has no row "${key}"`); process.exit(1); }
  return AE[key];
};
const AUD_SAMPLING = csv('13_audit_sampling').map((r) => ({ ...r, population: Number(r.population), reviewed: Number(r.reviewed) }));
const AUD_AGREE = csv('13_audit_agreement');
const AUD_CLAIMS = csv('13_audit_claims');
const AUD_SUB = csv('13_audit_substance').map((r) => ({ ...r, posts: Number(r.posts) }));
const AUD_PROD = csv('13_audit_production').map((r) => ({ ...r, holds: r.holds === '1', audit_realtime: r.audit_realtime === '1', views: Number(r.views) }));
const PA = Object.fromEntries(csv('13_audit_primary_agreement').map((r) => [r.field, Number(r.rate)]));
const PA_FRAME = Object.fromEntries(csv('13_audit_primary_agreement').map((r) => [r.field, Number(r.frame_rate)]));
const SA = S.audit || {};
const AUDITOR = SA.auditor || 'an independent reviewer';
const AUDITED_MODEL = SA.audited_model || 'Claude Sonnet 5';
const FRAME_SHORT = AUDITED_MODEL.replace('Claude ', '');  // the labels the audit sampled from, short: "Sonnet 5"
const LABELLED = need('labelled').value;
// the audited shares are shares of this base: the labels' own use-case base when review/estimate-opus.py ran them
const ESTBASE = need('estimate_base').value;
const MODEL_AUDIT = SA.model_audit || null;
const insideOf = (key) => { const e = need(key); return e.lo !== null && e.model !== null && e.lo <= e.model && e.model <= e.hi; };
// an audited share and its 95% interval: aud('baseline_none', 0) -> '78% (76 to 80)'; d: decimals of the
// estimate, di: of the bounds (the page rounds each number the way it is quoted in the text)
const bound = (x, di) => (x * 100).toFixed(di);
const audRange = (key, di = 1) => { const e = need(key); return `${bound(e.lo, di)} to ${bound(e.hi, di)}`; };
const aud = (key, d = 1, di = d) => { const e = need(key); return e.lo === null ? pct(e.value, d) : `${pct(e.value, d)} (${audRange(key, di)})`; };

// ---------------------------------------------------------------- dates, from the data
// summary.json carries the first and last post (UTC) and the feed snapshot time, so a refresh
// updates every date on the page and in the charts. PUBLISHED is the byline date.
const PUBLISHED = process.env.PUBLISHED || '24 September 2026';
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const [DAY0, DAY1] = S.window_days;
const dnum = (iso) => Number(iso.slice(8, 10));
const mname = (iso, short = false) => { const m = MONTHS[Number(iso.slice(5, 7)) - 1]; return short ? m.slice(0, 3) : m; };
const span = (short = false, joiner = 'to') => (DAY0.slice(0, 7) === DAY1.slice(0, 7)
  ? `${dnum(DAY0)} ${joiner} ${dnum(DAY1)} ${mname(DAY1, short)}`
  : `${dnum(DAY0)} ${mname(DAY0, short)} ${joiner} ${dnum(DAY1)} ${mname(DAY1, short)}`);
const YEAR = DAY1.slice(0, 4);
const ordinal = (n) => `${n}${n % 100 >= 11 && n % 100 <= 13 ? 'th' : ['th', 'st', 'nd', 'rd'][n % 10] || 'th'}`;
// '2026-09-16 00:28:26.330000+00:00' or '2026-09-23 18:47 UTC' -> { day: '16 September', short: '16 Sep', time: '00:28' }
const stamp = (t) => ({ day: `${dnum(t)} ${mname(t)}`, short: `${dnum(t)} ${mname(t, true)}`, time: t.slice(11, 16) });
const FIRST = stamp(S.window_utc[0]), LAST = stamp(S.window_utc[1]);
const FEED = stamp(S.feed.updated);
const LAST_PARTIAL = Boolean(S.last_day_partial);
const SOURCE = `Source: jev.openchamber.dev, ${fmt(S.posts)} posts ${span(true)} ${YEAR} (UTC), classified with ${LABELS_MODEL}, ${fmt(LABELLED)} posts audited blind by ${AUDITOR}; analysis by Matthew O'Riordan`;
const DISCLOSURE = 'Disclosure: the author is CEO of Ably, a realtime infrastructure company.';
// A chart on the page carries one short source line that points to the method at the end of the page.
// A chart file (charts/*.svg, and the PNGs made from the light files) travels without the page, so it
// keeps the full source line and the disclosure. frame() takes the footer as an option.
const PAGE_SOURCE = `Source: jev.openchamber.dev, ${fmt(S.posts)} posts, ${span(true)} ${YEAR}. Method and audit: see the end of this page.`;
const FOOTERS = { page: [PAGE_SOURCE], file: [SOURCE, DISCLOSURE] };
const FONT = "Manrope, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif";

// ---------------------------------------------------------------- palette
// Validated with the dataviz skill's validate_palette.js:
//   categorical pair (blue secondary, orange accent): PASS light and dark, CVD dE 24.7 / 26.8
//   blue ordinal steps (blueLo, blue, blueHi): PASS --ordinal light and dark
// Greys are de-emphasis marks; every grey-filled mark is also named in a legend or a label,
// and each chart has a table view on the page.
const PALETTE = {
  light: {
    surface: '#fcfcfb', ink: '#0b0b0b', ink2: '#52514e', muted: '#6f6e69', grid: '#e6e5df', axis: '#b9b8ae',
    accent: '#eb6834', blue: '#2a78d6', blueLo: '#86b6ef', blueHi: '#104281',
    g1: '#dcdbd3', g2: '#bdbcb2', g3: '#8a8981',
    seq0: '#f0efec', seq1: '#b7d3f6', seq2: '#86b6ef', seq3: '#5598e7', seq4: '#2a78d6', seq5: '#1c5cab', seq6: '#104281',
    sqt1: '#0b0b0b', sqt2: '#0b0b0b', sqt3: '#0b0b0b', sqt4: '#ffffff', sqt5: '#ffffff', sqt6: '#ffffff',
  },
  dark: {
    surface: '#1a1a19', ink: '#ffffff', ink2: '#c3c2b7', muted: '#9d9b93', grid: '#2c2c2a', axis: '#4a4a46',
    accent: '#d95926', blue: '#3987e5', blueLo: '#1c5cab', blueHi: '#b7d3f6',
    g1: '#3a3a37', g2: '#5a5954', g3: '#8a8880',
    seq0: '#242423', seq1: '#104281', seq2: '#1c5cab', seq3: '#2a78d6', seq4: '#5598e7', seq5: '#86b6ef', seq6: '#b7d3f6',
    sqt1: '#ffffff', sqt2: '#ffffff', sqt3: '#ffffff', sqt4: '#0b0b0b', sqt5: '#0b0b0b', sqt6: '#0b0b0b',
  },
};
const THEMES = {
  light: { mode: 'light', ...PALETTE.light },
  dark: { mode: 'dark', ...PALETTE.dark },
  vars: { mode: 'vars' },
};
const cssVars = (mode) => Object.entries(PALETTE[mode]).map(([k, v]) => `--v-${k}:${v}`).join(';');

// fill / stroke by role. Concrete themes get presentation attributes (most portable);
// the vars theme gets CSS custom properties so one SVG can follow the page or the OS.
function paint(T, fill, stroke) {
  if (T.mode === 'vars') {
    const s = [];
    if (fill) s.push(fill === 'none' ? 'fill:none' : `fill:var(--v-${fill})`);
    if (stroke) s.push(`stroke:var(--v-${stroke})`);
    return `style="${s.join(';')}"`;
  }
  const a = [];
  if (fill) a.push(`fill="${fill === 'none' ? 'none' : T[fill]}"`);
  if (stroke) a.push(`stroke="${T[stroke]}"`);
  return a.join(' ');
}

// ---------------------------------------------------------------- text
// Width estimate for Manrope (slightly wider than Helvetica). Used for wrapping and
// label placement; errs wide so fallback fonts never overflow.
function tw(s, size, weight = 400) {
  let w = 0;
  for (const ch of String(s)) {
    if (" iljI.,:;!|'’".includes(ch)) w += 0.29;
    else if ('ftr()[]-/'.includes(ch)) w += 0.39;
    else if ('mwMW%@'.includes(ch)) w += 0.9;
    else if (/[A-Z]/.test(ch)) w += 0.69;
    else if (/[0-9]/.test(ch)) w += 0.6;
    else if ('×–≈·'.includes(ch)) w += 0.6;
    else w += 0.57;
  }
  return w * size * (weight >= 600 ? 1.06 : 1);
}
function wrap(s, maxW, size, weight = 400) {
  const words = String(s).split(' ');
  const lines = [];
  let cur = '';
  for (const word of words) {
    const test = cur ? `${cur} ${word}` : word;
    if (cur && tw(test, size, weight) > maxW) { lines.push(cur); cur = word; } else cur = test;
  }
  if (cur) lines.push(cur);
  return lines;
}
function tx(T, x, y, s, { size = 12, weight = 400, role = 'ink', anchor = 'start' } = {}) {
  const a = [`x="${r1(x)}"`, `y="${r1(y)}"`, `font-size="${size}"`];
  if (weight !== 400) a.push(`font-weight="${weight}"`);
  if (anchor !== 'start') a.push(`text-anchor="${anchor}"`);
  return `<text ${a.join(' ')} ${paint(T, role)}>${esc(s)}</text>`;
}
// mixed runs on one line: spans = [{s, weight, role, size}]
function txs(T, x, y, spans, { size = 12, anchor = 'start' } = {}) {
  const a = [`x="${r1(x)}"`, `y="${r1(y)}"`, `font-size="${size}"`];
  if (anchor !== 'start') a.push(`text-anchor="${anchor}"`);
  const inner = spans.map((sp) => {
    const b = [];
    // Leading spaces become a dx offset: SVG renderers such as rsvg-convert strip them from a
    // tspan, which ran "81.5%" into "4,526 posts" in PNG exports. 0.29 em per space, as tw() assumes.
    const text = String(sp.s).trimStart();
    const lead = String(sp.s).length - text.length;
    if (lead) b.push(`dx="${r1(lead * 0.29 * (sp.size || size))}"`);
    if (sp.weight && sp.weight !== 400) b.push(`font-weight="${sp.weight}"`);
    if (sp.size) b.push(`font-size="${sp.size}"`);
    b.push(paint(T, sp.role || 'ink'));
    return `<tspan ${b.join(' ')}>${esc(text)}</tspan>`;
  }).join('');
  return `<text ${a.join(' ')}>${inner}</text>`;
}
const spansW = (spans, size) => sum(spans.map((sp) => tw(sp.s, sp.size || size, sp.weight || 400)));
function lines(T, x, y, text, maxW, { size = 12, lh = 16, weight = 400, role = 'ink', anchor = 'start' } = {}) {
  const ls = wrap(text, maxW, size, weight);
  const svg = ls.map((l, i) => tx(T, x, y + size + i * lh, l, { size, weight, role, anchor })).join('');
  return { svg, h: size + (ls.length - 1) * lh, n: ls.length };
}

// ---------------------------------------------------------------- marks
const ln = (T, x1, y1, x2, y2, role = 'grid', w = 1) =>
  `<line x1="${r1(x1)}" y1="${r1(y1)}" x2="${r1(x2)}" y2="${r1(y2)}" stroke-width="${w}" ${paint(T, null, role)}/>`;
const rect = (T, x, y, w, h, role, extra = '') =>
  `<rect x="${r1(x)}" y="${r1(y)}" width="${r1(Math.max(w, 0))}" height="${r1(Math.max(h, 0))}" ${paint(T, role)}${extra}/>`;
function hbarD(x, y, w, h, r = 4) { // rounded data-end on the right, square at the baseline
  if (w <= 0) return '';
  r = Math.min(r, w, h / 2);
  return `M${r1(x)} ${r1(y)}h${r1(w - r)}a${r1(r)} ${r1(r)} 0 0 1 ${r1(r)} ${r1(r)}v${r1(h - 2 * r)}a${r1(r)} ${r1(r)} 0 0 1 ${r1(-r)} ${r1(r)}h${r1(-(w - r))}z`;
}
function vbarD(x, yBase, w, h, r = 4) { // rounded data-end on top
  if (h <= 0) return '';
  r = Math.min(r, h, w / 2);
  return `M${r1(x)} ${r1(yBase)}v${r1(-(h - r))}a${r1(r)} ${r1(r)} 0 0 1 ${r1(r)} ${r1(-r)}h${r1(w - 2 * r)}a${r1(r)} ${r1(r)} 0 0 1 ${r1(r)} ${r1(r)}v${r1(h - r)}z`;
}
const pathEl = (T, d, role, title) => (d ? `<path d="${d}" ${paint(T, role)}>${title ? `<title>${esc(title)}</title>` : ''}</path>` : '');

// legend: items [{label, role, kind: rect|line|dot|diamond|tick}]
function legend(T, items, x0, x1, y, { size = 12 } = {}) {
  const out = [];
  const lh = size + 9;
  let x = x0, row = 0;
  for (const it of items) {
    const w = 20 + tw(it.label, size) + 18;
    if (x > x0 && x + w - 18 > x1) { x = x0; row++; }
    const cy = y + row * lh + size * 0.55;
    const kind = it.kind || 'rect';
    if (kind === 'rect') out.push(`<rect x="${r1(x)}" y="${r1(cy - 6)}" width="12" height="12" rx="2" ${paint(T, it.role)}/>`);
    else if (kind === 'line') out.push(ln(T, x - 1, cy, x + 15, cy, it.role, it.width || 2.5));
    else if (kind === 'dot') out.push(`<circle cx="${r1(x + 6)}" cy="${r1(cy)}" r="4.5" ${paint(T, it.role)}/>`);
    else if (kind === 'diamond') out.push(`<path d="M${r1(x + 6)} ${r1(cy - 6)}l6 6l-6 6l-6 -6z" ${paint(T, it.role)}/>`);
    else if (kind === 'tick') out.push(ln(T, x - 1, cy, x + 15, cy, it.role, 2.5));
    else if (kind === 'vline') out.push(ln(T, x + 6, cy - 7, x + 6, cy + 7, it.role, 2));
    out.push(tx(T, x + 20, y + row * lh + size - 1, it.label, { size, role: 'ink' }));
    x += w;
  }
  return { svg: out.join(''), y: y + (row + 1) * lh };
}

// nice axis maximum and step
function nice(max, maxTicks = 5) {
  let best = null;
  for (let k = -2; k <= 7; k++) {
    for (const s of [1, 2, 2.5, 5]) {
      const step = s * 10 ** k;
      const n = Math.ceil(max / step);
      if (n < 2 || n > maxTicks) continue;
      const m = n * step;
      if (!best || m < best.max || (m === best.max && step > best.step)) best = { max: m, step };
    }
  }
  return best;
}

// ---------------------------------------------------------------- chart frame
function frame(T, chart, W, variant, footer = 'file') {
  const narrow = W < 480;
  const pad = narrow ? 16 : 24;
  const inner = W - 2 * pad;
  const id = `${chart.key}-${variant}`;
  const parts = [];
  let y = pad;
  const ts = narrow ? 17 : 20;
  let b = lines(T, pad, y, chart.title, inner, { size: ts, lh: Math.round(ts * 1.24), weight: 700 });
  parts.push(b.svg); y += b.h + 9;
  b = lines(T, pad, y, chart.subtitle, inner, { size: 13, lh: 18, role: 'ink2' });
  parts.push(b.svg); y += b.h + 18;
  const body = chart.body(T, { x0: pad, x1: W - pad, y0: y, W, narrow, id });
  parts.push(body.svg); y = body.y + 22;
  parts.push(ln(T, pad, y, W - pad, y, 'grid')); y += 3;
  for (const f of FOOTERS[footer]) {
    b = lines(T, pad, y, f, inner, { size: 11, lh: 14.5, role: 'muted' });
    parts.push(b.svg); y += b.h + 4;
  }
  const H = Math.ceil(y + pad - 6);
  const desc = `${chart.subtitle} ${chart.desc || ''}`.trim();
  const style = variant.endsWith('auto') ? `<style>svg{${cssVars('light')}}@media (prefers-color-scheme: dark){svg{${cssVars('dark')}}}</style>` : '';
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-labeledby="${id}-t ${id}-d" font-family="${FONT}">`
    + `<title id="${id}-t">${esc(chart.title)}</title><desc id="${id}-d">${esc(desc)}</desc>${style}`
    + rect(T, 0, 0, W, H, 'surface') + parts.join('') + '</svg>';
}

// ---------------------------------------------------------------- figure order
// Page order. Charts 11 and 12 break down figure 1: chart 11 its Other or meta posts ("Figure 1b"), chart 12
// the 91 builds most likely to show something new among its measured demos ("Figure 1c", the substance test). Every other
// figure keeps the number of its chart file.
const ORDER = ['01', '11', '12', '02', '03', '04', '05', '06', '07', '08', '09', '10'];
const FIG_LABEL = { '11': '1b', '12': '1c' };
const figNo = (key) => FIG_LABEL[key] || String(Number(key));

// ---------------------------------------------------------------- shared data
const FAM = {
  other_or_meta: ['Other or meta', 'Other/meta'],
  games_control_loops_simulation: ['Games and control loops', 'Games'],
  classification_routing_triage: ['Classification and routing', 'Classification'],
  agent_harness_and_tool_gating: ['Agent harness and gating', 'Agent harness'],
  search_rerank_extraction: ['Search, rerank, extraction', 'Search'],
  evals_and_judging: ['Evals and judging', 'Evals'],
  moderation_and_guardrails: ['Moderation and guardrails', 'Moderation'],
  trading_and_markets: ['Trading and markets', 'Trading'],
  data_and_telemetry: ['Data and telemetry', 'Data'],
  browser_and_computer_use: ['Browser and computer use', 'Browser'],
  compaction_and_context: ['Compaction and context', 'Compaction'],
  live_chat_streams_events: ['Live chat and streams', 'Live chat'],
  collaboration_and_typing: ['Collaboration and typing', 'Collaboration'],
  voice_and_turn_taking: ['Voice and turn-taking', 'Voice'],
};
const GAMES = 'games_control_loops_simulation';

const famRows = csv('01_family_distribution');
const FAMS = famRows.map((r) => r.family);
const famPosts = Object.fromEntries(famRows.map((r) => [r.family, num(r.posts)]));
const BASE = S.use_case_base;
check(sum(Object.values(famPosts)) === BASE, 'family posts do not sum to the use-case base');
check(FAMS.every((f) => FAM[f]), 'unknown family in 01_family_distribution');
const perCard = csv('08_ladder_per_card');
check(perCard.length === BASE, `08_ladder_per_card has ${perCard.length} rows, base is ${BASE}`);

// ================================================================ chart 1: the week, on the measurement ladder
// Each post is tinted by its evidence label, the field the audit found stable: no measurement, measured demo,
// measured production. The model's measured-production posts are split by the audit's re-read of every one.
const LADDER = [
  { key: 'no_measurement', label: 'No measurement', role: 'g2' },
  { key: 'measured_demo', label: 'Measured demo', role: 'blueLo' },
  { key: 'prod_not', label: 'Labeled production, not confirmed', role: 'blue' },
  { key: 'prod_ok', label: 'Production, confirmed', role: 'accent' },
];
const stepOf = (r) => (r.ladder === 'measured_production' ? (r.audit_production === 'holds' ? 'prod_ok' : 'prod_not') : r.ladder);
const c1 = Object.fromEntries(FAMS.map((f) => [f, Object.fromEntries(LADDER.map((b) => [b.key, 0]))]));
perCard.forEach((r) => { c1[r.family][stepOf(r)]++; });
const stepTot = Object.fromEntries(LADDER.map((b) => [b.key, sum(FAMS.map((f) => c1[f][b.key]))]));
const ladderRows = Object.fromEntries(csv('08_ladder').map((r) => [r.step, { posts: num(r.posts), share_views: num(r.share_views) }]));
check(stepTot.no_measurement === ladderRows.no_measurement.posts, 'ladder: per-card no-measurement posts vs 08_ladder');
check(stepTot.measured_demo === ladderRows.measured_demo.posts, 'ladder: per-card measured demos vs 08_ladder');
check(stepTot.prod_not + stepTot.prod_ok === ladderRows.measured_production.posts, 'ladder: per-card production vs 08_ladder');
check(ladderRows.measured_production.posts === S.evidence.measured_production, 'ladder production vs summary evidence');
check(stepTot.prod_ok === S.ladder.measured_production.confirmed_by_audit, 'confirmed production vs summary');
const PROD = need('production_strict'), PROD1 = need('production_first_pass');
// the labels' production posts: the ones the audit re-read (k hold), and the rest (n seen in its samples, k called production)
const PIC = need('production_primary_in_census'), POT = need('production_primary_other');
check(ladderRows.measured_demo.posts === need('ladder_measured_demo_model').value, 'measured demos vs the audit tables');
check(stepTot.prod_ok === PIC.k && PIC.value + POT.value === ladderRows.measured_production.posts, 'confirmed production vs the audit census');
if (AUDITED) check(stepTot.prod_ok === PROD.k && ladderRows.measured_production.posts === PROD.n, 'confirmed production vs the audit census (audited labels)');
// production is always the audit's count; the labels' own count is not published (the audit agrees with PA_READ.k of the PA_READ.n it read)
const PA_READ = { k: PIC.k + POT.k, n: PIC.value + POT.n };
const prodOfLabels = AUDITED
  ? `The model labeled ${fmt(ladderRows.measured_production.posts)} posts measured production, the audit re-read all ${fmt(PROD.n)}, and ${fmt(PROD.k)} hold.`
  : `The audit re-read every post the ${FRAME_SHORT} labels called production and ${fmt(PROD.k)} hold. ${LABELS_SHORT} labels those ${fmt(PROD.k)} production too, but of all the posts it labels production the audit read ${fmt(PA_READ.n)} and agrees with only ${fmt(PA_READ.k)}, so the count here is the audit's.`;
const measuredOf = (f) => c1[f].measured_demo + c1[f].prod_not + c1[f].prod_ok;
const measuredDemoShare = ladderRows.measured_demo.posts / BASE;
const prodWords = (k) => (k === 0 ? 'none' : fmt(k));

const chart1 = {
  key: '01', file: '01-week-in-one-picture', section: 'The week in one picture',
  title: `About a third of the week's posts measured a demo, and ${fmt(stepTot.prod_ok)} of ${fmt(BASE)} measured production`,
  subtitle: `${fmt(BASE)} posts. Audited: measured demo ${aud('ladder_measured_demo', 0)}, production ${pct(PROD.value, 2)} (at most ${pct(PROD.hi, 0)}).`,
  desc: LADDER.map((b) => `${b.label}: ${fmt(stepTot[b.key])} posts.`).join(' '),
  body(T, { x0, x1, y0, narrow }) {
    const out = [];
    const lg = legend(T, LADDER.map((b) => ({ label: `${b.label} ${fmt(stepTot[b.key])}`, role: b.role })), x0, x1, y0);
    out.push(lg.svg);
    let y = lg.y + 12;
    const pitch = narrow ? 4 : 5, sq = pitch - 1;
    const labelW = narrow ? 0 : 184;
    const gx0 = x0 + labelW;
    const cols = Math.floor((x1 - gx0 + 1) / pitch);
    for (const f of FAMS) {
      const n = famPosts[f];
      const rows = Math.ceil(n / cols);
      const sub = `${fmt(n)} posts · ${pct(measuredOf(f) / n, 0)} measured`;
      let by;
      if (narrow) {
        out.push(txs(T, x0, y + 11, [{ s: FAM[f][0], weight: 600 }, { s: `   ${sub}`, role: 'ink2', size: 11 }], { size: 12 }));
        by = y + 17;
      } else {
        out.push(tx(T, x0, y + 10, FAM[f][0], { size: 12.5, weight: 600 }));
        out.push(tx(T, x0, y + 25, sub, { size: 11.5, role: 'ink2' }));
        by = y + 1;
      }
      let i = 0;
      for (const b of LADDER) {
        const k = c1[f][b.key];
        if (!k) continue;
        let d = '';
        for (let j = 0; j < k; j++, i++) {
          const cx = gx0 + (i % cols) * pitch, cy = by + Math.floor(i / cols) * pitch;
          d += `M${cx} ${cy}h${sq}v${sq}h-${sq}z`;
        }
        out.push(pathEl(T, d, b.role, `${FAM[f][0]}, ${b.label.toLowerCase()}: ${fmt(k)} posts`));
      }
      const gridH = rows * pitch;
      y = narrow ? by + gridH + 11 : y + Math.max(gridH, 30) + 9;
    }
    return { svg: out.join(''), y: y - 6 };
  },
  table() {
    return {
      head: ['Family', ...LADDER.map((b) => b.label), 'Posts'],
      rows: [
        ...FAMS.map((f) => [FAM[f][0], ...LADDER.map((b) => fmt(c1[f][b.key])), fmt(famPosts[f])]),
        ['All posts', ...LADDER.map((b) => `${fmt(stepTot[b.key])} (${pct(stepTot[b.key] / BASE)})`), fmt(BASE)],
      ],
    };
  },
};

// ================================================================ chart 2: attention
const lorenz = csv('06_lorenz_points').map((r) => ({ p: num(r.share_of_cards_top) * 100, v: num(r.share_of_views) }));
const conc = csv('06_attention_concentration');
const stats = csv('06_attention_stats')[0];
const byDay = csv('06_attention_by_day');
const top1 = conc.find((r) => r.views_top === '1%');
check(near(num(top1.views_share), S.concentration.top1pct_views), 'top 1% views share vs summary');
check(near(num(top1.likes_share), S.concentration.top1pct_likes), 'top 1% likes share vs summary');
const early = byDay.filter((r) => r.day <= '2026-09-19');
const earlyViews = sum(early.map((r) => num(r.share_views)));
const earlyPosts = sum(early.map((r) => num(r.posts))) / BASE;
const totalViews = num(stats.total_views), totalLikes = num(stats.total_likes);
// the audit recounted attention from the same data on its own base: to the digit on the audited labels, within a point otherwise
const attTol = AUDITED ? 1e-5 : 0.01;
check(near(need('attention_top1_views').value, num(top1.views_share), attTol) && near(need('attention_top1_likes').value, num(top1.likes_share), attTol)
  && near(need('attention_top1_views_excl_suspect').value, num(stats.top1pct_views_excl_suspect), attTol)
  && near(need('attention_top_card').value, num(stats.top_card_share), attTol), 'attention: the audit recount vs 06_attention_*');
const attnAudit = AUDITED ? 'The audit recounted these from the same data and got the same numbers.'
  : `The audit recounted these on the ${fmt(SA.use_case_base)} posts it sampled from and got ${pct(need('attention_top1_views').value)} and ${pct(need('attention_top1_views_excl_suspect').value)}.`;

const chart2 = {
  key: '02', file: '02-attention-concentration', section: 'Half the views went to 1 percent of posts',
  title: `Half the views went to 1 percent of posts: the top ${top1.views_cards} held ${pct(num(top1.views_share))}`,
  subtitle: `${fmt(BASE)} posts, ${(totalViews / 1e6).toFixed(1)}M views and ${fmt(totalLikes)} likes.`,
  desc: `Top 1% of posts: ${pct(num(top1.views_share))} of views, ${pct(num(top1.likes_share))} of likes. Median post: ${fmt(num(stats.median_views))} views.`,
  body(T, { x0, x1, y0, narrow }) {
    const out = [];
    const lg = legend(T, [
      { label: 'Views', role: 'blue', kind: 'line' },
      { label: 'Likes', role: 'g3', kind: 'line' },
      { label: 'Equal share for every post', role: 'axis', kind: 'line', width: 1.5 },
    ], x0, x1, y0);
    out.push(lg.svg);
    const px0 = x0 + 36, px1 = x1 - 6;
    const py0 = lg.y + 22, h = narrow ? 230 : 280, py1 = py0 + h;
    const X = (p) => px0 + ((Math.log10(p) + 2) / 4) * (px1 - px0);
    const Y = (v) => py1 - v * h;
    out.push(tx(T, x0, py0 - 12, 'Cumulative share of views or likes', { size: 11.5, role: 'ink2' }));
    for (const v of [0, 0.25, 0.5, 0.75, 1]) {
      out.push(ln(T, px0, Y(v), px1, Y(v), v === 0 ? 'axis' : 'grid'));
      out.push(tx(T, px0 - 6, Y(v) + 4, `${v * 100}%`, { size: 11, role: 'ink2', anchor: 'end' }));
    }
    for (const [p, l] of [[0.01, '0.01%'], [0.1, '0.1%'], [1, '1%'], [10, '10%'], [100, '100%']]) {
      out.push(ln(T, X(p), py0, X(p), py1, 'grid'));
      out.push(tx(T, X(p), py1 + 16, l, { size: 11, role: 'ink2', anchor: p === 100 ? 'end' : p === 0.01 ? 'start' : 'middle' }));
    }
    out.push(tx(T, (px0 + px1) / 2, py1 + 34, 'Share of posts, most-viewed first (log scale)', { size: 11.5, role: 'ink2', anchor: 'middle' }));
    // equal-share reference
    let d = '';
    for (let i = 0; i <= 80; i++) { const p = 10 ** (-2 + (4 * i) / 80); d += `${i ? 'L' : 'M'}${r1(X(p))} ${r1(Y(p / 100))}`; }
    out.push(`<path d="${d}" fill="none" stroke-width="1.5" ${paint(T, null, 'axis')}/>`);
    out.push(tx(T, X(35), Y(0.35) + 16, 'equal share', { size: 11, role: 'ink2', anchor: 'middle' }));
    // likes: the six measured cut points of 06_attention_concentration
    const likePts = [...conc.map((r) => ({ p: (num(r.likes_cards) / BASE) * 100, v: num(r.likes_share), top: r.likes_top })), { p: 100, v: 1, top: '100%' }];
    d = likePts.map((q, i) => `${i ? 'L' : 'M'}${r1(X(q.p))} ${r1(Y(q.v))}`).join('');
    out.push(`<path d="${d}" fill="none" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" ${paint(T, null, 'g3')}/>`);
    // views: every point of 06_lorenz_points plus the measured cut points of
    // 06_attention_concentration (the Lorenz file is sampled every 11 posts, coarse at the top)
    const viewPts = [...lorenz, ...conc.map((r) => ({ p: (num(r.views_cards) / BASE) * 100, v: num(r.views_share) }))]
      .sort((m, n) => m.p - n.p)
      .filter((q, i, arr) => i === 0 || Math.abs(q.p - arr[i - 1].p) > 1e-9);
    d = viewPts.map((q, i) => `${i ? 'L' : 'M'}${r1(X(q.p))} ${r1(Y(q.v))}`).join('');
    out.push(`<path d="${d}" fill="none" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" ${paint(T, null, 'blue')}/>`);
    for (const q of likePts.slice(0, -1)) {
      out.push(`<circle cx="${r1(X(q.p))}" cy="${r1(Y(q.v))}" r="4" stroke-width="2" ${paint(T, 'g3', 'surface')}><title>Top ${q.top} of posts: ${pct(q.v)} of likes</title></circle>`);
    }
    for (const r of conc) {
      const p = (num(r.views_cards) / BASE) * 100;
      out.push(`<circle cx="${r1(X(p))}" cy="${r1(Y(num(r.views_share)))}" r="${r.views_top === '1%' ? 5 : 4}" stroke-width="2" ${paint(T, 'blue', 'surface')}><title>Top ${r.views_top} of posts (${fmt(num(r.views_cards))}): ${pct(num(r.views_share))} of views</title></circle>`);
    }
    // top 1% annotation
    const p1 = (num(top1.views_cards) / BASE) * 100;
    out.push(ln(T, X(p1), Y(num(top1.views_share)) + 6, X(p1), py1, 'ink2', 1));
    const ax = X(p1) + 8, ay = Y(0.36);
    out.push(tx(T, ax, ay, `Top 1% of posts (${top1.views_cards})`, { size: 12, weight: 700 }));
    out.push(tx(T, ax, ay + 16, `${pct(num(top1.views_share))} of views`, { size: 12 }));
    out.push(tx(T, ax, ay + 31, `${pct(num(top1.likes_share))} of likes`, { size: 12 }));
    // top post
    const t0 = lorenz[0];
    out.push(tx(T, X(t0.p) - 2, Y(t0.v) + 17, `The top post: ${pct(t0.v)}`, { size: 11.5, role: 'ink2' }));
    return { svg: out.join(''), y: py1 + 40 };
  },
  table() {
    return {
      head: ['Top share of posts', 'Posts', 'Share of views', 'Share of likes', 'Smallest post in group (views)'],
      rows: conc.map((r) => [r.views_top, fmt(num(r.views_cards)), pct(num(r.views_share)), pct(num(r.likes_share)), fmt(num(r.views_min_in_group))]),
    };
  },
};

// ================================================================ chart 3: baselines
const baseRows = Object.fromEntries(csv('05_baseline_overall').map((r) => [r.baseline, r]));
const BASELINES = [
  ['none', 'Nothing', false],
  ['frontier_llm', 'Frontier LLM', false],
  ['small_llm', 'Small LLM', false],
  ['rules_or_regex', 'Rules or regex', true],
  ['classic_classifier_or_ml', 'Classic classifier or ML', true],
  ['vendor_api', 'Vendor API', true],
];
const incShare = sum(BASELINES.filter((b) => b[2]).map((b) => num(baseRows[b[0]].share_posts)));
const incPosts = sum(BASELINES.filter((b) => b[2]).map((b) => num(baseRows[b[0]].posts)));
check(near(incShare, S.baseline_shares.incumbent_classic_rules_vendor), 'incumbent share vs summary');

const AUD_BASE = { none: 'baseline_none', frontier_llm: 'baseline_frontier_llm', small_llm: 'baseline_small_llm' };
const AB = { none: need('baseline_none'), frontier: need('baseline_frontier_llm'), small: need('baseline_small_llm'), repl: need('baseline_replacement') };
if (AUDITED) {
  check(near(AB.none.model, num(baseRows.none.share_posts), 1e-4) && near(AB.frontier.model, num(baseRows.frontier_llm.share_posts), 1e-4)
    && near(AB.small.model, num(baseRows.small_llm.share_posts), 1e-4) && near(AB.repl.model, incShare, 1e-4), 'baseline model shares vs the audit tables');
  check(AUD_SAMPLING.find((r) => r.key === 'baseline_none').population === num(baseRows.none.posts)
    && AUD_SAMPLING.find((r) => r.key === 'replacement_baseline').population === incPosts, 'baseline strata vs 05_baseline_overall');
}
const allBaseInside = ['baseline_none', 'baseline_frontier_llm', 'baseline_small_llm', 'baseline_replacement'].every(insideOf);
// the rounding the text uses: whole-number bounds, one decimal under 10%
const audBase = { none: aud('baseline_none', 0), frontier: aud('baseline_frontier_llm', 1, 0), small: aud('baseline_small_llm', 1, 0), repl: aud('baseline_replacement', 1, 0) };

const chart3 = {
  key: '03', file: '03-what-they-compared-against', section: 'What did they compare against?',
  title: 'About four in five posts compared Jev with nothing, and about 1 in 30 with what it would replace',
  subtitle: `${fmt(BASE)} posts. Audited: nothing ${audBase.none}, the tools Jev would replace ${audBase.repl}.`,
  desc: BASELINES.map((b) => `${b[1]}: ${pct(num(baseRows[b[0]].share_posts))}.`).join(' ') + ` Audited: nothing ${audBase.none}, frontier LLM ${audBase.frontier}, small LLM ${audBase.small}, the tools Jev would replace ${audBase.repl}.`,
  body(T, { x0, x1, y0, narrow }) {
    const out = [];
    const lg = legend(T, [
      { label: `${LABELS_SHORT}'s labels`, role: 'g2' },
      { label: 'Audit estimate and 95% interval', role: 'ink', kind: 'diamond' },
    ], x0, x1, y0, { size: 11.5 });
    out.push(lg.svg);
    const labelW = narrow ? 0 : 172;
    const bx0 = x0 + labelW, bx1 = x1 - 8;
    const barH = 18, pitch = narrow ? 52 : 40;
    let y = lg.y + 12;
    const top = y;
    const Xw = (s) => s * (bx1 - bx0);
    const rowsY = [];
    for (const [key, label, inc] of BASELINES) {
      const r = baseRows[key];
      const s = num(r.share_posts), w = Xw(s);
      const by = narrow ? y + 18 : y;
      if (narrow) out.push(tx(T, x0, y + 12, label, { size: 12, weight: 600 }));
      else out.push(tx(T, x0, by + 13, label, { size: 12.5, weight: 600 }));
      out.push(pathEl(T, hbarD(bx0, by, Math.max(w, 1.5), barH), inc ? 'blue' : 'g2', `${label}: ${pct(s)} of posts (${fmt(num(r.posts))}), ${LABELS_SHORT}'s labels`));
      const spans = [{ s: pct(s), weight: 700 }, { s: `  ${fmt(num(r.posts))} posts`, role: 'ink2', size: 11.5 }];
      const lw = spansW(spans, 12.5);
      if (w > lw + 20) out.push(txs(T, bx0 + w - 8, by + 13, spans, { size: 12.5, anchor: 'end' }));
      else out.push(txs(T, bx0 + Math.max(w, 1.5) + 7, by + 13, spans, { size: 12.5 }));
      // the audit's estimate for this comparison, just under the bar
      if (AUD_BASE[key]) {
        const e = need(AUD_BASE[key]);
        const my = by + barH + 7, xa = bx0 + Xw(e.lo), xb = bx0 + Xw(e.hi), xe = bx0 + Xw(e.value);
        out.push(`<g><title>${esc(`${label}: audit ${pct(e.value)} (95% interval ${pct(e.lo)} to ${pct(e.hi)})`)}</title>`
          + ln(T, xa, my, xb, my, 'ink', 1.5) + ln(T, xa, my - 3.5, xa, my + 3.5, 'ink', 1.5) + ln(T, xb, my - 3.5, xb, my + 3.5, 'ink', 1.5)
          + `<path d="M${r1(xe)} ${r1(my - 5)}l5 5l-5 5l-5 -5z" stroke-width="1.2" ${paint(T, 'ink', 'surface')}/></g>`);
        const note = `audit ${key === 'none' ? audBase.none : key === 'frontier_llm' ? audBase.frontier : audBase.small}`;
        const nw = tw(note, 11);
        if (xb + 8 + nw <= x1) out.push(tx(T, xb + 8, my + 4, note, { size: 11, role: 'ink2' }));
        else out.push(tx(T, xa - 8, my + 4, note, { size: 11, role: 'ink2', anchor: 'end' }));
      }
      rowsY.push({ by, inc, end: Math.max(bx0 + Math.max(w, 1.5) + 7 + lw, narrow ? x0 + tw(label, 12, 600) : 0) });
      y += pitch;
    }
    // gridlines under the plot (drawn after so ticks read; bars are opaque)
    const bottom = y - pitch + (narrow ? 18 : 0) + barH + 8;
    const grid = [];
    for (const v of [0, 0.25, 0.5, 0.75, 1]) {
      grid.push(ln(T, bx0 + Xw(v), top - 4, bx0 + Xw(v), bottom, v === 0 ? 'axis' : 'grid'));
      grid.push(tx(T, bx0 + Xw(v), bottom + 15, `${v * 100}%`, { size: 11, role: 'ink2', anchor: v === 1 ? 'end' : v === 0 ? 'start' : 'middle' }));
    }
    // bracket for the tools Jev would replace, with the audit's estimate for the group
    const inc = rowsY.filter((r) => r.inc);
    const bxk = Math.max(...inc.map((r) => r.end)) + 14;
    const yA = inc[0].by + 1, yB = inc[inc.length - 1].by + barH - 1;
    out.push(ln(T, bxk, yA, bxk, yB, 'ink', 1.5), ln(T, bxk - 5, yA, bxk, yA, 'ink', 1.5), ln(T, bxk - 5, yB, bxk, yB, 'ink', 1.5));
    const tb = lines(T, bxk + 10, (yA + yB) / 2 - 30, `${pct(incShare)} combined (${incPosts} posts): the tools Jev would replace. Audit: ${audBase.repl}`, x1 - bxk - 10, { size: 12.5, lh: 16, weight: 600 });
    out.push(tb.svg);
    return { svg: grid.join('') + out.join(''), y: bottom + 22 };
  },
  table() {
    const auditOf = { none: audBase.none, frontier_llm: audBase.frontier, small_llm: audBase.small };
    return {
      head: ['Baseline', 'Posts', 'Share of posts', 'Share of views', 'Audit estimate (95% interval)'],
      rows: [
        ...BASELINES.map(([k, l]) => [l, fmt(num(baseRows[k].posts)), pct(num(baseRows[k].share_posts)), pct(num(baseRows[k].share_views)), auditOf[k] || '']),
        ['The tools Jev would replace (the last three)', fmt(incPosts), pct(incShare), '', audBase.repl],
      ],
    };
  },
};

// ================================================================ chart 4: evidence
const EVID = [
  ['measured_production', AUDITED ? 'Measured production' : 'Labeled production', 'blueHi'],
  ['measured_demo', 'Measured demo', 'blueLo'],
  ['demo_no_numbers', 'Demo, no numbers', 'g2'],
  ['proposal_or_idea', 'Proposal or idea', 'g3'],
  ['commentary_or_meme', 'Commentary or meme', 'g1'],
];
const evFam = Object.fromEntries(csv('03_evidence_by_family_counts').map((r) => [r.family, r]));
const evAll = Object.fromEntries(csv('03_evidence_overall').map((r) => [r.evidence, num(r.posts)]));
check(evAll.measured_production === S.evidence.measured_production, 'measured production vs summary');
const measuredShare = (r) => (num(r.measured_production) + num(r.measured_demo)) / sum(EVID.map((e) => num(r[e[0]])));
const evOrder = [...FAMS].sort((a, b) => measuredShare(evFam[b]) - measuredShare(evFam[a]));
const P = S.production;
const prodHeld = AUD_PROD.filter((r) => r.holds);
check(prodHeld.length === PROD.k && AUD_PROD.length === PROD.n, 'production census rows vs the estimates');
check(prodHeld.every((r) => r.audit_evidence === 'measured_production'), 'production census: a held card is not measured production');
if (AUDITED) {
  check(AUD_SAMPLING.find((r) => r.key === 'measured_production').population === evAll.measured_production
    && AUD_SAMPLING.find((r) => r.key === 'demo_no_numbers').population === evAll.demo_no_numbers
    && AUD_SAMPLING.find((r) => r.key === 'measured_demo').population === evAll.measured_demo, 'evidence strata vs 03_evidence_overall');
}

const chart4 = {
  key: '04', file: '04-claims-without-numbers', section: 'Claims without numbers',
  title: `Two thirds of builds showed no numbers, and ${fmt(PROD.k)} of ${fmt(BASE)} measured production on a blind re-read`,
  subtitle: `${fmt(BASE)} posts. Audited: no measurement ${aud('ladder_no_measurement', 0)}, production ${pct(PROD.value, 2)} (at most ${pct(PROD.hi, 0)}).`,
  desc: EVID.map((e) => `${e[1]}: ${fmt(evAll[e[0]])} posts.`).join(' '),
  body(T, { x0, x1, y0, narrow }) {
    const out = [];
    const lg = legend(T, EVID.map((e) => ({ label: e[1], role: e[2] })), x0, x1, y0);
    out.push(lg.svg);
    const labelW = narrow ? 0 : 194, right = 48;
    const bx0 = x0 + labelW, bx1 = x1 - right, bw = bx1 - bx0;
    const barH = 14, pitch = narrow ? 33 : 22, gap = 2;
    let y = lg.y + 30;
    const top = y;
    out.push(tx(T, x1, y - 8, 'measured', { size: 10.5, role: 'ink2', anchor: 'end' }));
    const rows = [['All posts', { ...Object.fromEntries(EVID.map((e) => [e[0], evAll[e[0]]])) }, true], ...evOrder.map((f) => [FAM[f][0], evFam[f], false])];
    const barYs = [];
    rows.forEach(([label, r, isAll], idx) => {
      const counts = EVID.map((e) => num(r[e[0]]));
      const n = sum(counts);
      const by = narrow ? y + 16 : y;
      if (narrow) out.push(txs(T, x0, y + 11, [{ s: label, weight: isAll ? 800 : 600 }, { s: `  ${fmt(n)}`, role: 'ink2', size: 11 }], { size: 12 }));
      else out.push(txs(T, x0, by + 11.5, [{ s: label, weight: isAll ? 800 : 600 }, { s: `  ${fmt(n)}`, role: 'ink2', size: 11 }], { size: 12 }));
      let x = bx0;
      const nz = counts.map((c, i) => [c, i]).filter(([c]) => c > 0);
      nz.forEach(([c, i], k) => {
        const w = (c / n) * bw;
        const last = k === nz.length - 1;
        const dw = Math.max(last ? w : w - gap, 1.5);
        const d = last ? hbarD(x, by, dw, barH) : `M${r1(x)} ${r1(by)}h${r1(dw)}v${barH}h${r1(-dw)}z`;
        out.push(pathEl(T, d, EVID[i][2], `${label}, ${EVID[i][1].toLowerCase()}: ${fmt(c)} posts (${pct(c / n)})`));
        x += w;
      });
      out.push(tx(T, x1, by + 11.5, pct(measuredShare(r), 0), { size: 12, weight: isAll ? 700 : 400, role: isAll ? 'ink' : 'ink2', anchor: 'end' }));
      barYs.push(by);
      y += pitch + (isAll ? (narrow ? 24 : 10) : 0);
    });
    // production call-out on the All row: above the bar, or under it in the phone layout
    const allY = barYs[0];
    const callout = AUDITED ? `Measured production: ${evAll.measured_production} as labeled, ${PROD.k} on re-read` : `Measured production: ${PROD.k} posts on the audit's re-read`;
    if (narrow) {
      out.push(ln(T, bx0 + 1, allY + barH, bx0 + 1, allY + barH + 8, 'ink', 1.5));
      out.push(tx(T, bx0 + 5, allY + barH + 12, callout, { size: 11.5, weight: 600 }));
    } else {
      out.push(ln(T, bx0 + 1, allY - 11, bx0 + 1, allY, 'ink', 1.5));
      out.push(tx(T, bx0 + 5, allY - 4, callout, { size: 11.5, weight: 600 }));
    }
    const bottom = barYs[barYs.length - 1] + barH + 8;
    const grid = [];
    for (const v of [0, 0.5, 1]) {
      grid.push(ln(T, bx0 + v * bw, top - 16, bx0 + v * bw, bottom, v === 0 ? 'axis' : 'grid'));
      grid.push(tx(T, bx0 + v * bw, bottom + 15, `${v * 100}%`, { size: 11, role: 'ink2', anchor: v === 1 ? 'end' : v === 0 ? 'start' : 'middle' }));
    }
    grid.push(tx(T, bx0 + bw / 2, bottom + 31, 'Share of the family’s posts', { size: 11.5, role: 'ink2', anchor: 'middle' }));
    return { svg: grid.join('') + out.join(''), y: bottom + 36 };
  },
  table() {
    return {
      head: ['Family', ...EVID.map((e) => e[1]), 'Measured share'],
      rows: [
        ['All posts', ...EVID.map((e) => fmt(evAll[e[0]])), pct(measuredShare(evAll))],
        ...evOrder.map((f) => [FAM[f][0], ...EVID.map((e) => fmt(num(evFam[f][e[0]]))), pct(measuredShare(evFam[f]))]),
      ],
    };
  },
};

// ================================================================ chart 5: claims
const chipsLong = csv('11_chip_multiples_long');
const chipSum = Object.fromEntries(csv('11_chip_multiples').map((r) => [r.claim, r]));
const CLAIMS = [
  { claim: 'cost multiple (N× cheaper)', short: 'Cost claims, N× cheaper', surveyKey: 'cost' },
  { claim: 'speed multiple (N× faster)', short: 'Speed claims, N× faster', surveyKey: 'speed' },
];
// OpenChamber's own survey of user reports, as cited in report/landscape.md section 11
// (https://openchamber.dev/blog/jev-typesafe-ai/). Not a CSV value: an external cross-check.
const SURVEY = { cost: 30, speed: 7 };
// Optional measured small-model reference band. The Pong comparison's "5 to 10x cost, 2 to 4x latency
// from the Pong comparison" is not in the report data, so it is not drawn. To draw it, add
// data/14_small_model_reference.csv with columns claim,low,high,label (claim = cost|speed).
const REF_FILE = join(DATA, '14_small_model_reference.csv');
const REF = existsSync(REF_FILE) ? Object.fromEntries(csv('14_small_model_reference').map((r) => [r.claim, r])) : {};
const SLOTS = [
  { lo: 0, hi: 1, label: '<1' },
  { lo: 1, hi: 2 }, { lo: 2, hi: 5 }, { lo: 5, hi: 10 }, { lo: 10, hi: 20 }, { lo: 20, hi: 50 },
  { lo: 50, hi: 100 }, { lo: 100, hi: 200 }, { lo: 200, hi: 500 }, { lo: 500, hi: 1000 }, { lo: 1000, hi: Infinity },
];
const EDGE_LABELS = ['1', '2', '5', '10', '20', '50', '100', '200', '500', '1k'];
const slotOf = (v) => SLOTS.findIndex((s) => v >= s.lo && v < s.hi);
const claimData = CLAIMS.map((c) => {
  const vals = chipsLong.filter((r) => r.claim === c.claim).map((r) => num(r.value)).sort((a, b) => a - b);
  const s = chipSum[c.claim];
  check(vals.length === num(s.chips), `${c.claim}: ${vals.length} chips vs ${s.chips}`);
  const med = vals.length % 2 ? vals[(vals.length - 1) / 2] : (vals[vals.length / 2 - 1] + vals[vals.length / 2]) / 2;
  check(near(med, num(s.median)), `${c.claim}: median ${med} vs ${s.median}`);
  const bins = SLOTS.map(() => ({ one: 0, rest: 0 }));
  vals.forEach((v) => { const i = slotOf(v); if (v === 1) bins[i].one++; else bins[i].rest++; });
  return { ...c, vals, s, bins, median: num(s.median), medianNo1: num(s.median_without_1x), ones: num(s.chips_reading_1x) };
});
const fmtX = (v) => `${v % 1 ? v : v.toLocaleString('en-US')}×`;

const chart5 = {
  key: '05', file: '05-what-people-claimed', section: 'What people claimed',
  title: `The typical claim was ${fmtX(claimData[0].median)} cheaper and ${fmtX(claimData[1].median)} faster, in line with OpenChamber's own survey`,
  subtitle: `${claimData[0].s.chips} cost chips on ${claimData[0].s.cards} posts and ${claimData[1].s.chips} speed chips on ${claimData[1].s.cards} posts.`,
  desc: claimData.map((c) => `${c.short}: median ${fmtX(c.median)}, interquartile ${fmtX(num(c.s.p25))} to ${fmtX(num(c.s.p75))}.`).join(' '),
  body(T, { x0, x1, y0, narrow }) {
    const out = [];
    let y = y0;
    const px0 = x0 + 30, px1 = x1;
    const slotW = (px1 - px0) / SLOTS.length;
    const colW = Math.min(24, slotW * 0.7);
    const ph = narrow ? 96 : 112;
    const pos = (v) => {
      const i = slotOf(v); const s = SLOTS[i];
      const f = s.lo > 0 && Number.isFinite(s.hi) ? Math.log(v / s.lo) / Math.log(s.hi / s.lo) : 0.5;
      return px0 + (i + f) * slotW;
    };
    claimData.forEach((c, ci) => {
      out.push(txs(T, x0, y + 12, [{ s: c.short, weight: 700 }, { s: `  ${c.s.chips} chips`, role: 'ink2', size: 11.5 }], { size: 13 }));
      const lgItems = [
        { label: `median ${fmtX(c.median)} (${fmtX(c.medianNo1)} without 1× chips)`, role: 'ink', kind: 'vline' },
        { label: `OpenChamber survey, about ${SURVEY[c.surveyKey]}×`, role: 'ink', kind: 'diamond' },
        { label: '1× chips', role: 'g2' },
      ];
      if (REF[c.surveyKey]) lgItems.push({ label: REF[c.surveyKey].label, role: 'blueLo' });
      const lg = legend(T, lgItems, x0, x1, y + 22, { size: 11.5 });
      out.push(lg.svg);
      const py0 = lg.y + 14, py1 = py0 + ph;
      const maxBin = Math.max(...c.bins.map((b) => b.one + b.rest));
      const ax = nice(maxBin, 4);
      const Y = (v) => py1 - (v / ax.max) * ph;
      for (let v = 0; v <= ax.max + 1e-9; v += ax.step) {
        out.push(ln(T, px0, Y(v), px1, Y(v), v === 0 ? 'axis' : 'grid'));
        out.push(tx(T, px0 - 6, Y(v) + 4, fmt(v), { size: 11, role: 'ink2', anchor: 'end' }));
      }
      if (REF[c.surveyKey]) {
        const a = pos(num(REF[c.surveyKey].low)), b = pos(num(REF[c.surveyKey].high));
        out.push(rect(T, a, py0, b - a, ph, 'blueLo', ' opacity="0.35"'));
      }
      c.bins.forEach((b, i) => {
        const cx = px0 + i * slotW + (slotW - colW) / 2;
        const range = i === 0 ? 'under 1×' : `${fmtX(SLOTS[i].lo)} to ${Number.isFinite(SLOTS[i].hi) ? fmtX(SLOTS[i].hi) : 'more'}`;
        if (b.one) out.push(pathEl(T, b.rest ? `M${r1(cx)} ${r1(py1)}h${r1(colW)}v${r1(-(b.one / ax.max) * ph)}h${r1(-colW)}z` : vbarD(cx, py1, colW, (b.one / ax.max) * ph), 'g2', `Exactly 1×: ${b.one} chips`));
        if (b.rest) {
          const base = py1 - (b.one ? (b.one / ax.max) * ph + 2 : 0);
          out.push(pathEl(T, vbarD(cx, base, colW, (b.rest / ax.max) * ph), 'blue', `${range}: ${b.rest} chips`));
        }
      });
      // median and survey markers
      const xm = pos(c.median), xs = pos(SURVEY[c.surveyKey]);
      out.push(ln(T, xm, py0 - 4, xm, py1, 'surface', 5), ln(T, xm, py0 - 4, xm, py1, 'ink', 1.5));
      out.push(`<path d="M${r1(xs)} ${r1(py0 - 12)}l5 5l-5 5l-5 -5z" stroke-width="1.5" ${paint(T, 'ink', 'surface')}/>`);
      // axis labels at bin edges
      out.push(tx(T, px0 + slotW / 2, py1 + 15, '<1', { size: 11, role: 'ink2', anchor: 'middle' }));
      EDGE_LABELS.forEach((l, k) => {
        const ex = px0 + (k + 1) * slotW;
        out.push(ln(T, ex, py1, ex, py1 + 4, 'axis'));
        out.push(tx(T, ex, py1 + 15, l, { size: 11, role: 'ink2', anchor: 'middle' }));
      });
      y = py1 + 22;
      if (ci === claimData.length - 1) { out.push(tx(T, (px0 + px1) / 2, y + 10, 'Claimed multiple (×), log bins; bars count chips', { size: 11.5, role: 'ink2', anchor: 'middle' })); y += 16; }
      else y += 16;
    });
    return { svg: out.join(''), y };
  },
  table() {
    const head = ['Claimed multiple', ...claimData.map((c) => `${c.short} (chips)`)];
    const rows = SLOTS.map((s, i) => [
      i === 0 ? 'under 1×' : `${fmtX(s.lo)} to ${Number.isFinite(s.hi) ? `under ${fmtX(s.hi)}` : 'more'}`,
      ...claimData.map((c) => `${c.bins[i].one + c.bins[i].rest}${c.bins[i].one ? ` (${c.bins[i].one} read exactly 1×)` : ''}`),
    ]);
    rows.push(['Median', ...claimData.map((c) => `${fmtX(c.median)} (${fmtX(c.medianNo1)} without 1×)`)]);
    rows.push(['Middle half', ...claimData.map((c) => `${fmtX(num(c.s.p25))} to ${fmtX(num(c.s.p75))}`)]);
    return { head, rows };
  },
};

// ================================================================ chart 6: who needs it fast (the coarse, audited split)
// The seven-level tier distribution is withdrawn: a human calibration disagreed with both models on tier for most
// posts, and tier is the field the audit agrees with least. One coarse split is kept, as a single bar: the audit's
// estimate of the posts that need a decision in under 300 ms (frame, feel or turn), and the share of those that are games.
const jevLat = S.agreement.jev_latency;
const F300 = need('sub300_set'), G300 = need('sub300_games');
check(F300.lo <= F300.value && F300.value <= F300.hi && G300.lo <= G300.value && G300.value <= G300.hi, 'under-300 ms estimates outside their intervals');
check(near(G300.model, S.sub300.games_share, 1e-4) && near(F300.model, S.sub300.share, 1e-4), 'under-300 ms model shares vs the audit tables');

const chart6 = {
  key: '06', file: '06-who-needs-it-fast', section: 'Who needs it fast',
  title: `About ${Math.round(F300.value * 100)} percent of posts need a decision in under 300 ms, and about 9 in 10 of those are games`,
  subtitle: `${fmt(ESTBASE)} posts. Audited: under 300 ms ${pct(F300.value)} (${audRange('sub300_set', 1)}), games ${pct(G300.value, 0)} of those (${audRange('sub300_games', 0)}).`,
  desc: `Under 300 ms: ${pct(F300.value)} of posts (${audRange('sub300_set', 1)}); games ${pct(G300.value)} of those.`,
  body(T, { x0, x1, y0, narrow }) {
    const out = [];
    const bw = x1 - x0, barH = narrow ? 24 : 28;
    const X = (s) => x0 + s * bw;
    // the subtitle carries the audited shares and their intervals; the bar draws them
    let y = y0 + 6;
    // the 95% interval of the under-300 ms share, over the bar
    const wy = y;
    out.push(`<g><title>${esc(`Under 300 ms: ${pct(F300.value)} of posts, 95% interval ${pct(F300.lo)} to ${pct(F300.hi)}`)}</title>`
      + ln(T, X(F300.lo), wy, X(F300.hi), wy, 'ink', 1.5) + ln(T, X(F300.lo), wy - 4, X(F300.lo), wy + 4, 'ink', 1.5)
      + ln(T, X(F300.hi), wy - 4, X(F300.hi), wy + 4, 'ink', 1.5) + '</g>');
    y += 9;
    const g = F300.value * G300.value, o = F300.value * (1 - G300.value);
    const seg = (x, w, role, title, rx = 0) => `<rect x="${r1(x)}" y="${r1(y)}" width="${r1(Math.max(w, 0))}" height="${barH}"${rx ? ` rx="${rx}"` : ''} ${paint(T, role)}><title>${esc(title)}</title></rect>`;
    out.push(seg(X(0), g * bw, 'blue', `Games under 300 ms: ${pct(g)} of posts`));
    out.push(seg(X(g), Math.max(o * bw, 1.5), 'blueLo', `Other posts under 300 ms: ${pct(o)} of posts`));
    out.push(seg(X(F300.value) + 2, bw - F300.value * bw - 2, 'g1', `Everything else: ${pct(1 - F300.value)} of posts`, 3));
    y += barH;
    for (const v of [0, 0.25, 0.5, 0.75, 1]) {
      out.push(ln(T, X(v), y, X(v), y + 4, 'axis'));
      out.push(tx(T, X(v), y + 17, `${v * 100}%`, { size: 11, role: 'ink2', anchor: v === 1 ? 'end' : v === 0 ? 'start' : 'middle' }));
    }
    y += 26;
    out.push(tx(T, (x0 + x1) / 2, y + 4, `Share of the ${fmt(ESTBASE)} posts`, { size: 11.5, role: 'ink2', anchor: 'middle' }));
    y += 16;
    const lg = legend(T, [
      { label: 'Games under 300 ms', role: 'blue' },
      { label: 'Other posts under 300 ms', role: 'blueLo' },
      { label: 'Everything else', role: 'g1' },
      { label: '95% interval', role: 'ink', kind: 'line', width: 1.5 },
    ], x0, x1, y, { size: 11.5 });
    out.push(lg.svg);
    return { svg: out.join(''), y: lg.y };
  },
  table() {
    return {
      head: ['Audited estimate', 'Estimate', '95% interval', 'From'],
      rows: [
        ['Posts that need a decision in under 300 ms', pct(F300.value), `${pct(F300.lo)} to ${pct(F300.hi)}`, `${F300.k} of ${F300.n} re-read posts still under 300 ms${F300.plug ? `, plus ${fmt(F300.plug)} that only ${LABELS_SHORT} puts there` : ''}`],
        ...(F300.ao !== null ? [['The same, on the audit\'s samples alone', pct(F300.ao), `${pct(F300.aoLo)} to ${pct(F300.aoHi)}`, 'neither model\'s word']] : []),
        ['Games, among those posts', pct(G300.value), `${pct(G300.lo)} to ${pct(G300.hi)}`, `${G300.k} of ${G300.n}`],
      ],
    };
  },
};

// ================================================================ chart 7: realtime slice
const RT_SEGS = [
  { key: 'prod', label: AUDITED ? 'Measured production' : 'Labeled production', role: 'blueHi' },
  { key: 'demo', label: 'Measured demo', role: 'blueLo' },
  { key: 'nonum', label: 'Demo, no numbers', role: 'g2' },
  { key: 'other', label: 'Proposal or commentary', role: 'g1' },
];
const rtCards = perCard.filter((r) => r.realtime_infra === 'True' && r.family !== GAMES);
check(rtCards.length === S.realtime.non_game_cards, `non-game realtime ${rtCards.length} vs summary`);
const rtSeg = (r) => {
  if (r.evidence === 'measured_production') return 'prod';
  if (r.evidence === 'measured_demo') return 'demo';
  if (r.evidence === 'demo_no_numbers') return 'nonum';
  return 'other';
};
const rtFams = [...new Set(rtCards.map((r) => r.family))];
const c7 = Object.fromEntries(rtFams.map((f) => [f, Object.fromEntries(RT_SEGS.map((s) => [s.key, 0]))]));
rtCards.forEach((r) => { c7[r.family][rtSeg(r)]++; });
const rtTot = Object.fromEntries(RT_SEGS.map((s) => [s.key, sum(rtFams.map((f) => c7[f][s.key]))]));
const rtOrder = rtFams.sort((a, b) => sum(Object.values(c7[b])) - sum(Object.values(c7[a])));
check(rtTot.prod === S.realtime.measured_production_non_game, 'non-game realtime production vs summary');
const RT = S.realtime;
const LL = need('live_loop_nongame'), LLA = need('live_loop_all'), RTF = need('rt_families');
const rtfProd = need('rt_families_production').value, rtfClaims = need('rt_families_production_claims').value;
// production in this slice on the audit's re-read: the model's production posts here that hold, and the
// held production posts the audit calls realtime
const rtProdIds = new Set(rtCards.filter((r) => r.evidence === 'measured_production').map((r) => r.id));
const rtProdHeld = AUD_PROD.filter((r) => rtProdIds.has(r.id) && r.holds).length;
const heldRealtime = AUD_PROD.filter((r) => r.holds && r.audit_realtime).length;
const rtProdAll = AUD_PROD.filter((r) => r.holds && (rtProdIds.has(r.id) || r.audit_realtime)).length;
const capFirst = (t) => t.charAt(0).toUpperCase() + t.slice(1);
if (AUDITED) {
  check(AUD_SAMPLING.find((r) => r.key === 'realtime_infra_true_nongame').population === RT.non_game_cards, 'realtime stratum vs summary');
  check(AUD_SAMPLING.find((r) => r.key === 'realtime_family').population === S.realtime_families.cards, 'realtime families vs summary');
  check(near(LL.model, RT.non_game_share_of_all_posts, 1e-6) && near(RTF.model, S.realtime_families.share_posts, 1e-6), 'realtime model shares vs the audit tables');
}
const noneOr = (k) => (k === 0 ? 'none' : fmt(k));
const words = (k) => (['none', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten'][k] ?? fmt(k));
// the labels' flags against the audit: above its interval they are an upper bound
const flagsAbove = LL.model > LL.hi;
const flagSentence = flagsAbove
  ? `Those flags are generous. The audit re-read ${LL.n} of the ${AUDITED ? '' : `${FRAME_SHORT} labels' `}non-game ones and ${LL.k} held.`
  : `${AUDITED ? '' : `${FRAME_SHORT}'s flags were generous (the audit kept ${LL.k} of the ${LL.n} it re-read); `}${LABELS_SHORT}'s ${pct(LL.model)} sits inside the audit's interval.`;
// the production posts the labels put in this slice, and what the audit made of them
const RT_PROD_WORDS = { '2100907300932219347': 'a live news feed', '2102732461524369874': 'a launch-alert model for trading' };
// the two voice, live chat or collaboration posts the audit's labels say claim production without a number (review/audit-opus.md, claim 4)
const RT_CLAIMS = 'a live news feed and a Discord moderation bot';
const rtP = rtCards.filter((r) => r.evidence === 'measured_production');
const rtRe = rtP.filter((r) => r.audit_production === 'holds' || r.audit_production === 'does_not_hold');
const rtHeld = rtP.filter((r) => r.audit_production === 'holds');
const rtUnseen = rtP.filter((r) => r.audit_production === 'not_reread');
const rtNamed = rtP.every((r) => RT_PROD_WORDS[r.id]);
const rtNames = (list) => (rtNamed ? `, ${list.map((r) => RT_PROD_WORDS[r.id]).join(' and ')},` : '');
const rtProdSentence = rtP.length === 0 ? 'None of the posts in this slice is labeled measured production.'
  : `${AUDITED ? 'The model' : LABELS_SHORT} labels ${words(rtP.length)} ${rtP.length === 1 ? 'post' : 'posts'} in this slice measured production: ${[
    rtRe.length ? `the audit re-read ${rtRe.length === rtP.length && rtP.length === 2 ? 'both' : words(rtRe.length)}${rtNames(rtRe)} and ${rtHeld.length === 0 ? (rtRe.length === 1 ? "it didn't hold" : 'neither held') : `${words(rtHeld.length)} held`}` : '',
    rtUnseen.length ? `it never saw ${rtUnseen.length === 1 ? (rtRe.length ? 'the other' : 'it') : `the other ${words(rtUnseen.length)}`}${rtNames(rtUnseen).replace(/,$/, '')}` : '',
  ].filter(Boolean).join('; ')}.`;

const chart7 = {
  key: '07', file: '07-realtime-slice', section: 'The realtime slice',
  title: `Outside games, about ${Math.round(LL.value * 100)} percent of posts have a live loop, and ${noneOr(rtProdAll)} of them ${rtProdAll === 1 ? 'is' : rtProdAll === 0 ? 'is' : 'are'} in production`,
  subtitle: `${fmt(RT.non_game_cards)} posts flagged realtime outside games. Audited: a live loop ${pct(LL.value)} of posts (${audRange('live_loop_nongame', 1)}).`,
  desc: RT_SEGS.map((s) => `${s.label}: ${fmt(rtTot[s.key])}.`).join(' '),
  body(T, { x0, x1, y0, narrow }) {
    const out = [];
    const lg = legend(T, RT_SEGS.map((s) => ({ label: `${s.label} ${fmt(rtTot[s.key])}`, role: s.role })), x0, x1, y0);
    out.push(lg.svg);
    const labelW = narrow ? 0 : 184;
    const bx0 = x0 + labelW, bx1 = x1 - 36;
    const maxN = Math.max(...rtOrder.map((f) => sum(Object.values(c7[f]))));
    const ax = nice(maxN, 7);
    const X = (v) => bx0 + (v / ax.max) * (bx1 - bx0);
    const barH = 14, pitch = narrow ? 33 : 22, gap = 2;
    let y = lg.y + 12;
    const top = y;
    const barYs = [];
    for (const f of rtOrder) {
      const counts = RT_SEGS.map((s) => c7[f][s.key]);
      const n = sum(counts);
      const by = narrow ? y + 16 : y;
      out.push(tx(T, x0, (narrow ? y : by) + 11.5, FAM[f][0], { size: 12, weight: 600 }));
      let x = bx0;
      const nz = counts.map((c, i) => [c, i]).filter(([c]) => c > 0);
      nz.forEach(([c, i], k) => {
        const w = X(c) - bx0, last = k === nz.length - 1;
        const dw = Math.max(last ? w : w - gap, 1.5);
        const d = last ? hbarD(x, by, dw, barH) : `M${r1(x)} ${r1(by)}h${r1(dw)}v${barH}h${r1(-dw)}z`;
        out.push(pathEl(T, d, RT_SEGS[i].role, `${FAM[f][0]}, ${RT_SEGS[i].label.toLowerCase()}: ${fmt(c)} posts`));
        x += w;
      });
      out.push(tx(T, x + 6, by + 11.5, fmt(n), { size: 11.5, role: 'ink2' }));
      barYs.push(by);
      y += pitch;
    }
    const bottom = barYs[barYs.length - 1] + barH + 8;
    const grid = [];
    for (let v = 0; v <= ax.max + 1e-9; v += ax.step) {
      grid.push(ln(T, X(v), top - 4, X(v), bottom, v === 0 ? 'axis' : 'grid'));
      grid.push(tx(T, X(v), bottom + 15, fmt(v), { size: 11, role: 'ink2', anchor: v === 0 ? 'start' : 'middle' }));
    }
    grid.push(tx(T, (bx0 + bx1) / 2, bottom + 31, `Posts ${LABELS_SHORT} flags realtime${flagsAbove ? ' (upper bound)' : ''}`, { size: 11.5, role: 'ink2', anchor: 'middle' }));
    return { svg: grid.join('') + out.join(''), y: bottom + 36 };
  },
  table() {
    return {
      head: ['Family', ...RT_SEGS.map((s) => s.label), 'Flagged realtime'],
      rows: [
        ...rtOrder.map((f) => [FAM[f][0], ...RT_SEGS.map((s) => fmt(c7[f][s.key])), fmt(sum(Object.values(c7[f])))]),
        ['All outside games', ...RT_SEGS.map((s) => fmt(rtTot[s.key])), fmt(RT.non_game_cards)],
      ],
    };
  },
};

// ================================================================ chart 8: what measuring buys (views per post by evidence grade)
// Replaces the chart of views by what a post leads with: framing is withdrawn (a human calibration showed that one
// choice misrepresents posts that lead with cost and latency together). Evidence is the field the audit found stable.
const EV_LABEL = { measured_production: 'Measured production', measured_demo: 'Measured demo', demo_no_numbers: 'Demo, no numbers', proposal_or_idea: 'Proposal or idea', commentary_or_meme: 'Commentary or meme' };
const evAllRows = csv('03_evidence_overall').map((r) => ({ key: r.evidence, posts: num(r.posts), views: num(r.views), median: num(r.median_views), mean: num(r.views) / num(r.posts), shareViews: num(r.share_views) }));
const allMean = totalViews / BASE;
check(near(allMean, S.concentration.mean_views, 1e-6), 'mean views vs summary');
check(sum(evAllRows.map((r) => r.posts)) === BASE && evAllRows.every((r) => EV_LABEL[r.key]), 'evidence rows vs the base');
// the labels' measured-production row is left out unless they are the audited labels: the audit does not support that label
const evRows = evAllRows.filter((r) => AUDITED || r.key !== 'measured_production');
const byE = Object.fromEntries(evAllRows.map((r) => [r.key, r]));
const shift = (label) => S.v1_to_v2.shifts.find((s) => s.label === label);
const meanRatio = byE.measured_demo.mean / byE.demo_no_numbers.mean, medRatio = byE.measured_demo.median / byE.demo_no_numbers.median;

const chart8 = {
  key: '08', file: '08-what-measuring-buys', section: 'What measuring buys',
  title: `Measured demos averaged ${meanRatio >= 1.7 && meanRatio < 2.6 ? 'twice' : `${meanRatio.toFixed(1)} times`} the views of demos with no numbers, but the typical post gained little`,
  subtitle: `${fmt(sum(evRows.map((r) => r.posts)))} posts by evidence level${AUDITED ? '' : `, without the ${fmt(evAll.measured_production)} labeled production`}.`,
  desc: evRows.map((r) => `${EV_LABEL[r.key]}: ${fmt(r.posts)} posts, median ${fmt(r.median)}, mean ${fmt(r.mean)} views.`).join(' '),
  body(T, { x0, x1, y0, narrow }) {
    const out = [];
    const panels = [
      { title: 'Median views per post', key: 'median', all: num(stats.median_views) },
      { title: 'Mean views per post', key: 'mean', all: allMean },
    ];
    const labelW = narrow ? 142 : 160;
    const barH = 16, pitch = 30;
    let y = y0;
    const drawPanel = (pn, px0, px1, py) => {
      const ax = nice(Math.max(...evRows.map((f) => f[pn.key])), 4);
      const bx0 = px0 + labelW, bx1 = px1 - 50;
      const X = (v) => bx0 + (v / ax.max) * (bx1 - bx0);
      const o = [];
      o.push(tx(T, bx0, py + 12, pn.title, { size: 12.5, weight: 700 }));
      const top = py + 24;
      let yy = top;
      const grid = [];
      evRows.forEach((f) => {
        const hi = f.key === 'measured_demo' || f.key === 'measured_production';
        o.push(tx(T, px0, yy + 12, EV_LABEL[f.key], { size: narrow ? 12 : 12.5, weight: 600 }));
        o.push(tx(T, px0, yy + 26, `${fmt(f.posts)} posts`, { size: 11, role: 'ink2' }));
        const w = Math.max(X(f[pn.key]) - bx0, 1.5);
        o.push(pathEl(T, hbarD(bx0, yy + 2, w, barH), hi ? 'blue' : 'g2', `${EV_LABEL[f.key]}: ${pn.key} ${fmt(f[pn.key])} views per post, ${fmt(f.posts)} posts`));
        o.push(tx(T, bx0 + w + 6, yy + 15, fmt(f[pn.key]), { size: 12, weight: 700 }));
        yy += pitch;
      });
      const bottom = yy - 4;
      for (let v = 0; v <= ax.max + 1e-9; v += ax.step) {
        grid.push(ln(T, X(v), top - 2, X(v), bottom, v === 0 ? 'axis' : 'grid'));
        grid.push(tx(T, X(v), bottom + 14, v >= 1000 ? `${v / 1000}k` : fmt(v), { size: 11, role: 'ink2', anchor: v === 0 ? 'start' : 'middle' }));
      }
      return { svg: grid.join('') + o.join(''), y: bottom + 18 };
    };
    // stacked in both layouts: five labels need the width
    let a = drawPanel(panels[0], x0, x1, y); out.push(a.svg); y = a.y + 14;
    a = drawPanel(panels[1], x0, x1, y); out.push(a.svg); y = a.y;
    return { svg: out.join(''), y };
  },
  table() {
    return {
      head: ['Evidence', 'Posts', 'Median views', 'Mean views', 'Share of views'],
      rows: evRows.map((f) => [EV_LABEL[f.key], fmt(f.posts), fmt(f.median), fmt(f.mean), pct(f.shareViews)]),
    };
  },
};

// ================================================================ chart 9: Jev grading Jev
const deciles = csv('12_calibration_equal_count_deciles').map((r) => ({
  d: r.pdec, cards: num(r.cards), lo: num(r.prob_min), hi: num(r.prob_max), mean: num(r.mean_prob), agree: num(r.agreement_v2),
}));
check(near(deciles[0].agree, S.agreement.deciles.D1.agreement_v2) && near(deciles[9].agree, S.agreement.deciles.D10.agreement_v2), 'decile agreement vs summary');
const AG = S.agreement;
const costRows = csv('00_gateway_cost');
const jevCost = num(costRows.find((r) => r.item.startsWith('v1 pass: Jev')).usd);
const sonnetV2Cost = num(costRows.find((r) => r.item.startsWith('v2 pass: Sonnet 5, full run')).usd);
check(near(jevCost, S.cost.jev_usd) && near(sonnetV2Cost, S.cost.v2_full.usd), 'costs vs summary');
const usd = (v) => (v === null || v === undefined || Number.isNaN(v) ? 'n/a' : `$${Number(v).toFixed(2)}`);
const labelsCost = S.cost.labels_run ? S.cost.labels_run.usd : sonnetV2Cost;  // the reference-label run, whatever the model
if (AUDITED) check(near(labelsCost, sonnetV2Cost), 'reference-label cost vs the Sonnet v2 run');
const JA = need('jev_audit_p99');

const chart9 = {
  key: '09', file: '09-jev-grading-jev', section: 'Jev grading Jev',
  title: `When Jev was surest, it picked the same family as ${LABELS_SHORT} ${pct(deciles[9].agree)} of the time`,
  subtitle: `${fmt(AG.n)} Jev calls in tenths. Audited: at 0.99 or more, Jev matched ${pct(JA.value)} of ${fmt(JA.n)} posts.`,
  desc: deciles.map((d) => `${d.d}: ${pct(d.agree)}.`).join(' '),
  body(T, { x0, x1, y0, narrow }) {
    const out = [];
    const lg = legend(T, [
      { label: `Jev agreed with ${LABELS_SHORT}`, role: 'accent' },
      { label: 'Disagreed', role: 'g2' },
      { label: 'Jev’s average stated probability', role: 'ink', kind: 'tick' },
    ], x0, x1, y0);
    out.push(lg.svg);
    const px0 = x0 + 34, px1 = x1;
    const ph = narrow ? 200 : 230;
    const py0 = lg.y + 24, py1 = py0 + ph;
    const ax9 = nice(Math.max(...deciles.map((d) => d.cards)), 4);
    const ymax = ax9.max;
    const Y = (v) => py1 - (v / ymax) * ph;
    out.push(tx(T, x0, py0 - 12, 'Cards', { size: 11.5, role: 'ink2' }));
    for (let v = 0; v <= ymax + 1e-9; v += ax9.step) {
      out.push(ln(T, px0, Y(v), px1, Y(v), v === 0 ? 'axis' : 'grid'));
      out.push(tx(T, px0 - 6, Y(v) + 4, fmt(v), { size: 11, role: 'ink2', anchor: 'end' }));
    }
    const slotW = (px1 - px0) / 10, colW = Math.min(28, slotW * 0.6);
    deciles.forEach((d, i) => {
      const cx = px0 + i * slotW + (slotW - colW) / 2;
      const agreeN = Math.round(d.agree * d.cards), disN = d.cards - agreeN;
      const ha = (agreeN / ymax) * ph, hd = (disN / ymax) * ph;
      out.push(pathEl(T, `M${r1(cx)} ${r1(py1)}h${r1(colW)}v${r1(-ha)}h${r1(-colW)}z`, 'accent', `${d.d} (stated ${d.lo.toFixed(2)}–${d.hi.toFixed(2)}): agreed on ${fmt(agreeN)} of ${fmt(d.cards)}, ${pct(d.agree)}`));
      if (disN > 0) out.push(pathEl(T, vbarD(cx, py1 - ha - 2, colW, Math.max(hd - 2, 1.5)), 'g2', `${d.d}: disagreed on ${fmt(disN)} of ${fmt(d.cards)}`));
      const yt = Y(d.mean * d.cards);
      out.push(ln(T, cx - 4, yt, cx + colW + 4, yt, 'ink', 2));
      if ([0, 4, 9].includes(i)) out.push(tx(T, cx + colW / 2, Y(d.cards) - 8, pct(d.agree), { size: narrow ? 11 : 12, weight: 700, anchor: 'middle' }));
      out.push(tx(T, cx + colW / 2, py1 + 15, d.d, { size: 11, weight: 600, anchor: 'middle' }));
      if (!narrow) out.push(tx(T, cx + colW / 2, py1 + 28, `${d.lo.toFixed(2)}–${d.hi.toFixed(2)}`, { size: 10, role: 'ink2', anchor: 'middle' }));
    });
    const ay = py1 + (narrow ? 32 : 46);
    out.push(tx(T, (px0 + px1) / 2, ay, narrow ? 'Tenths of Jev’s calls, least to most sure' : 'Tenths of Jev’s calls, least to most sure, with the stated probability range', { size: 11.5, role: 'ink2', anchor: 'middle' }));
    return { svg: out.join(''), y: ay + 6 };
  },
  table() {
    return {
      head: ['Tenth', 'Cards', 'Stated probability', 'Mean stated', `Agreement with ${LABELS_MODEL}`],
      rows: deciles.map((d) => [d.d, fmt(d.cards), `${d.lo.toFixed(2)} to ${d.hi.toFixed(2)}`, d.mean.toFixed(3), pct(d.agree)]),
    };
  },
};

// ================================================================ chart 10: where
const langRows = csv('10_language_overall').map((r) => ({ ...r, posts: num(r.posts) }));
check(sum(langRows.map((r) => r.posts)) === BASE, 'language posts do not sum to the base');
const LANG_NAME = { en: 'English', ja: 'Japanese', zh: 'Chinese' };
const mainLangs = langRows.filter((r) => LANG_NAME[r.lang]);
const otherLangs = langRows.filter((r) => !LANG_NAME[r.lang]);
const langBars = [
  ...mainLangs.map((r) => ({ label: LANG_NAME[r.lang], posts: r.posts, hi: r.lang === 'ja' })),
  { label: `${otherLangs.length} other language codes`, posts: sum(otherLangs.map((r) => r.posts)), hi: false },
];
const days = byDay.map((r) => ({ day: r.day, n: num(r.posts) }));
check(sum(days.map((d) => d.n)) === BASE, 'posts per day do not sum to the base');
const peak = days.reduce((a, b) => (b.n > a.n ? b : a));
const peakIdx = days.indexOf(peak);
const ja = mainLangs.find((r) => r.lang === 'ja');

const chart10 = {
  key: '10', file: '10-where-the-builders-were', section: 'Where the builders were',
  title: `One post in five was in Japanese, and posting peaked on day ${peakIdx + 1}`,
  subtitle: `${fmt(BASE)} posts by language and by posting day (UTC).`,
  desc: `${langBars.map((l) => `${l.label}: ${pct(l.posts / BASE)}.`).join(' ')} Peak day ${peak.day}: ${fmt(peak.n)} posts.`,
  body(T, { x0, x1, y0, narrow }) {
    const out = [];
    const drawLang = (px0, px1, py) => {
      const o = [tx(T, px0, py + 12, 'Language of the post', { size: 12.5, weight: 700 })];
      let yy = py + 26;
      const bw = px1 - px0 - 96;
      for (const l of langBars) {
        o.push(tx(T, px0, yy + 11, l.label, { size: 12, weight: 600 }));
        const w = (l.posts / BASE) * bw;
        o.push(pathEl(T, hbarD(px0, yy + 17, Math.max(w, 1.5), 14), l.hi ? 'blue' : 'g2', `${l.label}: ${fmt(l.posts)} posts (${pct(l.posts / BASE)})`));
        o.push(txs(T, px0 + w + 7, yy + 28.5, [{ s: pct(l.posts / BASE), weight: 700 }, { s: `  ${fmt(l.posts)}`, role: 'ink2', size: 11 }], { size: 12 }));
        yy += 42;
      }
      return { svg: o.join(''), y: yy };
    };
    const drawDays = (px0, px1, py) => {
      const o = [tx(T, px0, py + 12, 'Posts per day (UTC), September', { size: 12.5, weight: 700 })];
      const cx0 = px0 + 38;
      const ph = narrow ? 150 : 170;
      const cy0 = py + 34, cy1 = cy0 + ph;
      const ax = nice(peak.n, 5);
      const Y = (v) => cy1 - (v / ax.max) * ph;
      for (let v = 0; v <= ax.max + 1e-9; v += ax.step) {
        o.push(ln(T, cx0, Y(v), px1, Y(v), v === 0 ? 'axis' : 'grid'));
        o.push(tx(T, cx0 - 6, Y(v) + 4, fmt(v), { size: 11, role: 'ink2', anchor: 'end' }));
      }
      const slotW = (px1 - cx0) / days.length, colW = Math.min(24, slotW * 0.62);
      days.forEach((d, i) => {
        const partial = i === 0 || (LAST_PARTIAL && i === days.length - 1);
        const cx = cx0 + i * slotW + (slotW - colW) / 2;
        const role = i === peakIdx ? 'blue' : partial ? 'g1' : 'g2';
        o.push(pathEl(T, vbarD(cx, cy1, colW, (d.n / ax.max) * ph), role, `${d.day}: ${fmt(d.n)} posts${partial ? ' (partial day)' : ''}`));
        if (i === peakIdx || partial) o.push(tx(T, cx + colW / 2, Y(d.n) - 6, fmt(d.n), { size: 11.5, weight: 700, anchor: 'middle' }));
        o.push(tx(T, cx + colW / 2, cy1 + 15, d.day.slice(8), { size: 11, weight: i === peakIdx ? 700 : 400, role: i === peakIdx ? 'ink' : 'ink2', anchor: 'middle' }));
        if (partial) o.push(tx(T, cx + colW / 2, cy1 + 28, 'partial', { size: 10, role: 'ink2', anchor: 'middle' }));
      });
      return { svg: o.join(''), y: cy1 + 32 };
    };
    if (narrow) {
      const a = drawLang(x0, x1, y0); out.push(a.svg);
      const b = drawDays(x0, x1, a.y + 10); out.push(b.svg);
      return { svg: out.join(''), y: b.y };
    }
    const split = x0 + (x1 - x0) * 0.46;
    const a = drawLang(x0, split - 12, y0), b = drawDays(split + 16, x1, y0);
    out.push(a.svg, b.svg);
    return { svg: out.join(''), y: Math.max(a.y, b.y) };
  },
  table() {
    return {
      head: ['Language or day', 'Posts', 'Share of posts'],
      rows: [
        ...langBars.map((l) => [l.label, fmt(l.posts), pct(l.posts / BASE)]),
        ...days.map((d) => [`${d.day}${d === days[0] || (LAST_PARTIAL && d === days[days.length - 1]) ? ' (partial)' : ''}`, fmt(d.n), pct(d.n / BASE)]),
      ],
    };
  },
};

// ================================================================ chart 11: what the noise is made of
// The noise of figure 1 (other_or_meta, or commentary in another family) by sub-type, from
// scripts/classify-noise.ts (rubric: report/rubric-noise.md) via analyze.py.
const NOISE_SUB = {
  unrelated_or_unclear: ['Unrelated or unclear', 'unrelated or unclear posts'],
  benchmark_of_the_model: ['Benchmarks of the model', 'benchmarks of the model'],
  tooling_or_wrapper: ['Tooling or wrappers', 'tooling or wrappers'],
  explainer_or_tutorial: ['Explainers or tutorials', 'explainers or tutorials'],
  news_or_repost: ['News or reposts', 'news or reposts'],
  hot_take_or_commentary: ['Hot takes', 'hot takes'],
  meme_or_joke: ['Memes or jokes', 'memes or jokes'],
  not_subtyped: ['Not yet sub-typed', 'posts not yet sub-typed'],
};
const noiseRows = csv('12_noise_breakdown').map((r) => ({
  key: r.subtype, posts: num(r.posts), share: num(r.share_of_noise), shareAll: num(r.share_of_all_posts),
  views: num(r.views), vshare: num(r.share_of_noise_views), median: num(r.median_views),
  topViews: num(r.top_card_views), topUrl: r.top_card_url, topTitle: r.top_card_title,
}));
const stance = Object.fromEntries(csv('12b_noise_stance').map((r) => [r.stance, num(r.posts)]));
const NZ = S.noise;
const noiseN = sum(noiseRows.map((r) => r.posts));
const hotN = (noiseRows.find((r) => r.key === 'hot_take_or_commentary') || { posts: 0 }).posts;
check(noiseRows.every((r) => NOISE_SUB[r.key]), 'unknown sub-type in 12_noise_breakdown');
const isNoise = (r) => r.family === 'other_or_meta' || r.evidence === 'commentary_or_meme';
check(noiseN === perCard.filter(isNoise).length, `noise sub-types sum to ${noiseN}; 08_ladder_per_card has ${perCard.filter(isNoise).length} noise posts`);
const MS = need('meta_still'), MM = need('meta_meme'), MH = need('meta_hot'), MA = need('meta_all_samples');
// the meta share: the audit's estimate with the labels filling what it did not sample, and its samples-only variant
const META_RANGE = 'posts that state no use case, benchmark the model itself or wrap it';
if (AUDITED) check(near(MS.model, famPosts.other_or_meta / BASE, 1e-6) && AUD_SAMPLING.find((r) => r.key === 'other_or_meta').population === famPosts.other_or_meta, 'meta stratum vs 01_family_distribution');
const underHalf = MM.value < 0.005 && MH.value < 0.005 && MM.model < 0.005 && MH.model < 0.005;
check(noiseN === NZ.posts, 'noise posts vs summary');
check(near(sum(noiseRows.map((r) => r.share)), 1, 1e-6), 'noise shares do not sum to 1');
check(near(sum(noiseRows.map((r) => r.vshare)), 1, 1e-6), 'noise view shares do not sum to 1');
check(sum(Object.values(stance)) === hotN && hotN === NZ.hot_takes, 'stance counts vs hot takes');
const nw = (k) => NOISE_SUB[k][1];
const cap = (t) => t.charAt(0).toUpperCase() + t.slice(1);
const nTop3 = noiseRows.filter((r) => r.key !== 'not_subtyped').slice(0, 3);

const chart11 = {
  key: '11', file: '11-what-the-noise-is-made-of', section: 'What the noise is made of',
  title: `About a fifth of posts are meta, and memes and hot takes are ${underHalf ? 'under half a percent each' : 'a small share'}`,
  subtitle: `${fmt(noiseN)} noise posts by sub-type. Audited: meta ${aud('meta_still', 0)} of all posts.`,
  desc: noiseRows.map((r) => `${NOISE_SUB[r.key][0]}: ${fmt(r.posts)} posts (${pct(r.share)}), ${pct(r.vshare)} of the noise's views.`).join(' '),
  body(T, { x0, x1, y0, narrow }) {
    const out = [];
    const lg = legend(T, [
      { label: 'Share of the noise posts', role: 'blue' },
      { label: 'Share of the noise views', role: 'blueLo' },
    ], x0, x1, y0);
    out.push(lg.svg);
    const labelW = narrow ? 0 : 172;
    const bx0 = x0 + labelW, bx1 = x1 - 116; // room for the value labels to the right of the longest bar
    const ax = nice(100 * Math.max(...noiseRows.map((r) => Math.max(r.share, r.vshare))), 5);
    const X = (share) => bx0 + ((100 * share) / ax.max) * (bx1 - bx0);
    const pH = 15, vH = 8, gap = 2;
    const pitch = narrow ? 52 : 38;
    let y = lg.y + 10;
    const top = y;
    let last = 0;
    for (const r of noiseRows) {
      const by = narrow ? y + 18 : y;
      const label = NOISE_SUB[r.key][0];
      out.push(tx(T, x0, (narrow ? y : by) + 12, label, { size: narrow ? 12 : 12.5, weight: 600 }));
      const wP = Math.max(X(r.share) - bx0, 1.5), wV = Math.max(X(r.vshare) - bx0, 1.5);
      out.push(pathEl(T, hbarD(bx0, by, wP, pH), r.key === 'not_subtyped' ? 'g2' : 'blue', `${label}: ${fmt(r.posts)} posts, ${pct(r.share)} of the noise`));
      out.push(pathEl(T, hbarD(bx0, by + pH + gap, wV, vH, 3), 'blueLo', `${label}: ${fmt(r.views)} views, ${pct(r.vshare)} of the noise's views`));
      out.push(txs(T, bx0 + wP + 7, by + 12, [{ s: pct(r.share), weight: 700 }, { s: `  ${fmt(r.posts)} posts`, role: 'ink2', size: 11.5 }], { size: 12.5 }));
      out.push(tx(T, bx0 + wV + 7, by + pH + gap + vH, `${pct(r.vshare)} of views`, { size: 11, role: 'ink2' }));
      last = by;
      y += pitch;
    }
    const bottom = last + pH + gap + vH + 8;
    const grid = [];
    for (let v = 0; v <= ax.max + 1e-9; v += ax.step) {
      grid.push(ln(T, X(v / 100), top - 4, X(v / 100), bottom, v === 0 ? 'axis' : 'grid'));
      grid.push(tx(T, X(v / 100), bottom + 15, `${v}%`, { size: 11, role: 'ink2', anchor: v === 0 ? 'start' : 'middle' }));
    }
    grid.push(tx(T, (bx0 + bx1) / 2, bottom + 31, 'Share of the noise', { size: 11.5, role: 'ink2', anchor: 'middle' }));
    return { svg: grid.join('') + out.join(''), y: bottom + 36 };
  },
  table() {
    return {
      head: ['Sub-type', 'Posts', 'Share of noise', 'Share of all posts', 'Share of noise views', 'Median views', 'Most-viewed post (views)'],
      rows: [
        ...noiseRows.map((r) => [NOISE_SUB[r.key][0], fmt(r.posts), pct(r.share), pct(r.shareAll), pct(r.vshare), fmt(r.median), r.topUrl ? `${r.topTitle} (${fmt(r.topViews)})` : '']),
        ['All noise', fmt(noiseN), '100%', pct(noiseN / BASE), '100%', fmt(NZ.median_views), `${NZ.top_card.title} (${fmt(NZ.top_card.views)})`],
        ...['bullish', 'skeptical', 'mixed', 'neutral'].map((k) => [`Hot takes, ${k}`, fmt(stance[k] || 0), '', '', '', '', '']),
      ],
    };
  },
};

// ================================================================ chart 12: what would have done the job before (figure 1c)
// The audit read each of the 91 candidate builds from its title and text and named what a team would have used
// for that job before Jev (review/work/substance.py, via 13_audit_substance.csv). "Unavailable at any price" is
// the bar for new.
const BEFORE = AUD_SUB.filter((r) => r.kind === 'before');
const JOBS = AUD_SUB.filter((r) => r.kind === 'job').sort((m, n) => n.posts - m.posts);
const CAND = need('candidates').value, DISTINCT = need('substance_distinct').value, UNAVAIL = need('substance_unavailable').value;
const STILL = need('candidates_still_meeting');
const byBefore = Object.fromEntries(BEFORE.map((r) => [r.key, r.posts]));
check(need('substance_n').value === CAND && sum(BEFORE.map((r) => r.posts)) === CAND, 'substance: the prior methods do not sum to the candidates');
check(sum(JOBS.map((r) => r.posts)) === CAND, 'substance: the jobs do not sum to the candidates');
check(byBefore.unavailable === UNAVAIL, 'substance: "unavailable at any price" vs the estimates');
check(Object.entries(SA.substance || {}).every(([k, v]) => byBefore[k] === v), 'substance vs summary');
check(DISTINCT <= CAND && STILL.value <= CAND, 'substance: distinct builds or survivors exceed the candidates');
check(AUD_SAMPLING.find((r) => r.key === 'material').population === CAND, 'candidates vs the audit sampling table');
if (AUDITED) check(perCard.filter((r) => r.candidate === 'True').length === CAND, 'candidates in 08_ladder_per_card vs the audit');
else check(perCard.filter((r) => r.candidate === 'True').length <= CAND, 'candidates in 08_ladder_per_card vs the audit');
const jobWords = (list) => list.map((j) => `${j.label.toLowerCase()} (${j.posts})`);

const chart12 = {
  key: '12', file: '12-what-would-have-done-the-job', section: 'What would have done the job before?',
  title: `Of the ${CAND} builds most likely to show something new, ${UNAVAIL === 0 ? 'none' : fmt(UNAVAIL)} did something that was unavailable before`,
  subtitle: `${CAND} builds (${DISTINCT} distinct), by what a team would have used before Jev.`,
  desc: BEFORE.map((r) => `${r.label}: ${r.posts} of ${CAND}.`).join(' '),
  body(T, { x0, x1, y0, narrow }) {
    const out = [];
    const labelW = narrow ? 0 : 184;
    const bx0 = x0 + labelW, bx1 = x1 - (narrow ? 64 : 76);
    const max = Math.max(...BEFORE.map((r) => r.posts));
    const X = (v) => (v / max) * (bx1 - bx0);
    const barH = 20, pitch = narrow ? 50 : 38;
    let y = y0 + 4;
    let last = y;
    for (const r of BEFORE) {
      const by = narrow ? y + 18 : y;
      const zero = r.key === 'unavailable';
      out.push(tx(T, x0, narrow ? y + 12 : by + 14.5, r.label, { size: narrow ? 12 : 12.5, weight: zero ? 800 : 600 }));
      if (zero) {
        // the empty slot, as long as the largest bar: the bar none of the builds reached
        out.push(`<rect x="${r1(bx0 + 0.75)}" y="${r1(by + 0.75)}" width="${r1(bx1 - bx0 - 1.5)}" height="${barH - 1.5}" rx="3" fill="none" stroke-width="1.5" stroke-dasharray="5 4" ${paint(T, null, 'accent')}><title>${esc(`${r.label}: ${r.posts} of ${CAND} posts`)}</title></rect>`);
        out.push(txs(T, bx0 + 10, by + 15, [{ s: fmt(r.posts), weight: 800 }, { s: `  of ${CAND} posts`, role: 'ink2', size: 11.5 }], { size: 13.5 }));
      } else {
        const w = Math.max(X(r.posts), 2);
        out.push(pathEl(T, hbarD(bx0, by, w, barH), 'blue', `${r.label}: ${r.posts} of ${CAND} posts`));
        out.push(txs(T, bx0 + w + 7, by + 15, [{ s: fmt(r.posts), weight: 700 }, { s: `  ${pct(r.posts / CAND, 0)}`, role: 'ink2', size: 11.5 }], { size: 13 }));
      }
      last = by;
      y += pitch;
    }
    return { svg: out.join(''), y: last + barH + 6 };
  },
  table() {
    return {
      head: ['What would have done the job before', 'Posts', 'Share of the candidates'],
      rows: [
        ...BEFORE.map((r) => [r.label, fmt(r.posts), pct(r.posts / CAND, 0)]),
        ['Distinct builds among them', fmt(DISTINCT), ''],
        ...JOBS.map((j) => [`Job: ${j.label.toLowerCase()}`, fmt(j.posts), pct(j.posts / CAND, 0)]),
      ],
    };
  },
};

const BY_KEY = { '01': chart1, '02': chart2, '03': chart3, '04': chart4, '05': chart5, '06': chart6, '07': chart7, '08': chart8, '09': chart9, '10': chart10, '11': chart11, '12': chart12 };
check(ORDER.length === Object.keys(BY_KEY).length && ORDER.every((k) => BY_KEY[k]), 'figure order does not list every chart once');
const CHARTS = ORDER.map((k) => BY_KEY[k]);

if (problems.length) {
  console.error(`Data checks failed:\n- ${problems.join('\n- ')}`);
  process.exit(1);
}

// ---------------------------------------------------------------- chart layouts
// The files are written at the end, after the audit checks below have passed too.
const XML = '<?xml version="1.0" encoding="UTF-8"?>\n';
const WIDE = 640, NARROW = 360;

// ---------------------------------------------------------------- page
const REPO = process.env.REPO_URL || 'https://github.com/mattheworiordan/jev-landscape';
const REPO_SHORT = REPO.replace(/^https?:\/\//, '');
const L = {
  feed: 'https://jev.openchamber.dev/data/cards.json',
  survey: 'https://openchamber.dev/blog/jev-typesafe-ai/',
  voice: 'https://x.com/uezochan/status/2100608556823388486',
  sheet: 'https://x.com/dabit3/status/2100780008193020049',
  browser: 'https://x.com/gregpr07/status/2100411066966749359',
  snake: 'https://x.com/NFT_Chen/status/2101675124747338229',
  // the public repo: the page is served from its root by GitHub Pages; review files are linked at their repo paths
  repo: REPO,
  review: `${REPO}/blob/main/review/critical-review-grok.md`,
  reviewLabels: `${REPO}/blob/main/review/hand-labels-grok.jsonl`,
  reviewOpus: `${REPO}/blob/main/review/audit-opus.md`,
};
const a = (href, text) => `<a href="${href}">${text}</a>`;
const langFam = Object.fromEntries(csv('10_language_by_family_counts').map((r) => [r.family, r]));
const jaShare = (f) => num(langFam[f].ja) / famPosts[f];
const RF = S.realtime_families;
const v2cost = S.cost.v2_pass_usd, pilots = S.cost.v2_pilots.usd;
const jaRange = () => {
  const s = ['collaboration_and_typing', 'live_chat_streams_events', 'voice_and_turn_taking'].map(jaShare);
  return `${pct(Math.min(...s), 0)} to ${pct(Math.max(...s), 0)}`;
};

// The production posts that hold on the audit's re-read, in the words the lead uses. A copy check says if
// the audit's census changes under them.
const PROD_WORDS = {
  '2100468943853085061': 'a task router deployed "for a real production use case"',
  '2101000072062222802': 'a deploy approval gate',
  '2101663804492787715': 'a news pipeline',
  '2102633943891857663': 'a search reranker',
  '2101607957083435427': 'an episode recommender',
  '2101315927593648436': 'a fleet-wide decision layer',
};
const QA_SITES = { '2100833556469833867': 'AskJev.ai', '2102199555706024144': 'AskJev.net' };
const heldById = Object.fromEntries(AUD_PROD.filter((r) => r.holds).map((r) => [r.id, r]));
const prodList = [
  ...Object.entries(PROD_WORDS).filter(([id]) => heldById[id]).map(([id, w]) => a(heldById[id].url, w)),
  `two public Q&amp;A sites, ${Object.entries(QA_SITES).filter(([id]) => heldById[id]).map(([id, w]) => a(heldById[id].url, w)).join(' and ')}, that counted their questions and visitors`,
];
// The two turn-tier demos the realtime lead names, and what the audit says did those jobs before.
const SUBC = Object.fromEntries(csv('13_audit_substance_cards').map((r) => [r.id, r]));
const BEFORE_WORDS = { llm: 'an LLM', rules: 'rules or heuristics', vendor: 'a vendor API', classic: 'a classic model' };
const voiceBefore = SUBC['2100608556823388486'], sheetBefore = SUBC['2100780008193020049'];

// Each chart's lead is at most two sentences: the finding and, where it is needed, the one caveat that
// changes how to read it. How the labels were made is in the method section at the end of the page.
const evTop = evOrder[0], evBottom = evOrder[evOrder.length - 1];
const noiseTop3 = noiseRows.filter((r) => r.key !== 'not_subtyped').sort((m, n) => n.posts - m.posts).slice(0, 3);
const SECTIONS = {
  '01': `<p>Two thirds of the posts measured nothing, ${aud('ladder_no_measurement', 0)} on the audit, and about a third reported a number from the author's own run, ${aud('ladder_measured_demo', 0)}. Production is only the ${fmt(stepTot.prod_ok)} orange squares, the posts that held when the audit re-read them: ${pct(PROD.value, 2)} of posts, and at most ${pct(PROD.hi, 0)}.</p>`,
  '11': `<p>About a fifth of posts state no use case, benchmark the model itself or wrap it: ${aud('meta_still', 0)} on the audit. Of the ${fmt(noiseN)} noise posts, ${pct(sum(noiseTop3.map((r) => r.share)), 0)} are ${noiseTop3.slice(0, -1).map((r) => nw(r.key)).join(', ')} and ${nw(noiseTop3[noiseTop3.length - 1].key)}, and memes and hot takes are ${underHalf ? 'under half a percent of all posts each' : 'a small share of all posts'}.</p>`,
  '12': `<p>${UNAVAIL === 0 ? 'None' : `Only ${fmt(UNAVAIL)}`} of the ${CAND} builds most likely to show something new, the posts labeled as a measured decision made while a person waits, did something that was unavailable before: a team would have used an LLM for ${byBefore.llm}, rules for ${byBefore.rules}, a vendor API for ${byBefore.vendor} and a classic model for ${byBefore.classic}. The audit judged each one from its post, not by running the build.</p>`,
  '02': `<p>The top 1% of posts, ${top1.views_cards} of them, hold ${pct(num(top1.views_share))} of the ${(totalViews / 1e6).toFixed(1)} million views and ${pct(num(top1.likes_share))} of the likes, and the median post has ${fmt(num(stats.median_views))} views. The most-viewed post alone is ${pct(num(stats.top_card_share))} of views, with a like rate far below the median, but without the ${stats.suspect_cards} posts like it the top 1% still hold ${pct(num(stats.top1pct_views_excl_suspect))}.</p>`,
  '03': `<p>About four in five posts compare Jev with nothing, ${audBase.none} on the audit, and about 1 in 30 with the classifiers, rules and vendor APIs it would replace, ${audBase.repl}. A week of "${fmtX(claimData[0].median)} cheaper", and almost nobody asking "than what I already had?"</p>`,
  '04': `<p>By family, ${FAM[evTop][0].toLowerCase()} measured most often, ${pct(measuredShare(evFam[evTop]), 0)} of its posts, and ${FAM[evBottom][0].toLowerCase()} least, ${pct(measuredShare(evFam[evBottom]), 0)}. Only ${words(PROD.k)} posts measured Jev in production on the audit's re-read: ${prodList.slice(0, -1).join(', ')}, and ${prodList[prodList.length - 1]}.</p>`,
  '05': `<p>The median claim on the cards was ${fmtX(claimData[0].median)} cheaper and ${fmtX(claimData[1].median)} faster, close to ${a(L.survey, "OpenChamber's own survey of user reports")} at about ${SURVEY.cost}× and ${SURVEY.speed}×. These are the authors' numbers, and figure ${figNo('03')} shows what most of them are measured against: nothing named at all, or a frontier model.</p>`,
  '06': `<p>On the audit, about ${pct(F300.value, 0)} of posts need a decision in under 300 ms, and about nine in ten of those are games. Jev's own median call took ${fmt(jevLat.p50_ms)} ms from a laptop, above every one of those budgets.</p>`,
  '07': `<p>Outside games, a live loop is ${pct(LL.value)} of posts on the audit (${audRange('live_loop_nongame', 1)}), and ${heldRealtime === 0 ? 'none' : words(heldRealtime)} of the ${words(PROD.k)} posts that measured production ${heldRealtime > 1 ? 'are realtime builds' : 'is a realtime build'}. The best realtime demos, a ${a(L.voice, 'voice turn-end detector at 0.224 s')} and a ${a(L.sheet, 'predictive spreadsheet that scores rows as you type')}, are faster versions of jobs ${BEFORE_WORDS[voiceBefore.before]} and ${BEFORE_WORDS[sheetBefore.before]} already did.</p>`,
  '08': `<p>Measuring buys the hits, not the typical post: measured demos averaged ${fmt(byE.measured_demo.mean)} views against ${fmt(byE.demo_no_numbers.mean)} for demos with no numbers, but the median barely moves, ${fmt(byE.measured_demo.median)} against ${fmt(byE.demo_no_numbers.median)}. Most posts got little attention either way: ${pct(num(stats.cards_under_100_views) / BASE, 0)} had under 100 views.</p>`,
  '09': `<p>When Jev was surest it picked ${LABELS_SHORT}'s family ${pct(deciles[9].agree)} of the time, against ${pct(deciles[0].agree)} when it was least sure, and it labeled every post for ${usd(jevCost)} against ${usd(labelsCost)} for ${LABELS_SHORT}: a cheap model that knows when it's sure can sit in front of a slower one. That's agreement, not accuracy, but on the ${fmt(JA.n)} audited posts where Jev said 0.99 or more, it matched the audit's family ${pct(JA.value)} of the time.</p>`,
  '10': `<p>Japanese builders wrote ${pct(num(ja.share), 0)} of all posts but ${jaRange()} of the live chat, voice and collaboration posts, the families I care about most. The feed starts at ${FIRST.time} UTC on the ${ordinal(dnum(DAY0))}, about six hours after launch, so the first evening is missing.</p>`,
};

const svgInline = (c, W, tag) => frame(THEMES.vars, c, W, tag, 'page');
const tableHTML = (t) => `<div class="tablewrap"><table><thead><tr>${t.head.map((h) => `<th scope="col">${esc(h)}</th>`).join('')}</tr></thead><tbody>${t.rows.map((r) => `<tr>${r.map((v, i) => (i === 0 ? `<th scope="row">${esc(v)}</th>` : `<td>${esc(v)}</td>`)).join('')}</tr>`).join('')}</tbody></table></div>`;
const figHTML = (c) => `
<section class="fig" id="figure-${figNo(c.key)}" aria-labeledby="h-${c.key}">
  <p class="eyebrow">Figure ${figNo(c.key)}</p>
  <h2 id="h-${c.key}">${esc(c.section)}</h2>
  <div class="prose">${SECTIONS[c.key]}</div>
  <figure>
    <div class="fig-wide">${svgInline(c, WIDE, 'pw')}</div>
    <div class="fig-narrow">${svgInline(c, NARROW, 'pn')}</div>
    <figcaption class="figlinks"><span>SVG:</span> <a href="charts/${c.file}-light.svg">light</a> <a href="charts/${c.file}-dark.svg">dark</a> <a href="charts/${c.file}.svg">adaptive</a> <a href="charts/narrow/${c.file}-light.svg">phone</a></figcaption>
    <details><summary>Show the numbers</summary>${tableHTML(c.table())}</details>
  </figure>
</section>`;

const tokenBlock = (mode) => `${cssVars(mode)};`;
const VERDICTS = ['Holds', 'Holds with correction', 'Fails'];
const verdictN = Object.fromEntries(VERDICTS.map((v) => [v, AUD_CLAIMS.filter((c) => c.verdict === v).length]));
check(AUD_CLAIMS.length === 10 && AUD_CLAIMS.every((c) => VERDICTS.includes(c.verdict)), 'the audit claims table needs ten claims with a known verdict');
check(VERDICTS.every((v) => (SA.verdicts || {})[v] === verdictN[v] || (!(SA.verdicts || {})[v] && verdictN[v] === 0)), 'audit verdicts vs summary');
check(AUD_SAMPLING.every((r) => (r.kind === 'census' ? r.reviewed === r.population : r.reviewed < r.population)), 'audit sampling: a census stratum not fully reviewed, or a sample larger than its stratum');
const AGREE_P = AUD_AGREE.filter((r) => r.labels === LB.file);
const AGREE_F = AUD_AGREE.filter((r) => r.labels === SA.audited_labels);
check(AGREE_P.length === AUD_SAMPLING.length + 1 && (AUDITED || AGREE_F.length === AGREE_P.length), 'audit agreement rows vs the strata');
const allAgree = AGREE_P.find((r) => r.key === 'all_labelled');
check(Number(allAgree.n) === LABELLED, 'audit agreement: all-labelled n vs the labelled count');
const AFIELDS = [['family', 'Family'], ['tier', 'Tier'], ['evidence', 'Evidence'], ['baseline', 'Baseline'], ['realtime_infra', 'Realtime'], ['production_claim', 'Production']];
check(AFIELDS.every(([f]) => near(Number(allAgree[f]), need(`agreement_${f}`).value, 1e-6)), 'audit agreement vs 13_audit_estimates');
check(AFIELDS.every(([f]) => near(PA[f], Number(allAgree[f]), 1e-6)), 'primary-label agreement vs the audit agreement table');
if (!AUDITED) check(AFIELDS.every(([f]) => near(PA_FRAME[f], Number(AGREE_F.find((r) => r.key === 'all_labelled')[f]), 1e-6)), 'first-label agreement vs the audit agreement table');
for (const e of Object.values(AE)) {
  if (e.lo !== null) check(e.lo <= e.value + 1e-9 && e.value <= e.hi + 1e-9 && e.lo >= 0 && e.hi <= 1, `audit estimate ${e.key}: ${e.value} outside [${e.lo}, ${e.hi}]`);
  const s = (SA.estimates || {})[e.key];
  check(s && near(s.value, e.value, 1e-5), `audit estimate ${e.key}: 13_audit_estimates vs summary.json`);
}
check(need('snapshot_matches').value === 1, 'the audit describes an earlier snapshot of the Sonnet v2 labels (snapshot_matches = 0): redo the audit for this base before publishing');
check(need('use_case_base').value === SA.use_case_base, 'audit base vs summary');
if (AUDITED) check(need('use_case_base').value === BASE, `the audit sampled a base of ${need('use_case_base').value} posts; the page's base is ${BASE}`);
const plainTable = (head, rows, cls = '') => `<div class="tablewrap"><table${cls ? ` class="${cls}"` : ''}><thead><tr>${head.map((h) => `<th scope="col">${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((v, i) => (i === 0 ? `<th scope="row">${esc(v)}</th>` : `<td>${esc(v)}</td>`)).join('')}</tr>`).join('')}</tbody></table></div>`;
const auditSampling = plainTable(['Group', 'How', 'Posts in the group', 'Audited'], [
  ...AUD_SAMPLING.map((r) => [r.stratum, r.kind === 'census' ? 'every post' : 'random sample', fmt(r.population), fmt(r.reviewed)]),
  ['Unique posts audited', '', '', `${fmt(LABELLED)} (${fmt(need('census_unique').value)} in the census groups)`],
]);
// the audit's own table rounds half to even (Python); so does this one, so the two read the same
const pctEven = (x) => {
  const v = x * 100, f = Math.floor(v);
  return `${Math.abs(v - f - 0.5) < 1e-9 ? (f % 2 === 0 ? f : f + 1) : Math.round(v)}%`;
};
const auditAgreement = plainTable(['Group', 'Posts', ...AFIELDS.map(([, l]) => l)],
  AGREE_P.map((r) => [r.stratum, fmt(Number(r.n)), ...AFIELDS.map(([f]) => pctEven(Number(r[f])))]));
const KAPPA = Object.fromEntries(csv('13_audit_primary_agreement').map((r) => [r.field, { p: optNum(r.kappa), f: optNum(r.frame_kappa) }]));
const auditCompare = plainTable(['Field', `${FRAME_SHORT} (first labels)`, `${LABELS_MODEL.replace('Claude ', '')} (this page)`],
  AFIELDS.map(([f, l]) => [l, `${pctEven(PA_FRAME[f])}${KAPPA[f].f !== null ? ` (κ ${KAPPA[f].f.toFixed(2)})` : ''}`, `${pctEven(PA[f])}${KAPPA[f].p !== null ? ` (κ ${KAPPA[f].p.toFixed(2)})` : ''}`]));
const EST_ROWS = [
  ['baseline_none', 'Compare Jev with nothing', 1], ['baseline_frontier_llm', 'Compare it with a frontier LLM', 1], ['baseline_small_llm', 'Compare it with a small LLM', 1],
  ['baseline_replacement', 'Compare it with the tools it would replace', 1], ['ladder_no_measurement', 'Measured nothing', 1],
  ['ladder_demo_no_numbers', 'Demo with no numbers', 1], ['ladder_claim_no_number', 'A cost, speed or accuracy claim with no number', 1],
  ['ladder_measured_demo', 'Measured demo', 1], ['production_strict', 'Measured production', 2], ['rt_families', 'Voice, live chat or collaboration', 1],
  ['live_loop_nongame', 'A live loop outside games', 1], ['sub300_set', 'Need a decision in under 300 ms', 1], ['sub300_games', 'Games, of those under 300 ms', 1],
  ['meta_still', 'Meta (no use case, a benchmark or a wrapper)', 1],
];
const estCell = (v, lo, hi, d) => (v === null ? '' : `${pct(v, d)}${lo === null ? '' : ` (${bound(lo, d === 2 ? 2 : 1)} to ${bound(hi, d === 2 ? 2 : 1)})`}`);
const auditEstimates = plainTable(['Posts that', 'Audited', 'Samples only', `${LABELS_SHORT} labels`, `Audit on ${FRAME_SHORT}`],
  EST_ROWS.map(([k, l, d]) => { const e = need(k); return [l, estCell(e.value, e.lo, e.hi, d), estCell(e.ao, e.aoLo, e.aoHi, d), e.model === null ? '' : pct(e.model, d), estCell(e.frameValue, e.frameLo, e.frameHi, d)]; }), 'wrap');
const auditClaims = AUDITED
  ? plainTable(['#', 'Claim', 'Published', 'Corrected', '95% interval', 'Verdict'], AUD_CLAIMS.map((c) => [c.claim, c.topic, c.published, c.corrected, c.interval, c.verdict]), 'wrap')
  : plainTable(['#', 'Claim', 'Published', 'Audit on Sonnet', 'Verdict', `Audit on ${LABELS_SHORT}`, `Verdict on ${LABELS_SHORT}`],
    AUD_CLAIMS.map((c) => [c.claim, c.topic, c.published, `${c.corrected}; ${c.interval}`, c.verdict, c.labels_audit, c.labels_verdict]), 'wrap claims');
const LIM = { f: need('limits_frontier_stratum'), s: need('limits_small_stratum'), r: need('limits_unsampled_remainder'), c: need('limits_numeric_chip'), o: need('limits_prior_overlap') };
const costOnly = need('cost_only_as_described');
const PAU = need('production_audit_unconfirmed');
const auditCouldNot = `${AUDITED
  ? `The ${fmt(LIM.f.value)} posts that compare Jev with a frontier LLM and the ${fmt(LIM.s.value)} that compare it with a small LLM weren't sampled, so those two estimates assume the model's labels are right there.`
  : `The audit drew its groups on the ${FRAME_SHORT} labels, so for ${LABELS_SHORT}'s labels some groups are thin: it read only part of the posts ${LABELS_SHORT} puts in voice, live chat and collaboration, for example. The ${fmt(need('plug_frontier_small').value)} posts the ${FRAME_SHORT} labels say compare Jev with a frontier or small LLM weren't sampled, so those estimates take ${LABELS_SHORT}'s word there.`} The posts from those groups the audit happened to label for other reasons agree ${LIM.f.k} of ${LIM.f.n} and ${LIM.s.k} of ${LIM.s.n} with the ${FRAME_SHORT} labels, and that slice isn't a random sample. The audit re-read the ${fmt(PROD.n)} posts the ${FRAME_SHORT} labels called production; its first-pass labels call ${words(PAU.value)} more posts production, which its count leaves out${AUDITED ? '' : ` (${LABELS_SHORT} calls ${PAU.k === PAU.value ? `all ${words(PAU.value)}` : words(PAU.k)} production too)`}, and the ${pct(PROD.hi, 0)} upper end allows for posts like those. The first review's re-read of the first pass's 95 production posts wasn't repeated. Games were left out of the check for missed voice, live chat and collaboration posts. The ${fmt(AUDITED ? LIM.r.value : need('plug_remainder').value)} proposal and commentary posts stayed on the model's label. The feed cuts post text at 400 characters and a claim chip can invent a number: ${LIM.c.k} of the ${fmt(LIM.c.n)} posts the audit calls demos with no numbers still carry a numeric chip. And the auditor is another AI model, not a person.${HC.n ? ` I labeled ${HC.n} posts myself, enough to drop two labels but not enough to check the rest, so human labels are still the missing check.` : ' Human labels are still the missing check.'}`;


// ---------------------------------------------------------------- the method section
// Visible: the feed, the rubric, the four passes, why the headlines are ranges, the two dropped fields,
// the human calibration, the spend, the repo and the licences, the disclosure. Everything else, the
// audit tables and the notes that used to sit under each chart, is in one collapsed <details>.
const REFUSED = (SA.labels_refused || []).length;
const FAMILY_WORDS = FAMS.length === 14 ? 'fourteen' : fmt(FAMS.length);
const v1SonnetCost = sum(costRows.filter((r) => r.item.startsWith('v1 pass: Sonnet')).map((r) => num(r.usd)));
check(near(v1SonnetCost + jevCost, S.cost.v1_pass_usd, 1e-6), 'first-pass costs (00_gateway_cost) vs summary');
const SPEND = { v1: v1SonnetCost, sonnet: v1SonnetCost + v2cost, labels: AUDITED ? 0 : labelsCost, noise: S.cost.noise_usd, jev: jevCost };
// the total is the sum of the parts as printed, so the sentence adds up
const cents = (v) => Math.round(v * 100);
const SPEND_TOTAL = (cents(SPEND.sonnet) + cents(SPEND.labels) + cents(SPEND.noise) + cents(SPEND.jev)) / 100;
const CHART_NOTES = {
  '01': `No measurement: a demo with no numbers, a claim with no number, a proposal or commentary. Measured demo: a number from the author's own run. Production: a number from a live system. ${prodOfLabels} The other ${words(PROD.n - PROD.k)} posts the audit re-read are tests, a figure measured in development, or a claim with no number from the live system. The first labeling pass said ${pct(PROD1.value)} (${P.v1_measured_production} posts), and its own re-read kept ${P.reread_holds}, a looser reading the audit did not repeat.`,
  '11': `Noise is a post in Other or meta, or commentary in another family. Unrelated or unclear: not about Jev, or the author's own app or demo where the post doesn't say what Jev decides. Benchmarks: tests of Jev itself with no application. Tooling: SDKs, clients, ports and infrastructure for calling Jev. On the audit's re-read memes are ${pct(MM.value, 2)} of posts and hot takes ${pct(MH.value, 2)}, and of the ${fmt(hotN)} hot takes ${stance.bullish || 0} are bullish, ${stance.skeptical || 0} skeptical, ${stance.mixed || 0} mixed and ${stance.neutral || 0} neutral. The label moves both ways: the audit re-read ${MS.n} of the posts the ${FRAME_SHORT} labels call meta and moved ${MS.n - MS.k} of them to a real use, most often classification, and it also found meta posts among the ones the labels gave a use.${HC.meta_by_both_models ? ` When I labeled posts myself, I gave a real use to ${HC.meta_given_real_use === HC.meta_by_both_models ? `all ${words(HC.meta_by_both_models)}` : `${words(HC.meta_given_real_use)} of the ${words(HC.meta_by_both_models)}`} that both models call meta, so a careful human reader would likely put the share lower.` : ''}`,
  '12': `The ${CAND} are every post ${AUDITED ? 'the model' : `the ${FRAME_SHORT} labels`} called a measured decision inside a live system, made while a person waits (100 ms to 1 s), and compared with nothing, rules, classic ML or a frontier LLM. On the audit's own labels ${STILL.value} of them still meet that test, and ${CAND - DISTINCT} are a second post about a build already counted. The largest jobs: ${jobWords(JOBS.slice(0, 2)).join(', ')} and ${jobWords(JOBS.slice(2, 3))[0]}.`,
  '02': `Views are X impressions and likes are X likes, as the feed recorded them, unverified. The top post is ${pct(num(stats.top_card_share))} of views at a like rate of ${pct(num(stats.top_card_like_rate), 2)}, against a median of ${pct(num(stats.median_like_rate_1k_plus), 2)} for posts with 1,000 or more views; without it the top 1% hold ${pct(num(stats.top1pct_views_excl_top_card))}. Posts from 16 to 19 September are ${pct(earlyPosts, 0)} of posts and hold ${pct(earlyViews, 0)} of views: older posts had longer to collect them. ${attnAudit}`,
  '03': `A comparison counts only when it is named or clearly implied, such as "replaced my keyword filter" (rules) or a before-and-after figure. The frontier and small-LLM groups weren't sampled, so their estimates rest on ${AUDITED ? 'the labels' : `${LABELS_SHORT}'s labels`} there.${allBaseInside ? ` All four of ${LABELS_SHORT}'s shares are inside the audit's intervals.` : ''}`,
  '04': `Bars are ${AUDITED ? "the model's" : `${LABELS_SHORT}'s`} evidence labels by family, sorted by the share that measured anything.${AUDITED ? '' : ` The darkest segment is ${LABELS_SHORT}'s production label, which the audit doesn't support: of the posts it labels production, the audit read ${fmt(PA_READ.n)} and agrees with ${fmt(PA_READ.k)}.`}`,
  '05': `The feed extracts the claim chips from the full post. The "1×" chips (${claimData[0].ones} cost, ${claimData[1].ones} speed) are an extractor artifact; without them the medians are ${fmtX(claimData[0].medianNo1)} and ${fmtX(claimData[1].medianNo1)}. Accuracy and latency chips aren't charted: they mix Jev's numbers with the baseline's and with Jev's stated confidence.`,
  '06': `Under 300 ms is the frame, feel or turn tier. The rubric puts ordinary game input in the feel tier, so part of the games share is built in.${insideOf('sub300_set') ? '' : ` ${LABELS_SHORT}'s own count, ${pct(F300.model)}, is outside the audit's interval.`} Jev's p95 call took ${fmt(jevLat.p95_ms)} ms.`,
  '07': `Bars are ${AUDITED ? "the model's" : `${LABELS_SHORT}'s`} realtime flags${flagsAbove ? ', an upper bound' : ''}. ${flagSentence} ${rtProdSentence} Voice, live chat and collaboration are ${pct(RTF.value)} of posts on the audit (${audRange('rt_families', 1)}), with ${noneOr(rtfProd)} measured in production${AUDITED ? '' : ` and ${words(rtfClaims)} claiming it without a number, ${RT_CLAIMS}`}. With games, a live loop is about a fifth of all posts (${pct(LLA.value)}).`,
  '08': `Views favor older posts.${AUDITED ? '' : ` The posts ${LABELS_SHORT} labels measured production are left out: the audit confirms ${fmt(PROD.k)} production posts in all.`} This chart replaces one of views by what a post leads with, the framing field that is dropped.`,
  '09': `Each column is one tenth of Jev's ${fmt(AG.n)} calls, ranked by the probability Jev stated for its answer; Jev chose among the first pass's 14 families. Overall it picked ${LABELS_SHORT}'s family for ${pct(AG.jev_vs_v2)} of cards (kappa ${AG.kappa_v2.toFixed(2)}), and ${pct(AG.top_bin_games_trading, 0)} of its calls at 0.99 or above are games or trading, the easiest families. On 120 cards labeled blind by Claude Opus 5.5 in a separate run, not by people, Jev is right on ${AG.hand.jev_at_099.replace('/', ' of ')} of its calls at 0.99 or above.`,
  '10': `The feed's first post is at ${FIRST.time} UTC on ${FIRST.short} and the last at ${LAST.time} UTC on ${LAST.short}, so ${LAST_PARTIAL ? 'both are partial days' : 'the first is a partial day'}.`,
};
check(ORDER.every((k) => CHART_NOTES[k]), 'every chart needs its notes in the audit tables');

const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>A week of Jev, sorted</title>
<meta name="description" content="What ${fmt(S.posts)} posts from ${fmt(S.authors)} authors built with Jev in its first week, where the attention went, how much of it was measured, and whether any of it was new.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Manrope:wght@400;500;600;700;800&display=swap">
<style>
:root{
  color-scheme: light;
  --bg:#fcfcfb; --bg-2:#f3f2ee; --ink:#0b0b0b; --ink-2:#52514e; --muted:#6f6e69; --rule:#e1e0d9;
  --accent:#eb6834; --focus:#2a78d6; --tip-bg:#0b0b0b; --tip-ink:#fcfcfb;
  ${tokenBlock('light')}
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    color-scheme: dark;
    --bg:#1a1a19; --bg-2:#232322; --ink:#ffffff; --ink-2:#c3c2b7; --muted:#9d9b93; --rule:#34342f;
    --accent:#d95926; --focus:#5598e7; --tip-bg:#f3f2ee; --tip-ink:#0b0b0b;
    ${tokenBlock('dark')}
  }
}
:root[data-theme="dark"]{
  color-scheme: dark;
  --bg:#1a1a19; --bg-2:#232322; --ink:#ffffff; --ink-2:#c3c2b7; --muted:#9d9b93; --rule:#34342f;
  --accent:#d95926; --focus:#5598e7; --tip-bg:#f3f2ee; --tip-ink:#0b0b0b;
  ${tokenBlock('dark')}
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:400 17px/1.62 Manrope,ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;padding-inline:16px}
main{max-width:720px;margin-inline:auto;padding-block:48px 72px}
.prose{max-width:40em}
.prose p{margin:0 0 14px}
.mono,code,.eyebrow,.byline,summary,.figlinks,.chip{font-family:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
code{font-size:.86em;background:var(--bg-2);padding:1px 5px;border-radius:4px}
a{color:inherit;text-decoration-color:var(--accent);text-decoration-thickness:2px;text-underline-offset:3px}
a:hover{text-decoration-thickness:3px}
a:focus-visible,summary:focus-visible{outline:2px solid var(--focus);outline-offset:3px;border-radius:2px}
header{padding-bottom:28px;border-bottom:1px solid var(--rule)}
.kicker{font:500 12px/1.4 "IBM Plex Mono",ui-monospace,monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0 0 18px}
h1{font-weight:800;font-size:clamp(2.6rem,9vw,4.4rem);line-height:.98;letter-spacing:-.035em;margin:0 0 18px;text-wrap:balance}
.dek{font-size:clamp(1.12rem,2.6vw,1.3rem);line-height:1.45;color:var(--ink-2);max-width:34em;margin:0 0 20px;text-wrap:pretty}
.byline{font-size:13px;color:var(--muted);margin:0}
.byline strong{color:var(--ink);font-weight:500}
.sorted{margin-top:34px}
.sorted p{font-size:14px;color:var(--ink-2);margin:0 0 10px}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:0;padding:0;list-style:none}
.chip{display:inline-flex;align-items:center;gap:8px;padding:6px 11px 6px 9px;border:1px solid var(--rule);border-radius:999px;font-size:13px;line-height:1;background:var(--bg)}
.chip i{width:10px;height:10px;border-radius:2px;flex:none}
.chip b{font-family:Manrope,ui-sans-serif,system-ui,sans-serif;font-weight:700;font-variant-numeric:tabular-nums}
.chip.is-accent{border-color:var(--v-accent)}
.intro{margin-top:32px}
.short{margin-top:28px;padding-top:18px;border-top:1px solid var(--rule)}
.short h2{font-size:1.1rem;margin:0 0 10px;letter-spacing:0}
.short ul{margin:0;padding-left:1.1em}
.short li{margin:0 0 6px}
section.fig{margin-top:76px}
.eyebrow{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0}
h2{font-weight:800;font-size:clamp(1.45rem,4vw,1.8rem);line-height:1.15;letter-spacing:-.02em;margin:6px 0 14px;text-wrap:balance}
h3{font-weight:700;font-size:1.05rem;margin:28px 0 8px}
figure{margin:26px 0 0}
figure svg{display:block;width:100%;height:auto}
.fig-narrow{display:none}
@media (max-width:560px){.fig-wide{display:none}.fig-narrow{display:block}}
.figlinks{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12px;color:var(--muted);margin-top:10px}
details{margin-top:10px;border-top:1px solid var(--rule);padding-top:10px}
summary{cursor:pointer;font-size:13px;color:var(--ink-2)}
.tablewrap{overflow-x:auto;margin-top:10px;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;font-size:13.5px;font-variant-numeric:tabular-nums;min-width:100%}
th,td{text-align:right;padding:6px 10px;border-bottom:1px solid var(--rule);white-space:nowrap;vertical-align:top}
thead th{font-weight:700;color:var(--ink-2);font-size:12.5px}
tbody th{text-align:left;font-weight:600}
thead th:first-child{text-align:left}
.method{margin-top:88px;padding-top:28px;border-top:1px solid var(--rule)}
.method ul{padding-left:1.1em}
.method li{margin:0 0 8px}
.audit-tables{margin-top:26px}
.audit-tables > h3:first-of-type{margin-top:18px}
.audit-tables .tablewrap{margin-bottom:6px}
table.wrap th,table.wrap td{white-space:normal;min-width:6.5em;text-align:left}
table.wrap td:nth-child(6){white-space:nowrap}
table.claims td:nth-child(6){white-space:normal}
table.wrap th:first-child{min-width:0}
.disclosure{margin-top:22px;padding:14px 0 0;border-top:1px solid var(--rule);font-size:15px;color:var(--ink-2)}
.disclosure b{color:var(--ink)}
figure [data-tip]{transition:opacity .12s}
figure [data-tip]:hover{opacity:.72}
.tip{position:fixed;left:0;top:0;pointer-events:none;background:var(--tip-bg);color:var(--tip-ink);font:600 12.5px/1.35 Manrope,ui-sans-serif,system-ui,sans-serif;padding:6px 9px;border-radius:6px;max-width:280px;z-index:10}
@media (prefers-reduced-motion:reduce){figure [data-tip]{transition:none}}
/* Print and the PDF: light theme on white, the wide charts, no tooltip or download links, every
   <details> open (the page script opens them before printing), and no chart split across pages. */
@media print{
  @page{size:A4;margin:14mm 14mm 16mm}
  :root:not(#print-light){
    color-scheme:light;
    --bg:#ffffff; --bg-2:#f3f2ee; --ink:#0b0b0b; --ink-2:#52514e; --muted:#6f6e69; --rule:#e1e0d9;
    --accent:#eb6834; --focus:#2a78d6; --tip-bg:#0b0b0b; --tip-ink:#fcfcfb;
    ${tokenBlock('light')}
    --v-surface:#ffffff;
  }
  html,body{background:#ffffff}
  body{padding:0;font-size:13.5px;line-height:1.5;-webkit-print-color-adjust:exact;print-color-adjust:exact}
  main{max-width:none;padding:0}
  .prose,.dek{max-width:none}
  h1{font-size:40px;margin-bottom:12px}
  header{padding-bottom:18px}
  .sorted{margin-top:18px}
  .intro{margin-top:20px}
  .short{margin-top:18px}
  /* each figure and the method start a page: heading, lead and chart together, the numbers after */
  section.fig,.method{break-before:page;margin-top:0}
  .method{padding-top:0;border-top:0}
  .eyebrow,h1,h2,h3{break-after:avoid}
  p,li{orphans:3;widows:3}
  figure{margin-top:12px}
  .fig-wide{display:block !important;break-inside:avoid}
  .fig-narrow,.figlinks,.tip{display:none !important}
  figure svg{width:100%;height:auto;max-height:212mm;break-inside:avoid}
  details{border-top:0;padding-top:0;margin-top:6px}
  details > summary{display:none}
  .tablewrap{overflow:visible}
  table{font-size:10.5px;min-width:0;width:100%}
  th,td{white-space:normal;padding:4px 6px}
  thead{display:table-header-group}
  tr{break-inside:avoid}
  a{text-decoration-thickness:1px}
}
</style>
</head>
<body>
<main>
<header>
  <p class="kicker">Data · ${fmt(S.posts)} posts · ${span()} ${YEAR}</p>
  <h1>A week of Jev, sorted</h1>
  <p class="dek">What ${fmt(S.posts)} posts from ${fmt(S.authors)} authors built with Jev in its first week, where the attention went, how much of it was measured, and whether any of it was new.</p>
  <p class="byline"><strong>Matthew O'Riordan</strong> · ${PUBLISHED} · Disclosure: I'm CEO of Ably, a realtime infrastructure company.</p>
  <div class="sorted">
    <p>Every post that uses Jev, on the measurement ladder (figure ${figNo('01')}):</p>
    <ul class="chips">${LADDER.map((b) => `<li class="chip${b.key === 'prod_ok' ? ' is-accent' : ''}"><i style="background:var(--v-${b.role})"></i>${b.label.toLowerCase()}<b>${fmt(stepTot[b.key])}</b></li>`).join('')}</ul>
  </div>
</header>

<div class="intro prose">
  <p>Jev, TypeSafe AI's typed-decision model, launched on 15 September, the first of a new category that everyone got excited about at once. It doesn't write prose: it answers typed questions about a state (pick one of these, score this, yes or no), and it answers fast.</p>
  <p>I went looking for where it applies to realtime, the part of the stack I spend my days on, so I sorted every post in ${a(L.feed, "OpenChamber's Jev feed")} from that first week. Wherever ${a('#audit', `a blind audit of ${fmt(LABELLED)} posts`)} checked a number, I give its range, not a model's count.</p>
  <div class="short">
    <h2>The short version</h2>
    <ul>
      <li>${UNAVAIL === 0 ? 'None' : `Only ${fmt(UNAVAIL)}`} of the ${CAND} builds most likely to show something new did something that was unavailable before: a team would have used an LLM for ${byBefore.llm} of them (figure ${figNo('12')}).</li>
      <li>About four in five posts compare Jev with nothing, ${audBase.none}, and about 1 in 30 with the tools it would replace, ${audBase.repl}.</li>
      <li>${capFirst(words(PROD.k))} of ${fmt(BASE)} posts measured Jev in production, ${pct(PROD.value, 2)} (at most ${pct(PROD.hi, 0)}), and ${heldRealtime === 0 ? 'none of them is a realtime build' : `${words(heldRealtime)} of them ${heldRealtime === 1 ? 'is' : 'are'} realtime`}.</li>
      <li>When Jev was surest it agreed with ${LABELS_SHORT} ${pct(deciles[9].agree)} of the time, and it labeled every post for ${usd(jevCost)} against ${usd(labelsCost)} for ${LABELS_SHORT}.</li>
    </ul>
  </div>
</div>

${CHARTS.map(figHTML).join('\n')}

<section class="method prose" id="audit" aria-labeledby="h-method">
  <p class="eyebrow">Method</p>
  <h2 id="h-method">How this was measured</h2>
  <p>The posts come from ${a(L.feed, "OpenChamber's Jev feed")}, snapshot ${FEED.day} ${FEED.time} UTC: ${fmt(S.posts)} posts from ${fmt(S.authors)} authors between ${span(false, 'and')}, as OpenChamber selected them. Without ${S.duplicates_merged} duplicates${REFUSED ? `, the ${S.not_a_jev_build} posts that don't use Jev and the ${REFUSED === 1 ? 'one post' : `${REFUSED} posts`} ${LABELS_SHORT} refused to label` : ` and the ${S.not_a_jev_build} posts that don't use Jev`}, ${fmt(BASE)} remain.</p>
  <p>A written rubric sorted each post into one of ${FAMILY_WORDS} families by what Jev decides, and labeled what it measured, what it compared Jev with and whether it needs realtime infrastructure.</p>
  <p>${AUDITED
    ? `Claude Sonnet 5 labeled every post first. A critical review of those labels tightened the rubric, and Sonnet labeled every post again; the charts use those labels. Then ${AUDITOR}, an independent model, labeled ${fmt(LABELLED)} posts blind: every post in the rare groups the headlines rest on, and random samples of the rest. It agrees with Sonnet on what a post is for ${pct(PA.family, 0)} of the time, and on whether it measured anything ${pct(PA.evidence, 0)} of the time.`
    : `Claude Sonnet 5 labeled every post first. A critical review of those labels tightened the rubric, and Sonnet labeled every post again. Then ${AUDITOR}, an independent model, labeled ${fmt(LABELLED)} posts blind: every post in the rare groups the headlines rest on, and random samples of the rest. Sonnet agreed with it on what a post is for only ${pct(PA_FRAME.family, 0)} of the time, so ${LABELS_MODEL} labeled every post a final time; it agrees ${pct(PA.family, 0)} of the time, and the charts use its labels.`}</p>
  <p>That's why the headlines come with ranges: the audit read samples, so each share it checked is an estimate with a 95% interval, and the page uses it, not the labels' count.</p>
  <p>Two fields are dropped. Framing, what a post leads with, misrepresented the many posts that lead with cost and latency together, and the seven-level latency tier agrees with the audit least (${pct(PA.tier, 0)}), so figure ${figNo('06')} keeps only the split at 300 ms.</p>
  ${HC.n ? `<p>I labeled ${HC.n} posts myself as a calibration, too few to check the models but enough to find both problems: I disagreed with both models on the tier of ${HC.tier_differs_from_both}.</p>` : ''}
  <p>At Vercel AI Gateway list prices the labeling cost ${usd(SPEND_TOTAL)}: ${usd(SPEND.sonnet)} for the two Sonnet passes, ${AUDITED ? '' : `${usd(SPEND.labels)} for ${LABELS_SHORT}, `}${usd(SPEND.noise)} to sort the noise and ${usd(SPEND.jev)} for Jev.</p>
  <p>The labels, tables, rubric and code are at ${a(L.repo, esc(REPO_SHORT))}, without the text of any post: code under MIT, data and method under CC BY 4.0. This page and its charts are © ${YEAR} Matthew O'Riordan; the posts belong to their authors.</p>
  <p class="disclosure"><b>Disclosure.</b> I'm CEO of Ably, a realtime infrastructure company.</p>
  <details class="audit-tables">
    <summary>Show the audit tables</summary>
    <h3>The audit</h3>
    <p>A piece about unmeasured claims should show its own measurements being checked. An independent reviewer, ${AUDITOR}, labeled ${fmt(LABELLED)} posts against the same rubric without seeing the model's labels: all ${fmt(need('census_unique').value)} posts in the rare groups the headlines rest on, and seeded random samples of ${fmt(Math.min(...AUD_SAMPLING.filter((r) => r.kind === 'sample').map((r) => r.reviewed)))} to ${fmt(Math.max(...AUD_SAMPLING.filter((r) => r.kind === 'sample').map((r) => r.reviewed)))} posts from the rest. Each sample is scaled up to its group with a 95% Wilson interval. The ${a(L.review, 'review')} is published with ${a(L.reviewLabels, 'every label')} and the scripts that turn them into the numbers on this page.${AUDITED ? '' : ` The audit sampled from the ${FRAME_SHORT} labels. Because the charts use ${LABELS_SHORT}'s, I reran its estimators with ${LABELS_SHORT} as the model being checked (${a(L.reviewOpus, 'the rerun')}): the audit's labels stay the reference, shares are of ${LABELS_SHORT}'s ${fmt(ESTBASE)} posts, and where the audit didn't sample, ${LABELS_SHORT}'s labels fill in, with the count stated.`}</p>
    <p>It tested ten of the claims I'd published: ${verdictN.Holds} hold, ${verdictN['Holds with correction']} hold with a correction and ${verdictN.Fails} fail. The failures are why this page no longer sorts posts into buckets. "Cost-only" (${pct(costOnly.model)} of posts) was the bin every other measured post fell into, and its description fits about ${pct(costOnly.value, 1)} (${audRange('cost_only_as_described', 1)}). And not one of the ${CAND} "materially different" builds did something that was unavailable before.${AUDITED ? '' : ` The other two fails, the share of posts that compare Jev with nothing and the share that are meta, rest on the audit taking the labels as right wherever it didn't sample. On its own random samples, the ${FRAME_SHORT} labels' ${pct(need('baseline_none').frameModel)} and ${pct(need('meta_still').frameModel)} sit inside the intervals (${bound(need('baseline_none').frameAoLo, 0)} to ${bound(need('baseline_none').frameAoHi, 0)}, and ${bound(need('meta_still').frameAoLo, 0)} to ${bound(need('meta_still').frameAoHi, 0)}). That's why the audited numbers on this page are ranges.`}</p>
    <h3>What was checked</h3>
    ${auditSampling}
    <h3>How often the audit agrees with the model</h3>
    <p>The share of audited posts where the audit's label matches the ${LABELS_MODEL} label, field by field. The groups aren't a random sample of the week, so the last row is agreement on the audited posts, not on every post.</p>
    ${auditAgreement}
    ${AUDITED ? '' : `<p>The ${AUDITED_MODEL} labels the audit sampled from agree less on every field:</p>
    ${auditCompare}`}
    <h3>The ten claims</h3>
    <p>As first published, with the audit's corrected value and its 95% interval.</p>
    ${auditClaims}
    ${AUDITED ? '' : `<h3>The numbers this page uses</h3>
    <p>Each audited estimate with its 95% interval, as a share of ${LABELS_SHORT}'s ${fmt(ESTBASE)} posts. "Samples only" uses the audit's random samples where it didn't look, instead of ${LABELS_SHORT}'s labels. The last column is the audit's own estimate on the ${FRAME_SHORT} labels.</p>
    ${auditEstimates}`}
    <h3>What the audit couldn't check</h3>
    <p>${auditCouldNot}</p>
    <h3>How the posts were labeled</h3>
    <ul>
      <li><b>Data.</b> ${a(L.feed, "OpenChamber's Jev feed")}, snapshot ${FEED.day} ${FEED.time} UTC: ${fmt(S.posts)} posts from ${fmt(S.authors)} authors, which OpenChamber selected with its own filter for what counts as a build.${S.feed.kept_from_earlier ? ` That includes ${S.feed.kept_from_earlier} posts an earlier snapshot held and the feed later dropped.` : ''}${S.feed.cut_after_through ? ` Posts after ${dnum(S.feed.through)} ${mname(S.feed.through)} (UTC) are left out.` : ''} Post times decoded from the X ids run from ${FIRST.day} ${FIRST.time} to ${LAST.day} ${LAST.time} UTC. Views are X impressions and likes are X likes, both as the feed recorded them.</li>
      <li><b>Open data.</b> The labels from every model and the audit, the tables behind every chart, the rubric and the code are at ${a(L.repo, esc(REPO_SHORT))}. The feed's post text isn't republished there; the repo says how to fetch it.</li>
      <li><b>Rubric.</b> The v2 rubric has 15 families (the ${FAMILY_WORDS} on the charts, and one for posts that don't use Jev), 7 latency tiers, 5 evidence levels, 5 framings, 6 baselines, and two flags: realtime infrastructure and a production claim. The framings and the seven tiers were labeled but aren't charted; they are in the labels file. "Measured" needs a number from the author's own run; TypeSafe's launch numbers quoted as Jev's general speed or price don't count. "Unclear" is allowed and preferred to a guess.</li>
      <li><b>Models.</b> ${AUDITED ? `Claude Sonnet 5 labeled every post through Vercel AI Gateway, in batches of 40, with the rubric as a cached system prompt. Sonnet 5 ignores temperature, so runs aren't deterministic: on the same 120 cards, two runs matched on family for ${S.v2_stability_on_120.family.replace('/', ' of ')}.` : `${LABELS_MODEL}, with adaptive thinking, labeled every post through Vercel AI Gateway, in batches of 40, with the v2 rubric as a cached system prompt (<code>${esc(LB.file)}</code>). Its safety filter refused ${S.audit.labels_refused.length === 1 ? 'one post' : `${S.audit.labels_refused.length} posts`}, which ${S.audit.labels_refused.length === 1 ? 'is' : 'are'} left out. Claude Sonnet 5 made the first two passes, and its v2 labels are the ones the audit sampled from. The Gateway ignores temperature for both models, so both runs were sampled at its default and aren't deterministic: on the same 120 cards, two Sonnet runs matched on family for ${S.v2_stability_on_120.family.replace('/', ' of ')}.`} Jev classified the family of every post again as a second classifier, one call per post.</li>
      <li><b>Noise sub-types.</b> A separate Claude Sonnet 5 pass sorted the noise posts (Other or meta, or commentary in another family) into sub-types, and the hot takes by stance, against <code>report/rubric-noise.md</code>.</li>
      <li><b>Cost.</b> At Gateway list prices the first Sonnet pass cost ${usd(SPEND.v1)} and the second ${usd(v2cost)} (${usd(sonnetV2Cost)} for the full run${S.classified_sonnet_v2 > S.v1_set.cards ? ' and the refreshes' : ''}, ${usd(pilots)} for two 120-card pilots).${AUDITED ? '' : ` The ${LABELS_MODEL} run cost ${usd(labelsCost)}.`} Sorting the noise into sub-types (figure ${figNo('11')}) cost ${usd(S.cost.noise_usd)}, and Jev's pass ${usd(jevCost)}.</li>
      <li><b>Base.</b> ${S.duplicates_merged} duplicate posts were merged, and the ${S.not_a_jev_build} posts that don't use Jev (${pct(S.not_a_jev_build_stats.share_of_deduped)}: local clones, distillations, Jev-compatible APIs over other models, builds on other models) are left out of every use-case chart${AUDITED ? '' : `, as is the post ${LABELS_SHORT} refused`}. That leaves ${fmt(BASE)} posts.</li>
      <li><b>Agreement.</b> The audit is the main check: ${AUDITOR} labeled ${fmt(LABELLED)} posts blind, and agrees with ${AUDITED ? 'the model' : LABELS_SHORT} on family for ${pct(PA.family, 0)} of them, on evidence for ${pct(PA.evidence, 0)} and on tier for ${pct(PA.tier, 0)}. An earlier check, 120 random posts labeled blind by Claude Opus 5.5 in a separate run, is in the report.${HC.n ? ` I labeled ${HC.n} posts myself as a calibration.` : ''} The readers that checked every number are AI models; a proper human sample is the check still missing.</li>
    </ul>
    <h3>What the charts count</h3>
    <ul>
      ${ORDER.map((k) => `<li><b>Figure ${figNo(k)}.</b> ${CHART_NOTES[k]}</li>`).join('\n      ')}
    </ul>
    <h3>The buckets are gone</h3>
    <p>The first versions of this page put every post in one of six buckets: noise, hype, demo, cost-only, fast loop and material. The rules were finished after the data arrived, and the audit showed they didn't hold (claim 3), so the buckets are withdrawn. The measurement ladder in figure ${figNo('01')} and the substance test in figure ${figNo('12')} replace them. The bucket tables are kept for the record in the repo (<code>report/v1/buckets-on-v2-labels.md</code>), and so is the Sonnet version of this analysis (<code>report/v2/</code>).</p>
    <h3>What changed from the first pass</h3>
    <p>A critical review of the first pass found that "hype" rested on Sonnet calling any build "capability", that the accuracy and latency chip medians mixed Jev's numbers with baselines, and that "${fmt(S.v1_set.cards)} people" was ${fmt(S.v1_set.cards)} posts from ${fmt(S.v1_set.authors)} authors. The v2 rubric moved measured production from ${shift('evidence = measured_production')['v1 share']} to ${shift('evidence = measured_production')['v2 share']} of posts and production claims from ${shift('production_claim = True')['v1 share']} to ${shift('production_claim = True')['v2 share']}. The realtime flag went the other way (${shift('realtime_infra = True')['v1 share']} to ${shift('realtime_infra = True')['v2 share']}) because v2 flags nearly every game; figure ${figNo('07')} corrects for that with the audit.</p>
    <h3>Data quality and limits</h3>
    <ul>
      <li>Post text in the feed is capped at 400 characters, and ${fmt(S.data_quality.text_exactly_400_chars)} posts (${pct(S.data_quality.text_exactly_400_chars / S.posts, 0)}) are cut. The claim chips come from the full post, so some numbers are visible only as chips.</li>
      <li>The most-viewed post has a like rate of ${pct(num(stats.top_card_like_rate), 2)}, and ${stats.suspect_cards} posts with 100,000 or more views and a like rate under 0.2% hold ${pct(num(stats.suspect_share_views))} of views. Figure ${figNo('02')} gives the numbers without them.</li>
      <li>Every label is one model's reading of a short post, not a check of what was built. Claims on the cards are the authors' own and aren't reproduced here.</li>
      <li>Every table behind these charts, the rubric and the scripts are in ${a(L.repo, 'the repo')}; this page and its charts are generated from those CSVs by <code>report/site/scripts/charts.mjs</code>.</li>
    </ul>
  </details>
</section>
</main>
<script>
(() => {
  const tip = document.createElement('div');
  tip.className = 'tip'; tip.hidden = true; tip.setAttribute('role', 'presentation');
  document.body.appendChild(tip);
  document.querySelectorAll('figure svg title').forEach((t) => {
    const el = t.parentElement;
    if (!el || el.tagName.toLowerCase() === 'svg') return;
    el.setAttribute('data-tip', t.textContent);
    t.remove();
  });
  const hide = () => { tip.hidden = true; };
  document.addEventListener('pointermove', (e) => {
    const el = e.target && e.target.closest ? e.target.closest('[data-tip]') : null;
    if (!el) return hide();
    tip.textContent = el.getAttribute('data-tip');
    tip.hidden = false;
    const w = tip.offsetWidth, h = tip.offsetHeight;
    const x = Math.max(8, Math.min(e.clientX + 14, window.innerWidth - w - 8));
    const y = e.clientY + 18 + h > window.innerHeight ? e.clientY - h - 12 : e.clientY + 18;
    tip.style.transform = 'translate(' + x + 'px,' + y + 'px)';
  });
  document.addEventListener('pointerleave', hide);
  window.addEventListener('scroll', hide, { passive: true });
  // printing shows every table: open the closed <details> for the print, and close them after
  const opened = [];
  window.addEventListener('beforeprint', () => {
    document.querySelectorAll('details:not([open])').forEach((d) => { d.open = true; opened.push(d); });
  });
  window.addEventListener('afterprint', () => { opened.splice(0).forEach((d) => { d.open = false; }); });
})();
</script>
</body>
</html>
`;
// ---------------------------------------------------------------- copy checks
// Some sentences state a fact in words ("nine in ten", "about a third", which families lead).
// They were written for the 23 September data and the 24 September audit. After a refresh these checks
// name any that no longer hold. They warn and do not stop the build: read the sentence and rewrite it.
// "The audit tables" is the collapsed <details> at the end of the page, where the old chart notes went.
// The last checks keep the page's own rules: one-line subtitles and footer, and the method's numbers.
const copyWarnings = [];
const claim = (cond, where, text) => { if (!cond) copyWarnings.push(`${where}: "${text}"`); };
const within = (v, lo, hi) => v >= lo && v < hi;
claim(within(num(top1.views_share), 0.45, 0.58), 'figure 2 title', `Half the views went to 1 percent of posts (now ${pct(num(top1.views_share))})`);
claim(within(AB.none.value, 0.75, 0.85) && within(num(baseRows.none.share_posts), 0.75, 0.85), 'figure 3 title and lead, and the short version',
  `About four in five posts compared Jev with nothing (audit ${pct(AB.none.value)}, labels ${pct(num(baseRows.none.share_posts))})`);
claim(within(AB.repl.value, 0.028, 0.042) && within(incShare, 0.028, 0.045), 'figure 3 title and lead, and the short version',
  `about 1 in 30 with what it would replace (audit ${pct(AB.repl.value)}, labels ${pct(incShare)})`);
claim(within(evAll.demo_no_numbers / BASE, 0.6, 0.72), 'figure 4 title', `Two thirds of builds showed no numbers (now ${pct(evAll.demo_no_numbers / BASE)})`);
claim(within(F300.value, 0.085, 0.13) && within(G300.value, 0.85, 0.95), 'figure 6 title and lead',
  `About ${Math.round(F300.value * 100)} percent of posts need a decision in under 300 ms, about 9 in 10 of them games (audit ${pct(F300.value)}, ${pct(G300.value)})`);
claim(within(num(ja.share), 0.17, 0.23), 'figure 10 title', `One post in five was in Japanese (now ${pct(num(ja.share))})`);
claim(within(measuredDemoShare, 0.28, 0.38) && within(need('ladder_measured_demo').value, 0.28, 0.38), 'figure 1 title and lead',
  `About a third of the week's posts measured a demo (labels ${pct(measuredDemoShare)}, audit ${pct(need('ladder_measured_demo').value)})`);
claim(within(need('ladder_no_measurement').value, 0.6, 0.72), 'figure 1 lead', `Two thirds of posts measured nothing (audit ${pct(need('ladder_no_measurement').value)})`);
claim(stepTot.prod_ok === PROD.k, 'figure 1 lead', 'production is only the orange squares: the labels call every post that holds on the audit production');
claim(UNAVAIL === 0, 'figure 1c lead and the short version', 'none did something that was unavailable before');
claim(byBefore.llm === Math.max(...BEFORE.map((r) => r.posts)), 'figure 1c lead and the short version', 'an LLM is the most common prior method');
claim(within(MS.value, 0.18, 0.23) && within(MA.value, 0.17, 0.24), 'figure 1b title and lead', `About a fifth of posts are meta (audit ${pct(MS.value)}, samples only ${pct(MA.value)})`);
claim(underHalf, 'figure 1b title and lead', 'memes and hot takes are under half a percent of posts each');
claim(!HC.meta_by_both_models || HC.meta_given_real_use >= HC.meta_by_both_models / 2, 'the audit tables, figure 1b', 'a careful human reader gives most of the posts both models call meta a use');
claim(Object.keys(PROD_WORDS).every((id) => heldById[id]) && Object.keys(QA_SITES).every((id) => heldById[id])
  && Object.keys(heldById).length === Object.keys(PROD_WORDS).length + Object.keys(QA_SITES).length, 'figure 4 lead',
  'the production posts named in the lead are exactly the ones that hold on the audit');
claim(PROD.n - PROD.k === AUD_PROD.filter((r) => !r.holds && ['measured_demo', 'demo_no_numbers'].includes(r.audit_evidence)).length, 'the audit tables, figure 1',
  'the production posts that do not hold are tests, a figure from development, or claims with no number');
claim(AUDITED || PA_READ.k < PA_READ.n * 0.7, 'the audit tables, figures 1 and 4', `the labels are generous with production: the audit agrees with ${PA_READ.k} of the ${PA_READ.n} it read`);
claim(within(LLA.value, 0.17, 0.25), 'the audit tables, figure 7', `about a fifth of all posts have a live loop, games included (now ${pct(LLA.value)})`);
claim(heldRealtime === 0 && rtHeld.length === 0 && rtfProd === 0, 'figure 7 title and lead, the short version', 'no production post that holds is a realtime build, and none in the live families is measured in production');
claim(AUDITED || rtfClaims === 2, 'the audit tables, figure 7', `two live-family posts claim production without a number: ${RT_CLAIMS}`);
claim(rtNamed, 'the audit tables, figure 7', 'every production post the labels put in the realtime slice is named');
claim(AUDITED || !flagsAbove, 'the audit tables, figure 7', `the labels' non-game realtime share sits inside the audit's interval (labels ${pct(LL.model)}, audit ${audRange('live_loop_nongame', 1)})`);
claim(Boolean(voiceBefore && sheetBefore) && voiceBefore.before === 'vendor' && sheetBefore.before === 'llm', 'figure 7 lead',
  'a vendor API already did the voice turn-end job and an LLM the spreadsheet job (both among the candidate builds)');
claim(within(meanRatio, 1.7, 2.6) && medRatio < 1.3, 'figure 8 title and lead',
  `Measured demos averaged twice the views of demos with no numbers, but the median barely moves (mean ${meanRatio.toFixed(2)}×, median ${medRatio.toFixed(2)}×)`);
claim(within(num(stats.cards_under_100_views) / BASE, 0.3, 0.6), 'figure 8 lead', `most posts got little attention: ${pct(num(stats.cards_under_100_views) / BASE)} had under 100 views`);
claim(verdictN.Fails === 3, 'the audit tables', 'one failed claim and "the other two fails": three of the ten claims fail');
claim(AUDITED || AFIELDS.every(([f]) => PA[f] >= PA_FRAME[f]), 'the method and the audit tables', 'the labels agree with the audit more than Sonnet on every field');
claim(AUDITED || (insideOf('baseline_none') && insideOf('baseline_frontier_llm') && insideOf('baseline_small_llm') && insideOf('baseline_replacement')), 'the audit tables, figure 3', "all four of the labels' baseline shares are inside the audit's intervals");
claim(AUDITED || (need('baseline_none').frameAoLo <= need('baseline_none').frameModel && need('baseline_none').frameModel <= need('baseline_none').frameAoHi
  && need('meta_still').frameAoLo <= need('meta_still').frameModel && need('meta_still').frameModel <= need('meta_still').frameAoHi), 'the audit tables',
  "the Sonnet labels' no-comparison and meta shares sit inside the audit's samples-only intervals");
claim(claimData.every((c) => within(c.median / SURVEY[c.surveyKey], 0.67, 1.5)), 'figure 5 title and lead', "in line with OpenChamber's own survey");
claim(['live_chat_streams_events', 'voice_and_turn_taking', 'collaboration_and_typing'].every((f) => jaShare(f) > num(ja.share)),
  'figure 10 lead', 'Japanese builders are over-represented in live chat, voice and collaboration');
claim(jevLat.p50_ms > 300, 'figure 6 lead', "Jev's median call is above every budget under 300 ms");
claim(within(num(stats.top1pct_views_excl_suspect), 0.45, 0.58), 'figure 2 lead', `without the suspect posts the top 1% "still hold" about half the views (now ${pct(num(stats.top1pct_views_excl_suspect))})`);
claim(PROD.k > 1, 'figure 1, figure 4 and figure 7 leads, the short version', `the production posts are counted in the plural ("${words(PROD.k)} posts")`);
claim(S.posts - S.duplicates_merged - S.not_a_jev_build - REFUSED === BASE, 'the method',
  `${fmt(S.posts)} posts less ${S.duplicates_merged} duplicates, ${S.not_a_jev_build} posts that don't use Jev and ${REFUSED} refused leave ${fmt(BASE)}`);
claim(AFIELDS.every(([f]) => PA.tier <= PA[f]), 'the method', 'the latency tier is the field the audit agrees with least');
claim(!HC.n || HC.tier_differs_from_both > HC.n / 2, 'the method', `the calibration found the tier problem: I disagreed with both models on the tier of ${HC.tier_differs_from_both} of ${HC.n}`);
// the page's own rules: a one-line subtitle for every chart, and a one-line source under each chart on the page
for (const c of CHARTS) claim(wrap(c.subtitle, WIDE - 48, 13).length === 1, `figure ${figNo(c.key)} subtitle`, `fits on one line at ${WIDE} px: ${c.subtitle}`);
claim(wrap(PAGE_SOURCE, WIDE - 48, 11).length === 1, 'the source line under each chart on the page', `fits on one line at ${WIDE} px: ${PAGE_SOURCE}`);

// The audit checks above run after the first gate: stop here too, before any file is written.
if (problems.length) {
  console.error(`Audit checks failed:\n- ${problems.join('\n- ')}`);
  process.exit(1);
}

// ---------------------------------------------------------------- write the chart files and the page
// The files carry the full source line and the disclosure (footer 'file'); the page inlines the same
// charts with its one-line source (footer 'page').
mkdirSync(join(OUT, 'narrow'), { recursive: true });
const written = [];
for (const c of CHARTS) {
  for (const [dir, W, tag] of [[OUT, WIDE, 'w'], [join(OUT, 'narrow'), NARROW, 'n']]) {
    const files = [
      [`${c.file}.svg`, frame(THEMES.vars, c, W, `${tag}auto`, 'file')],
      [`${c.file}-light.svg`, frame(THEMES.light, c, W, `${tag}light`, 'file')],
      [`${c.file}-dark.svg`, frame(THEMES.dark, c, W, `${tag}dark`, 'file')],
    ];
    for (const [name, svg] of files) { writeFileSync(join(dir, name), XML + svg + '\n'); written.push(join(dir, name)); }
  }
}
writeFileSync(join(SITE, 'index.html'), html);
written.push(join(SITE, 'index.html'));
console.log(`Wrote ${written.length} files:\n${written.map((f) => `  ${f.replace(`${SITE}/`, '')}`).join('\n')}`);
if (copyWarnings.length) {
  console.warn(`COPY CHECK: ${copyWarnings.length} worded claim(s) no longer hold; read and rewrite them before publishing:`);
  for (const w of copyWarnings) console.warn(`COPY CHECK: ${w}`);
} else console.log('Copy checks: every worded claim on the page still holds.');

// ---------------------------------------------------------------- the PDF (--pdf)
// A4, light, the wide charts, every <details> open so the numbers and the audit tables are in it; the print
// rules are the page's own @media print CSS. The page loads its fonts from Google Fonts, the only network use.
if (process.argv.includes('--pdf')) {
  const { chromium } = await import('playwright');
  const pdfPath = join(SITE, 'jev-week-sorted.pdf');
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ colorScheme: 'light' });
    await page.goto(pathToFileURL(join(SITE, 'index.html')).href, { waitUntil: 'load' });
    await page.emulateMedia({ media: 'print', colorScheme: 'light' });
    const fonts = await page.evaluate(async () => {
      document.documentElement.dataset.theme = 'light';
      document.querySelectorAll('details').forEach((d) => { d.open = true; });
      await document.fonts.ready;
      return [...document.fonts].filter((f) => f.status === 'loaded').length;
    });
    if (!fonts) console.warn('PDF: no web fonts loaded (offline?); the PDF uses the fallback fonts');
    await page.pdf({
      path: pdfPath, format: 'A4', printBackground: true, preferCSSPageSize: true, outline: true, tagged: true,
      displayHeaderFooter: true,
      headerTemplate: '<span></span>',
      footerTemplate: `<div style="width:100%;margin:0 14mm;font:8px Helvetica,Arial,sans-serif;color:#6f6e69;display:flex;justify-content:space-between">`
        + `<span>A week of Jev, sorted · Matthew O'Riordan · ${esc(PUBLISHED)}</span><span><span class="pageNumber"></span> of <span class="totalPages"></span></span></div>`,
    });
    console.log(`Wrote ${pdfPath.replace(`${SITE}/`, '')}`);
  } finally {
    await browser.close();
  }
}
