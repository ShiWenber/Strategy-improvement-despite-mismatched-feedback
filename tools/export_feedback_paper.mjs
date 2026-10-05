#!/usr/bin/env node
/**
 * Offline Markdown -> Pandoc HTML/MathML -> Chromium PDF.
 * Run from any directory:
 *   node tools/export_feedback_paper.mjs
 *   node tools/export_feedback_paper.mjs --html-only
 * Optional: --input FILE --output FILE --work-dir DIR --browser EXE
 * Dependencies: Pandoc on PATH; Playwright from NODE_PATH, local node_modules,
 * or the bundled Codex runtime; a local Chrome/Edge/Playwright Chromium.
 * No network resources are loaded. Existing PDFs receive a timestamped backup.
 */
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(scriptDir, '..');
const options = {};
for (let i = 2; i < process.argv.length; i++) {
  const key = process.argv[i];
  if (key === '--html-only') { options.htmlOnly = true; continue; }
  if (!['--input', '--output', '--work-dir', '--browser'].includes(key) || !process.argv[i + 1]) {
    throw new Error(`Unknown or incomplete option: ${key}`);
  }
  options[key.slice(2)] = process.argv[++i];
}
const input = path.resolve(options.input || path.join(repo, 'docs/direct_reciprocity/FEEDBACK_ATTRIBUTION_DRAFT.md'));
const output = path.resolve(options.output || input.replace(/\.md$/i, '.pdf'));
const workDir = path.resolve(options['work-dir'] || path.join(repo, 'tmp/pdfs/feedback_paper'));
const htmlPath = path.join(workDir, 'paper.html');
const cssPath = path.join(repo, 'docs/direct_reciprocity/paper_print.css');
const source = fs.readFileSync(input, 'utf8');
const css = fs.readFileSync(cssPath, 'utf8');
const fragment = execFileSync('pandoc', [input, '--from=markdown+tex_math_single_backslash-implicit_figures', '--to=html5', '--mathml', '--wrap=none'], { encoding: 'utf8', windowsHide: true });
const title = source.match(/^#\s+(.+)$/m)?.[1] || path.basename(input, '.md');
const escapeHtml = text => text.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
const html = `<!doctype html>\n<html lang="zh-CN"><head><meta charset="utf-8"><title>${escapeHtml(title)}</title><base href="${pathToFileURL(path.dirname(input) + path.sep).href}"><style>${css}</style></head><body><main>${fragment}</main></body></html>\n`;
fs.mkdirSync(workDir, { recursive: true });
fs.writeFileSync(htmlPath, html, 'utf8');
if (options.htmlOnly) {
  console.log(JSON.stringify({ html: htmlPath, mathElements: (fragment.match(/<math\b/g) || []).length }, null, 2));
  process.exit(0);
}

const require = createRequire(import.meta.url);
const moduleRoots = [
  ...(process.env.NODE_PATH || '').split(path.delimiter).filter(Boolean),
  path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'),
];
let playwright;
try { playwright = require('playwright'); } catch {
  for (const root of moduleRoots) {
    try { playwright = require(path.join(root, 'playwright')); break; } catch { /* Try the next installed runtime. */ }
  }
}
if (!playwright) throw new Error('Playwright is unavailable; set NODE_PATH to the installed node_modules directory.');
const browserCandidates = [
  options.browser,
  process.env.PAPER_BROWSER,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  playwright.chromium.executablePath(),
].filter(Boolean);
const executablePath = browserCandidates.find(candidate => fs.existsSync(candidate));
if (!executablePath) throw new Error('No local Chromium browser found. Supply --browser EXE.');
const browser = await playwright.chromium.launch({ executablePath, headless: true });
try {
  // Match the printable width (210 - 2 * 17 mm) for preflight layout checks.
  const page = await browser.newPage({ viewport: { width: Math.round(176 * 96 / 25.4), height: 1123 } });
  const remoteRequests = [];
  await page.route(/^https?:/, route => { remoteRequests.push(route.request().url()); return route.abort(); });
  await page.goto(pathToFileURL(htmlPath).href, { waitUntil: 'load' });
  await page.emulateMedia({ media: 'print' });
  const checks = await page.evaluate(async () => {
    // The manuscript keeps prose captions in the paragraph after each image.
    // Group the pair so the image and its caption stay on the same printed page.
    for (const image of [...document.querySelectorAll('main > p > img')]) {
      const paragraph = image.parentElement;
      if (paragraph.children.length !== 1 || paragraph.textContent.trim()) continue;
      const figure = document.createElement('figure');
      paragraph.before(figure);
      figure.append(image);
      const next = paragraph.nextElementSibling;
      if (next?.tagName === 'P' && /^图\s*\d/.test(next.textContent.trim())) {
        const caption = document.createElement('figcaption');
        caption.innerHTML = next.innerHTML;
        figure.append(caption);
        next.remove();
      }
      paragraph.remove();
    }
    // Treat the prose label immediately before a table as a table caption.
    for (const table of document.querySelectorAll('table')) {
      const previous = table.previousElementSibling;
      if (previous?.tagName === 'P' && /^表\s*(?:[A-Z]\s*)?\d/.test(previous.textContent.trim())) {
        const caption = document.createElement('caption');
        caption.innerHTML = previous.innerHTML;
        table.prepend(caption);
        previous.remove();
      }
      table.querySelectorAll('colgroup').forEach(group => group.remove());
    }
    for (const paragraph of document.querySelectorAll('main > p')) {
      if (paragraph.textContent.length < 500) paragraph.classList.add('keep-paragraph');
    }
    await document.fonts.ready;
    await Promise.all([...document.images].map(image => image.decode()));
    const main = document.querySelector('main');
    const width = main.getBoundingClientRect().width;
    const imageInfo = [...document.images].map(image => ({
      source: image.getAttribute('src'),
      width: image.naturalWidth,
      height: image.naturalHeight,
      renderedWidth: image.getBoundingClientRect().width,
      renderedHeight: image.getBoundingClientRect().height,
    }));
    const overflow = [...main.querySelectorAll('p, table, pre, figure, math')]
      .filter(element => element.getBoundingClientRect().width > width + 2)
      .map(element => ({ element: element.tagName, text: element.textContent.slice(0, 120) }));
    return {
      figures: document.querySelectorAll('figure').length,
      images: imageInfo,
      mathElements: document.querySelectorAll('math').length,
      tables: document.querySelectorAll('table').length,
      overflow,
      textLength: main.innerText.length,
    };
  });
  if (remoteRequests.length) throw new Error(`Remote resources requested: ${remoteRequests.join(', ')}`);
  if (checks.images.some(image => !image.width || !image.height)) throw new Error('At least one image failed to load.');
  if (checks.overflow.length) throw new Error(`Content extends beyond page width: ${JSON.stringify(checks.overflow)}`);
  const expectedMath = (fragment.match(/<math\b/g) || []).length;
  if (checks.mathElements !== expectedMath) throw new Error('MathML element count changed during browser rendering.');
  await page.screenshot({ path: path.join(workDir, 'html_preview.png'), fullPage: true });
  const candidate = path.join(workDir, 'candidate.pdf');
  await page.pdf({
    path: candidate,
    format: 'A4',
    printBackground: true,
    preferCSSPageSize: true,
    displayHeaderFooter: true,
    headerTemplate: '<span></span>',
    footerTemplate: '<div style="width:100%;text-align:center;font-family:Arial,sans-serif;font-size:8px;color:#666"><span class="pageNumber"></span></div>',
  });
  let backup = null;
  if (fs.existsSync(output)) {
    const stamp = new Date().toISOString().replaceAll(':', '').replaceAll('.', '').replaceAll('-', '');
    backup = path.join(workDir, `before_${stamp}.pdf`);
    fs.copyFileSync(output, backup, fs.constants.COPYFILE_EXCL);
  }
  fs.mkdirSync(path.dirname(output), { recursive: true });
  fs.copyFileSync(candidate, output);
  const audit = {
    input, output, backup, html: htmlPath,
    sourceSha256: crypto.createHash('sha256').update(source).digest('hex'),
    pdfSha256: crypto.createHash('sha256').update(fs.readFileSync(output)).digest('hex'),
    createdAt: new Date().toISOString(),
    pandocVersion: execFileSync('pandoc', ['--version'], { encoding: 'utf8', windowsHide: true }).split(/\r?\n/)[0],
    browser: browser.version(), executablePath, remoteRequests, ...checks,
  };
  fs.writeFileSync(path.join(workDir, 'export_audit.json'), JSON.stringify(audit, null, 2) + '\n');
  console.log(JSON.stringify(audit, null, 2));
} finally {
  await browser.close();
}
