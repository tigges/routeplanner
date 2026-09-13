"""Shared helpers for the route-planner pipeline. Every step takes the country config as argv[1]."""
import json, math, os, sys, time, urllib.request, urllib.parse, urllib.error
R = 6371.0088
UA = {'User-Agent': 'route-planner/1.0 (github.com/tigges/routeplanner)'}

def load_cfg():
    cfg = json.load(open(sys.argv[1])); W = cfg['workdir']; os.makedirs(W, exist_ok=True)
    return cfg, W
def jload(W, name, default=None):
    p = os.path.join(W, name)
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else default
def jdump(W, name, obj, compact=False):
    with open(os.path.join(W, name), 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, **({'separators': (',', ':')} if compact else {}))

def hav(a, b):
    la1, lo1 = map(math.radians, a[:2]); la2, lo2 = map(math.radians, b[:2])
    h = math.sin((la2-la1)/2)**2 + math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
    return 2*R*math.asin(math.sqrt(h))
def densify(pts, gap):
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        n = int(hav(a, b) // gap)
        for i in range(1, n+1):
            f = i/(n+1); out.append((a[0]+(b[0]-a[0])*f, a[1]+(b[1]-a[1])*f))
        out.append(b)
    return out
def decimate(pts, step_km=1.0):
    out = [pts[0]]; acc = 0
    for a, b in zip(pts, pts[1:]):
        acc += hav(a, b)
        if acc >= step_km: out.append(b); acc = 0
    if out[-1] is not pts[-1]: out.append(pts[-1])
    return out

# --- map projection: Mercator, x = kx*lon + bx ; y = ky*mlat + by (y grows downwards) ---------
def mlat(lat): return math.log(math.tan(math.pi/4 + math.radians(lat)/2))
class Proj:
    def __init__(self, PR): self.kx, self.bx, self.ky, self.by = PR['kx'], PR['bx'], PR['ky'], PR['by']
    def xy(self, lat, lon): return (self.kx*lon + self.bx, self.ky*mlat(lat) + self.by)
    def ll(self, x, y):
        lon = (x - self.bx) / self.kx; m = (y - self.by) / self.ky
        return math.degrees(2*math.atan(math.exp(m)) - math.pi/2), lon
def fit_proj(points, width=520.0):
    """Choose the projection so the given lat/lon points span `width` map units horizontally."""
    lons = [p[1] for p in points]; ms = [mlat(p[0]) for p in points]
    lat0 = sum(p[0] for p in points) / len(points)
    kx = width / (max(lons) - min(lons)); ky = -kx * 180 / math.pi     # lon is in degrees, mlat in radians; equal scaling, y downwards
    return dict(kx=kx, bx=-kx*min(lons), ky=ky, by=-ky*max(ms))

# --- geocoding and routing, both cached in the workdir -----------------------------------------
def geocode(W, nid, query):
    cache = jload(W, 'geo_cache.json', {})
    if nid in cache: return cache[nid][:2]
    url = 'https://nominatim.openstreetmap.org/search?' + urllib.parse.urlencode({'q': query, 'format': 'json', 'limit': 1})
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r: res = json.load(r)
    time.sleep(1.1)
    if not res: raise SystemExit('no geocode result for %s (%s) — give lat/lon in the config' % (nid, query))
    cache[nid] = (float(res[0]['lat']), float(res[0]['lon']), res[0]['display_name'][:80]); jdump(W, 'geo_cache.json', cache)
    print('geocoded', nid, cache[nid], flush=True); return cache[nid][:2]
def route(W, key, a_ll, b_ll, profile='trekking', cache_name='route_cache.json', via=()):
    """BRouter leg a→b; via = optional list of (lat, lon) waypoints the line must pass (used to follow a cycle route)."""
    rt = jload(W, cache_name, {})
    if key in rt: return rt[key]
    pts = [a_ll] + [tuple(v) for v in via] + [b_ll]
    url = 'https://brouter.de/brouter?lonlats=%s&profile=%s&alternativeidx=0&format=geojson' % ('|'.join('%.5f,%.5f' % (lo, la) for la, lo in pts), profile)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=180) as r: gj = json.load(r)
            f = gj['features'][0]; pr = f['properties']; coords = f['geometry']['coordinates']
            rt[key] = dict(km=round(float(pr['track-length'])/1000, 1), asc=int(pr['filtered ascend']),
                           line=[[round(c[1], 5), round(c[0], 5), int(c[2]) if len(c) > 2 else None] for c in coords])
            jdump(W, cache_name, rt); time.sleep(1.5)
            print('routed %-34s %6.1f km  +%4d m  (%s)' % (key, rt[key]['km'], rt[key]['asc'], profile), flush=True)
            return rt[key]
        except urllib.error.HTTPError as e:
            msg = e.read().decode('utf-8', 'ignore')[:120]
            if e.code == 400: raise SystemExit('routing failed for %s: %s — a node is probably not on a road (inside a station, lake or building); move its lat/lon a little' % (key, msg))
            print('route retry', key, attempt, e, flush=True); time.sleep(8)
        except Exception as e:
            print('route retry', key, attempt, e, flush=True); time.sleep(8)
    raise SystemExit('routing failed: ' + key)

# --- a planner segment from a routed line ---------------------------------------------------------
def make_segment(P, sid, a, b, variant, r, climb_div=10.0):
    """Planner segment dict + seg_data entry (profile) from a BRouter result r = {km, asc, line}."""
    pj = Proj(P); line = r['line']; cum = [0.0]
    for p, q in zip(line, line[1:]): cum.append(cum[-1] + hav(p, q))
    scale = r['km'] / cum[-1] if cum[-1] else 1; cum = [c * scale for c in cum]
    ele = [p[2] if p[2] is not None else 0 for p in line]
    step = 0.7; prof = []; k = 0.0; i = 0
    while k <= r['km'] + 1e-6:
        while i < len(cum) - 2 and cum[i+1] < k: i += 1
        t = (k - cum[i]) / (cum[i+1] - cum[i]) if cum[i+1] > cum[i] else 0
        prof.append([round(k, 1), int(round(ele[i] + (ele[i+1] - ele[i]) * t))]); k += step
    z = [p[1] for p in prof]; zs = [z[0]] + [sorted(z[j-1:j+2])[1] for j in range(1, len(z)-1)] + [z[-1]]
    prof = [[p[0], v] for p, v in zip(prof, zs)]
    asc = r['asc']; gain = max(1, sum(max(0, q - p) for p, q in zip(zs, zs[1:])))
    desc = int(round(sum(max(0, p - q) for p, q in zip(zs, zs[1:])) * (asc / gain)))
    effort = int(round(r['km'] + asc / climb_div)); effortR = int(round(r['km'] + desc / climb_div))
    xy = [pj.xy(p[0], p[1]) for p in decimate(line, 1.0)]
    def eff_at(kk): return kk + sum(max(0, q - p) for (ka, p), (kb, q) in zip(prof, prof[1:]) if kb <= kk) / climb_div * (asc / gain)
    cand = []; kk = 0.0
    while kk < r['km'] - 4 or kk == 0.0:
        idx = min(range(len(cum)), key=lambda q: abs(cum[q] - kk)); px, py = pj.xy(line[idx][0], line[idx][1]); e = eff_at(kk)
        cand.append(dict(km=round(kk, 1), eff=round(e, 1), effR=round(effort - e, 1), beds=1, node=None, label='', x=round(px, 1), y=round(py, 1)))
        kk += 8.0
    cand.append(dict(km=r['km'], eff=float(effort), effR=0.0, beds=0, node=b, label='', x=round(xy[-1][0], 1), y=round(xy[-1][1], 1)))
    seg = dict(id=sid, frm=a, to=b, variant=variant, mode='ride', km=r['km'], ascent=asc, note='', effort=effort, descent=desc,
               effortR=effortR, line=' '.join('%.1f,%.1f' % p for p in xy), cand=cand)
    return seg, dict(covered=False, prof=prof, fac={})

def seg_geojson(sid, line):
    return {'type': 'Feature', 'properties': {'id': sid}, 'geometry': {'type': 'LineString', 'coordinates': [[p[1], p[0]] for p in line]}}
def seg_fn(sid): return sid.replace('#', '__') + '.geojson'
def seg_id(fn): return fn[:-8].replace('__', '#')


def water_block(cfg, pj):
    """P.water from graph.water.file (step 12), projected: lakes as filled shapes, big rivers as lines. None when there is no file."""
    wf = (cfg.get('graph', {}).get('water') or {}).get('file')
    if not wf or not os.path.exists(wf): return None
    wg = json.load(open(wf)); water = dict(lakes=[], rivers=[])
    for f in wg['features']:
        pr = f.get('properties') or {}; geo = f['geometry']
        if pr.get('kind') == 'lake':
            polys = geo['coordinates'] if geo['type'] == 'MultiPolygon' else [geo['coordinates']]
            for poly in polys:
                pts = decimate([(c[1], c[0]) for c in poly[0]], 0.3)
                if len(pts) > 2: water['lakes'].append(dict(name=pr.get('name', ''), km2=pr.get('km2', 0), pts=' '.join('%.1f,%.1f' % pj.xy(*q) for q in pts)))
        elif pr.get('kind') == 'river':
            pts = decimate([(c[1], c[0]) for c in geo['coordinates']], 0.3)
            if len(pts) > 1: water['rivers'].append(dict(name=pr.get('name', ''), pts=' '.join('%.1f,%.1f' % pj.xy(*q) for q in pts)))
    return water
