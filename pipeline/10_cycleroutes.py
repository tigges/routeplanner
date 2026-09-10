"""Step 10 — offer a signed-cycle-route alternative for legs that mostly ignore one.
For every ride segment whose cycle-route share is below `threshold` (default 0.5), collect every national/regional
bicycle route relation (OSM network=ncn/rcn) that runs along the corridor (within `reach` km of the current line for
at least `min-run` km), and route the leg again with BRouter through waypoints taken along those stretches, in order; keep it if it is not more than `max_ratio` × the original
length. Writes <workdir>/cycleroute_candidates.json (one entry per candidate, with both sets of numbers) and prints
a table. Turning candidates into planner alternatives is a config edit (trunks with `via`), see the runbook.
usage: python3 pipeline/10_cycleroutes.py config/<country>.json [--threshold 0.5] [--reach 5 (km from the current line)] [--min-run 8 (km a route must follow the corridor)] [--max-ratio 1.35] [--only id,id]"""
import json, math, os, sys
import numpy as np, osmium
from scipy.spatial import cKDTree
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
cfg, W = load_cfg()
def arg(k, d): return type(d)(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d
THRESH, REACH, MAXR, MINRUN = arg('--threshold', 0.5), arg('--reach', 5.0), arg('--max-ratio', 1.35), arg('--min-run', 8.0)
ONLY = set(arg('--only', '').split(',')) - {''}
SPACING, MAXVIA = 5.0, 40
P = jload(W, 'P.json'); SC = jload(W, 'seg_scores.json', {}); pj = Proj(jload(W, 'proj.json'))
NODE = {n['id']: n for n in P['nodes']}
def nll(nid): n = NODE[nid]; return pj.ll(n['x'], n['y'])
segs = [s for s in P['segments'] if s['mode'] == 'ride' and s['id'] in SC and SC[s['id']]['route_any'] < THRESH and (not ONLY or s['id'] in ONLY)]
print(len(segs), 'legs below', THRESH, 'cycle-route share')
# --- relations from the extracts (cached) -----------------------------------------------------------
REL = jload(W, 'cycleroute_relations.json', {}); DONE = set(REL.pop('__done__', []))
if True:
    for pbf in cfg['osm']['extracts']:
        if not os.path.exists(pbf): print('missing', pbf); continue
        if os.path.basename(pbf) in DONE: continue
        rels = {}; wayrel = {}
        for o in osmium.FileProcessor(pbf, osmium.osm.RELATION).with_filter(osmium.filter.KeyFilter('route')):
            t = o.tags
            if t.get('route') != 'bicycle' or t.get('network') not in ('ncn', 'rcn'): continue
            rid = str(o.id); rels[rid] = dict(name=t.get('name:en') or t.get('name') or rid, local=t.get('name', ''), network=t['network'], ways=[])
            for m in o.members:
                if m.type == 'w': rels[rid]['ways'].append(m.ref); wayrel.setdefault(m.ref, []).append(rid)
        print(os.path.basename(pbf), len(rels), 'ncn/rcn relations', flush=True)
        if not rels: continue
        WAY = {}
        for o in osmium.FileProcessor(pbf, osmium.osm.NODE | osmium.osm.WAY).with_locations().with_filter(osmium.filter.IdFilter(list(wayrel)).enable_for(osmium.osm.WAY)):
            if not o.is_way(): continue
            WAY[o.id] = [(round(nd.location.lat, 5), round(nd.location.lon, 5)) for nd in o.nodes if nd.location.valid()]
        for rid, r in rels.items():
            ways = [WAY[w] for w in r['ways'] if w in WAY and len(WAY[w]) > 1]
            chains = []       # join ways end to end greedily
            while ways:
                ch = list(ways.pop(0)); grown = True
                while grown and ways:
                    grown = False
                    for i, w in enumerate(ways):
                        if hav(ch[-1], w[0]) < 0.05: ch += w[1:]
                        elif hav(ch[-1], w[-1]) < 0.05: ch += w[::-1][1:]
                        elif hav(ch[0], w[-1]) < 0.05: ch = w[:-1] + ch
                        elif hav(ch[0], w[0]) < 0.05: ch = w[::-1][:-1] + ch
                        else: continue
                        ways.pop(i); grown = True; break
                chains.append(decimate(ch, 0.2))
            key = rid if rid not in REL else rid + '@' + os.path.basename(pbf)
            REL[key] = dict(name=r['name'], local=r['local'], network=r['network'], chains=[c for c in chains if len(c) > 5])
        DONE.add(os.path.basename(pbf)); REL['__done__'] = sorted(DONE); jdump(W, 'cycleroute_relations.json', REL, compact=True); REL.pop('__done__')
        if '--one' in sys.argv: print('one extract done; re-run for the next'); sys.exit()
print(len(REL), 'relations,', sum(len(r['chains']) for r in REL.values()), 'chains')
# --- match: stitch every signed route that follows the corridor -----------------------------------
lat0 = float(np.mean([nll(n)[0] for n in NODE])); k = math.pi*R/180
def xy(la, lo): return (lo*k*math.cos(math.radians(lat0)), la*k)
CH = []
for rk, r in REL.items():
    for ci, c in enumerate(r['chains']):
        cum = [0.0]
        for p, q in zip(c, c[1:]): cum.append(cum[-1] + hav(p, q))
        CH.append((rk, ci, c, cum))
out = jload(W, 'cycleroute_candidates.json', {}); rows = []
for s in segs:
    if s['id'] in out and '--redo' not in sys.argv: continue
    a, b = nll(s['frm']), nll(s['to'])
    g = json.load(open(os.path.join(W, 'segments', seg_fn(s['id'])))); line = densify([(c[1], c[0]) for c in g['geometry']['coordinates']], 0.5)
    lcum = [0.0]
    for p, q in zip(line, line[1:]): lcum.append(lcum[-1] + hav(p, q))
    ltree = cKDTree([xy(*p) for p in line]); pieces = []
    for rk, ci, c, cum in CH:
        d, idx = ltree.query([xy(*p) for p in c]); run = []
        for j, (dj, ij) in enumerate(zip(d, idx)):
            if dj <= REACH: run.append(j)
            if dj > REACH or j == len(c) - 1:
                if run and cum[run[-1]] - cum[run[0]] >= MINRUN:
                    ka, kb = lcum[idx[run[0]]], lcum[idx[run[-1]]]
                    pts = [c[q] for q in run]
                    if ka > kb: pts = pts[::-1]; ka, kb = kb, ka
                    pieces.append((ka, kb, cum[run[-1]] - cum[run[0]], rk, pts))
                run = []
    pieces.sort(); chosen = []; kend = -1
    for ka, kb, L, rk, pts in pieces:
        if ka >= kend - 1 and kb > kend: chosen.append((ka, kb, L, rk, pts)); kend = kb
    if not chosen: continue
    via = []
    for ka, kb, L, rk, pts in chosen:
        pc = [0.0]
        for p, q in zip(pts, pts[1:]): pc.append(pc[-1] + hav(p, q))
        n = max(1, int(pc[-1] / SPACING))
        for j in range(1, n + 1):
            kk = pc[-1] * j / (n + 1); idx = min(range(len(pc)), key=lambda q: abs(pc[q] - kk)); via.append(pts[idx])
    if len(via) > MAXVIA: via = [via[int(j * (len(via) - 1) / (MAXVIA - 1))] for j in range(MAXVIA)]
    names = []
    for ch in chosen:
        nm = REL[ch[3]]['name']
        if nm not in names: names.append(nm)
    covered = sum(kb - ka for ka, kb, L, rk, pts in chosen)
    sid = s['id'].split('#')[0] + '#ncr'
    try: r = route(W, sid, a, b, via=via, cache_name='route_cache.json')
    except SystemExit as e: print('  skip', s['id'], e); continue
    ratio = r['km'] / s['km']
    rec = dict(seg=s['id'], frm=s['frm'], to=s['to'], routes=names, corridor_km=round(covered, 1), km=r['km'], asc=r['asc'], orig_km=s['km'], orig_asc=s['ascent'],
               orig_route=SC[s['id']]['route_any'], ratio=round(ratio, 2), via=via, keep=ratio <= MAXR)
    out[s['id']] = rec; rows.append(rec); jdump(W, 'cycleroute_candidates.json', out)
    print('%-34s %-40s %6.1f km +%5d m  (was %6.1f km +%5d m, %2d%% on route)  x%.2f %s' % (s['id'], ' + '.join(names)[:40], r['km'], r['asc'], s['km'], s['ascent'], round(100*rec['orig_route']), ratio, '' if rec['keep'] else 'TOO LONG'), flush=True)
print(len(rows), 'new candidates;', sum(1 for r in out.values() if r['keep']), 'of', len(out), 'within', MAXR, 'x')
