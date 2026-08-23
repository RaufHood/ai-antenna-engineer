import { chromium } from 'playwright';
const b=await chromium.launch({channel:'chrome'});
const OUT='/private/tmp/claude-501/-Users-damiavicensramis-Desktop-Exec-docs/c440f1b2-ccd3-4710-8d11-72373cb52895/scratchpad/';
async function test(name, mutate){
  const p=await b.newPage();
  await p.goto('file:///Users/damiavicensramis/Desktop/Exec-docs/kevin-pitch/index.html',{waitUntil:'networkidle'});
  await p.evaluate(mutate);
  await p.emulateMedia({media:'print'});
  await p.waitForTimeout(1500);
  await p.pdf({path:OUT+name+'.pdf',width:'1920px',height:'1080px',printBackground:true});
  const sz=(await import('fs')).statSync(OUT+name+'.pdf').size;
  console.log(name, Math.round(sz/1024)+'KB');
  await p.close();
}
// A: only slide 5 in the document
await test('isoA', ()=>{ document.querySelectorAll('.slide').forEach((s,i)=>{ if(i!==4) s.remove(); }); });
// B: whole deck, but slide 5's figure image swapped for a plain block
await test('isoB', ()=>{ const f=document.querySelectorAll('.slide')[4].querySelector('.figure'); f.style.flex='none'; f.style.height='560px'; });
// C: whole deck, slide 5's grid turned into flex
await test('isoC', ()=>{ const g=document.querySelectorAll('.slide')[4].querySelector('.slide-body > div:last-child'); g.style.display='flex'; });
await b.close();
