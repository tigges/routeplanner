// Test ride: open two builds of a page and compare the computed journeys.
// usage: node tools/ridecheck.js <a.html> <b.html> [tripsFile] [slug]
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const JS = (t) => {
  try {
    var legs = t.legs || [{s:t.s, e:t.e, p:t.p}], ch = [];
    for (var i=0;i<legs.length;i++){ var L=legs[i], c=withPicks(L.p,function(){return chain(L.s,L.e);}); if(!c.length) return {error:'no chain'}; ch=ch.concat(c); }
    var km=0, asc=0, eff=0, pts=0;
    ch.forEach(function(v){ if(v.mode!=='ride') return; km+=v.km; asc+=v.ascent; eff+=v.effort; pts+=v.line.split(' ').length; });
    return {km:Math.round(km*10)/10, asc:Math.round(asc), eff:Math.round(eff), n:ch.length, pts:pts};
  } catch(e) { return {error: String(e)} }
};

(async () => {
  const [aPath, bPath, tripsFile, slug] = process.argv.slice(2);
  const all = tripsFile ? JSON.parse(fs.readFileSync(tripsFile, 'utf8')).trips : null;
  const trips = all && slug ? all.filter(t => t.slug === slug) : all;
  const b = await chromium.launch();
  const out = {};
  for (const [tag, p] of [['A', aPath], ['B', bPath]]) {
    const pg = await b.newPage();
    const errs = [];
    pg.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
    pg.on('pageerror', e => errs.push('pageerror: ' + e.message));
    const t0 = Date.now();
    await pg.goto('file://' + path.resolve(p));
    await pg.waitForTimeout(1200);
    const load = Date.now() - t0;
    const rows = {};
    const list = trips || [];
    if (list.length) {
      for (const t of list) rows[t.id] = await pg.evaluate(JS, { s: t.s, e: t.e, p: t.p, legs: t.legs });
    } else {
      rows['default'] = await pg.evaluate(() => {
        try {
          var ns = P.nodes.filter(n => n.entry);
          var c = chain(ns[0].id, ns[ns.length - 1].id);
          var km = 0, asc = 0, eff = 0, pts = 0;
          c.forEach(v => { if (v.mode !== 'ride') return; km += v.km; asc += v.ascent; eff += v.effort; pts += v.line.split(' ').length; });
          return { km: Math.round(km * 10) / 10, asc: Math.round(asc), eff: Math.round(eff), n: c.length, pts };
        } catch (e) { return { error: String(e) } }
      });
    }
    out[tag] = { rows, errs, load, bytes: fs.statSync(p).size };
    await pg.close();
  }
  await b.close();
  const A = out.A, B = out.B;
  console.log('           %s  ->  %s', aPath, bPath);
  console.log('  size     %s MB -> %s MB   load %d ms -> %d ms',
    (A.bytes / 1e6).toFixed(2), (B.bytes / 1e6).toFixed(2), A.load, B.load);
  let bad = 0;
  for (const k of Object.keys(A.rows)) {
    const a = A.rows[k] || {}, c = B.rows[k] || {};
    const same = a.km === c.km && a.asc === c.asc && a.eff === c.eff && a.n === c.n;
    if (!same) bad++;
    console.log('  ' + k.padEnd(18) + (same ? 'ok   ' : 'CHANGED ') + String(a.km).padStart(7) + ' km ' + String(a.asc).padStart(6) + ' m  effort ' + String(a.eff).padStart(5) + '  ' + String(a.n).padStart(3) + ' legs   points ' + String(a.pts).padStart(6) + ' -> ' + String(c.pts).padStart(6));
    if (!same) console.log('        now', JSON.stringify(c));
  }
  if (A.errs.length) console.log('  console errors (A):', A.errs.slice(0, 5));
  if (B.errs.length) console.log('  console errors (B):', B.errs.slice(0, 5));
  console.log(bad ? '  ** ' + bad + ' journeys changed **' : '  all journeys identical');
})();
