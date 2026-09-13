"""Recompute every day-end candidate's `effR` from the stored profile — no routing, no OSM scan.

`effR` is what a day costs when the leg is ridden the other way. It used to be stored as "the forward
effort still to come", which counts the wrong hill and adds up to the forward total instead of the
reverse one, so any stretch a journey walks backwards got its days in the wrong places (on the Albula
that was an 8 km "day" with the effort of 114). common.make_segment now computes it properly; this
brings the data that was built before that up to date.

Works on the country's graph wherever it lives: work/<slug>/P.json (+ examples/<slug>/P.json) when the
data is in the repository, otherwise the `var P=…` block of docs/<slug>/index.html. Re-render or rebuild
the page afterwards.
usage: python3 tools/fix_effr.py config/<country>.json
"""
import json, os, re, shutil, sys
here = os.path.dirname(os.path.abspath(__file__)); root = os.path.abspath(os.path.join(here, '..')); os.chdir(root)
cfg = json.load(open(sys.argv[1], encoding='utf-8')); slug = cfg['slug']; W = cfg['workdir']
CLIMB_DIV = 10.0

def fix(P, SD):
    n = 0
    for s in P['segments']:
        if s.get('mode') != 'ride': continue
        prof = (SD.get(s['id']) or {}).get('prof')
        if not prof or not s.get('cand'): continue
        gain = max(1, sum(max(0, q[1] - p[1]) for p, q in zip(prof, prof[1:])))
        f = (s.get('ascent') or 0) / gain
        drop = []                                   # descent from each profile point to the end of the leg
        acc = 0.0
        for p, q in zip(reversed(prof[:-1]), reversed(prof[1:])): acc += max(0, p[1] - q[1]); drop.append((p[0], acc))
        drop.reverse()
        def desc_from(kk):
            for ka, a in drop:
                if ka >= kk: return a
            return 0.0
        for c in s['cand']:
            c['effR'] = 0.0 if c.get('node') else round((s['km'] - c['km']) + desc_from(c['km']) / CLIMB_DIV * f, 1)
        n += 1
    return n

def blocks(page):
    src = open(page, encoding='utf-8').read()
    def grab(name):
        m = re.search(r'^var %s=(.*?);\s*(?://.*)?$' % name, src, re.M)
        return (m.group(1) if m else '{}'), m
    return src, grab

pw = os.path.join(W, 'P.json'); ex = os.path.join('examples', slug)
if not os.path.exists(pw) and os.path.exists(os.path.join(ex, 'P.json')):
    os.makedirs(W, exist_ok=True)
    for fn in os.listdir(ex):
        if fn.endswith('.json'): shutil.copy(os.path.join(ex, fn), W)
if os.path.exists(pw) and '--page' not in sys.argv:
    for a, b in (('moped_segments.json', 'moped_sd.json'), ('signed_segments.json', 'signed_sd.json')):   # the moped and signed-route lines carry their own candidates
        fa, fb = os.path.join(W, a), os.path.join(W, b)
        if os.path.exists(fa) and os.path.exists(fb):
            segs = json.load(open(fa, encoding='utf-8')); sd = json.load(open(fb, encoding='utf-8'))
            k = fix({'segments': list(segs.values()) if isinstance(segs, dict) else segs}, sd)
            json.dump(segs, open(fa, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
            if os.path.isdir(ex): shutil.copy(fa, ex)
            print(slug + ':', a, '—', k, 'segments')
if os.path.exists(pw) and '--page' not in sys.argv:
    P = json.load(open(pw, encoding='utf-8')); SD = json.load(open(os.path.join(W, 'seg_data.json'), encoding='utf-8'))
    n = fix(P, SD)
    json.dump(P, open(pw, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    if os.path.isdir(ex): shutil.copy(pw, ex)
    print(slug + ': effR recomputed on', n, 'segments in', pw)
else:
    page = os.path.join('docs', slug, 'index.html')
    src, grab = blocks(page)
    ptxt, pm = grab('P'); stxt, _ = grab('SD')
    if not pm: raise SystemExit('no P block in ' + page)
    P = json.loads(ptxt); SD = json.loads(stxt); n = fix(P, SD)
    out = src[:pm.start(1)] + json.dumps(P, ensure_ascii=False, separators=(',', ':')) + src[pm.end(1):]
    open(page, 'w', encoding='utf-8').write(out)
    print(slug + ': effR recomputed on', n, 'segments in', page)
