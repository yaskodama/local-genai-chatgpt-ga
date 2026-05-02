// Headless smoke test driver for the browser-abcl demo pages.
// Spawned by _smoke_test.sh --dynamic.  Inputs come from env vars
// so it stays compatible with bash 3.2.
//   ABCL_CHROME : absolute path to the Chrome/Chromium executable
//   ABCL_BASE   : http base URL of the local server
//   ABCL_WAIT   : ms to keep each page open (default 5000)

import puppeteer from 'puppeteer-core';

const CHROME = process.env.ABCL_CHROME;
const BASE   = process.env.ABCL_BASE   || 'http://localhost:8765';
const WAIT   = Number(process.env.ABCL_WAIT || 5000);

if (!CHROME) {
  console.error('ABCL_CHROME env var is required');
  process.exit(2);
}

const pages = [
  'bounded_buffer.html',
  'philosophers.html',
  'rotate4lines.html',
  'drone_simulator.html',
];

const isBenign = (u) => /\/favicon\.ico(\?|$)/.test(u);

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: true,
  args: ['--no-sandbox'],
});

let pass = 0, fail = 0;
for (const html of pages) {
  const page = await browser.newPage();
  const errs = [];
  page.on('pageerror', (e) => errs.push(String(e)));
  page.on('requestfailed', (req) => {
    if (!isBenign(req.url())) errs.push('reqfail ' + req.url());
  });
  page.on('response', (res) => {
    if (res.status() >= 400 && !isBenign(res.url())) {
      errs.push('HTTP ' + res.status() + ' ' + res.url());
    }
  });
  page.on('console', (msg) => {
    if (msg.type() !== 'error') return;
    const loc = msg.location && msg.location();
    if (loc && loc.url && isBenign(loc.url)) return;
    if (isBenign(msg.text())) return;
    errs.push(msg.text());
  });

  try {
    await page.goto(`${BASE}/${html}`, { waitUntil: 'load', timeout: 10000 });
    await new Promise((r) => setTimeout(r, WAIT));
    const log = await page.evaluate(() => {
      const el = document.querySelector('#log') || document.querySelector('pre, canvas');
      return el ? (el.innerText || el.textContent || '').slice(0, 200) : '';
    });
    if (errs.length === 0) {
      const head = JSON.stringify(log.replace(/\s+/g, ' ').slice(0, 80));
      console.log(`  PASS  ${html}  log=${head}`);
      pass++;
    } else {
      console.log(`  FAIL  ${html}`);
      errs.slice(0, 3).forEach((e) => console.log('        ' + e.split('\n')[0]));
      fail++;
    }
  } catch (e) {
    console.log(`  FAIL  ${html}  load: ${e.message.split('\n')[0]}`);
    fail++;
  }
  await page.close();
}

await browser.close();
console.log(`__DYN__ pass=${pass} fail=${fail}`);
process.exit(fail === 0 ? 0 : 1);
