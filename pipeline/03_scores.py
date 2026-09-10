"""Step 3 — per-segment scores from the OSM extracts: share on designated cycle routes (ncn/rcn/lcn
relations within 300 m), traffic proxy (nearest road class within 150 m), named sights within 2 km.
Incremental: only segments missing from seg_scores.json (pass --all to redo). Also usable for the moped
lines: --segdir <dir> --out <file>."""
import json, math, os, sys, glob
import numpy as np, osmium
from scipy.spatial import cKDTree
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
cfg, W = load_cfg()
SEGDIR = sys.argv[sys.argv.index('--segdir') + 1] if '--segdir' in sys.argv else os.path.join(W, 'segments')
OUT = sys.argv[sys.argv.index('--out') + 1] if '--out' in sys.argv else 'seg_scores.json'
prev = jload(W, OUT, {}) if '--all' not in sys.argv else {}
segs = {}
for fn in sorted(os.listdir(SEGDIR)):
    sid = seg_id(fn)
    if sid in prev: continue
    g = json.load(open(os.path.join(SEGDIR, fn))); segs[sid] = densify([(c[1], c[0]) for c in g['geometry']['coordinates']], 0.25)
if not segs: print('nothing to do'); sys.exit()
lats, lons, meta = [], [], []
for sid, pts in segs.items():
    for i, (la, lo) in enumerate(pts): lats.append(la); lons.append(lo); meta.append((sid, i))
lat0 = float(np.mean(lats)); k = math.pi*R/180
def proj(lat, lon): return np.column_stack([np.asarray(lon)*k*math.cos(math.radians(lat0)), np.asarray(lat)*k])
tree = cKDTree(proj(np.array(lats), np.array(lons)))
bbox = (min(lats)-0.05, min(lons)-0.05, max(lats)+0.05, max(lons)+0.05)
nv = len(meta)
route_mark = np.zeros(nv, dtype=np.int8); road_mark = np.zeros(nv, dtype=np.int8); road_dist = np.full(nv, 9e9)
sights = {sid: [] for sid in segs}
NET = {'ncn': 3, 'rcn': 2, 'lcn': 1}
BUSY = {'motorway': 3, 'motorway_link': 3, 'trunk': 3, 'trunk_link': 3, 'primary': 3, 'primary_link': 3, 'secondary': 2, 'secondary_link': 2}
QUIET = {'tertiary', 'tertiary_link', 'unclassified', 'residential', 'living_street', 'cycleway', 'service', 'track', 'path', 'footway', 'pedestrian'}
SIGHT = {'tourism': {'attraction', 'museum', 'viewpoint', 'artwork', 'gallery', 'zoo', 'aquarium', 'theme_park'},
         'historic': {'castle', 'monument', 'memorial', 'ruins', 'archaeological_site', 'shrine', 'temple', 'church', 'monastery', 'city_gate', 'fort'},
         'natural': {'hot_spring', 'waterfall', 'beach', 'cape', 'volcano', 'peak', 'glacier'}}
seen_sight = set()
def nearest(lat, lon, r):
    xy = proj(np.array([lat]), np.array([lon]))[0]; return tree.query_ball_point(xy, r), xy
for pbf in cfg['osm']['extracts']:
    if not os.path.exists(pbf): print('missing', pbf); continue
    name = os.path.basename(pbf); print('relations', name, flush=True); wayset = {}
    for o in osmium.FileProcessor(pbf, osmium.osm.RELATION).with_filter(osmium.filter.KeyFilter('route')):
        t = o.tags
        if t.get('route') != 'bicycle': continue
        lvl = NET.get(t.get('network', ''), 1)
        for m in o.members:
            if m.type == 'w': wayset[m.ref] = max(wayset.get(m.ref, 0), lvl)
    print('  bicycle-route ways', len(wayset), '| ways+nodes', name, flush=True)
    for o in osmium.FileProcessor(pbf, osmium.osm.NODE | osmium.osm.WAY).with_locations().with_filter(osmium.filter.EmptyTagFilter()):
        t = o.tags
        if o.is_way():
            hw = t.get('highway'); lvl = wayset.get(o.id, 0)
            if not hw and not lvl: continue
            pts = [(nd.location.lat, nd.location.lon) for nd in o.nodes if nd.location.valid()]
            if not pts: continue
            la, lo = pts[0]
            if not (bbox[0] <= la <= bbox[2] and bbox[1] <= lo <= bbox[3]): continue
            for la, lo in pts[::2] if len(pts) > 40 else pts:
                idx, xy = nearest(la, lo, 0.3 if lvl else 0.15)
                if not idx: continue
                if lvl:
                    for i in idx: route_mark[i] = max(route_mark[i], lvl)
                if hw:
                    cls = BUSY.get(hw, 1 if hw in QUIET else 0)
                    if cls:
                        for i in idx:
                            d = float(np.hypot(*(tree.data[i]-xy)))
                            if d < road_dist[i]: road_dist[i] = d; road_mark[i] = cls
        else:
            kind = next((t.get(k) for k, v in SIGHT.items() if t.get(k) in v), None) or ('waterfall' if t.get('waterway') == 'waterfall' else None)
            if not kind or not (t.get('name') or t.get('name:en')): continue
            la, lo = o.location.lat, o.location.lon
            if not (bbox[0] <= la <= bbox[2] and bbox[1] <= lo <= bbox[3]): continue
            idx, xy = nearest(la, lo, 2.0)
            if not idx or o.id in seen_sight: continue
            seen_sight.add(o.id); best = {}
            for i in idx:
                sid, vi = meta[i]; d = float(np.hypot(*(tree.data[i]-xy)))
                if sid not in best or d < best[sid][1]: best[sid] = (vi, d)
            for sid, (vi, d) in best.items(): sights[sid].append([vi, t.get('name:en') or t.get('name'), kind, round(d, 1), t.get('name')])
    print('  done', name, flush=True)
out = dict(prev)
for sid, pts in segs.items():
    idxs = [i for i, (s, _) in enumerate(meta) if s == sid]; n = len(idxs); rm = route_mark[idxs]; rd = road_mark[idxs]
    km = sum(hav(a, b) for a, b in zip(pts, pts[1:])) or 1
    sl = sorted(sights[sid], key=lambda x: x[0])
    out[sid] = dict(km=round(km, 1), route_any=round(float((rm > 0).mean()), 3), route_ncn=round(float((rm == 3).mean()), 3),
                    route_rcn=round(float((rm == 2).mean()), 3), busy=round(float((rd == 3).mean()), 3), secondary=round(float((rd == 2).mean()), 3),
                    quiet=round(float((rd == 1).mean()), 3), unknown=round(float((rd == 0).mean()), 3), sights=len(sl), sights_per100=round(len(sl)/km*100, 1),
                    sight_list=[[round(v/n*km, 1), nm, kd, d, ja if ja != nm else None] for v, nm, kd, d, ja in sl][:60])
jdump(W, OUT, out)
print('scored', len(segs), 'segments ->', OUT)
