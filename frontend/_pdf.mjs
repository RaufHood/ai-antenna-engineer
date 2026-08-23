// Chrome's paged renderer silently drops some slides when the whole deck is
// printed as one tall document. Shoot each slide instead and bind the frames.
import { chromium } from 'playwright';
import fs from 'fs';
const OUT='/private/tmp/claude-501/-Users-damiavicensramis-Desktop-Exec-docs/c440f1b2-ccd3-4710-8d11-72373cb52895/scratchpad/pages';
fs.rmSync(OUT,{recursive:true,force:true}); fs.mkdirSync(OUT,{recursive:true});
const b=await chromium.launch({channel:'chrome'});
const p=await b.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:1.5});
await p.goto('file:///Users/damiavicensramis/Desktop/Exec-docs/kevin-pitch/index.html',{waitUntil:'networkidle'});
await p.waitForTimeout(1500);
// presenter chrome lives outside the stage and does not belong in the export
await p.addStyleTag({content:'.deck-controls,.counter{display:none!important}'});
const n=await p.evaluate(()=>document.querySelectorAll('.slide').length);
for(let i=0;i<n;i++){
  if(i>0) await p.keyboard.press('ArrowRight');
  await p.waitForTimeout(4200);              // let every staggered reveal land
  await p.screenshot({path:`${OUT}/p${String(i+1).padStart(2,'0')}.png`});
}
console.log('captured', n, 'slides');
await b.close();
