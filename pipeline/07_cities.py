"""Step 7 (optional) — which sizeable places lie within reach of the lines? Every OSM place=city/town with a
population ≥ config.cities.population_min, distance to the nearest segment. Writes cities_near_route.csv sorted
into detour candidates (≤ detour_km) and rest-day candidates (≤ rest_day_km)."""
import csv, os, sys, math
import numpy as np, osmium
from scipy.spatial import cKDTree
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
cfg, W = load_cfg(); C = cfg.get('cities', {}); P = jload(W, 'P.json'); SEG = {s['id']: s for s in P['segments']}
SEGDIR = os.path.join(W, 'segments'); segs = {}
for fn in sorted(os.listdir(SEGDIR)):
    g = json.load(open(os.path.join(SEGDIR, fn))); segs[seg_id(fn)] = densify([(c[1], c[0]) for c in g['geometry']['coordinates']], 1.0)
lats, lons, meta = [], [], []
for sid, pts in segs.items():
    L = [0.0]
    for a, b in zip(pts, pts[1:]): L.append(L[-1] + hav(a, b))
    for i, (la, lo) in enumerate(pts): lats.append(la); lons.append(lo); meta.append((sid, L[i]))
lat0 = float(np.mean(lats)); k = math.pi*R/180
def proj(lat, lon): return np.column_stack([np.asarray(lon)*k*math.cos(math.radians(lat0)), np.asarray(lat)*k])
tree = cKDTree(proj(np.array(lats), np.array(lons))); rows = []; seen = set()
for pbf in cfg['osm']['extracts']:
    if not os.path.exists(pbf): continue
    print('scan', pbf, flush=True)
    for o in osmium.FileProcessor(pbf, osmium.osm.NODE).with_filter(osmium.filter.KeyFilter('place')):
        t = o.tags
        if t.get('place') not in ('city', 'town'): continue
        try: pop = int(t.get('population', '0').replace(',', ''))
        except ValueError: continue
        if pop < C.get('population_min', 30000): continue
        name = t.get('name:en') or t.get('name')
        if (name, pop) in seen: continue
        seen.add((name, pop)); la, lo = o.location.lat, o.location.lon
        d, i = tree.query(proj(np.array([la]), np.array([lo]))[0])
        if d > C.get('rest_day_km', 80): continue
        sid, km = meta[i]
        rows.append(dict(city=name, local=t.get('name'), population=pop, dist_km=round(d, 1), segment=sid, km_along=round(km, 1),
                         seg_from=SEG[sid]['frm'], seg_to=SEG[sid]['to'], on_line=d <= 3, detour=3 < d <= C.get('detour_km', 25), lat=round(la, 4), lon=round(lo, 4)))
rows.sort(key=lambda r: (r['dist_km'] > C.get('detour_km', 25), -r['population']))
with open(os.path.join(W, 'cities_near_route.csv'), 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print(len(rows), 'places ->', os.path.join(W, 'cities_near_route.csv'))
for r in [r for r in rows if r['detour']][:25]: print('%-18s %8d %5.1f km off  %s @ km %.0f' % (r['city'], r['population'], r['dist_km'], r['segment'], r['km_along']))
