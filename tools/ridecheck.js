// node tools/ridecheck.js <before.html> <after.html>
// Opens two builds of the same page headless and prints, for every trip that lives on the page, the km,
// climb, effort, leg count and day count each build gives, with the difference. The test ride to run
// before handing over a change that should not move the numbers. Also reports console/page errors and
// the page weight. Trips a build does not have (a new one, or one whose towns changed) show as "-".
const { chromium } = require('playwright'); const fs = require('fs'), path = require('path');
const read = async (page, file) => {
  const errs = [];
  page.on('pageerror', e => errs.push('PAGEERROR ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errs.push('CONSOLE ' + m.text()); });
  await page.goto('file://' + path.resolve(file));
  await page.waitForTimeout(1800);
  const rows = await page.evaluate(() => {
    const out = {};
    TRIPS.forEach(t => {
      if (!tripHere(t)) return;
      const ch = tripChain(t);
      if (!ch.length) { out[t.id] = null; return; }
      const s = tripStats(t);
      out[t.id] = { name: t.name, km: s.km, asc: s.asc, days: s.days, legs: ch.length,
                    eff: Math.round(ch.reduce((a, v) => a + (v.effort || 0), 0)) };
    });
    return out;
  });
  return { rows, errs, mb: (fs.statSync(file).size / 1048576).toFixed(2) };
};
(async () => {
  const [A, B] = process.argv.slice(2, 4);
  const b = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined });
  const pa = await b.newPage({ viewport: { width: 1400, height: 900 } }); const a = await read(pa, A);
  const pb = await b.newPage({ viewport: { width: 1400, height: 900 } }); const c = await read(pb, B);
  await b.close();
  const ids = [...new Set([...Object.keys(a.rows), ...Object.keys(c.rows)])];
  const f = (r, k) => (r && r[k] != null ? String(r[k]) : '-');
  const pad = (s, n) => String(s).padEnd(n); const rpad = (s, n) => String(s).padStart(n);
  console.log(pad('trip', 16) + rpad('km', 12) + rpad('climb', 14) + rpad('effort', 12) + rpad('days', 9) + rpad('legs', 9));
  let moved = 0;
  for (const id of ids) {
    const x = a.rows[id], y = c.rows[id];
    const cell = k => { const u = f(x, k), v = f(y, k); return u === v ? rpad(u, 0) : u + '→' + v; };
    const same = ['km', 'asc', 'eff', 'days', 'legs'].every(k => f(x, k) === f(y, k));
    if (!same) moved++;
    console.log(pad(id, 16) + rpad(cell('km'), 12) + rpad(cell('asc'), 14) + rpad(cell('eff'), 12) +
                rpad(cell('days'), 9) + rpad(cell('legs'), 9) + (same ? '' : '   *'));
  }
  console.log('\n' + moved + ' of ' + ids.length + ' trips moved.  page ' + a.mb + ' MB → ' + c.mb + ' MB');
  [['before', a], ['after', c]].forEach(([n, r]) => r.errs.forEach(e => console.log(n + ': ' + e)));
  if (!a.errs.length && !c.errs.length) console.log('no console or page errors');
})();
