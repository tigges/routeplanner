# Runbook — building a planner for a new country

Everything below is driven by one config file, `config/<country>.json`. Copy
`config/switzerland.example.json` and edit. Every pipeline step is `python3 pipeline/<step>.py config/<country>.json`
and can be re-run; steps are incremental (only new segments are processed) unless `--all` is passed.

## 0. Decide the route strategy first (a conversation, not a script)
- Start, end, and the **base trunk**: the line you would ride if there were no alternatives, as a list of
  towns roughly 40–120 km apart. Towns are the only places a fork can happen and the preferred day ends.
- **Alternative trunks** worth pricing: each one is a list of towns that starts at a town on the base trunk
  (the fork) and ends at a town on it (the rejoin). Detours to a city are the same thing with one inner town.
- Rule used for Japan: legs are scored, not hand-picked. Add every plausible alternative and let the fork
  comparison (km, climb, cycle-route share, busy roads, sights, beds) decide.
- Ferries, tunnels and other non-ride links go in `ferries` with a km figure.

## 1. Config
```
slug, title, workdir            "switzerland", "Across Switzerland", "work/switzerland"
lang                            local: OSM language code; localLabel: button text; romanise: "pykakasi" (Japanese) or null
osm.extracts                    list of .osm.pbf files (Geofabrik). Keep each under 400 MB if they must travel through the
                                Claude desktop bridge (split with PowerShell/`split`, re-join with `cat`)
nodes                           id → {name, lat, lon, type?, entry?}. Give lat/lon on a road (a station forecourt, a
                                street) — a point inside a station hall or on a lake makes BRouter answer "target island"
                                (the step tells you which node). Leave lat/lon out to geocode by name (Nominatim, slow).
trunks                          [{variant:"base", nodes:[…]}, {variant:"alpine", nodes:[fork, …, rejoin]}]
ferries                         [{from, to, km, variant?}]
forkLabels / optionNames /      the words shown on the fork buttons; defaultOptionNames names the default (first) option
defaultOptionNames              per fork node
skipRule                        optional {density, minKm}: a segment counts as a train-hop candidate for the "Days I have"
                                slider when it has at least `density` shops + eateries per km (built-up; default 25) and is
                                at least `minKm` long (default 20). Computed on the page from the facility data.
skippable / neverSkip           optional segment ids to add to, or bar from, the train-hop candidates
vehicles                        names, default slider value, min/max day per vehicle; moped.* controls step 9
graph.outline                   optional GeoJSON of the country border / coast (geoBoundaries, Natural Earth)
basemap                         turns on the online map-tile underlay and its picker (top-left of the map). Every page gets
                                four built-in choices for free — Esri "Plain map" (light grey, ≤ zoom 16), CyclOSM "Cycling
                                map", OpenTopoMap "Topographic", Esri "Satellite" — plus "auto" (plain below `switchZoom`,
                                cycling above it) and "none". `"basemap": {}` is enough to switch this on with just the
                                built-ins. Add a `sources.national` entry (`{name, url, s, min, max, attr, light}`, `{z}/{x}/
                                {y}` in `url`, `{-y}` for a TMS flipped-Y source, `s` a subdomain letter pool for `{s}`) for
                                the country's own mapping agency tiles where one exists with a public XYZ/WMTS endpoint —
                                Japan: GSI, Switzerland: swisstopo, Spain: IGN. No key needed for any of the four built-ins
                                or these three; skip `national` for a country without a no-key tile source (this is why
                                Britain's `uk`/`london` pages ship `"basemap": {}` with no national layer — Ordnance
                                Survey's are behind an API key). Leave the key out entirely to omit the picker and tiles
                                altogether, as no page needs to be dark-underlay-only anymore. `order` overrides the picker's
                                left-to-right choices; `auto.switchZoom` overrides the zoom the auto mode switches on (default
                                10). Our own coast/lake/segment SVG lines always stay on top; the tiles are a photographic
                                floor underneath them, so a slow or blocked tile host degrades gracefully to the plain
                                offline map.
```

## 2. Steps
| step | what it does | needs | time |
|---|---|---|---|
| `01_graph.py` | geocodes, routes every leg with BRouter (trekking), fits the projection, writes P.json, seg_data.json (profiles), segments/*.geojson, forks, outline | network | seconds per leg |
| `02_facilities.py` | facilities within the corridor from the OSM extracts → seg_data.json | extracts | ~5 min per extract |
| `03_scores.py` | cycle-route share, busy-road share, sights → seg_scores.json | extracts | ~10 min per extract |
| `04_beds.py` | bed counts on the split candidates, extra candidates at bed clusters | — | seconds |
| `05_names.py` | English + local name for every facility and sight | — | seconds (minutes with romanisation) |
| `06_candnames.py` | settlement name for every possible day end (Nominatim, 1/s, cached) | network | ~1 s per candidate |
| `07_cities.py` | optional: sizeable places within reach of the lines → detour / rest-day candidates | extracts | ~2 min per extract |
| `08_motorfree.py` | optional (vehicle): share of each line on cycle-only ways | extracts | ~5 min per extract |
| `09_moped.py` | optional (vehicle): moped re-routing of affected segments + their facilities/scores/names | extracts, network | as 02+03 for those segments |
| `10_cycleroutes.py` | optional: for legs with little signed-route share, stitch nearby ncn/rcn route relations along the corridor and re-route through them; writes cycleroute_candidates.json (a report, not applied). Make a good one the default with `viaBase` in the config, or offer it as a fork. | extracts, network | ~5 min per extract |
| `11_signed.py` | optional: the "Prefer signed cycle routes" switch. For each leg in `signedRoutes.legs`, rebuilds the line through the step-10 waypoints, then its facilities, scores, names, beds and day ends (writes signed_segments/sd/sc.json). `--extract <file>` does one region per run; finish with a run without it. Choose legs by how much signed route they gain, not just by extra length (on Japan 21 of 32 candidates gained under 10 points). | extracts, network | as 02+03 for those legs (~3 min per region for 11 legs) |
| `12_water.py` | optional (cosmetic): lakes of 3 km² and up plus the named big rivers (`graph.water.rivers`) from the extracts → `graph.water.file` (GeoJSON); cross-border lakes cut by every extract fall back to the outline's / `graph.water.fallback` Natural Earth shapes. Re-run `01_graph` afterwards: it projects the file into `P.water` and leaves the outline's lake features to it. | extracts | ~1 min per extract |
| `build_planner.py` | template + data → work/<slug>/planner.html and planner_pub.html | — | seconds |

Minimum viable planner: 01 → build. Everything else adds data to the same page; run 02–06 for a real one.

## 3. Publish
**GitHub Pages (the simple URL):** `python3 pipeline/publish.py config/<country>.json` copies the built page to
`docs/<slug>/index.html` and rebuilds the hub `docs/index.html`; commit and push `docs/`. Pages must be switched on once
(repository Settings → Pages → Source: Deploy from a branch → main, folder /docs). Pages are then at
`https://tigges.github.io/routeplanner/` (hub) and `https://tigges.github.io/routeplanner/<slug>/`. Each publish adds the
page (~10–15 MB) to git history; fine for now, prune later if the repository gets heavy.

**Claude artifact (optional):** `planner_pub.html` is the page without the html/head/body wrapper — publish it as a claude.ai artifact
(the Artifact tool wraps it). Republish to the same artifact to keep the link. Keep a copy of
`planner.html` in the country's Downloads/project as the offline version. The page is self-contained;
its size is roughly 8 MB per 100 segments with facilities, double that with moped lines.

## 3a. Config settings added on Japan (available to every country)
- `viaBase`: `{"a--b#variant": [[lat,lon],…]}` bends an existing leg through waypoints (onto a signed cycle route) without adding a fork.
  At present this only takes effect for a country that ships a prebuilt graph (Japan); a from-scratch country still ignores it.
- `signedRoutes`: `{"label": "Prefer signed cycle routes", "legs": ["a--b#variant", …]}` — legs that get a signed-route line behind the page switch
  (bicycle and e-bike only; the moped keeps its own line). Needs steps 10 and 11. With no `signedRoutes` the switch does not appear.
- `vehicles.kmCap`: `{"bike": 90, "ebike": 110}` the day length in km the splitter tries not to pass, per vehicle, whatever the
  effort asked for. Soft: passing it costs (quadratically, ×600), a town a few km beyond is still worth stopping at, and it never
  makes a stretch unsplittable. It is what stops a flat leg running on to the next town 140 km away. With no `kmCap` nothing changes.
  Note the trade: above roughly the default effort the cap, not the slider, decides how long a flat day is — Switzerland's longest
  day is 93 km at effort 100 and 109 km at effort 300 (before: 93 km and 217 km).
- `vehicles.targetRange`: `{"bike": [45,300], …}` the two ends of the daily-effort slider, per vehicle. `minDay`/`maxDay` stay the hard
  limits on a single day. Effort is km plus a climb penalty, so divide by the route's effort/km ratio (Japan ~1.8, Switzerland ~2.1)
  to read a slider number as km/day. Keep both ends and `defaultTarget` on the slider's step of 5. Missing `targetRange` falls back to
  `[minDay, maxDay]`.
- `tools/retemplate.py config/<country>.json` re-renders a published page with the current template for a country whose `work/` data
  is not in the repository (lifts the data blocks out of `docs/<slug>/index.html`, takes CFG from the config). Verify with
  `--verify` on a country you can build first — it must come out identical to a freshly built page.
- `trips`: the "pick a trip" front door. A list, or the name of a file in `config/` holding `{"trips": [...]}` that several pages of one
  country share (Switzerland: `switzerland-trips.json`). Each trip: `id`, `num` (the badge: a national route number, "E–W", …), `name`, `sub`,
  `note`, `kind` (`crossing` draws dashed on the picker map), `tags` (filter chips), `slug` (the page it lives on), `s`/`e`/`p` (that page's
  start, end and fork picks) — or `legs: [{s,e,p}, …]` for a trip stitched from several walks (a loop: Andermatt → Meiringen → Andermatt).
  `kind` is `crossing` or `route` (numbered, drawn bold), `pass` or `section` (drawn muted, small badge). `top` (a rank, 1–15) and `why`
  (one line from the guides) add a Top-5/10/15 marker and the reason to the card and a "top" chip that orders the list by rank. Run
  `python3 tools/trips_geo.py config/<trips file>` after any page changes: it opens the published pages headless and stores km, climb,
  effort and a lat/lon line under `geo`, which is what other pages use to draw and size a trip that is not theirs, plus every page's built
  legs under `networks` (the faint dashed network under the trips).
  A country with several pages: give the extra pages `"hub": false` so only one entry appears on the hub (`publish.py --hub-only` rebuilds the
  hub without copying a page). With trips, the sidebar heading stays the page title and the loaded trip is named in a strip on the map. With two or more trips a page opens on the picker (all trips on one map plus cards); `#trip=<id>` opens a page straight on that trip;
  `‹ Trips` in the planner goes back. Japan and Spain have no trips and open on the planner as before. Re-render every page after a
  template change: `python3 tools/retemplate.py config/<country>.json` for each.
- `vehicles.moped.dropFacilities`: categories left out of the moped data at build time (default eat, wc; they fall back to the bicycle list). Saves ~3 MB on Japan.
- Steps 02, 03 and 11 take `--extract <file>` to scan one OSM extract per run (time-limited sessions).
- `tools/densify.py config/<country>.json` redraws the page lines from the routing caches so they follow the road instead of
  cutting the corner every kilometre. It touches only each segment's `line` (and the day-end dots' positions on it) — km, climb,
  effort, facilities, scores, beds and day-end names are left alone, so no OSM scan is needed. A cached line is used only when it
  is still the same road (length within 5%, the typical point at rounding distance, anything further off confined to the first or
  last fifth of the leg); legs that fail keep the coarse line and are listed with the reason. `--fetch` routes the legs that have
  no cached line (~2 s each) and applies the same tests; a line it then rejects is dropped from the cache again, because 01_graph
  cuts the OSM corridor along the cached line. Run it on `work/<slug>/` after 01_graph and before `build_planner`, then copy
  `P.json` (and `moped_segments.json`, `signed_segments.json`) back into `examples/<slug>/`. For a country with no work data in the
  repository (Spain, Switzerland north–south) `--page` lifts the graph out of the published page and writes the redrawn lines
  straight back into it; re-render with `tools/retemplate.py` afterwards. Cost: Japan's page grew 14.3 → 15.1 MB, Britain's
  0.37 → 0.56 MB; load time unchanged.
- **Colours.** Every colour on the page is named in the `:root` block at the top of `planner/template.html` — about 70
  variables, grouped as surfaces, borders, text, accents, the map and the trip picker's map. The stylesheet reads them with
  `var(--x)`; the script, which paints the map by setting `fill` and `stroke` straight onto SVG shapes where no stylesheet rule
  can reach, reads the same names through `C("route")`. Nothing below `:root` contains a hex code, so a different look is a
  different block of values and nothing else. Names describe the role, not the shade (`--card-hi`, `--mute2`, `--maplbl-day`),
  and the same shade used for two jobs has two names, because the two jobs part company in another palette. After swapping a
  palette at runtime call `recolour()` (it drops the script's cached values) and then `render()`.
  `tools/preview.js <page.html> <palette.css> <out.png> [tripId] [zoom]` does exactly that against a built page, so a palette can
  be seen before anything is committed.
- `tools/pixcheck.js <page.html> <out-dir> [tripId]` screenshots a page in ten states (picker, a loaded trip, zoomed, facility
  layers, the moped, friendliness colours, a selected leg, light and no map, folds closed) with real tiles. Run it on two builds
  and compare the images to prove a change alters nothing it should not. Compare with Pillow, not by eye — and when images differ,
  re-run the reference against itself first: a tile that has not arrived yet shows up as tens of thousands of changed pixels.
- `tools/ridecheck.js <a.html> <b.html> [tripsFile] [slug]` opens two builds of a page headless and prints every trip's km, climb,
  effort and leg count side by side, with console errors and page weight — the test ride to run before handing over any change
  that should not move the numbers. `tools/shot.js <page.html> <prefix> [tripId] [zoom]` screenshots a page with real map tiles
  (the sandbox proxy blocks the browser from the tile hosts but not curl, so each tile request is fulfilled from a curl).
- `tools/segfiles.py config/<country>.json` writes `work/<slug>/segments/*.geojson` back from an existing P.json and the routing
  cache. The per-segment files live in `work/`, which is not committed, so a fresh clone has the graph but not the files, and
  `01_graph` would then re-make every segment and throw its facilities, scores and day-end names away (a full 02/03 rescan, an hour).
  Run this straight after copying `examples/<slug>/*.json` into `work/<slug>/` and only the legs that really changed are rebuilt.
- `tools/fix_effr.py config/<country>.json [--page]` recomputes every day-end candidate's `effR` from the stored profile (no routing,
  no scan). `effR` is what the leg costs ridden the other way; it used to be stored as the forward climb still to come, so any stretch
  a journey walks backwards was split in the wrong places. Fixed in `common.make_segment` for anything built since; this tool brings
  older data up to date, in `work/`+`examples/` or, with `--page`, in the `var P=` block of the published page (then re-render).
- Tools named in this runbook that are **not in the repository**: `densify.py`, `preview.js`, `pixcheck.js`, `shot.js` (and so
  `catchup.py --densify`). Write them again rather than hunting for them.
- `tools/catchup.py config/<a>.json config/<b>.json` brings a country's page up to the current template and data layers in one go: downloads missing extracts (`osm.urls`, or `osm.mirror` paths on download.openstreetmap.fr), runs step 12, refreshes the graph (01 where the data is in work/ or examples/, else retemplate, which now injects the water into the lifted P), rebuilds, publishes, re-measures trips. `--densify` adds the line redraw above (with `--fetch` to route what is not cached), on whichever of the two paths the country takes. Needs `pip install osmium shapely numpy scipy playwright` once. Then `git add docs config examples`, commit, push.
- `graph.land_fill: true` paints the country in a land tone (only for a closed border like Switzerland or Spain; Japan's coast comes in pieces and stays a line).
- Background jobs in the Claude sandbox are killed when a tool call ends unless started with `setsid nohup … &`.

## 4. Adding to an existing country
Edit the config (a new trunk, a detour, a renamed fork) and re-run the steps in order. Routing, geocoding
and reverse-geocoding are cached; unchanged segments keep their facilities, beds and names; only new
segments are scanned. Never edit `work/` files by hand — they are rebuilt.

## 5. Things learned on Japan (don't rediscover)
- Cut days at town nodes and bed clusters, never at a fixed km — day lengths drift otherwise.
- The "cycle route" score is the share of the line within 300 m of an OSM bicycle route relation; "busy"
  is the share whose nearest road is trunk/primary; sights are a raw count of named tourism/historic/
  natural points within 2 km (relative measure, not absolute).
- Compare fork options **pairwise against the default** on the stretch that differs; comparing "the stretch
  common to all options" dilutes a small detour against a whole-trunk choice.
- Romanised readings of place-name kanji are sometimes wrong; always keep the local form.
- Facility names come from OSM `name`/`name:en`; expect half of them to be local-only outside big cities.
- BRouter's moped profile is shorter but sometimes busier; keep the bicycle line where mopeds may push
  (tunnels), and sanity-check any moped leg more than 3× the bicycle length (step 9 does).
- Nominatim: one request per second, a real User-Agent, cache everything.
- Anything that decides "is there room to draw this" belongs on pixels, not on map units. Town labels and the
  road-station/sight layer were gated on `vb[2]` alone, so a wide monitor — more pixels, more room — showed
  *fewer* labels than a laptop, and the hint's "~60 km" was only true at one window shape. `detailLimit(base)`
  scales the threshold with the map pane's width and never goes below `base`, so a wide pane gains and a narrow
  one or a phone keeps what it had.
- Clicking a day must never widen the view: on a one-day trip the day is the whole route, so re-framing it only
  added margin and switched the sights off. `zoomDay` now pads like the trip fit and clamps to the current width.
- Overpass is not reachable from the sandbox. Geofabrik IS reachable (curl -L follows to the dated file);
  a session can download the country extracts straight into downloads/ (all Japan regions ~2.4 GB in a few minutes).
