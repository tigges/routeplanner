"""Step 12 — lakes and big rivers for the map, from the OSM extracts (optional, cosmetic).
Lakes: every natural=water lake/reservoir of at least `min_km2` (default 3) in any extract; the largest shape per name wins
(cross-border lakes come whole from whichever extract holds all of them). Rivers: waterway=river ways whose name is in
`graph.water.rivers` (config), joined and simplified. Lakes from the outline GeoJSON (Natural Earth, featurecla "Lake")
and from the files in `graph.water.fallback` are kept only where no OSM lake covers their centre. Writes the file named in `graph.water.file` (GeoJSON, lat/lon);
step 01 projects it into P.json as P.water and then leaves the outline's lake features out of the coast.
usage: python3 pipeline/12_water.py config/<country>.json [--extract <file>]"""
import json, math, os, sys
import osmium
from shapely.geometry import shape, LineString, MultiLineString, Point
from shapely.ops import linemerge
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
cfg, W = load_cfg(); wc = cfg['graph'].get('water') or {}
OUT = wc.get('file', 'config/%s_water.geojson' % cfg['slug']); MINKM2 = float(wc.get('min_km2', 3)); RIVERS = set(wc.get('rivers', []))
ONLYX = sys.argv[sys.argv.index('--extract') + 1] if '--extract' in sys.argv else None
fab = osmium.geom.GeoJSONFactory(); lakes = {}; rivers = {}
for pbf in cfg['osm']['extracts']:
    if not os.path.exists(pbf) or (ONLYX and os.path.basename(pbf) != ONLYX): continue
    print('scanning', pbf, flush=True); n = 0
    for o in osmium.FileProcessor(pbf, osmium.osm.NODE | osmium.osm.WAY | osmium.osm.RELATION | osmium.osm.AREA).with_areas().with_locations().with_filter(osmium.filter.KeyFilter('natural', 'waterway')):
        t = o.tags
        if o.is_area():
            if t.get('natural') != 'water' or t.get('water', 'lake') not in ('lake', 'reservoir'): continue
            try: g = shape(json.loads(fab.create_multipolygon(o)))
            except Exception: continue
            c = g.centroid; km2 = g.area * 111 * 111 * math.cos(math.radians(c.y))
            if km2 < MINKM2: continue
            name = t.get('name:en') or t.get('name') or str(o.id)
            if name in lakes and lakes[name]['km2'] >= km2: continue
            gs = g.simplify(0.0015)
            polys = gs.geoms if gs.geom_type == 'MultiPolygon' else [gs]
            lakes[name] = dict(name=name, local=t.get('name', ''), km2=round(km2, 1), centre=(c.y, c.x), geom=g,
                               rings=[[[round(y, 4), round(x, 4)] for x, y in p.exterior.coords] for p in polys]); n += 1
        elif o.is_way() and t.get('waterway') == 'river' and t.get('name') in RIVERS:
            pts = [(nd.lon, nd.lat) for nd in o.nodes if nd.location.valid()]
            if len(pts) > 1: rivers.setdefault(t['name'], []).append(LineString(pts))
    print('  ', n, 'lakes so far', flush=True)
feats = []
if cfg['graph'].get('outline'):        # only lakes that touch the country: within 5 km of its outline (Lake Annecy is not a Swiss lake)
    from shapely.ops import unary_union
    og = json.load(open(cfg['graph']['outline']))
    land = unary_union([shape(f['geometry']) for f in og.get('features', []) if (f.get('properties') or {}).get('featurecla') != 'Lake']).buffer(0.05)
    lakes = {k: l for k, l in lakes.items() if land.intersects(l['geom'])}
for l in sorted(lakes.values(), key=lambda x: -x['km2']):
    feats.append(dict(type='Feature', properties=dict(kind='lake', name=l['name'], local=l['local'], km2=l['km2']),
                      geometry=dict(type='MultiPolygon', coordinates=[[[[p[1], p[0]] for p in r]] for r in l['rings']])))
fallback = ([cfg['graph']['outline']] if cfg['graph'].get('outline') else []) + list(wc.get('fallback', []))
kept = 0
for fn in fallback:                    # Natural Earth lakes not covered by an OSM one (cross-border lakes are cut in every extract)
    g = json.load(open(fn))
    for f in g.get('features', []):
        if f.get('properties', {}).get('featurecla') != 'Lake': continue
        c = shape(f['geometry']).centroid
        if any(l['geom'].contains(c) for l in lakes.values()): continue
        feats.append(dict(type='Feature', properties=dict(kind='lake', name=f['properties'].get('name') or '', local='', km2=0, source='naturalearth'), geometry=f['geometry'])); kept += 1
print('kept', kept, 'fallback lakes not in OSM')
for name, ls in rivers.items():
    m = linemerge(MultiLineString(ls)).simplify(0.002)
    for l in (m.geoms if m.geom_type == 'MultiLineString' else [m]):
        if l.length * 111 > 8: feats.append(dict(type='Feature', properties=dict(kind='river', name=name), geometry=dict(type='LineString', coordinates=[[round(x, 4), round(y, 4)] for x, y in l.coords])))
json.dump(dict(type='FeatureCollection', features=feats), open(OUT, 'w'), separators=(',', ':'))
print('lakes', len(lakes), '| river pieces', sum(1 for f in feats if f['properties']['kind'] == 'river'), '->', OUT)
print(', '.join('%s %.0f' % (l['name'], l['km2']) for l in sorted(lakes.values(), key=lambda x: -x['km2'])[:20]))
