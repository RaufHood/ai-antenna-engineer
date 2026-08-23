import { chromium } from 'playwright';
const file='file:///Users/damiavicensramis/Desktop/Exec-docs/kevin-pitch/index.html';
const outDir='/private/tmp/claude-501/-Users-damiavicensramis-Desktop-Exec-docs/c440f1b2-ccd3-4710-8d11-72373cb52895/scratchpad/verify';
const MEDIA=process.env.MEDIA||'screen';
const b=await chromium.launch({channel:'chrome'});
const p=await b.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:1});
const errs=[]; p.on('pageerror',e=>errs.push(String(e).slice(0,200)));
p.on('requestfailed',r=>errs.push('404? '+r.url().slice(-60)));
await p.goto(file,{waitUntil:'networkidle'}); await p.emulateMedia({media:MEDIA}); await p.waitForTimeout(1500);
const n=await p.evaluate(()=>document.querySelectorAll('.slide').length);
console.log('media:',MEDIA,'| slides:',n,'| errors:',errs.length?errs:'none');
let fails=0;
for(let i=0;i<n;i++){
  if(i>0) await p.keyboard.press('ArrowRight');
  if(MEDIA==='print') await p.evaluate(k=>{document.querySelectorAll('.slide').forEach((s,j)=>s.classList.toggle('active',j===k));},i);
  await p.waitForTimeout(950);
  const r=await p.evaluate(idx=>{
    const s=document.querySelectorAll('.slide')[idx],pad=s.querySelector('.pad'),cs=getComputedStyle(pad),pr=pad.getBoundingClientRect();
    const box={l:pr.left+parseFloat(cs.paddingLeft),r:pr.right-parseFloat(cs.paddingRight),t:pr.top+parseFloat(cs.paddingTop),b:pr.bottom-parseFloat(cs.paddingBottom)};
    const out=[]; s.querySelectorAll('.pad *').forEach(el=>{const q=el.getBoundingClientRect(); if(q.width<1||q.height<1)return;
      const w=Math.max(box.l-q.left,q.right-box.r,box.t-q.top,q.bottom-box.b);
      if(w>2) out.push({el:String(el.className).slice(0,28),px:Math.round(w),txt:(el.textContent||'').trim().slice(0,36)});});
    const foot=s.querySelector('.slide-foot'),body=s.querySelector('.slide-body'),clash=[];
    if(foot&&body){const fr=foot.getBoundingClientRect();
      body.querySelectorAll('*').forEach(el=>{const q=el.getBoundingClientRect(); if(q.width<1||q.height<1)return;
        if(q.bottom>fr.top+1) clash.push({el:String(el.className).slice(0,26),px:Math.round(q.bottom-fr.top)});});}
    return {out:out.slice(0,5),outN:out.length,clash:clash.slice(0,3),clashN:clash.length};},i);
  const ok=r.outN===0&&r.clashN===0; if(!ok)fails++;
  console.log(`slide ${i+1}  ${ok?'OK':'ISSUE'}  outside=${r.outN} foot=${r.clashN}`);
  if(r.outN) console.log('   out: ',JSON.stringify(r.out));
  if(r.clashN) console.log('   foot:',JSON.stringify(r.clash));
  if(MEDIA==='screen') await p.screenshot({path:`${outDir}/t${i+1}.png`});
}
console.log(fails?`\n${fails} need work`:'\nall clean');
await b.close();
