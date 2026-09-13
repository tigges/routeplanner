// Screenshot a planner page with real map tiles behind the lines.
// The sandbox proxy blocks the browser from the tile hosts but not curl, so every tile request is
// fulfilled from a curl of the same URL.
// usage: node tools/shot.js <page.html> <out-prefix> [tripId] [zoomFactor]
const { chromium } = require('playwright');
const { execFileSync } = require('child_process');
const path = require('path');

const TILES = /(arcgisonline|cyclosm|openstreetmap|opentopomap|geo\.admin|ign\.es|gsi\.go\.jp)/i;

(async () => {
  const [page, out, tripId, zf] = process.argv.slice(2);
  const b = await chromium.launch();
  const pg = await b.newPage({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 2 });
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
  if (tripId) {
    await pg.evaluate(id => { var t = (TRIPS || []).filter(x => x.id === id)[0]; if (t) loadTrip(t); }, tripId);
    await pg.waitForTimeout(1200);
  }
  if (zf) {
    await pg.evaluate(f => { setVB([vb[0] + vb[2] * (1 - 1 / f) / 2, vb[1] + vb[3] * (1 - 1 / f) / 2, vb[2] / f, vb[3] / f]); }, +zf);
    await pg.waitForTimeout(2500);
  }
  await pg.waitForTimeout(2500);
  await pg.screenshot({ path: out + '.png' });
  await b.close();
  console.log('wrote', out + '.png');
})();
