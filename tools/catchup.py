"""Bring a country's published page up to the current template and data layers in one go.
For each config given: (1) download the OSM extracts named in `osm.extracts` if they are missing (from the URLs in
`osm.urls`, or from download.openstreetmap.fr by the region names in `osm.mirror`), (2) run step 12 (lakes and rivers)
when `graph.water` is set, (3) refresh the graph — `01_graph` for a country whose data is in work/ or examples/, else
`tools/retemplate.py`, which lifts the data from the published page and adds the water — (4) rebuild and publish, (5)
re-measure the trips file when the country has one. Then commit and push docs/ config/ examples/.
usage: python3 tools/catchup.py config/japan.json config/spain.json [--no-download] [--skip-water]"""
import json, os, shutil, subprocess, sys, urllib.request
here = os.path.dirname(os.path.abspath(__file__)); root = os.path.abspath(os.path.join(here, '..')); os.chdir(root)
PY = sys.executable
def run(*a): print('>', ' '.join(a), flush=True); subprocess.run([PY] + list(a), check=True)
def fetch(url, dst):
    print('downloading', url, '->', dst, flush=True); os.makedirs(os.path.dirname(dst), exist_ok=True)
    with urllib.request.urlopen(url) as r, open(dst + '.part', 'wb') as f: shutil.copyfileobj(r, f, 1 << 20)
    os.replace(dst + '.part', dst)
cfgs = [a for a in sys.argv[1:] if a.endswith('.json')]
for cp in cfgs:
    cfg = json.load(open(cp, encoding='utf-8')); slug = cfg['slug']; W = cfg['workdir']
    print('==', slug, flush=True)
    if '--no-download' not in sys.argv:
        urls = cfg['osm'].get('urls', {}); mirror = cfg['osm'].get('mirror', {})
        for pbf in cfg['osm']['extracts']:
            if os.path.exists(pbf): continue
            b = os.path.basename(pbf)
            url = urls.get(b) or (mirror.get(b) and 'https://download.openstreetmap.fr/extracts/' + mirror[b])
            if not url: raise SystemExit('no download URL for %s: add it under osm.urls (any URL) or osm.mirror (path on download.openstreetmap.fr)' % b)
            fetch(url, pbf)
    if cfg['graph'].get('water') and '--skip-water' not in sys.argv: run('pipeline/12_water.py', cp)
    ex = os.path.join('examples', slug)
    has_data = os.path.exists(os.path.join(W, 'P.json')) or os.path.exists(os.path.join(ex, 'P.json'))
    if has_data:
        if not os.path.exists(os.path.join(W, 'P.json')):
            os.makedirs(W, exist_ok=True)
            for fn in os.listdir(ex):
                if fn.endswith('.json'): shutil.copy(os.path.join(ex, fn), W)
        run('pipeline/01_graph.py', cp)
        if os.path.isdir(ex): shutil.copy(os.path.join(W, 'P.json'), ex)
        run('pipeline/build_planner.py', cp); run('pipeline/publish.py', cp)
    else:
        run('tools/retemplate.py', cp); run('pipeline/publish.py', cp, '--hub-only')
    t = cfg.get('trips')
    if isinstance(t, str):
        run('tools/trips_geo.py', os.path.join('config', t))
        if has_data: run('pipeline/build_planner.py', cp); run('pipeline/publish.py', cp)
        else: run('tools/retemplate.py', cp)
print('done — now: git add docs config examples; git commit; git push')
