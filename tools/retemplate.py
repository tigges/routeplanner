"""Re-render an already published page with the current template, without rebuilding the country's data.
For a country whose work/ data is not in the repository (no OSM run possible in this session), this lifts the data
blocks out of docs/<slug>/index.html and puts them into planner/template.html, so template fixes reach every country.
CFG is taken from the config file, not the old page, so config changes apply too.
Verify it first on a country you can build: `--verify <slug>` re-renders that country's published page and compares
it with a freshly built planner.html.
usage: python3 tools/retemplate.py config/<country>.json [--verify]"""
import json, os, re, sys
def load_trips(cfg, cfgpath):
    """`trips` in the config: a list, or the name of a file in config/ holding {"trips": [...]} (shared by several pages)."""
    t = cfg.get('trips'); nw = {}
    if isinstance(t, str):
        d = json.load(open(os.path.join(os.path.dirname(os.path.abspath(cfgpath)), t), encoding='utf-8')); t = d['trips']; nw = d.get('networks', {})
    return t or cfg.get('crossings', []), nw
here = os.path.dirname(os.path.abspath(__file__)); root = os.path.join(here, '..')
cfg = json.load(open(sys.argv[1])); slug = cfg['slug']
page = os.path.join(root, 'docs', slug, 'index.html')
tpl = open(os.path.join(root, 'planner', 'template.html'), encoding='utf-8').read()
src = open(page, encoding='utf-8').read()
NAMES = ['P', 'SD', 'SC', 'MSEG', 'MSD', 'MSC', 'MF', 'SSEG', 'SSD', 'SSC']
def grab(name):
    """the value of `var NAME=<json>;` at the start of a line in the published page"""
    m = re.search(r'^var %s=(.*?);\s*(?://.*)?$' % name, src, re.M)
    return m.group(1) if m else '{}'
TRIPS, NETWORKS = load_trips(cfg, sys.argv[1])
page_cfg = dict(title=cfg['title'], slug=cfg['slug'], by=cfg.get('by', ''), pickerDefault=cfg.get('pickerDefault', 'all'), landFill=bool(cfg.get('graph', {}).get('land_fill')), trips=TRIPS, networks=NETWORKS, lang=cfg['lang'], proj=json.loads(grab('CFG'))['proj'] if re.search(r'^var CFG=', src, re.M) else None,
                forkLabels=cfg.get('forkLabels', {}), optionNames=cfg.get('optionNames', {}),
                defaultOptionNames=cfg.get('defaultOptionNames', {}), skippable=cfg.get('skippable', []),
                neverSkip=cfg.get('neverSkip', []), skipRule=cfg.get('skipRule'), vehicles=cfg['vehicles'],
                signedRoutes={'label': cfg.get('signedRoutes', {}).get('label', 'Prefer signed cycle routes')})
if page_cfg['proj'] is None: raise SystemExit('no CFG in %s' % page)
subs = {'CFG': json.dumps(page_cfg, ensure_ascii=False)}
for n in NAMES: subs[n] = grab(n)
sys.path.insert(0, os.path.join(root, 'pipeline'))
from common import Proj, water_block                      # a country without work/ data still gets step 12's water: projected here into the lifted P
water = water_block(cfg, Proj(page_cfg['proj']))
if water:
    P = json.loads(subs['P']); P['water'] = water; subs['P'] = json.dumps(P, ensure_ascii=False, separators=(',', ':')); print('water:', len(water['lakes']), 'lake shapes', len(water['rivers']), 'river pieces')
subs['PRESETS'] = json.dumps(cfg.get('presets', []), ensure_ascii=False)
out = tpl
for k, v in subs.items():
    ph = '/*@%s@*/' % k; assert out.count(ph) == 1, k; out = out.replace(ph, v)
if '--verify' in sys.argv:
    built = open(os.path.join(cfg['workdir'], 'planner.html'), encoding='utf-8').read()
    print('identical to a freshly built page' if built == out else 'DIFFERENT from the freshly built page (%d vs %d bytes)' % (len(built), len(out)))
    sys.exit(0 if built == out else 1)
open(page, 'w', encoding='utf-8').write(out)
print('re-rendered', page, len(out), 'bytes')
