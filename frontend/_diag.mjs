import { chromium } from 'playwright';
const b=await chromium.launch({channel:'chrome'});
const p=await b.newPage({viewport:{width:1920,height:1080}});
await p.goto('file:///Users/damiavicensramis/Desktop/Exec-docs/kevin-pitch/index.html',{waitUntil:'networkidle'});
for (const media of ['screen','print']) {
  await p.emulateMedia({media});
  await p.waitForTimeout(900);
  const r = await p.evaluate(()=>{
    const s=document.querySelectorAll('.slide')[4];
    const pick=(sel)=>{const e=s.querySelector(sel); if(!e) return 'MISSING';
      const q=e.getBoundingClientRect(); const cs=getComputedStyle(e);
      return `${Math.round(q.width)}x${Math.round(q.height)} @${Math.round(q.top)} disp=${cs.display} vis=${cs.visibility} op=${cs.opacity}`;};
    return {

      body:  pick('.slide-body'),
      grid:  pick('.slide-body > div:last-child'),
      motion:pick('.motion'),
      video: pick('.motion video'),
      figure:pick('.figure'),
      img:   pick('.figure img'),
      rows:  pick('.spec-rows'),
    };
  }).catch(e=>String(e));
  console.log(media, JSON.stringify(r,null,1));
}
await b.close();
