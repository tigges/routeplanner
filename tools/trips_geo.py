"""Fill in the geometry of every trip in a trips file from the published pages.
For each trip it opens docs/<trip.slug>/index.html headless, walks the chain from `s` to `e` with the fork picks `p`,
and stores km, climb, effort (bicycle) and a simplified lat/lon line under `geo`. The pages of every country that
shares the trips file then draw all trips on the 'pick a trip' map, whichever page they belong to.
usage: python3 tools/trips_geo.py config/switzerland-trips.json     (needs playwright: pip install playwright)"""
import json, os, sys
from playwright.sync_api import sync_playwright
here = os.path.dirname(os.path.abspath(__file__)); root = os.path.abspath(os.path.join(here, '..'))
path = sys.argv[1]; T = json.load(open(path, encoding='utf-8'))
JS = r"""(t) => {
  var legs=t.legs||[{s:t.s,e:t.e,p:t.p}], ch=[];
  for(var i=0;i<legs.length;i++){ var L=legs[i], c=withPicks(L.p,function(){return chain(L.s,L.e);}); if(!c.length) return {error:'no chain from '+L.s+' to '+L.e}; ch=ch.concat(c); }
  var km=0,asc=0,eff=0,pts=[];
  ch.forEach(function(v){ if(v.mode!=='ride'){return;} km+=v.km; asc+=v.ascent; eff+=v.effort;
    var p=v.line.split(' ').map(function(q){var a=q.split(','); return [+a[0],+a[1]];}); if(v.rev) p.reverse(); pts=pts.concat(p); });
  // simplify (Douglas-Peucker) in page units; 0.6 unit ~ 1 km on the Swiss pages
  function dp(a,tol){ if(a.length<3) return a; var dmax=0,idx=0,A=a[0],B=a[a.length-1];
    for(var i=1;i<a.length-1;i++){ var x=a[i][0],y=a[i][1],dx=B[0]-A[0],dy=B[1]-A[1],L2=dx*dx+dy*dy,t=L2?((x-A[0])*dx+(y-A[1])*dy)/L2:0; t=Math.max(0,Math.min(1,t));
      var d=Math.hypot(x-(A[0]+t*dx),y-(A[1]+t*dy)); if(d>dmax){dmax=d;idx=i;} }
    if(dmax>tol){ var l=dp(a.slice(0,idx+1),tol), r=dp(a.slice(idx),tol); return l.slice(0,-1).concat(r); } return [A,B]; }
  var tol=km/1000; // ~ 1 unit per 1000 km of route -> keeps a few hundred points
  var sp=dp(pts,tol);
  return {km:Math.round(km), asc:Math.round(asc), eff:Math.round(eff), n:ch.length, line:sp.map(function(p){var ll=toLL(p[0],p[1]); return [+ll[0].toFixed(4),+ll[1].toFixed(4)];})};
}"""
with sync_playwright() as pw:
    b = pw.chromium.launch(); pages = {}
    for t in T['trips']:
        slug = t['slug']
        if slug not in pages:
            pg = b.new_page(); pg.goto('file://' + os.path.join(root, 'docs', slug, 'index.html')); pg.wait_for_timeout(800); pages[slug] = pg
        r = pages[slug].evaluate(JS, {k: t.get(k) for k in ('s', 'e', 'p', 'legs')})
        if 'error' in r: raise SystemExit('%s: %s' % (t['id'], r['error']))
        t['geo'] = r; print('%-4s %-22s %4d km %5d m  effort %4d  %3d points' % (t['id'], t['name'], r['km'], r['asc'], r['eff'], len(r['line'])))
    T['networks'] = {}
    for slug, pg in pages.items():          # every built leg of the page, simplified, so other pages can draw it as a ghost network
        T['networks'][slug] = pg.evaluate(r"""() => P.segments.filter(function(s){return s.line}).map(function(s){
          var pts=s.line.split(' ').map(function(q){var a=q.split(',');return [+a[0],+a[1]];});
          function dp(a,tol){ if(a.length<3) return a; var dmax=0,idx=0,A=a[0],B=a[a.length-1];
            for(var i=1;i<a.length-1;i++){ var x=a[i][0],y=a[i][1],dx=B[0]-A[0],dy=B[1]-A[1],L2=dx*dx+dy*dy,t=L2?((x-A[0])*dx+(y-A[1])*dy)/L2:0; t=Math.max(0,Math.min(1,t));
              var d=Math.hypot(x-(A[0]+t*dx),y-(A[1]+t*dy)); if(d>dmax){dmax=d;idx=i;} }
            if(dmax>tol){ var l=dp(a.slice(0,idx+1),tol), r=dp(a.slice(idx),tol); return l.slice(0,-1).concat(r); } return [A,B]; }
          return dp(pts,0.6).map(function(p){var ll=toLL(p[0],p[1]); return [+ll[0].toFixed(3),+ll[1].toFixed(3)];}); })""")
        print('network %-24s %3d legs' % (slug, len(T['networks'][slug])))
    b.close()
body = ',\n  '.join(json.dumps(t, ensure_ascii=False, separators=(',', ':')) for t in T['trips'])   # one trip per line
nets = ',\n  '.join('%s: %s' % (json.dumps(k), json.dumps(v, separators=(',', ':'))) for k, v in T['networks'].items())
open(path, 'w', encoding='utf-8').write('{\n "_comment": %s,\n "trips": [\n  %s\n ],\n "networks": {\n  %s\n }\n}\n' % (json.dumps(T.get('_comment', ''), ensure_ascii=False), body, nets))
print('wrote', path)
