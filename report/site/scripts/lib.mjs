// Shared drawing helpers, extracted verbatim from charts.mjs (lines 149 to 338) so page-v3.mjs draws in the same style.
// Keep in sync with charts.mjs; charts.mjs itself is unchanged.
export const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
export const fmt = (n) => Math.round(n).toLocaleString('en-US');
export const pct = (x, d = 1) => `${(x * 100).toFixed(d)}%`;
export const r1 = (v) => Math.round(v * 10) / 10;
export const sum = (a) => a.reduce((x, y) => x + y, 0);
export const FOOTERS = { page: [], file: [] };
export const FONT = "Manrope, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif";

// ---------------------------------------------------------------- palette
// Validated with the dataviz skill's validate_palette.js:
//   categorical pair (blue secondary, orange accent): PASS light and dark, CVD dE 24.7 / 26.8
//   blue ordinal steps (blueLo, blue, blueHi): PASS --ordinal light and dark
// Greys are de-emphasis marks; every grey-filled mark is also named in a legend or a label,
// and each chart has a table view on the page.
export const PALETTE = {
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
export const THEMES = {
  light: { mode: 'light', ...PALETTE.light },
  dark: { mode: 'dark', ...PALETTE.dark },
  vars: { mode: 'vars' },
};
export const cssVars = (mode) => Object.entries(PALETTE[mode]).map(([k, v]) => `--v-${k}:${v}`).join(';');

// fill / stroke by role. Concrete themes get presentation attributes (most portable);
// the vars theme gets CSS custom properties so one SVG can follow the page or the OS.
export function paint(T, fill, stroke) {
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
export function tw(s, size, weight = 400) {
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
export function wrap(s, maxW, size, weight = 400) {
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
export function tx(T, x, y, s, { size = 12, weight = 400, role = 'ink', anchor = 'start' } = {}) {
  const a = [`x="${r1(x)}"`, `y="${r1(y)}"`, `font-size="${size}"`];
  if (weight !== 400) a.push(`font-weight="${weight}"`);
  if (anchor !== 'start') a.push(`text-anchor="${anchor}"`);
  return `<text ${a.join(' ')} ${paint(T, role)}>${esc(s)}</text>`;
}
// mixed runs on one line: spans = [{s, weight, role, size}]
export function txs(T, x, y, spans, { size = 12, anchor = 'start' } = {}) {
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
export const spansW = (spans, size) => sum(spans.map((sp) => tw(sp.s, sp.size || size, sp.weight || 400)));
export function lines(T, x, y, text, maxW, { size = 12, lh = 16, weight = 400, role = 'ink', anchor = 'start' } = {}) {
  const ls = wrap(text, maxW, size, weight);
  const svg = ls.map((l, i) => tx(T, x, y + size + i * lh, l, { size, weight, role, anchor })).join('');
  return { svg, h: size + (ls.length - 1) * lh, n: ls.length };
}

// ---------------------------------------------------------------- marks
export const ln = (T, x1, y1, x2, y2, role = 'grid', w = 1) =>
  `<line x1="${r1(x1)}" y1="${r1(y1)}" x2="${r1(x2)}" y2="${r1(y2)}" stroke-width="${w}" ${paint(T, null, role)}/>`;
export const rect = (T, x, y, w, h, role, extra = '') =>
  `<rect x="${r1(x)}" y="${r1(y)}" width="${r1(Math.max(w, 0))}" height="${r1(Math.max(h, 0))}" ${paint(T, role)}${extra}/>`;
export function hbarD(x, y, w, h, r = 4) { // rounded data-end on the right, square at the baseline
  if (w <= 0) return '';
  r = Math.min(r, w, h / 2);
  return `M${r1(x)} ${r1(y)}h${r1(w - r)}a${r1(r)} ${r1(r)} 0 0 1 ${r1(r)} ${r1(r)}v${r1(h - 2 * r)}a${r1(r)} ${r1(r)} 0 0 1 ${r1(-r)} ${r1(r)}h${r1(-(w - r))}z`;
}
export function vbarD(x, yBase, w, h, r = 4) { // rounded data-end on top
  if (h <= 0) return '';
  r = Math.min(r, h, w / 2);
  return `M${r1(x)} ${r1(yBase)}v${r1(-(h - r))}a${r1(r)} ${r1(r)} 0 0 1 ${r1(r)} ${r1(-r)}h${r1(w - 2 * r)}a${r1(r)} ${r1(r)} 0 0 1 ${r1(r)} ${r1(r)}v${r1(h - r)}z`;
}
export const pathEl = (T, d, role, title) => (d ? `<path d="${d}" ${paint(T, role)}>${title ? `<title>${esc(title)}</title>` : ''}</path>` : '');

// legend: items [{label, role, kind: rect|line|dot|diamond|tick}]
export function legend(T, items, x0, x1, y, { size = 12 } = {}) {
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
export function nice(max, maxTicks = 5) {
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
export function frame(T, chart, W, variant, footer = 'file') {
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
// the 91 most promising builds among its measured demos ("Figure 1c", the substance test). Every other
// figure keeps the number of its chart file.
