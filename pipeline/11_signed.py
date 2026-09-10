"""Step 11 (option) — the "prefer signed cycle routes" lines.
For every leg listed in config.signedRoutes.legs, route the bicycle line again through the waypoints step 10 found
along the signed route (cycleroute_candidates.json), build planner segments, then facilities, scores, names, beds and
day-end names for those lines, the same way step 9 does for the moped. The page swaps them in when the rider ticks
"Prefer signed cycle routes" (bicycle and e-bike only). Writes signed_segments.json, signed_sd.json, signed_sc.json.
Time-limited sessions: --extract <file> scans one OSM extract per run; re-run without it when every extract is done.
usage: python3 pipeline/11_signed.py config/<country>.json [--extract <file>]"""
import os, sys, shutil, subprocess, csv, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
cfg, W = load_cfg(); here = os.path.dirname(os.path.abspath(__file__))
LEGS = cfg.get('signedRoutes', {}).get('legs', [])
if not LEGS: print('config.signedRoutes.legs is empty - nothing to do'); sys.exit()
P = jload(W, 'P.json'); PR = jload(W, 'proj.json'); pj = Proj(PR); SEGB = {s['id']: s for s in P['segments']}
CAND = jload(W, 'cycleroute_candidates.json', {}); BYSEG = {c['seg']: c for c in CAND.values()}
LL = {n['id']: pj.ll(n['x'], n['y']) for n in P['nodes']}
SS = jload(W, 'signed_segments.json', {}); SD = jload(W, 'signed_sd.json', {})
for sid in list(SS):                       # a leg taken off the list drops out of the layer
    if sid not in LEGS: SS.pop(sid); SD.pop(sid, None)
sdir = os.path.join(W, 'segments_signed'); os.makedirs(sdir, exist_ok=True)
for fn in os.listdir(sdir):
    if seg_id(fn) not in LEGS: os.remove(os.path.join(sdir, fn))
# 1. lines -------------------------------------------------------------------------------------------
for sid in LEGS:
    if sid in SS: continue
    if sid not in SEGB: raise SystemExit('signedRoutes: %s is not a segment of the graph' % sid)
    if sid not in BYSEG: raise SystemExit('signedRoutes: no step-10 candidate for %s (run 10_cycleroutes.py)' % sid)
    b = SEGB[sid]; c = BYSEG[sid]
    r = route(W, sid + '@signed', LL[b['frm']], LL[b['to']], via=c['via'], cache_name='signed_cache.json')
    seg, sd = make_segment(PR, sid, b['frm'], b['to'], b['variant'], r); seg['note'] = b.get('note', ''); seg['signed'] = True
    seg['routes'] = c['routes']; SS[sid] = seg; SD[sid] = sd
    json.dump(seg_geojson(sid, r['line']), open(os.path.join(sdir, seg_fn(sid)), 'w'))
jdump(W, 'signed_segments.json', SS); jdump(W, 'signed_sd.json', SD, compact=True)
print(len(SS), 'signed-route lines')
# 2. facilities, one extract at a time (resumable) ---------------------------------------------------
todo = sorted(sid for sid in SS if not SD[sid].get('covered'))
fdir = os.path.join(W, 'fac_signed'); os.makedirs(fdir, exist_ok=True)
state = jload(fdir, 'state.json', {}) if os.path.exists(os.path.join(fdir, 'state.json')) else {}
if state.get('todo') != todo: state = dict(todo=todo, done=[])
ONLYX = sys.argv[sys.argv.index('--extract') + 1] if '--extract' in sys.argv else None
extracts = [p for p in cfg['osm']['extracts'] if os.path.exists(p)]
missing = [os.path.basename(p) for p in cfg['osm']['extracts'] if not os.path.exists(p)]
if missing: print('not downloaded (skipped - fine if no signed leg passes through them):', ', '.join(missing))
if todo:
    tmp = os.path.join(W, 'segments_signed_todo'); shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp)
    for sid in todo: shutil.copy(os.path.join(sdir, seg_fn(sid)), tmp)
    for pbf in extracts:
        name = os.path.basename(pbf)
        if name in state['done'] or (ONLYX and name != ONLYX): continue
        print('facilities:', name, flush=True)
        subprocess.run([sys.executable, os.path.join(here, 'extract_facilities.py'), '--segments-dir', tmp, '--pbf', pbf,
                        '--corridor', str(cfg['osm'].get('corridor_km', 2.0)), '--out', os.path.join(fdir, name.split('.')[0] + '.csv')], check=True)
        state['done'].append(name); jdump(fdir, 'state.json', state)
        if ONLYX: break
# 3. scores (step 3 on the signed lines; it resumes by itself) ----------------------------------------
xs = ['--extract', ONLYX] if ONLYX else []
subprocess.run([sys.executable, os.path.join(here, '03_scores.py'), sys.argv[1], '--segdir', sdir, '--out', 'signed_sc.json', *xs], check=True)
if ONLYX: print('extract done; run the next one, then once more without --extract'); sys.exit()
# 4. merge facilities, then names, beds, day-end names -----------------------------------------------
if todo:
    left = [os.path.basename(p) for p in extracts if os.path.basename(p) not in state['done']]
    if left: raise SystemExit('facilities not yet scanned: %s' % left)
    CATS = {'food_shop': 'shop', 'lodging': 'stay', 'camping': 'camp', 'bath': 'bath', 'michi_no_eki': 'mne', 'water': 'water',
            'toilets': 'wc', 'bike': 'bike', 'laundry': 'laundry', 'rail': 'rail', 'food_eat': 'eat'}
    fac = {}; seen = set()
    for f in sorted(glob.glob(os.path.join(fdir, '*.csv'))):
        for r in csv.DictReader(open(f, encoding='utf-8')):
            cat = CATS.get(r['category']); sid = r['segment_id']
            if not cat or sid not in todo or (sid, r['osm']) in seen: continue
            seen.add((sid, r['osm'])); fac.setdefault(sid, {}).setdefault(cat, []).append([round(float(r['km_along']), 1), round(float(r['offset_km']), 1), r['name_en'], r['name'], r['subtype']])
    for sid in todo: SD[sid]['fac'] = {c: sorted(v) for c, v in fac.get(sid, {}).items()}; SD[sid]['covered'] = True
    jdump(W, 'signed_sd.json', SD, compact=True); shutil.rmtree(fdir, ignore_errors=True)
run = lambda step, *a: subprocess.run([sys.executable, os.path.join(here, step), sys.argv[1], *a], check=True)
run('05_names.py', '--signed'); run('04_beds.py', '--signed'); run('06_candnames.py', '--signed')
print('signed-route lines done:', len(SS))
