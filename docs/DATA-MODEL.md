# Data model

All files live in `work/<slug>/` and are plain JSON. Map coordinates are in **planner units**
(Mercator: `x = kx·lon + bx`, `y = ky·mlat + by`, y downwards), defined by `proj.json`; the page inverts
them for Google Maps links and GPX.

## P.json — the graph
```
nodes:    [{id, name, type: terminus|handle|gateway|fork|ncr, x, y, rank, entry: 0|1, requires?: [variant]}]
segments: [{id, frm, to, variant, mode: ride|ferry, km, ascent, descent, effort, effortR, note,
            line: "x,y x,y …" (≈1 point per km), cand: [{km, eff, effR, beds, node|null, label, x, y}]}]
forks:    [{node, options: [variant, …]}]   first option = default
coast:    ["x,y x,y …", …]                  faint background outline
```
- `rank` orders nodes along the journey (start = 0); alternative-trunk nodes get interpolated ranks and
  `requires` = the variant that must be picked to reach them.
- Segment `id` = `frm--to` for the base variant, `frm--to#variant` otherwise.
- `effort` = km + climb/10 (bicycle); `effortR` the same ridden in reverse. The page recomputes both for
  the e-bike (climb/30) and the moped (km only).
- `cand` = the points a day may end at: every 8 km, every town, every bed cluster (≥ 3 beds within 3 km),
  each with cumulative effort in both directions, beds within ±3 km, and a settlement name (`label`).

## seg_data.json — per segment
```
{segid: {covered: bool, prof: [[km, m], …] (every 0.7 km), fac: {cat: [[km, off_km, name_en, name_local?], …]}}}
```
Categories: shop, stay, camp, bath, mne (road station), water, wc, bike, laundry, rail, eat.
`name_local` is present only when it differs from `name_en`.

## seg_scores.json — per segment
```
{segid: {km, route_any, route_ncn, route_rcn, busy, secondary, quiet, unknown, sights, sights_per100,
         sight_list: [[km, name_en, kind, dist_km, name_local|null], …] (≤ 60)}}
```

## Vehicle files (optional)
- `motorfree.json` `{segid: {km, share, km_blocked}}` — share of the bicycle line on ways a moped may not use.
- `moped_segments.json` `{segid: segment}` — same shape as a P.json segment, `moped: true`, effort = km.
- `moped_sd.json`, `moped_sc.json` — seg_data / seg_scores for those lines.

## Caches (keep them; they make re-runs free)
`route_cache.json` (BRouter trekking, key `frm--to`), `moped_cache.json` (BRouter moped, key = segment id),
`geo_cache.json` (Nominatim search), `rev_cache.json` (Nominatim reverse, key "lat,lon" to 3 dp).

## The page
`planner/template.html` holds the whole page; `build_planner.py` replaces `/*@CFG@*/`, `/*@P@*/`, `/*@SD@*/`,
`/*@SC@*/`, `/*@MSEG@*/`, `/*@MSD@*/`, `/*@MSC@*/`, `/*@MF@*/`. `CFG` carries title, language, projection,
fork labels, option names, skippable segments and the vehicle table. The page keeps its own state in the URL
hash (`#r=…`, everything needed to restore a route) and favourites in `localStorage`.
