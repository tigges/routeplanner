"""Step 8 (vehicle) — per segment, the share of the bicycle line on ways a moped may not use (cycleway, footway,
path, pedestrian, steps, or motor_vehicle/moped=no). Nearest way within 60 m of each 250 m vertex wins.
Writes motorfree.json {segid: {share, km_blocked, km}}."""
import os, sys, math
import numpy as np, osmium
from scipy.spatial import cKDTree
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
cfg, W = load_cfg(); SEGDIR = os.path.join(W, 'segments'); segs = {}
for fn in sorted(os.listdir(SEGDIR)):
    g = json.load(open(os.path.join(SEGDIR, fn))); segs[seg_id(fn)] = densify([(c[1], c[0]) for c in g['geometry']['coordinates']], 0.25)
lats, lons, meta = [], [], []
for sid, pts in segs.items():
    for i, (la, lo) in enumerate(pts): lats.append(la); lons.append(lo); meta.append((sid, i))
lat0 = float(np.mean(lats)); k = math.pi*R/180
def proj(lat, lon): return np.column_stack([np.asarray(lon)*k*math.cos(math.radians(lat0)), np.asarray(lat)*k])
tree = cKDTree(proj(np.array(lats), np.array(lons))); bbox = (min(lats)-0.05, min(lons)-0.05, max(lats)+0.05, max(lons)+0.05)
nv = len(meta); blocked = np.zeros(nv, dtype=np.int8); dist = np.full(nv, 9e9)
NOMOTOR = {'cycleway', 'footway', 'path', 'pedestrian', 'steps', 'bridleway', 'corridor'}
ROADS = {'motorway', 'motorway_link', 'trunk', 'trunk_link', 'primary', 'primary_link', 'secondary', 'secondary_link', 'tertiary', 'tertiary_link',
         'unclassified', 'residential', 'living_street', 'service', 'track', 'road'}
for pbf in cfg['osm']['extracts']:
    if not os.path.exists(pbf): continue
    print('scan', os.path.basename(pbf), flush=True)
    for o in osmium.FileProcessor(pbf, osmium.osm.NODE | osmium.osm.WAY).with_locations().with_filter(osmium.filter.EntityFilter(osmium.osm.WAY)).with_filter(osmium.filter.KeyFilter('highway')):
        t = o.tags; hw = t.get('highway')
        if hw in ROADS: nb = t.get('motor_vehicle') == 'no' or t.get('moped') == 'no' or t.get('motorcycle') == 'no' or (t.get('access') == 'no' and t.get('bicycle') in ('yes', 'designated'))
        elif hw in NOMOTOR: nb = not (t.get('moped') in ('yes', 'designated') or t.get('motor_vehicle') == 'yes')
        else: continue
        pts = [(nd.location.lat, nd.location.lon) for nd in o.nodes if nd.location.valid()]
        if not pts: continue
        la, lo = pts[0]
        if not (bbox[0] <= la <= bbox[2] and bbox[1] <= lo <= bbox[3]): continue
        for la, lo in pts[::2] if len(pts) > 40 else pts:
            xy = proj(np.array([la]), np.array([lo]))[0]
            for i in tree.query_ball_point(xy, 0.06):
                d = float(np.hypot(*(tree.data[i]-xy)))
                if d < dist[i]: dist[i] = d; blocked[i] = 1 if nb else 0
out = {}
for sid, pts in segs.items():
    idxs = [i for i, (s, _) in enumerate(meta) if s == sid]; km = sum(hav(a, b) for a, b in zip(pts, pts[1:])) or 1; sh = float(blocked[idxs].mean())
    out[sid] = dict(km=round(km, 1), share=round(sh, 3), km_blocked=round(sh*km, 1))
jdump(W, 'motorfree.json', out)
tot = sum(v['km'] for v in out.values()); bl = sum(v['km_blocked'] for v in out.values())
print('total %.0f km, on motor-free ways %.0f km (%.1f%%)' % (tot, bl, bl/tot*100))
for sid, v in sorted(out.items(), key=lambda kv: -kv[1]['km_blocked'])[:20]: print('%-36s %5.1f km of %6.1f  (%3.0f%%)' % (sid, v['km_blocked'], v['km'], v['share']*100))
