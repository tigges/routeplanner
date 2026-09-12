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
- Overpass is not reachable from the sandbox. Geofabrik IS reachable (curl -L follows to the dated file);
  a session can download the country extracts straight into downloads/ (all Japan regions ~2.4 GB in a few minutes).
