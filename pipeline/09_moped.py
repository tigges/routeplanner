"""Step 9 (vehicle) — the moped line for every segment whose bicycle line has ≥ threshold on motor-free ways:
route with BRouter's moped profile, build planner segments (effort = km), extract facilities and scores for
those lines, finish names, beds and day-end names. Writes moped_segments.json, moped_sd.json, moped_sc.json."""
import os, sys, shutil, subprocess, csv, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
cfg, W = load_cfg(); V = cfg['vehicles']['moped']; P = jload(W, 'P.json'); PR = jload(W, 'proj.json'); pj = Proj(PR)
MF = jload(W, 'motorfree.json'); SEGB = {s['id']: s for s in P['segments']}
LL = {n['id']: pj.ll(n['x'], n['y']) for n in P['nodes']}
for key, v in jload(W, 'route_cache.json', {}).items():
    a, b = key.split('--'); LL[a] = tuple(v['line'][0][:2]); LL[b] = tuple(v['line'][-1][:2])
for nid, n in cfg.get('nodes', {}).items():
    if 'lat' in n: LL[nid] = (n['lat'], n['lon'])
ids = [sid for sid, m in MF.items() if m['share'] >= V.get('reroute_if_motorfree_share_at_least', 0.05) and sid in SEGB and sid not in V.get('keep_bicycle_line', [])]
print(len(ids), 'segments to re-route for a moped')
MS = jload(W, 'moped_segments.json', {}); SD = jload(W, 'moped_sd.json', {})
mdir = os.path.join(W, 'segments_moped'); os.makedirs(mdir, exist_ok=True); new = []
for sid in ids:
    if sid in MS: continue
    b = SEGB[sid]; r = route(W, sid, LL[b['frm']], LL[b['to']], profile='moped', cache_name='moped_cache.json')
    if r['km'] > 3 * b['km']: print('  moped routing implausible for', sid, '- keeping the bicycle line'); continue
    seg, sd = make_segment(PR, sid, b['frm'], b['to'], b['variant'], r)
    seg['effort'] = int(round(r['km'])); seg['effortR'] = seg['effort']
    for c in seg['cand']: c['eff'] = round(c['km'], 1); c['effR'] = round(r['km'] - c['km'], 1)
    seg['cand'][-1]['eff'] = float(seg['effort']); seg['cand'][-1]['effR'] = 0.0; seg['moped'] = True
    MS[sid] = seg; SD[sid] = sd; new.append(sid)
    json.dump(seg_geojson(sid, r['line']), open(os.path.join(mdir, seg_fn(sid)), 'w'))
jdump(W, 'moped_segments.json', MS); jdump(W, 'moped_sd.json', SD, compact=True)
if not new: print('no new moped lines'); sys.exit()
# facilities for the new lines
tmp = os.path.join(W, 'segments_moped_todo'); shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp)
for sid in new: shutil.copy(os.path.join(mdir, seg_fn(sid)), tmp)
os.makedirs(os.path.join(W, 'fac_moped'), exist_ok=True); here = os.path.dirname(os.path.abspath(__file__))
tag = 'r%d' % len(glob.glob(os.path.join(W, 'fac_moped', '*.csv')))
for pbf in cfg['osm']['extracts']:
    out = os.path.join(W, 'fac_moped', '%s-%s.csv' % (os.path.basename(pbf).split('.')[0], tag))
    subprocess.run([sys.executable, os.path.join(here, 'extract_facilities.py'), '--segments-dir', tmp, '--pbf', pbf, '--corridor', str(cfg['osm'].get('corridor_km', 2.0)), '--out', out], check=True)
CATS = {'food_shop': 'shop', 'lodging': 'stay', 'camping': 'camp', 'bath': 'bath', 'michi_no_eki': 'mne', 'water': 'water',
        'toilets': 'wc', 'bike': 'bike', 'laundry': 'laundry', 'rail': 'rail', 'food_eat': 'eat'}
fac = {}; seen = set()
for f in sorted(glob.glob(os.path.join(W, 'fac_moped', '*.csv'))):
    for r in csv.DictReader(open(f, encoding='utf-8')):
        cat = CATS.get(r['category']); sid = r['segment_id']
        if not cat or sid not in SD or (sid, r['osm']) in seen: continue
        seen.add((sid, r['osm'])); fac.setdefault(sid, {}).setdefault(cat, []).append([round(float(r['km_along']), 1), round(float(r['offset_km']), 1), r['name_en'], r['name'], r['subtype']])
for sid in new: SD[sid]['fac'] = {c: sorted(v) for c, v in fac.get(sid, {}).items()}; SD[sid]['covered'] = True
jdump(W, 'moped_sd.json', SD, compact=True)
# scores, names, beds, day-end names for the moped lines
run = lambda step, *a: subprocess.run([sys.executable, os.path.join(here, step), sys.argv[1], *a], check=True)
run('03_scores.py', '--segdir', mdir, '--out', 'moped_sc.json'); run('05_names.py', '--moped'); run('04_beds.py', '--moped'); run('06_candnames.py', '--moped')
print('moped lines done:', len(MS))
