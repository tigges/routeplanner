"""Step 2 — facilities within the corridor of every segment, from the OSM extracts (config.osm.extracts).
Incremental: only segments that have no facility data yet are scanned (pass --all to redo everything).
Writes <workdir>/fac/<extract>.csv and merges them into seg_data.json as [km, off, name_en, name_local] entries
(names are finished by step 5)."""
import csv, glob, json, os, shutil, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
cfg, W = load_cfg(); SD = jload(W, 'seg_data.json'); P = jload(W, 'P.json')
todo = [s['id'] for s in P['segments'] if s['mode'] == 'ride' and ('--all' in sys.argv or not SD.get(s['id'], {}).get('covered'))]
if not todo: print('nothing to do'); sys.exit()
tmp = os.path.join(W, 'segments_todo'); shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp)
for sid in todo: shutil.copy(os.path.join(W, 'segments', seg_fn(sid)), tmp)
os.makedirs(os.path.join(W, 'fac'), exist_ok=True); tag = 'all' if '--all' in sys.argv else 'r%d' % len(glob.glob(os.path.join(W, 'fac', '*.csv')))
for pbf in cfg['osm']['extracts']:
    out = os.path.join(W, 'fac', '%s-%s.csv' % (os.path.basename(pbf).split('.')[0], tag))
    print('scanning', pbf, 'for', len(todo), 'segments', flush=True)
    subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'extract_facilities.py'), '--segments-dir', tmp,
                    '--pbf', pbf, '--corridor', str(cfg['osm'].get('corridor_km', 2.0)), '--out', out], check=True)
# merge every csv into seg_data (dedupe by segment + osm id); names finished in step 5
CATS = {'food_shop': 'shop', 'lodging': 'stay', 'camping': 'camp', 'bath': 'bath', 'michi_no_eki': 'mne', 'water': 'water',
        'toilets': 'wc', 'bike': 'bike', 'laundry': 'laundry', 'rail': 'rail', 'food_eat': 'eat'}
fac = {}; seen = set()
for f in sorted(glob.glob(os.path.join(W, 'fac', '*.csv'))):
    for r in csv.DictReader(open(f, encoding='utf-8')):
        cat = CATS.get(r['category']); sid = r['segment_id']
        if not cat or sid not in SD or (sid, r['osm']) in seen: continue
        seen.add((sid, r['osm']))
        fac.setdefault(sid, {}).setdefault(cat, []).append([round(float(r['km_along']), 1), round(float(r['offset_km']), 1), r['name_en'], r['name'], r['subtype']])
for sid in todo:
    SD[sid]['fac'] = {c: sorted(v) for c, v in fac.get(sid, {}).items()}; SD[sid]['covered'] = True
jdump(W, 'seg_data.json', SD, compact=True)
print('facilities merged for', len(todo), 'segments;', sum(len(v) for s in todo for v in SD[s]['fac'].values()), 'entries')
