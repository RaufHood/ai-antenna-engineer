import { chromium } from 'playwright';
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 1000 },
                            deviceScaleFactor: 2 });
const errs = [];
p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
p.on('pageerror', e => errs.push(String(e)));
await p.goto('http://localhost:3000', { waitUntil: 'networkidle' });
await p.waitForTimeout(9000);          // let the 5 MB GLB stream + build edges
await p.screenshot({ path: '/tmp/viewer.png' });
console.log(errs.length ? 'ERRORES:\n' + errs.slice(0,6).join('\n') : 'sin errores de consola');
await b.close();
