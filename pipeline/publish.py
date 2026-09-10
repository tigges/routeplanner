"""Publish a country's planner to the GitHub Pages folder.
usage: python3 pipeline/publish.py config/<country>.json
copies <workdir>/planner.html to docs/<slug>/index.html and rebuilds docs/index.html (the hub page) from docs/countries.json.
Then: git add docs && git commit -m "publish <slug>" && git push  ->  https://<user>.github.io/routeplanner/<slug>/"""
import json, os, sys, shutil, datetime
here = os.path.dirname(os.path.abspath(__file__)); root = os.path.join(here, '..'); docs = os.path.join(root, 'docs')
cfg = json.load(open(sys.argv[1])); slug = cfg['slug']
os.makedirs(os.path.join(docs, slug), exist_ok=True)
shutil.copy(os.path.join(root, cfg['workdir'], 'planner.html'), os.path.join(docs, slug, 'index.html'))
lst = os.path.join(docs, 'countries.json'); C = json.load(open(lst)) if os.path.exists(lst) else []
C = [c for c in C if c['slug'] != slug] + [dict(slug=slug, title=cfg['title'], published=datetime.date.today().isoformat())]
C.sort(key=lambda c: c['title']); json.dump(C, open(lst, 'w'), indent=1)
rows = ''.join('<li><a href="%s/">%s</a> <span>published %s</span></li>' % (c['slug'], c['title'], c['published']) for c in C)
open(os.path.join(docs, 'index.html'), 'w', encoding='utf-8').write('''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Journey planners</title>
<style>body{margin:0;padding:40px 24px;background:#111;color:#eee;font:16px/1.5 -apple-system,Segoe UI,Helvetica,Arial,sans-serif}
main{max-width:560px;margin:0 auto}h1{font-weight:600;font-size:22px;margin:0 0 6px}p{color:#aaa;margin:0 0 28px}
ul{list-style:none;padding:0;margin:0}li{padding:14px 0;border-top:1px solid #333}li:last-child{border-bottom:1px solid #333}
a{color:#fff;font-size:18px;text-decoration:none}a:hover{text-decoration:underline}li span{display:block;color:#888;font-size:13px}
footer{margin-top:28px;color:#666;font-size:13px}footer a{color:#888;font-size:13px}</style></head><body><main>
<h1>Journey planners</h1><p>Cycle-tour planners: pick start, end, route choices, vehicle and daily effort; the days are computed.</p>
<ul>%s</ul>
<footer>Built with <a href="https://github.com/tigges/routeplanner">tigges/routeplanner</a>.</footer></main></body></html>''' % rows)
print('published', slug, '->', 'docs/%s/index.html' % slug)
