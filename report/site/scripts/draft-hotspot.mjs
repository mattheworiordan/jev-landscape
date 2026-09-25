#!/usr/bin/env node
// draft-hotspot.mjs: DRAFT, 25 September 2026. Where the posts are against how fast the decision is needed:
// the six groups of page-v3.mjs by three latency bands (under 300 ms = frame, feel, turn; under a second =
// interaction; seconds or slower = task, batch) plus unclear, on the Opus labels, on the 5,595-post use-case base.
// Drawn with lib.mjs so it matches the report. Writes only to report/site/v3/drafts/; page-v3.mjs, charts.mjs,
// the page and publish/ are untouched.
// Run: node report/site/scripts/draft-hotspot.mjs
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import { FOOTERS, THEMES, esc, fmt, pct, r1, sum, tw, wrap, tx, txs, lines, rect, legend, frame } from './lib.mjs';

const SITE = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const REPORT = resolve(SITE, '..');
const PROJECT = resolve(REPORT, '..');
const DATA = join(REPORT, 'data');
const PDATA = join(PROJECT, 'data');
const OUT = join(SITE, 'v3', 'drafts');
const WIDE = 640, NARROW = 360;
const XML = '<?xml version="1.0" encoding="UTF-8"?>\n';

function parseCSV(text) { // as page-v3.mjs
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
const problems = [];
const check = (cond, msg) => { if (!cond) problems.push(msg); };

// ---------------------------------------------------------------- data
const S = JSON.parse(readFileSync(join(REPORT, 'summary.json'), 'utf8'));
const AE = Object.fromEntries(csv('13_audit_estimates').map((r) => [r.key, { value: +r.value, lo: r.lo === '' ? null : +r.lo, hi: r.hi === '' ? null : +r.hi, model: r.model === '' ? null : +r.model }]));
const BASE = S.use_case_base;
const perCard = csv('08_ladder_per_card');
check(perCard.length === BASE, `per-card rows ${perCard.length} should equal the use-case base ${BASE}`);
const tierOf = new Map();
for (const line of readFileSync(join(PDATA, 'classified-opus.jsonl'), 'utf8').split('\n')) { if (!line.trim()) continue; const r = JSON.parse(line); tierOf.set(String(r.id), r.tier); }
check(perCard.every((r) => tierOf.has(String(r.id))), 'every post in the base has an Opus tier');
const JOB = Object.fromEntries(csv('13_audit_substance').filter((r) => r.kind === 'job').map((r) => [r.key, r.label]));

// the six groups, as page-v3.mjs defines them
const GROUPS = [
  { key: 'data', name: 'Decisions about data', fams: ['classification_routing_triage', 'search_rerank_extraction', 'evals_and_judging', 'data_and_telemetry'] },
  { key: 'games', name: 'Decisions inside games and control loops', fams: ['games_control_loops_simulation'] },
  { key: 'agents', name: 'Decisions inside agent loops', fams: ['agent_harness_and_tool_gating', 'browser_and_computer_use', 'compaction_and_context'] },
  { key: 'people', name: 'Decisions about what a person just said or typed', fams: ['moderation_and_guardrails', 'voice_and_turn_taking', 'live_chat_streams_events', 'collaboration_and_typing'] },
  { key: 'money', name: 'Decisions about money', fams: ['trading_and_markets'] },
  { key: 'none', name: 'No decision stated', fams: ['other_or_meta'] },
];
const BANDS = [
  { key: 'sub300', name: 'Under 300 ms', short: 'Under 300 ms', tiers: ['frame', 'feel', 'turn'], note: 'frame, feel, turn' },
  { key: 'sub1s', name: 'Under a second', short: 'Under 1 s', tiers: ['interaction'], note: 'interaction' },
  { key: 'slow', name: 'Seconds or slower', short: 'Seconds+', tiers: ['task', 'batch'], note: 'task, batch' },
  { key: 'unclear', name: 'Unclear', short: 'Unclear', tiers: ['unclear'], note: 'not placed' },
];
// one short example per cell: the job names of the audit's substance table where a family maps to one, else the family in plain words
const EX = {
  classification_routing_triage: JOB.classify, search_rerank_extraction: JOB.search, evals_and_judging: 'Evals and judging', data_and_telemetry: 'Telemetry',
  games_control_loops_simulation: JOB.game_or_sim, agent_harness_and_tool_gating: 'Tool-call gating', browser_and_computer_use: JOB.computer_use, compaction_and_context: 'Context pruning',
  moderation_and_guardrails: JOB.feed_filter, voice_and_turn_taking: JOB.voice_turn, live_chat_streams_events: 'Live chat', collaboration_and_typing: JOB.typing_or_form,
  trading_and_markets: JOB.trading, other_or_meta: 'Talk about the model',
};
const groupOf = {}; for (const g of GROUPS) for (const f of g.fams) groupOf[f] = g.key;
const bandOf = {}; for (const b of BANDS) for (const t of b.tiers) bandOf[t] = b.key;

function grid(rows) {
  const cells = {}; for (const g of GROUPS) for (const b of BANDS) cells[`${g.key}.${b.key}`] = { n: 0, fams: {} };
  for (const r of rows) { const c = cells[`${groupOf[r.family]}.${bandOf[tierOf.get(String(r.id))]}`]; c.n++; c.fams[r.family] = (c.fams[r.family] || 0) + 1; }
  const rowN = Object.fromEntries(GROUPS.map((g) => [g.key, sum(BANDS.map((b) => cells[`${g.key}.${b.key}`].n))]));
  const colN = Object.fromEntries(BANDS.map((b) => [b.key, sum(GROUPS.map((g) => cells[`${g.key}.${b.key}`].n))]));
  return { cells, rowN, colN, n: rows.length };
}
const ALL = grid(perCard);
const MEAS = grid(perCard.filter((r) => ['measured_demo', 'measured_production'].includes(r.evidence)));
const RT = grid(perCard.filter((r) => r.realtime_infra === 'True'));
const NRT = grid(perCard.filter((r) => r.realtime_infra !== 'True'));
check(ALL.n === BASE && sum(Object.values(ALL.rowN)) === BASE, 'the grid covers every post once');
check(Object.keys(groupOf).length === 14 && perCard.every((r) => groupOf[r.family]), 'every family is in a group');
const sub300 = ALL.colN.sub300, sub300Games = ALL.cells['games.sub300'].n;
check(Math.abs(sub300 / BASE - AE.sub300_set.model) < 1e-6, `Opus's under-300 ms share ${sub300 / BASE} matches the audit table's model value ${AE.sub300_set.model}`);
check(Math.abs(sub300Games / sub300 - AE.sub300_games.model) < 1e-6, "Opus's games share of the under-300 ms posts matches the audit table");
const F = { set: AE.sub300_set, games: AE.sub300_games, tier: AE.agreement_tier };
const p0 = (x) => pct(x, 0), iv = (e, d = 1) => `${(e.lo * 100).toFixed(d)} to ${(e.hi * 100).toFixed(d)}`;

function example(cell) {
  if (cell.n < 25) return '';
  const top = Object.entries(cell.fams).sort((a, b) => b[1] - a[1]);
  const one = EX[top[0][0]];
  if (top[1] && top[1][1] >= 0.25 * cell.n) { const two = EX[top[1][0]]; return `${one}, ${two.charAt(0).toLowerCase()}${two.slice(1)}`; }
  return one;
}
const STEPS_N = [25, 100, 250, 500, 750, 1000];
const shade = (n) => { let k = 0; for (const t of STEPS_N) if (n >= t) k++; return k; };

// ---------------------------------------------------------------- the chart
const chart = {
  key: 'hs', file: 'hotspot',
  title: 'The need for a decision in under 300 ms has one hot spot: games',
  subtitle: `${fmt(BASE)} posts by what the decision is about and how soon it is needed, on Claude Opus's labels. Shade is the number of posts; the audit estimated only the under-300 ms column and its games share.`,
  desc: GROUPS.map((g) => `${g.name}: ${BANDS.map((b) => `${b.name.toLowerCase()} ${fmt(ALL.cells[`${g.key}.${b.key}`].n)}`).join(', ')}.`).join(' ') + ` Audited: ${pct(F.set.value)} of posts need under 300 ms (${iv(F.set)}), ${p0(F.games.value)} of them games (${iv(F.games, 0)}).`,
  body(T, { x0, x1, y0, narrow }) {
    const out = []; let y = y0;
    const lg = legend(T, [
      { label: 'under 25', role: 'seq0' }, { label: '25+', role: 'seq1' }, { label: '100+', role: 'seq2' }, { label: '250+', role: 'seq3' },
      { label: '500+', role: 'seq4' }, { label: '750+', role: 'seq5' }, { label: '1,000+ posts', role: 'seq6' },
      { label: 'Unclear', role: 'g1' }, { label: `Outlined: games, ${p0(F.games.value)} of the under-300 ms posts on the audit`, role: 'accent', kind: 'line' },
    ], x0, x1, y, { size: narrow ? 10 : 11 });
    out.push(lg.svg); y = lg.y + 10;
    const labelW = narrow ? 0 : 160; const totW = narrow ? 0 : 70; const gap = 3; const gapU = narrow ? 6 : 10;
    const cellsW = x1 - x0 - labelW - totW - (narrow ? 0 : 8);
    const wB = (cellsW - 2 * gap - gapU) / 4; const wU = wB;
    const cx = []; { let x = x0 + labelW; for (let i = 0; i < 3; i++) { cx.push(x); x += wB + gap; } cx.push(cx[2] + wB + gapU); }
    const cw = (i) => (i === 3 ? wU : wB);
    const totX = x1 - totW;
    // column heads
    const hs = narrow ? 10 : 11;
    const headLines = BANDS.map((b, i) => wrap(narrow ? b.short : b.name, cw(i) - 4, hs, 700));
    const hl = Math.max(...headLines.map((l) => l.length));
    BANDS.forEach((b, i) => {
      headLines[i].forEach((l, j) => out.push(tx(T, cx[i] + 2, y + hs + (hl - headLines[i].length + j) * (hs + 3), l, { size: hs, weight: 700, role: i === 3 ? 'ink2' : 'ink' })));
      out.push(tx(T, cx[i] + 2, y + hs + (hl - 1) * (hs + 3) + 13, b.note, { size: narrow ? 9 : 10, role: 'muted' }));
    });
    if (!narrow) { out.push(tx(T, totX + 8, y + hs + (hl - 1) * (hs + 3), 'All posts', { size: hs, weight: 700 })); out.push(tx(T, totX + 8, y + hs + (hl - 1) * (hs + 3) + 13, 'and share', { size: 10, role: 'muted' })); }
    y += hs + (hl - 1) * (hs + 3) + 22;
    const rh = narrow ? 38 : 62;
    const maxRow = Math.max(...Object.values(ALL.rowN));
    for (const g of GROUPS) {
      const rowN = ALL.rowN[g.key];
      if (narrow) {
        out.push(txs(T, x0, y + 11, [{ s: g.name, weight: 700 }], { size: 10.5 }));
        const nm = tw(g.name, 10.5, 700);
        if (nm + tw(`  ${fmt(rowN)} · ${p0(rowN / BASE)}`, 10) < x1 - x0) out.push(txs(T, x0 + nm, y + 11, [{ s: `  ${fmt(rowN)} · ${p0(rowN / BASE)}`, role: 'muted', size: 10 }], { size: 10 }));
        y += 16;
      } else {
        const b = lines(T, x0, y + (rh - (wrap(g.name, labelW - 12, 12, 700).length * 15)) / 2 - 3, g.name, labelW - 12, { size: 12, lh: 15, weight: 700 });
        out.push(b.svg);
      }
      BANDS.forEach((bd, i) => {
        const c = ALL.cells[`${g.key}.${bd.key}`]; const share = c.n / rowN;
        const k = shade(c.n);
        const fill = i === 3 ? (c.n >= 250 ? 'g2' : 'g1') : `seq${k}`;
        const ink = i === 3 || k === 0 ? 'ink' : `sqt${k}`;
        const tip = `${g.name}, ${bd.name.toLowerCase()}: ${fmt(c.n)} posts, ${p0(share)} of the group`;
        out.push(rect(T, cx[i], y, cw(i), rh, fill, ' rx="3"').replace('/>', `><title>${esc(tip)}</title></rect>`));
        const fs = narrow ? 11.5 : 13;
        out.push(txs(T, cx[i] + (narrow ? 6 : 8), y + (narrow ? 16 : 19), [{ s: fmt(c.n), weight: 700, role: ink }, ...(narrow ? [] : [{ s: `  ${p0(share)}`, role: ink, size: 10.5 }])], { size: fs }));
        if (narrow) out.push(tx(T, cx[i] + 6, y + 30, p0(share), { size: 9.5, role: ink }));
        else {
          const ex = example(c);
          if (ex) {
            let ls = wrap(ex, cw(i) - 14, 9.5);
            if (ls.length > 3) ls = wrap(EX[Object.entries(c.fams).sort((a, b2) => b2[1] - a[1])[0][0]], cw(i) - 14, 9.5);
            check(ls.length <= 3, `example for ${g.key}.${bd.key} fits in three lines`);
            ls.forEach((l, j) => out.push(tx(T, cx[i] + 8, y + 34 + j * 11, l, { size: 9.5, role: ink })));
          }
        }
        if (g.key === 'games' && bd.key === 'sub300') out.push(`<rect x="${r1(cx[i] + 1)}" y="${r1(y + 1)}" width="${r1(cw(i) - 2)}" height="${r1(rh - 2)}" rx="3" fill="none" stroke-width="2.5" ${T.mode === 'vars' ? 'style="stroke:var(--v-accent)"' : `stroke="${T.accent}"`}/>`);
      });
      if (!narrow) {
        const bw = (rowN / maxRow) * (totW - 12);
        out.push(txs(T, totX + 8, y + 19, [{ s: fmt(rowN), weight: 700 }, { s: `  ${p0(rowN / BASE)}`, role: 'ink2', size: 10.5 }], { size: 12 }));
        out.push(rect(T, totX + 8, y + 27, bw, 8, 'g2', ' rx="2"').replace('/>', `><title>${esc(`${g.name}: ${fmt(rowN)} posts, ${pct(rowN / BASE)} of all posts`)}</title></rect>`));
      }
      y += rh + gap;
    }
    // column totals
    y += 6;
    if (!narrow) out.push(tx(T, x0, y + 13, 'All groups', { size: 12, weight: 700 }));
    else { out.push(tx(T, x0, y + 11, `All groups  ${fmt(BASE)}`, { size: 10.5, weight: 700 })); y += 16; }
    BANDS.forEach((bd, i) => {
      const n = ALL.colN[bd.key];
      out.push(txs(T, cx[i] + (narrow ? 6 : 8), y + 13, [{ s: fmt(n), weight: 700 }, { s: `  ${p0(n / BASE)}`, role: 'ink2', size: narrow ? 9.5 : 10.5 }], { size: narrow ? 11 : 12 }));
    });
    if (!narrow) out.push(tx(T, totX + 8, y + 13, fmt(BASE), { size: 12, weight: 700 }));
    y += 22;
    const note = `Cells are Claude Opus's labels, and how soon a decision is needed is the field the blind audit agrees with least (${p0(F.tier.value)} at seven tiers). The audit puts ${pct(F.set.value)} of posts under 300 ms (${iv(F.set)}), not Opus's ${pct(F.set.model)}, and ${p0(F.games.value)} of those are games (${iv(F.games, 0)}): the only two numbers here it confirms.`;
    const b = lines(T, x0, y, note, x1 - x0, { size: narrow ? 10 : 10.5, lh: narrow ? 13.5 : 14, role: 'ink2' });
    out.push(b.svg); y += b.h;
    return { svg: out.join(''), y };
  },
};

// ---------------------------------------------------------------- render
const SOURCE_FILE = `Source: jev.openchamber.dev, ${fmt(S.posts)} posts 16 to 23 Sep 2026 (UTC), classified with Claude Opus 5.5, 1,681 posts audited blind by Grok; analysis by Matthew O'Riordan`;
FOOTERS.file.length = 0; FOOTERS.file.push(SOURCE_FILE, 'Draft for review, 25 Sep 2026. Not in the report.', 'Disclosure: the author is CEO of Ably, a realtime infrastructure company.');
mkdirSync(join(OUT, 'narrow'), { recursive: true });
const written = [];
for (const [dir, W, tag] of [[OUT, WIDE, 'w'], [join(OUT, 'narrow'), NARROW, 'n']]) {
  for (const [name, T, v] of [[`${chart.file}.svg`, THEMES.vars, `${tag}auto`], [`${chart.file}-light.svg`, THEMES.light, `${tag}light`], [`${chart.file}-dark.svg`, THEMES.dark, `${tag}dark`]]) {
    const p = join(dir, name); writeFileSync(p, XML + frame(T, chart, W, v, 'file') + '\n'); written.push(p);
  }
}
if (problems.length) { console.error('CHECKS FAILED:\n- ' + problems.join('\n- ')); process.exit(1); }
const png = join(OUT, `${chart.file}.png`);
execFileSync('rsvg-convert', ['-w', '1600', '-b', 'white', '-o', png, join(OUT, `${chart.file}-light.svg`)]); written.push(png);

// the numbers behind it
const rowsOut = ['cut,group,band,posts,row_share,col_share'];
for (const [cut, Gd] of [['all', ALL], ['measured', MEAS], ['realtime_infra_true', RT], ['realtime_infra_false', NRT]]) {
  for (const g of GROUPS) for (const b of BANDS) { const n = Gd.cells[`${g.key}.${b.key}`].n; rowsOut.push([cut, g.key, b.key, n, (n / Gd.rowN[g.key] || 0).toFixed(4), (n / Gd.colN[b.key] || 0).toFixed(4)].join(',')); }
}
writeFileSync(join(OUT, 'hotspot-grid.csv'), rowsOut.join('\n') + '\n'); written.push(join(OUT, 'hotspot-grid.csv'));
const show = (label, Gd) => {
  console.log(`\n${label} (${fmt(Gd.n)} posts)`);
  console.log('| Group | ' + BANDS.map((b) => b.name).join(' | ') + ' | All |');
  for (const g of GROUPS) console.log(`| ${g.name} | ` + BANDS.map((b) => { const n = Gd.cells[`${g.key}.${b.key}`].n; return `${fmt(n)} (${p0(n / Gd.rowN[g.key])})`; }).join(' | ') + ` | ${fmt(Gd.rowN[g.key])} |`);
  console.log('| All groups | ' + BANDS.map((b) => `${fmt(Gd.colN[b.key])} (${pct(Gd.colN[b.key] / Gd.n)})`).join(' | ') + ` | ${fmt(Gd.n)} |`);
  console.log(`games share of under 300 ms: ${pct(Gd.cells['games.sub300'].n / Gd.colN.sub300)}; games plus people: ${pct((Gd.cells['games.sub300'].n + Gd.cells['people.sub300'].n) / Gd.colN.sub300)}`);
};
show('All posts', ALL); show('Measured (demo or production)', MEAS); show('realtime_infra true', RT); show('realtime_infra false', NRT);
for (const g of GROUPS) for (const b of BANDS) { const c = ALL.cells[`${g.key}.${b.key}`]; if (c.n >= 25) console.log(`example ${g.key}.${b.key}: ${example(c)}`); }
console.log(`\nwrote ${written.length} files:\n${written.join('\n')}`);
