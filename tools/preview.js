// Preview a palette on a built page without changing it: inject a :root override, recolour, redraw.
// usage: node tools/preview.js <page.html> <palette.css> <out.png> [tripId] [zoom]
const { chromium } = require('playwright');
const { execFileSync } = require('child_process');
const path = require('path'), fs = require('fs');
const TILES = /(arcgisonline|cyclosm|openstreetmap|opentopomap|geo\.admin|ign\.es|gsi\.go\.jp)/i;

(async () => {
  const [page, css, out, tripId, zf] = process.argv.slice(2);
  const b = await chromium.launch();
  const pg = await b.newPage({ viewport: { width: 1400, height: 900 }, deviceScaleFactor: 2 });
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
  await pg.waitForTimeout(1400);
  await pg.addStyleTag({ content: fs.readFileSync(css, 'utf8') });
  await pg.evaluate(() => { recolour(); });
  if (tripId) { await pg.evaluate(id => { var t = (TRIPS || []).filter(x => x.id === id)[0]; if (t) loadTrip(t); }, tripId); await pg.waitForTimeout(900); }
  await pg.evaluate(() => { var s = document.getElementById('basemap'); if (s) { s.value = 'plain'; s.dispatchEvent(new Event('change')); } });
  await pg.waitForTimeout(900);
  await pg.evaluate(() => { render(); });
  if (zf) { await pg.evaluate(f => setVB([vb[0] + vb[2] * (1 - 1 / f) / 2, vb[1] + vb[3] * (1 - 1 / f) / 2, vb[2] / f, vb[3] / f]), +zf); }
  await pg.waitForTimeout(3000);
  await pg.screenshot({ path: out });
  await b.close();
  console.log('wrote', out);
})();
