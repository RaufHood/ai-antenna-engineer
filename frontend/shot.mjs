import { chromium } from 'playwright';
const [url, out, w=1600, h=1000] = process.argv.slice(2);
const b = await chromium.launch({ channel: 'chrome' });   // usa el Chrome del sistema
const p = await b.newPage({ viewport:{width:+w,height:+h}, deviceScaleFactor:2 });
const errs = [];
p.on('console', m => m.type()==='error' && errs.push(m.text().slice(0,160)));
p.on('pageerror', e => errs.push(String(e).slice(0,160)));
await p.goto(url, { waitUntil:'networkidle' });
await p.waitForTimeout(8000);
await p.screenshot({ path: out });
console.log(errs.length ? 'ERRORES:\n'+[...new Set(errs)].slice(0,5).join('\n') : 'sin errores de consola');
await b.close();
