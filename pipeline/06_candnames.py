"""Step 6 — name every unnamed split candidate (would otherwise show as 'km478') after the nearest
settlement, with Nominatim reverse geocoding (1 request/s, cached in rev_cache.json). --moped / --signed for the moped or signed-route lines."""
import os, sys, time, urllib.request, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
cfg, W = load_cfg(); LAYER = 'signed' if '--signed' in sys.argv else 'moped'; moped = '--moped' in sys.argv or '--signed' in sys.argv; pj = Proj(jload(W, 'proj.json'))
cache = jload(W, 'rev_cache.json', {})
KEYS = ['city', 'town', 'village', 'hamlet', 'suburb', 'municipality', 'city_district', 'county']
def rev(lat, lon):
    k = '%.3f,%.3f' % (lat, lon)
    if k in cache: return cache[k]
    url = 'https://nominatim.openstreetmap.org/reverse?' + urllib.parse.urlencode(dict(lat=lat, lon=lon, format='jsonv2', zoom=12, **{'accept-language': 'en'}))
    try:
        a = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20)).get('address', {})
        name = next((a[x] for x in KEYS if x in a), '')
    except Exception as e:
        print('fail', k, e); name = None
    time.sleep(1.1)
    if name is not None: cache[k] = name; jdump(W, 'rev_cache.json', cache)
    return name or ''
if moped: MS = jload(W, LAYER + '_segments.json'); segs = list(MS.values())
else: P = jload(W, 'P.json'); segs = P['segments']
n = 0
for s in segs:
    for c in s.get('cand', []):
        if c['node'] or c['label']: continue
        c['label'] = rev(*pj.ll(c['x'], c['y'])); n += 1
        if n % 20 == 0:
            jdump(W, LAYER + '_segments.json', MS) if moped else jdump(W, 'P.json', P)
if moped: jdump(W, LAYER + '_segments.json', MS)
else: jdump(W, 'P.json', P)
print('named', n, 'candidates')
