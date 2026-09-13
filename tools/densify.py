"""Redraw the page lines from the routing caches, at the shape of the real road.

`make_segment` used to keep one point per kilometre, so on a map tile the route is a string of long
straight strokes. This rewrites only the `line` of every segment already in the graph — from
`route_cache.json` (and `moped_cache.json`, `signed_cache.json` for the vehicle and signed layers) —
simplified with Douglas-Peucker instead, and moves each day-end candidate onto the new line. Nothing
else changes: km, climb, effort, facilities, scores, beds and day-end names are left exactly as they
are, so no OSM scan is needed.

A cached line is used only when it is still the same road. BRouter answers differently today than it
did when some of these legs were built, so: the length must be within `--max-km-pct` of the
segment's, the typical point of the line on the page must sit within `--med-dev-u` of the cached
one, and any point further off than `--max-dev-u` must be in the first or last `--end-share` of the
leg — BRouter changing its mind about the last streets into a town is fine, a different road in the
middle is not. Legs that fail, and legs with no cached line at all, keep the coarse line and are
listed with the reason.

usage: python3 tools/densify.py config/<country>.json [--fetch] [--dry-run]
                                [--tol-m 15] [--max-km-pct 5]
                                [--max-dev-u 0.3] [--med-dev-u 0.12] [--end-share 0.2]
       --fetch   ask BRouter for the legs that have no cached line (about 2 s each), then apply
                 the same two tests; new lines are written back into the cache.
Run it on `work/<slug>/` after 01_graph and before build_planner; copy the changed files back into
`examples/<slug>/` afterwards (tools/catchup.py --densify does the whole round trip).
"""
import json, math, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pipeline'))
from common import (load_cfg, jload, jdump, Proj, hav, page_line, m_per_unit, route,
                    LINE_TOL_M, LINE_STEP_M)

def arg(name, default):
    return type(default)(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default

TOL_M    = arg('--tol-m', LINE_TOL_M)
MAXDEV_U = arg('--max-dev-u', 0.3)      # page units: 3 steps of the 0.1 the old lines were stored with
MEDDEV_U = arg('--med-dev-u', 0.12)     # the typical old point must sit at rounding distance
ENDSHARE = arg('--end-share', 0.2)      # points further off are allowed only in this share of the leg, at one end
MAXPCT   = arg('--max-km-pct', 5.0)
FETCH    = '--fetch' in sys.argv
DRY      = '--dry-run' in sys.argv

cfg, W = load_cfg()
PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'docs', cfg['slug'], 'index.html')
FROMPAGE = '--page' in sys.argv         # no work data in the repository: lift it out of the published page

def page_blocks(src, names):
    """the `var NAME=<json>;` lines a published planner carries, one per data block"""
    out = {}
    for n in names:
        m = re.search(r'^var %s=(.*?);\s*(?://.*)?$' % n, src, re.M)
        if m and m.group(1).strip() not in ('', '{}', 'null'): out[n] = json.loads(m.group(1))
    return out

if FROMPAGE:
    src = open(PAGE, encoding='utf-8').read()
    blocks = page_blocks(src, ['CFG', 'P', 'MSEG', 'SSEG'])
    if 'P' not in blocks: raise SystemExit('no P in %s' % PAGE)
    os.makedirs(W, exist_ok=True)
    jdump(W, 'proj.json', blocks['CFG']['proj']); jdump(W, 'P.json', blocks['P'])
    for n, fn in [('MSEG', 'moped_segments.json'), ('SSEG', 'signed_segments.json')]:
        if n in blocks: jdump(W, fn, blocks[n], compact=True)

PR = jload(W, 'proj.json')
if not PR: raise SystemExit('no proj.json in %s — run 01_graph first, or pass --page' % W)
pj = Proj(PR)
P = jload(W, 'P.json')
NODES = cfg.get('nodes', {}); NB = {n['id']: n for n in P['nodes']}
lat0 = sum(pj.ll(n['x'], n['y'])[0] for n in P['nodes']) / len(P['nodes'])
MPU = m_per_unit(PR, lat0)


def ll_of(nid):
    """Where a town is, in lat/lon: the config value if there is one, else back out of the page."""
    n = NODES.get(nid)
    if n and 'lat' in n: return (n['lat'], n['lon'])
    b = NB.get(nid)
    if not b: return None
    return pj.ll(b['x'], b['y'])


def read_line(s):
    return [tuple(map(float, p.split(','))) for p in s.split()] if s else []


def offsets(old_xy, new_xy):
    """How far each point of the old line sits from the new one, in page units, in order along it.

    This way round on purpose. The old line is a kilometre-spaced sample of the very same routed
    line, so if the road has not changed every old point lies on the new one, give or take the
    rounding it was stored with (0.1 unit). Measuring the other way round would just rediscover how
    far a 1 km chord cuts a corner."""
    if len(new_xy) < 2: return [0.0]
    out = []
    for px, py in old_xy:
        best = 1e18
        for (ax, ay), (bx, by) in zip(new_xy, new_xy[1:]):
            dx, dy = bx-ax, by-ay; d2 = dx*dx + dy*dy
            if d2 == 0: d = (px-ax)**2 + (py-ay)**2
            else:
                t = ((px-ax)*dx + (py-ay)*dy) / d2
                t = 0.0 if t < 0 else (1.0 if t > 1 else t)
                d = (px-(ax+t*dx))**2 + (py-(ay+t*dy))**2
            if d < best: best = d
            if best == 0: break
        out.append(math.sqrt(best))
    return out


def same_road(old_xy, new_xy):
    """Is the cached line still the road the segment was measured along? (verdict, median, far points, why)

    One number cannot tell a re-drawn street corner from a re-routed leg, so there are two tests.
    The typical point must sit at rounding distance — the leg as a whole is the same road. And where
    points do sit further off, they must all be near one end of the leg and be few: BRouter changing
    its mind about the last streets into a town is fine, a different road in the middle is not."""
    d = offsets(old_xy, new_xy); n = len(d)
    med = sorted(d)[n // 2]
    far = [i for i, x in enumerate(d) if x > MAXDEV_U]
    if med > MEDDEV_U: return False, med, far, 'a different road'
    if not far: return True, med, far, ''
    if len(far) > max(2, int(n * ENDSHARE)): return False, med, far, 'a different road'
    if far[0] >= n * (1 - ENDSHARE) or far[-1] <= n * ENDSHARE: return True, med, far, ''
    return False, med, far, 'a different road'


def move_cands(seg, line, dec):
    """Put every day-end candidate back on the new line, at the kilometre it already has."""
    cand = seg.get('cand') or []
    if not cand: return
    cum = [0.0]
    for p, q in zip(line, line[1:]): cum.append(cum[-1] + hav(p, q))
    if cum[-1] <= 0: return
    total = seg['km'] or cum[-1]; scale = total / cum[-1]
    cum = [c * scale for c in cum]
    i = 0
    for c in sorted(cand, key=lambda c: c['km']):
        k = min(max(c['km'], 0.0), total)
        while i < len(cum) - 2 and cum[i+1] < k: i += 1
        span = cum[i+1] - cum[i]; t = (k - cum[i]) / span if span > 0 else 0.0
        la = line[i][0] + (line[i+1][0] - line[i][0]) * t
        lo = line[i][1] + (line[i+1][1] - line[i][1]) * t
        x, y = pj.xy(la, lo); c['x'] = round(x, dec); c['y'] = round(y, dec)


def cached(rc, keys):
    for k in keys:
        r = rc.get(k)
        if r and r.get('line') and len(r['line']) > 2: return k, r
    return None, None


def redraw(segs, rc, label, fetch_key=None, via_of=None):
    """Rewrite the line of every segment in `segs` from the cache `rc`. Returns a report."""
    done = skipped = fetched = 0; before = after = 0; notes = []; new_keys = {}; drop = set()
    for s in segs:
        if s.get('mode') != 'ride' or not s.get('line'): continue
        old_xy = read_line(s['line']); before += len(old_xy)
        keys = [s['id'] + '#viabase', s['id'] + '@signed', s['id'], s['frm'] + '--' + s['to']]
        key, r = cached(rc, keys)
        if not r and FETCH and fetch_key:
            a, b = ll_of(s['frm']), ll_of(s['to'])
            if a and b:
                k = fetch_key(s)
                try:
                    r = route(W, k, a, b, profile=('moped' if label == 'moped' else 'trekking'),
                              cache_name=RC_NAME[label], via=(via_of(s) if via_of else ()))
                    fetched += 1; new_keys[s['id']] = k
                except SystemExit as e:
                    notes.append((s['id'], 'routing failed')); r = None
        if not r or not r.get('line'):
            skipped += 1; after += len(old_xy); notes.append((s['id'], 'no cached line')); continue
        pct = abs(r['km'] - s['km']) / max(s['km'], 0.1) * 100
        txt, new_xy, dec = page_line(PR, r['line'], tol_m=TOL_M, step_m=LINE_STEP_M)
        ok, med, far, why = same_road(old_xy, new_xy)
        if pct > MAXPCT or not ok:
            skipped += 1; after += len(old_xy); drop.add(new_keys.pop(s['id'], None))
            notes.append((s['id'], '%s now: %.1f%% km, typically %.0f m off, %d of %d points over %.0f m%s'
                          % (why or 'a longer way round', pct, med * MPU, len(far), len(old_xy), MAXDEV_U * MPU,
                             (' at %s' % '/'.join('%.0f%%' % (i / max(1, len(old_xy) - 1) * 100) for i in far[:6])) if far else ''))); continue
        s['line'] = txt; move_cands(s, r['line'], dec); done += 1; after += len(new_xy)
    # a leg we routed and then rejected must not stay in the cache: 01_graph cuts the OSM corridor
    # along the cached line, so a road we decided not to draw would quietly become the one measured.
    drop.discard(None)
    if drop and not DRY:
        cur = jload(W, RC_NAME[label], {})      # from disk: route() wrote the fetched legs there, not into rc
        for k in drop: cur.pop(k, None)
        jdump(W, RC_NAME[label], cur, compact=True)
    return dict(label=label, done=done, skipped=skipped, fetched=fetched,
                before=before, after=after, notes=notes)


RC_NAME = {'route': 'route_cache.json', 'moped': 'moped_cache.json', 'signed': 'signed_cache.json'}
CAND = json.load(open(os.path.join(W, 'cycleroute_candidates.json'), encoding='utf-8')) \
    if os.path.exists(os.path.join(W, 'cycleroute_candidates.json')) else {}
VIA = {k: c['via'] for k, c in CAND.items() if isinstance(c, dict) and c.get('via')}

reports = []; written = {}
rc = jload(W, 'route_cache.json', {})
reports.append(redraw(P['segments'], rc, 'route', fetch_key=lambda s: s['frm'] + '--' + s['to']))
if not DRY: jdump(W, 'P.json', P); written['P'] = P

for label, fn, var in [('moped', 'moped_segments.json', 'MSEG'), ('signed', 'signed_segments.json', 'SSEG')]:
    segs = jload(W, fn)
    if not segs: continue
    c = jload(W, RC_NAME[label], {})
    reports.append(redraw(list(segs.values()), c, label,
                          fetch_key=(lambda s: s['id']) if label == 'moped' else (lambda s: s['id'] + '@signed'),
                          via_of=(lambda s: VIA.get(s['id'], ())) if label == 'signed' else None))
    if not DRY: jdump(W, fn, segs, compact=True); written[var] = segs

if FROMPAGE and not DRY:
    # there is nothing to rebuild the page from, so put the redrawn blocks back into it in place
    src = open(PAGE, encoding='utf-8').read(); n0 = len(src)
    for var, obj in written.items():
        src = re.sub(r'^(var %s=).*?;\s*$' % var, lambda m: m.group(1) + json.dumps(obj, ensure_ascii=False, separators=(',', ':')) + ';',
                     src, count=1, flags=re.M)
    open(PAGE, 'w', encoding='utf-8').write(src)
    print('  wrote the redrawn lines back into docs/%s/index.html (%d -> %d bytes)' % (cfg['slug'], n0, len(src)))

print('%s — Douglas-Peucker %.0f m, coordinates to %d decimals (%.1f m per step at %.1f°)'
      % (cfg['slug'], TOL_M, max(1, min(3, int(math.ceil(math.log10(MPU / LINE_STEP_M))))),
         MPU / 10 ** max(1, min(3, int(math.ceil(math.log10(MPU / LINE_STEP_M))))), lat0))
for r in reports:
    print('  %-7s %3d redrawn, %3d kept coarse%s — %6d points -> %6d'
          % (r['label'], r['done'], r['skipped'],
             (', %d newly routed' % r['fetched']) if r['fetched'] else '', r['before'], r['after']))
    for sid, why in r['notes']: print('        %-38s %s' % (sid, why))
if DRY: print('  (dry run — nothing written)')
