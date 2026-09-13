// Screenshot one page in a list of states. Run it on two builds and compare the images.
// usage: node tools/pixcheck.js <page.html> <out-dir> [tripId]
const { chromium } = require('playwright');
const { execFileSync } = require('child_process');
const path = require('path'), fs = require('fs');

const TILES = /(arcgisonline|cyclosm|openstreetmap|opentopomap|geo\.admin|ign\.es|gsi\.go\.jp)/i;

const STATES = [
  ['01-open', () => { }],
  ['02-trip', (t) => { var x = (TRIPS || []).filter(a => a.id === t)[0]; if (x) loadTrip(x); }],
  ['03-zoom', () => { setVB([vb[0] + vb[2] * .35, vb[1] + vb[3] * .35, vb[2] * .3, vb[3] * .3]); }],
  ['04-layers', () => { document.querySelectorAll('#layers .opt').forEach(b => b.click()); }],
  ['05-opium', () => { var v = document.getElementById('veh'); v.click(); v.click(); }],
  ['06-friend', () => { document.getElementById('friendtog').click(); }],
  ['07-seg', () => { var s = (P.segments || []).filter(x => x.mode === 'ride')[0]; if (s && window.selectSeg) selectSeg(s); }],
  ['08-maplight', () => { var s = document.getElementById('basemap'); if (s) { s.value = 'plain'; s.dispatchEvent(new Event('change')); } }],
  ['09-mapnone', () => { var s = document.getElementById('basemap'); if (s) { s.value = 'none'; s.dispatchEvent(new Event('change')); } }],
  ['10-folds', () => { document.querySelectorAll('.foldhead').forEach(h => h.click()); }],
];

(async () => {
  const [page, outDir, tripId] = process.argv.slice(2);
  fs.mkdirSync(outDir, { recursive: true });
  const b = await chromium.launch();
  const pg = await b.newPage({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 1 });
  const errs = [];
  pg.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  pg.on('pageerror', e => errs.push('pageerror: ' + e.message));
  await pg.route('**/*', async r => {
    const u = r.request().url();
    if (!TILES.test(u)) return r.continue();
    try {
      const buf = execFileSync('curl', ['-s', '-L', '--max-time', '20', u], { maxBuffer: 8e6 });
      if (!buf.length) return r.abort();
      r.fulfill({ status: 200, contentType: u.includes('.png') ? 'image/png' : 'image/jpeg', body: buf });
    } catch (e) { r.abort(); }
  });
  await pg.goto('file://' + path.resolve(page));
  await pg.waitForTimeout(1500);
  for (const [name, fn] of STATES) {
    try { await pg.evaluate(fn, tripId || null); } catch (e) { errs.push(name + ': ' + e.message); }
    await pg.waitForTimeout(name === '03-zoom' ? 2600 : 900);
    await pg.screenshot({ path: path.join(outDir, name + '.png') });
  }
  await b.close();
  fs.writeFileSync(path.join(outDir, 'errors.txt'), errs.join('\n'));
  console.log(path.basename(outDir), errs.length ? 'CONSOLE ERRORS: ' + errs.slice(0, 4).join(' | ') : 'no console errors');
})();
