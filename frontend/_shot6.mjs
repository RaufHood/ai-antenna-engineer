import { chromium } from 'playwright';
const b=await chromium.launch({channel:'chrome'});
const p=await b.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:1});
await p.goto('file:///Users/damiavicensramis/Desktop/Exec-docs/kevin-pitch/index.html',{waitUntil:'networkidle'});
await p.waitForTimeout(1200);
for(let i=0;i<5;i++){ await p.keyboard.press('ArrowRight'); await p.waitForTimeout(400); }
await p.waitForTimeout(4500);   // let the sweep finish
await p.screenshot({path:'/private/tmp/claude-501/-Users-damiavicensramis-Desktop-Exec-docs/c440f1b2-ccd3-4710-8d11-72373cb52895/scratchpad/s6-final.png'});
const n=await p.evaluate(()=>{
  const w=document.querySelector('.slide:nth-of-type(6) .s11 .win');
  return { winner: !!w, offset: w && getComputedStyle(w).strokeDashoffset, cands: document.querySelectorAll('.slide:nth-of-type(6) .s11 .cand').length };
});
console.log(JSON.stringify(n));
await b.close();
