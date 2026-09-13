"""Step 6 — name every unnamed split candidate (would otherwise show as 'km478') after the nearest
settlement, with Nominatim reverse geocoding (1 request/s, cached in rev_cache.json). --moped / --signed for the moped or signed-route lines.
The name is the smallest named place around the point (town, village, hamlet, quarter, suburb), with the municipality in
brackets when it differs — "Kitakatamachi-Nagai (Nobeoka)" rather than plain "Nobeoka" for a spot 18 km outside the town.
The cache keeps the whole Nominatim address, so the rule can change without re-querying; old string entries are used as they are."""
import os, sys, re, time, urllib.request, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
cfg, W = load_cfg(); LAYER = 'signed' if '--signed' in sys.argv else 'moped'; moped = '--moped' in sys.argv or '--signed' in sys.argv; pj = Proj(jload(W, 'proj.json'))
cache = jload(W, 'rev_cache.json', {})
SMALL = ['town', 'village', 'hamlet', 'quarter', 'suburb', 'neighbourhood']
BIG = ['city', 'municipality', 'town']          # the county is never worth the brackets
LATIN = re.compile(r'[A-Za-z]')
if cfg['lang'].get('romanise') == 'pykakasi':
    import pykakasi; kk = pykakasi.kakasi()
    def romanise(s):
        out = ' '.join(x['hepburn'] for x in kk.convert(s)); out = re.sub(r'\s+', ' ', out).strip()
        words = [w for w in out.split(' ') if w.lower() not in ('ji', 'aza', 'ooaza', 'oaza')]     # 字 / 大字 are address levels, not names
        return ' '.join(w[:1].upper() + w[1:] for w in words)
else:
    def romanise(s): return s
def place_label(a):
    """Label from a Nominatim address dict: smallest place, municipality in brackets when it adds something."""
    small = next((a[x] for x in SMALL if x in a), '')
    big = next((a[x] for x in BIG if x in a and a[x] != small), '')
    if small and not LATIN.search(small): small = romanise(small)
    if not small: return big or a.get('county', '')
    if not big or big.lower() in small.lower() or small.lower() in big.lower(): return small
    return '%s (%s)' % (small, big)
def rev(lat, lon):
    k = '%.3f,%.3f' % (lat, lon)
    if k in cache: return cache[k] if isinstance(cache[k], str) else place_label(cache[k])
    url = 'https://nominatim.openstreetmap.org/reverse?' + urllib.parse.urlencode(dict(lat=lat, lon=lon, format='jsonv2', zoom=14, **{'accept-language': 'en'}))
    a = None
    for attempt in range(3):
        try:
            a = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20)).get('address', {})
            a = {x: a[x] for x in SMALL + BIG if x in a}; break
        except Exception as e:
            print('fail', k, e); time.sleep(6)          # 429 = too fast for Nominatim; wait and try again
    time.sleep(1.3)
    if a is None: return ''
    cache[k] = a; jdump(W, 'rev_cache.json', cache)
    return place_label(a)
if moped: MS = jload(W, LAYER + '_segments.json'); segs = list(MS.values())
else: P = jload(W, 'P.json'); segs = P['segments']
n = 0; redo = '--all' in sys.argv
for s in segs:
    for c in s.get('cand', []):
        if c['node'] or (c['label'] and not redo): continue
        c['label'] = rev(*pj.ll(c['x'], c['y'])); n += 1
        if n % 20 == 0:
            jdump(W, LAYER + '_segments.json', MS) if moped else jdump(W, 'P.json', P)
if moped: jdump(W, LAYER + '_segments.json', MS)
else: jdump(W, 'P.json', P)
print('named', n, 'candidates')
