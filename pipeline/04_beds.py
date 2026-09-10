"""Step 4 — real lodging counts on every split candidate (beds within ±3 km along the line) and extra
candidates at bed clusters, so day ends land where beds are. Works on P.json; --moped / --signed for the moped or signed-route lines."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
cfg, W = load_cfg(); LAYER = 'signed' if '--signed' in sys.argv else 'moped'; moped = '--moped' in sys.argv or '--signed' in sys.argv
if moped: MS = jload(W, LAYER + '_segments.json'); segs = list(MS.values()); SD = jload(W, LAYER + '_sd.json')
else: P = jload(W, 'P.json'); segs = P['segments']; SD = jload(W, 'seg_data.json')
n_upd = n_add = 0
for s in segs:
    if s['mode'] != 'ride' or s['id'] not in SD: continue
    stays = sorted(x[0] for x in SD[s['id']]['fac'].get('stay', []))
    beds_at = lambda km: sum(1 for k in stays if abs(k - km) <= 3)
    cand = s['cand']
    for c in cand[:-1]: c['beds'] = beds_at(c['km']); n_upd += 1
    have = [c['km'] for c in cand]; line = [tuple(map(float, p.split(','))) for p in s['line'].split()]
    L = [0.0]
    for a, b in zip(line, line[1:]): L.append(L[-1] + ((b[0]-a[0])**2 + (b[1]-a[1])**2) ** .5)
    tot = L[-1] or 1; k = 4.0
    while k < s['km'] - 4:
        if beds_at(k) >= 3 and all(abs(k - h) > 4 for h in have):
            f = k / s['km'] * tot; i = max(0, min(len(L)-2, next((j for j in range(len(L)-1) if L[j+1] >= f), len(L)-2)))
            t = (f - L[i]) / ((L[i+1]-L[i]) or 1); x = line[i][0] + (line[i+1][0]-line[i][0])*t; y = line[i][1] + (line[i+1][1]-line[i][1])*t
            before = [c for c in cand if c['km'] <= k]; after = [c for c in cand if c['km'] > k]
            prev = max(before, key=lambda c: c['km']) if before else dict(km=0.0, eff=0.0, effR=float(s['effort']))
            nxt = min(after, key=lambda c: c['km']) if after else dict(km=float(s['km']), eff=float(s['effort']), effR=0.0)
            tt = (k - prev['km']) / ((nxt['km'] - prev['km']) or 1)
            e = prev['eff'] + (nxt['eff'] - prev['eff']) * tt; eR = prev['effR'] + (nxt['effR'] - prev['effR']) * tt
            cand.append(dict(km=round(k, 1), eff=round(e, 1), effR=round(eR, 1), beds=beds_at(k), node=None, label='', x=round(x, 1), y=round(y, 1)))
            have.append(k); n_add += 1
        k += 2.0
    cand.sort(key=lambda c: (c['km'], c['node'] is not None)); s['cand'] = cand
if moped: jdump(W, LAYER + '_segments.json', MS)
else: jdump(W, 'P.json', P)
print('beds on %d candidates, %d bed-cluster candidates added' % (n_upd, n_add))
