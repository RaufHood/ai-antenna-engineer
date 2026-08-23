const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
  const consoleErrors = [], pageErrors = [], failed = [], badResponses = [];
  page.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') consoleErrors.push(m.type()+': '+m.text()); });
  page.on('pageerror', e => pageErrors.push(String(e)));
  page.on('requestfailed', r => failed.push(r.url() + ' :: ' + (r.failure() && r.failure().errorText)));
  page.on('response', r => { if (r.status() >= 400) badResponses.push(r.status() + ' ' + r.url()); });
  await page.goto('http://localhost:3000', { waitUntil: 'networkidle', timeout: 60000 });
  await page.waitForTimeout(6000);

  const info = await page.evaluate(() => {
    const bodyBg = getComputedStyle(document.body).backgroundColor;
    const htmlBg = getComputedStyle(document.documentElement).backgroundColor;
    const sheets = Array.from(document.querySelectorAll('link[rel=stylesheet]')).map(l => l.href);
    const rules = Array.from(document.styleSheets).reduce((n,s)=>{ try { return n + s.cssRules.length } catch(e) { return n } }, 0);
    const text = document.body.innerText;
    return { bodyBg, htmlBg, sheets, rules, text };
  });

  console.log('=== BODY BG ===', info.bodyBg, '| html:', info.htmlBg);
  console.log('=== STYLESHEETS ===', JSON.stringify(info.sheets), 'cssRules:', info.rules);
  console.log('=== PAGE TEXT ===');
  console.log(info.text);
  console.log('=== CONSOLE (errors/warnings) ===');
  console.log(consoleErrors.join('\n') || '(none)');
  console.log('=== PAGE ERRORS ===');
  console.log(pageErrors.join('\n') || '(none)');
  console.log('=== FAILED REQUESTS ===');
  console.log(failed.join('\n') || '(none)');
  console.log('=== HTTP >=400 ===');
  console.log(badResponses.join('\n') || '(none)');
  await page.screenshot({ path: process.argv[2] || '/tmp/shot.png', fullPage: false });
  await browser.close();
})();
