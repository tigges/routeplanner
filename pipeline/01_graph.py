"""Step 1 — the segment graph.
New country: geocode the nodes, route every trunk leg with BRouter (trekking), fit the map projection,
build P.json (nodes, segments, forks, coast) + seg_data.json (profiles) + segments/<id>.geojson.
Country with a prebuilt graph (config.graph.prebuilt): copy it and write the per-segment GeoJSON."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
cfg, W = load_cfg(); SEGDIR = os.path.join(W, 'segments'); os.makedirs(SEGDIR, exist_ok=True)

if cfg['graph'].get('prebuilt_dir'):
    # a graph built before this pipeline existed (Japan): copy every data file, write the per-segment GeoJSON
    d = cfg['graph']['prebuilt_dir']; import shutil
    for fn in os.listdir(d):
        if fn.endswith('.json'): shutil.copy(os.path.join(d, fn), W)
    P = jload(W, 'P.json'); pj = Proj(jload(W, 'proj.json')); rc = jload(W, 'route_cache.json', {})
    for s in P['segments']:
        if s['mode'] != 'ride': continue
        key = s['frm'] + '--' + s['to']
        line = rc[key]['line'] if key in rc else [list(pj.ll(*map(float, p.split(',')))) for p in s['line'].split()]
        json.dump(seg_geojson(s['id'], line), open(os.path.join(SEGDIR, seg_fn(s['id'])), 'w'))
    print('prebuilt graph copied:', len(P['nodes']), 'nodes', len(P['segments']), 'segments')
    vb = cfg.get('viaBase') or {}
    if vb:
        SEG = {x['id']: x for x in P['segments']}; SD = jload(W, 'seg_data.json', {}); PR = jload(W, 'proj.json'); pjv = Proj(PR); NB = {n['id']: n for n in P['nodes']}
        for pair, via in vb.items():
            sid = pair; base = pair.split('#')[0]; a, b = base.split('--'); var = pair.split('#')[1] if '#' in pair else 'base'
            if sid not in SEG: print('viaBase: no base leg', sid); continue
            all = (NB[a]['lat'], NB[a]['lon']) if 'lat' in NB[a] else pjv.ll(NB[a]['x'], NB[a]['y'])
            bll = (NB[b]['lat'], NB[b]['lon']) if 'lat' in NB[b] else pjv.ll(NB[b]['x'], NB[b]['y'])
            r = route(W, sid + '#viabase', all, bll, via=via)
            seg, sd = make_segment(PR, sid, a, b, var, r)
            for i, x in enumerate(P['segments']):
                if x['id'] == sid: P['segments'][i] = seg
            SD[sid] = dict(sd, covered=False); json.dump(seg_geojson(sid, r['line']), open(os.path.join(SEGDIR, seg_fn(sid)), 'w'))
            print('viaBase rerouted', sid, '->', r['km'], 'km')
        jdump(W, 'P.json', P); jdump(W, 'seg_data.json', SD, compact=True)
    # --- extend it with the trunks in the config (fork town … rejoin town; new inner towns need lat/lon in nodes) ---
    ext = [t for t in cfg.get('trunks', []) if t['variant'] != 'base']
    if not ext: sys.exit()
    NODE = {n['id']: n for n in P['nodes']}; NODES = cfg.get('nodes', {}); SD = jload(W, 'seg_data.json', {}); PR = jload(W, 'proj.json')
    have = {s['id'] for s in P['segments']}; forks = {f['node']: f['options'] for f in P['forks']}
    def ll(nid):
        if nid in NODES and 'lat' in NODES[nid]: return (NODES[nid]['lat'], NODES[nid]['lon'])
        n = NODE[nid]; return pj.ll(n['x'], n['y'])
    for t in ext:
        v = t['variant']; ns = t['nodes']; a0, b0 = ns[0], ns[-1]
        inner = [n for n in ns[1:-1] if n not in NODE]
        ra = NODE[a0]['rank']; rb = NODE[b0]['rank'] if b0 in NODE else ra + 1
        for i, nid in enumerate(inner, 1):
            x, y = pj.xy(*ll(nid)); n = NODES[nid]
            NODE[nid] = dict(id=nid, name=n['name'], type=n.get('type', 'gateway'), x=round(x, 1), y=round(y, 1), rank=round(ra + (rb - ra) * i / (len(inner) + 1), 3), entry=1 if n.get('entry', True) else 0, requires=[v])
        for a, b in zip(ns, ns[1:]):
            sid = a + '--' + b + '#' + v
            if sid in have: continue
            via = (t.get('via') or {}).get(a + '--' + b, [])
            r = route(W, sid if via else a + '--' + b, ll(a), ll(b), via=via)
            seg, sd = make_segment(PR, sid, a, b, v, r); P['segments'].append(seg); SD[sid] = sd; have.add(sid)
            json.dump(seg_geojson(sid, r['line']), open(os.path.join(SEGDIR, seg_fn(sid)), 'w'))
        for f in cfg.get('ferries', []):
            if f.get('variant') == v:
                sid = f['from'] + '--' + f['to'] + '#' + v
                if sid not in have:
                    P['segments'].append(dict(id=sid, frm=f['from'], to=f['to'], variant=v, mode='ferry', km=f['km'], ascent=0, note=f.get('note', ''), effort=0, descent=0, effortR=0, line='', cand=[])); have.add(sid)
        if a0 not in forks:
            outs = [s for s in P['segments'] if s['frm'] == a0 and s['variant'] != v]
            forks[a0] = ['base' if any(s['variant'] == 'base' for s in outs) else outs[0]['variant']] if outs else ['base']
        if v not in forks[a0]: forks[a0].append(v)
        NODE[a0]['type'] = 'fork'
    for fk, opts in cfg.get('forks', {}).items(): forks[fk] = opts     # explicit override (also sets the default = first)
    P['nodes'] = sorted(NODE.values(), key=lambda n: n.get('rank') or 0); P['forks'] = [dict(node=n, options=o) for n, o in forks.items()]
    jdump(W, 'P.json', P); jdump(W, 'seg_data.json', SD, compact=True)
    print('extended:', len(P['nodes']), 'nodes', len(P['segments']), 'segments', len(forks), 'forks'); sys.exit()

# --- nodes -------------------------------------------------------------------------------------
NODES = cfg['nodes']; LL = {}
for nid, n in NODES.items():
    LL[nid] = (n['lat'], n['lon']) if 'lat' in n else geocode(W, nid, n.get('q', n['name'] + ' station, ' + cfg['title']))
# --- projection --------------------------------------------------------------------------------
PR = jload(W, 'proj.json') if '--refit' not in sys.argv else None      # keep the projection stable once data exists (pass --refit to change it)
if not PR: PR = fit_proj(list(LL.values()), cfg['graph'].get('map_width', 520.0)); jdump(W, 'proj.json', PR)
pj = Proj(PR)
# --- ranks and node records -----------------------------------------------------------------
trunks = cfg['trunks']; base = next(t for t in trunks if t['variant'] == 'base')
rank = {n: i for i, n in enumerate(base['nodes'])}
NODE = {}
def node_rec(nid, r, requires=None):
    x, y = pj.xy(*LL[nid]); n = NODES[nid]
    rec = dict(id=nid, name=n['name'], type=n.get('type', 'handle'), x=round(x, 1), y=round(y, 1), rank=round(r, 3), entry=1 if n.get('entry', True) else 0)
    if requires: rec['requires'] = requires
    return rec
for nid in base['nodes']: NODE[nid] = node_rec(nid, rank[nid])
NODE[base['nodes'][0]]['type'] = 'terminus'; NODE[base['nodes'][-1]]['type'] = 'terminus'
for t in trunks:
    if t['variant'] == 'base': continue
    inner = [n for n in t['nodes'] if n not in NODE]
    ra, rb = NODE[t['nodes'][0]]['rank'], NODE[t['nodes'][-1]]['rank'] if t['nodes'][-1] in NODE else NODE[t['nodes'][0]]['rank'] + 1
    for i, nid in enumerate(inner, 1): NODE[nid] = node_rec(nid, ra + (rb - ra) * i / (len(inner) + 1), t.get('requires', [t['variant']]))
# --- segments (re-running keeps the facilities, beds and names of segments that did not change) --
oldP = jload(W, 'P.json', {'segments': []}); oldSD = jload(W, 'seg_data.json', {})
old = {s['id']: s for s in oldP['segments']}
segments = []; SD = {}; kept = 0
for t in trunks:
    v = t['variant']
    for a, b in zip(t['nodes'], t['nodes'][1:]):
        sid = a + '--' + b + ('' if v == 'base' else '#' + v)
        r = route(W, a + '--' + b, LL[a], LL[b])
        if sid in old and old[sid]['km'] == r['km'] and sid in oldSD and os.path.exists(os.path.join(SEGDIR, seg_fn(sid))):
            segments.append(old[sid]); SD[sid] = oldSD[sid]; kept += 1; continue
        seg, sd = make_segment(PR, sid, a, b, v, r); segments.append(seg); SD[sid] = sd
        json.dump(seg_geojson(sid, r['line']), open(os.path.join(SEGDIR, seg_fn(sid)), 'w'))
if kept: print('kept', kept, 'unchanged segments with their data')
for f in cfg.get('ferries', []):
    v = f.get('variant', 'base'); sid = f['from'] + '--' + f['to'] + ('' if v == 'base' else '#' + v)
    segments.append(dict(id=sid, frm=f['from'], to=f['to'], variant=v, mode='ferry', km=f['km'], ascent=0, note=f.get('note', ''),
                         effort=0, descent=0, effortR=0, line='', cand=[]))
# --- forks: every non-base trunk forks at its first node ------------------------------------
forks = {}
for t in trunks:
    if t['variant'] == 'base': continue
    fk = t['nodes'][0]
    if fk not in forks:
        outs = [s for s in segments if s['frm'] == fk and s['variant'] != t['variant']]
        forks[fk] = ['base' if any(s['variant'] == 'base' for s in outs) else outs[0]['variant']] if outs else ['base']
    forks[fk].append(t['variant']); NODE[fk]['type'] = 'fork'
for fk, opts in cfg.get('forks', {}).items(): forks[fk] = opts     # explicit override
# --- outline (coast / border) ----------------------------------------------------------------
coast = []
if cfg['graph'].get('outline'):
    g = json.load(open(cfg['graph']['outline']))
    def rings(obj):
        t = obj.get('type')
        if t == 'FeatureCollection':
            for f in obj['features']: yield from rings(f)
        elif t == 'Feature': yield from rings(obj['geometry'])
        elif t == 'Polygon':
            for r in obj['coordinates']: yield r
        elif t == 'MultiPolygon':
            for p in obj['coordinates']:
                for r in p: yield r
        elif t in ('LineString',): yield obj['coordinates']
        elif t == 'MultiLineString':
            for r in obj['coordinates']: yield r
    for r in rings(g):
        pts = decimate([(c[1], c[0]) for c in r], 0.5)
        if len(pts) > 2: coast.append(' '.join('%.1f,%.1f' % pj.xy(*p) for p in pts))
P = dict(nodes=sorted(NODE.values(), key=lambda n: n['rank']), segments=segments, forks=[dict(node=n, options=o) for n, o in forks.items()], coast=coast)
jdump(W, 'P.json', P); jdump(W, 'seg_data.json', SD, compact=True)
print('graph:', len(P['nodes']), 'nodes', len(segments), 'segments', len(forks), 'forks', len(coast), 'outline pieces')
