// node tools/smoke.js work/<slug>/planner.html — loads the built page headless and prints the default journey
const { chromium } = require('playwright');
(async()=>{ const b=await chromium.launch(); const p=await b.newPage({viewport:{width:1400,height:900}});
 p.on('pageerror',e=>console.log('PAGEERROR',e.message));
 await p.goto('file://'+require('path').resolve(process.argv[2])); await p.waitForTimeout(1500);
 console.log(await p.evaluate(()=>[document.getElementById('sd').textContent+' days', document.getElementById('sk').textContent+' km', document.getElementById('sa').textContent+' m']));
 console.log(await p.$$eval('#days .day', els=>els.slice(0,8).map(e=>e.innerText.split('\n').slice(1,3).join(' | '))));
 await p.screenshot({path: process.argv[2].replace(/\.html$/,'.png')}); await b.close(); })();
