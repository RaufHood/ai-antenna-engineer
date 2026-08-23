import { chromium } from 'playwright';
const b = await chromium.launch({ channel:'chrome' });
const p = await b.newPage();
await p.goto('file:///Users/damiavicensramis/Desktop/Exec-docs/kevin-pitch/index.html',{waitUntil:'networkidle'});
await p.emulateMedia({ media:'print' });
await p.waitForTimeout(2500);
await p.pdf({ path:'/Users/damiavicensramis/Desktop/Exec-docs/kevin-pitch/kevin-pitch.pdf',
              width:'1920px', height:'1080px', printBackground:true, pageRanges:'1-9' });
console.log('pdf written');
await b.close();
