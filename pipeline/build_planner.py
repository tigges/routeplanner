"""Assemble the planner page from the template and a country's data.
usage: python3 pipeline/build_planner.py config/<country>.json
reads  <workdir>/P.json, seg_data.json, seg_scores.json, proj.json and (if present) moped_segments.json,
       moped_sd.json, moped_sc.json, motorfree.json
writes <workdir>/planner.html (standalone) and <workdir>/planner_pub.html (body only, for publishing as an artifact)."""
import json, os, sys
cfg = json.load(open(sys.argv[1])); W = cfg['workdir']
here = os.path.dirname(os.path.abspath(__file__)); tpl = open(os.path.join(here, '..', 'planner', 'template.html'), encoding='utf-8').read()
def load(name, default='{}'):
    p = os.path.join(W, name)
    return open(p, encoding='utf-8').read() if os.path.exists(p) else default
proj = json.load(open(os.path.join(W, 'proj.json')))
mf = json.load(open(os.path.join(W, 'motorfree.json'))) if os.path.exists(os.path.join(W, 'motorfree.json')) else {}
page_cfg = dict(title=cfg['title'], lang=cfg['lang'], proj=proj, forkLabels=cfg.get('forkLabels', {}), optionNames=cfg.get('optionNames', {}),
                defaultOptionNames=cfg.get('defaultOptionNames', {}), skippable=cfg.get('skippable', []), neverSkip=cfg.get('neverSkip', []), skipRule=cfg.get('skipRule'), vehicles=cfg['vehicles'])
subs = {'CFG': json.dumps(page_cfg, ensure_ascii=False), 'P': load('P.json'), 'SD': load('seg_data.json'), 'SC': load('seg_scores.json'),
        'MSEG': load('moped_segments.json'), 'MSD': load('moped_sd.json'), 'MSC': load('moped_sc.json'),
        'MF': json.dumps({k: v['share'] for k, v in mf.items()})}
s = tpl
for k, v in subs.items():
    ph = '/*@%s@*/' % k; assert s.count(ph) == 1, k; s = s.replace(ph, v)
open(os.path.join(W, 'planner.html'), 'w', encoding='utf-8').write(s)
i = s.find('<title>'); j = s.find('</head>'); k = s.find('<body>') + 6; l = s.rfind('</body>')
open(os.path.join(W, 'planner_pub.html'), 'w', encoding='utf-8').write(s[i:j] + '\n' + s[k:l] + '\n')
print('planner.html', len(s), 'bytes')
