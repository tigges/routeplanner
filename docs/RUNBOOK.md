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
| `build_planner.py` | template + data → work/<slug>/planner.html and planner_pub.html | — | seconds |

Minimum viable planner: 01 → build. Everything else adds data to the same page; run 02–06 for a real one.

## 3. Publish
`planner_pub.html` is the page without the html/head/body wrapper — publish it as a claude.ai artifact
(the Artifact tool wraps it). Republish to the same artifact to keep the link. Keep a copy of
`planner.html` in the country's Downloads/project as the offline version. The page is self-contained;
its size is roughly 8 MB per 100 segments with facilities, double that with moped lines.

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
- Geofabrik downloads and Overpass are not reachable from the Claude cloud sandbox; the user downloads
  the extracts and the session stages them through the desktop bridge (400 MB per file).
