"""Rebuild <workdir>/segments/<id>.geojson from an existing P.json and the routing cache.

01_graph keeps a segment's facilities, scores, beds and day-end names only when its GeoJSON file is still
there; the per-segment files live in work/, which is not committed, so a fresh clone has P.json (in
examples/<slug>/) but no segment files, and a plain 01_graph run would re-make all of them and throw the
scanned data away. Run this first and only the legs that really changed are rebuilt.
usage: python3 tools/segfiles.py config/<country>.json"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pipeline'))
from common import *
cfg, W = load_cfg()
SEGDIR = os.path.join(W, 'segments'); os.makedirs(SEGDIR, exist_ok=True)
P = jload(W, 'P.json'); pj = Proj(jload(W, 'proj.json')); rc = jload(W, 'route_cache.json', {})
made = kept = 0
for s in P['segments']:
    if s['mode'] != 'ride': continue
    fn = os.path.join(SEGDIR, seg_fn(s['id']))
    if os.path.exists(fn): kept += 1; continue
    r = rc.get(s['id']) or rc.get(s['frm'] + '--' + s['to'])      # variant legs are cached under their full id; base legs under frm--to
    line = r['line'] if r else [list(pj.ll(*map(float, p.split(',')))) for p in s['line'].split()]
    json.dump(seg_geojson(s['id'], line), open(fn, 'w')); made += 1
print('segment files:', made, 'written,', kept, 'already there')
