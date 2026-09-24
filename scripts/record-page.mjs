#!/usr/bin/env node
// Record a short scrolling video of report/site/index.html for social posts:
// a 1080x1350 (4:5) cut for X and a 1200x676 (16:9) cut for the LinkedIn feed.
//
//   node scripts/record-page.mjs                  both cuts
//   node scripts/record-page.mjs --only x         one cut: x | linkedin
//   node scripts/record-page.mjs --order listed   visit the stops in the order STOPS lists them
//                                                 (default "page": top to bottom, never scrolls up)
//   --input <html>  --out <dir>                   defaults: report/site/index.html, report/site/video
//
// How the cut is made: Playwright's recordVideo (VP8 webm, 25 fps) records the whole session,
// page load included. When the page is loaded and its fonts are ready, it shows a black sync
// frame for 0.4 s, then sits still for 1.2 s so the encoder can sharpen the title. ffmpeg
// blackdetect finds the sync frame in the webm; the MP4 (H.264, yuv420p) starts from there
// plus that measured gap and ends on the last frame of the choreography. The raw webm is kept
// beside the MP4.
//
// Needs: the playwright devDependency with its Chromium (pnpm exec playwright install chromium),
// and ffmpeg on PATH for the MP4 step. Without ffmpeg only the raw webm is written.

import { chromium } from 'playwright';
import { spawnSync } from 'node:child_process';
import { access, mkdir, mkdtemp, rm, stat } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

const VARIANTS = {
  x: { file: 'jev-week-x-1080x1350', width: 1080, height: 1350 },
  // H.264 with yuv420p needs even dimensions, so the 1200x675 feed size is recorded as 1200x676.
  linkedin: { file: 'jev-week-linkedin-1200x676', width: 1200, height: 676 },
};

// The stops, in the order the brief lists them. Each `find` entry is tried in turn and the
// first hit wins: `chart` is the chart's file slug in its SVG download links, `heading` is a
// case-insensitive regex on heading text, `id` is an element id.
const STOPS = [
  { key: 'title', kind: 'top', hold: 2.0 },
  { key: 'waffle', kind: 'chart', hold: 2.7,
    find: [{ chart: '01-week-in-one-picture' }, { heading: 'week in one picture' }, { id: 'figure-1' }] },
  { key: 'attention curve', kind: 'chart', hold: 2.7,
    find: [{ chart: '02-attention-concentration' }, { heading: 'half the views' }, { id: 'figure-2' }] },
  { key: 'baseline bars', kind: 'chart', hold: 2.7,
    find: [{ chart: '03-what-they-compared-against' }, { heading: 'compared? against' }, { id: 'figure-3' }] },
  { key: 'centrepiece', kind: 'chart', hold: 4.0, optional: true,
    find: [{ heading: 'what would have done the job before' }, { chart: '12-what-would-have-done-the-job' }] },
  { key: 'audit heading', kind: 'heading', hold: 2.0,
    find: [{ id: 'audit' }, { heading: 'checking my own numbers' }] },
];

const FPS = 25; // Playwright records at 25 fps; the MP4 keeps it rather than inventing frames.
const SYNC_MS = 400; // how long the black sync frame shows
const SETTLE_MS = 1200; // still time between the sync frame and the first frame of the cut
const TARGET_SECONDS = [20, 24];

// Slow for short hops, capped so the long run down to the audit stays a quick glide.
const scrollSeconds = (distance) => clamp(0.7 + distance / 3000, 1.0, 2.2);

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const rel = (p) => (p === ROOT || p.startsWith(ROOT + path.sep) ? path.relative(ROOT, p) || '.' : p);
const log = (...args) => console.log(...args);
const warn = (msg) => console.warn(`  warning: ${msg}`);

function usage() {
  log('usage: node scripts/record-page.mjs [--only x|linkedin] [--order page|listed] [--input <html>] [--out <dir>]');
}

function parseArgs(argv) {
  const opts = {
    only: null,
    order: 'page',
    input: path.join(ROOT, 'report/site/index.html'),
    out: path.join(ROOT, 'report/site/video'),
  };
  for (let i = 0; i < argv.length; i++) {
    let [flag, value] = argv[i].split(/=(.*)/s, 2);
    const take = () => {
      if (value === undefined) value = argv[++i];
      if (value === undefined) throw new Error(`${flag} needs a value`);
      return value;
    };
    if (flag === '--only') opts.only = take();
    else if (flag === '--order') opts.order = take();
    else if (flag === '--input') opts.input = path.resolve(take());
    else if (flag === '--out') opts.out = path.resolve(take());
    else if (flag === '-h' || flag === '--help') { usage(); process.exit(0); }
    else throw new Error(`unknown argument: ${argv[i]}`);
  }
  if (opts.only && !VARIANTS[opts.only]) throw new Error(`--only must be one of: ${Object.keys(VARIANTS).join(', ')}`);
  if (!['page', 'listed'].includes(opts.order)) throw new Error('--order must be page or listed');
  return opts;
}

// Runs in the page. Finds each stop and returns its geometry in document coordinates.
function measurePage(stops) {
  const docTop = (el) => el.getBoundingClientRect().top + window.scrollY;
  const shown = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const headings = [...document.querySelectorAll('h1, h2, h3')];
  const sections = [...document.querySelectorAll('section')];
  const locate = (f) => {
    if (f.id) {
      const el = document.getElementById(f.id);
      return el ? { section: el.closest('section') ?? el, heading: null } : null;
    }
    if (f.chart) {
      const section = sections.find((s) => s.querySelector(
        `a[href*="${f.chart}"], img[src*="${f.chart}"], object[data*="${f.chart}"]`));
      return section ? { section, heading: null } : null;
    }
    if (f.heading) {
      const re = new RegExp(f.heading, 'i');
      const heading = headings.find((h) => re.test(h.textContent));
      return heading ? { section: heading.closest('section') ?? heading.parentElement, heading } : null;
    }
    return null;
  };
  const out = { docHeight: document.documentElement.scrollHeight, title: document.title, stops: {} };
  for (const stop of stops) {
    for (const f of stop.find ?? []) {
      const hit = locate(f);
      if (!hit) continue;
      const { section } = hit;
      const heading = hit.heading ?? section.querySelector('h1, h2, h3');
      const eyebrow = section.querySelector('.eyebrow, .kicker');
      const anchors = [heading, eyebrow].filter((el) => el && shown(el)).map(docTop);
      const chart = [...section.querySelectorAll('figure svg, figure img, figure canvas')].find(shown)
        ?? [...section.querySelectorAll('svg, img, canvas')].find((el) => shown(el) && el.getBoundingClientRect().height > 120);
      const top = docTop(section);
      out.stops[stop.key] = {
        via: Object.entries(f).map(([k, v]) => `${k}: ${v}`).join(''),
        headingText: heading?.textContent.trim().replace(/\s+/g, ' ') ?? '',
        anchorTop: anchors.length ? Math.min(...anchors) : top,
        chartTop: chart ? docTop(chart) : null,
        chartBottom: chart ? docTop(chart) + chart.getBoundingClientRect().height : null,
      };
      break;
    }
  }
  return out;
}

// Where the viewport sits for a stop: `from` on arrival, `to` at the end of its hold.
// They differ only when a chart is taller than the frame; then the hold pans down it.
function frameStop(stop, m, vh, maxY) {
  const y = (v) => Math.round(clamp(v, 0, maxY));
  if (stop.kind === 'heading' || m.chartTop == null) {
    if (stop.kind === 'chart') warn(`no chart found for the ${stop.key}; framing its heading instead`);
    const at = y(m.anchorTop - 0.07 * vh);
    return { from: at, to: at, framing: 'heading near the top' };
  }
  const margin = Math.round(0.035 * vh);
  const blockTop = m.anchorTop - margin;
  const blockBottom = m.chartBottom + margin;
  if (blockBottom - blockTop <= vh) {
    const at = y((blockTop + blockBottom) / 2 - vh / 2);
    return { from: at, to: at, framing: 'heading and chart, centred' };
  }
  if (m.chartBottom - m.chartTop <= vh) {
    const at = y((m.chartTop + m.chartBottom) / 2 - vh / 2);
    return { from: at, to: at, framing: 'chart centred' };
  }
  return { from: y(m.chartTop - margin), to: y(m.chartBottom + margin - vh), framing: 'chart taller than frame: pan down it' };
}

function planStops(measured, vh, order) {
  const maxY = Math.max(0, measured.docHeight - vh);
  const planned = [];
  for (const stop of STOPS) {
    if (stop.kind === 'top') { planned.push({ ...stop, from: 0, to: 0, framing: 'top of page', via: 'scroll 0' }); continue; }
    const m = measured.stops[stop.key];
    if (!m) {
      const tried = stop.find.map((f) => Object.entries(f).map(([k, v]) => `${k}: ${v}`).join('')).join('; ');
      if (stop.optional) { log(`  skip: ${stop.key} is not on the page (tried ${tried})`); continue; }
      throw new Error(`could not find the ${stop.key} on the page (tried ${tried})`);
    }
    planned.push({ ...stop, ...frameStop(stop, m, vh, maxY), via: m.via, headingText: m.headingText });
  }
  if (order === 'page') {
    // Title first and audit last, as briefed; the charts in between go top to bottom.
    const [first, ...rest] = planned;
    const last = rest.pop();
    rest.sort((a, b) => a.from - b.from);
    return [first, ...rest, last];
  }
  return planned;
}

// Installed in the page: eased scroll to `to` over `ms`, resolved when it lands.
function installGlide() {
  window.__recordGlide = (to, ms) => new Promise((resolve) => {
    const from = window.scrollY;
    const t0 = performance.now();
    const ease = (t) => -(Math.cos(Math.PI * t) - 1) / 2; // ease-in-out sine: no jolt at either end
    const step = (now) => {
      const p = Math.min(1, (now - t0) / ms);
      window.scrollTo({ top: from + (to - from) * ease(p), behavior: 'instant' });
      if (p < 1) requestAnimationFrame(step);
      else resolve(window.scrollY);
    };
    requestAnimationFrame(step);
  });
}

async function showSyncFrame(ms) {
  const frame = () => new Promise((resolve) => requestAnimationFrame(() => resolve()));
  const cover = document.createElement('div');
  cover.style.cssText = 'position:fixed;inset:0;background:#000;z-index:2147483647';
  document.body.appendChild(cover);
  await frame(); await frame();
  await new Promise((resolve) => setTimeout(resolve, ms));
  cover.remove();
  await frame();
  return Date.now();
}

async function record(browser, variant, opts) {
  const { width, height } = variant;
  const tmpDir = await mkdtemp(path.join(os.tmpdir(), 'record-page-'));
  const context = await browser.newContext({
    viewport: { width, height },
    deviceScaleFactor: 1,
    colorScheme: 'light',
    reducedMotion: 'no-preference',
    recordVideo: { dir: tmpDir, size: { width, height } },
  });
  try {
    const tPageCreated = Date.now();
    const page = await context.newPage();
    page.on('pageerror', (err) => warn(`page error: ${err.message}`));
    await page.goto(pathToFileURL(opts.input).href, { waitUntil: 'load' });

    // Light theme even if the page later honours a stored or system preference, no scrollbar,
    // and no CSS smooth scrolling fighting the scripted scroll.
    await page.evaluate(() => { document.documentElement.dataset.theme = 'light'; });
    await page.addStyleTag({ content: 'html{scroll-behavior:auto!important;scrollbar-width:none}::-webkit-scrollbar{display:none}' });
    const fonts = await page.evaluate(async () => {
      await document.fonts.ready;
      await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      const faces = [...document.fonts];
      const loaded = [...new Set(faces.filter((f) => f.status === 'loaded').map((f) => `${f.family.replace(/["']/g, '')} ${f.weight}`))];
      const failed = [...new Set(faces.filter((f) => f.status === 'error').map((f) => `${f.family.replace(/["']/g, '')} ${f.weight}`))];
      return { loaded, failed };
    });
    if (!fonts.loaded.length) warn('no web fonts loaded (offline?); the video uses fallback fonts');
    if (fonts.failed.length) warn(`fonts failed to load: ${fonts.failed.join(', ')}`);

    const measured = await page.evaluate(measurePage, STOPS);
    const planned = planStops(measured, height, opts.order);
    await page.evaluate(installGlide);
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));

    const tSyncEnd = await page.evaluate(showSyncFrame, SYNC_MS);
    await sleep(SETTLE_MS);

    const tStart = Date.now();
    const timeline = [];
    let y = 0;
    for (const [i, s] of planned.entries()) {
      const scroll = i > 0 && s.from !== y ? scrollSeconds(Math.abs(s.from - y)) : 0;
      if (scroll) await page.evaluate(([to, ms]) => window.__recordGlide(to, ms), [s.from, scroll * 1000]);
      const at = (Date.now() - tStart) / 1000;
      if (s.to !== s.from) await page.evaluate(([to, ms]) => window.__recordGlide(to, ms), [s.to, s.hold * 1000]);
      else await sleep(s.hold * 1000);
      timeline.push({ ...s, scroll, at });
      y = s.to;
    }
    const tEnd = Date.now();

    const video = page.video();
    await context.close();
    const raw = path.join(opts.out, `${variant.file}.raw.webm`);
    await video.saveAs(raw);
    await video.delete();
    return {
      raw, timeline, fonts, title: measured.title,
      cutSeconds: (tEnd - tStart) / 1000,
      startAfterSync: (tStart - tSyncEnd) / 1000,
      syncEndGuess: (tSyncEnd - tPageCreated) / 1000,
    };
  } finally {
    await context.close().catch(() => {});
    await rm(tmpDir, { recursive: true, force: true });
  }
}

function run(cmd, args) {
  const r = spawnSync(cmd, args, { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
  if (r.error) throw r.error;
  return r;
}

const hasTool = (cmd) => !spawnSync(cmd, ['-version'], { stdio: 'ignore' }).error;

function probe(file) {
  const r = run('ffprobe', ['-v', 'error', '-select_streams', 'v:0',
    '-show_entries', 'stream=codec_name,profile,pix_fmt,width,height,avg_frame_rate:format=duration',
    '-of', 'json', file]);
  const j = JSON.parse(r.stdout);
  const s = j.streams?.[0] ?? {};
  return { ...s, duration: Number(j.format?.duration ?? NaN) };
}

// The sync frame is the only fully black stretch; take the one nearest where the clock says it ended.
function findSyncEnd(raw, guess) {
  const r = run('ffmpeg', ['-hide_banner', '-nostats', '-i', raw, '-vf', 'blackdetect=d=0.2:pix_th=0.10', '-an', '-f', 'null', '-']);
  const ends = [...r.stderr.matchAll(/black_end:\s*([\d.]+)/g)].map((m) => Number(m[1]));
  if (!ends.length) throw new Error('could not find the black sync frame in the raw webm');
  const best = ends.reduce((a, b) => (Math.abs(b - guess) < Math.abs(a - guess) ? b : a));
  if (Math.abs(best - guess) > 1.5) warn(`sync frame found at ${best.toFixed(2)} s, expected near ${guess.toFixed(2)} s`);
  return best;
}

function encodeMp4(raw, mp4, start, seconds, title) {
  const r = run('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y',
    '-ss', start.toFixed(3), '-i', raw, '-t', seconds.toFixed(3),
    '-map', '0:v:0', '-an',
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '18', '-profile:v', 'high', '-pix_fmt', 'yuv420p',
    '-r', String(FPS), '-movflags', '+faststart',
    '-metadata', `title=${title}`,
    mp4]);
  if (r.status !== 0) throw new Error(`ffmpeg failed to write ${rel(mp4)}:\n${r.stderr}`);
}

const mb = async (file) => `${((await stat(file)).size / 1e6).toFixed(1)} MB`;

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  await access(opts.input).catch(() => { throw new Error(`input not found: ${opts.input}`); });
  await mkdir(opts.out, { recursive: true });
  const ffmpeg = hasTool('ffmpeg') && hasTool('ffprobe');
  if (!ffmpeg) warn('ffmpeg/ffprobe not found on PATH: writing the raw webm only (it includes the page load and the sync frame)');

  const names = opts.only ? [opts.only] : Object.keys(VARIANTS);
  const browser = await chromium.launch();
  let failed = false;
  try {
    for (const name of names) {
      const variant = VARIANTS[name];
      log(`\n${name}: ${variant.width}x${variant.height} from ${rel(opts.input)} (order: ${opts.order})`);
      try {
        const rec = await record(browser, variant, opts);
        for (const s of rec.timeline) {
          const move = s.scroll ? `scroll ${s.scroll.toFixed(1)} s, ` : '';
          const pan = s.to !== s.from ? ` -> ${s.to}` : '';
          log(`  ${s.at.toFixed(1).padStart(5)} s  ${s.key.padEnd(15)} ${move}hold ${s.hold.toFixed(1)} s  y ${s.from}${pan}  [${s.framing}; ${s.via}]`);
        }
        log(`  cut length ${rec.cutSeconds.toFixed(1)} s`);
        if (rec.cutSeconds < TARGET_SECONDS[0] || rec.cutSeconds > TARGET_SECONDS[1]) {
          warn(`cut is ${rec.cutSeconds.toFixed(1)} s, outside the ${TARGET_SECONDS.join(' to ')} s target`);
        }
        log(`  raw webm  ${rel(rec.raw)}  ${await mb(rec.raw)}`);
        if (!ffmpeg) continue;
        const syncEnd = findSyncEnd(rec.raw, rec.syncEndGuess);
        const start = syncEnd + rec.startAfterSync;
        const rawInfo = probe(rec.raw);
        if (start + rec.cutSeconds > rawInfo.duration + 0.05) {
          warn(`raw webm ends at ${rawInfo.duration.toFixed(2)} s, before the cut ends at ${(start + rec.cutSeconds).toFixed(2)} s`);
        }
        const mp4 = path.join(opts.out, `${variant.file}.mp4`);
        encodeMp4(rec.raw, mp4, start, rec.cutSeconds, rec.title);
        const info = probe(mp4);
        log(`  mp4       ${rel(mp4)}  ${info.width}x${info.height}  ${info.duration.toFixed(2)} s  ${await mb(mp4)}  ${info.codec_name} ${info.profile} ${info.pix_fmt} ${info.avg_frame_rate} fps  (cut from ${start.toFixed(2)} s of the raw webm)`);
      } catch (err) {
        failed = true;
        console.error(`  ${name} failed: ${err.message}`);
      }
    }
  } finally {
    await browser.close();
  }
  if (failed) process.exitCode = 1;
}

main().catch((err) => {
  console.error(err.message);
  process.exitCode = 1;
});
