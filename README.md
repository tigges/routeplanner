# routeplanner

A journey planner for long-distance cycle tours, built from a **segment graph** (towns as nodes,
routed road segments between them, alternatives at forks) plus OpenStreetMap data cut along every
segment: elevation, facilities within 2 km (shops, beds, baths, water, stations…), scores (share on
designated cycle routes, busy-road share, named sights), and a day splitter that computes days from a
daily-effort slider instead of storing a fixed itinerary.

First built for Japan (Cape Sōya → Cape Sata, 113 towns, 126 segments); Japan ships as a ready-made
example. A new country is a config file, one or more OSM extracts, and an afternoon of machine time.

What the page does: pick start and end, choose at each fork (with the numbers for the stretch that
differs), set daily effort or a day limit (train hops are proposed), switch vehicle (bicycle / e-bike /
45 km/h speed pedelec with its own re-routed lines), zoom to a day, tap any dot or town for both name
forms and Google Maps links, save favourites, copy a link, copy the day list (CSV) or the route (GPX).

```
config/      one JSON per country (japan.json is complete; switzerland.example.json shows a new one)
planner/     template.html — the page, with /*@…@*/ placeholders for data
pipeline/    numbered steps; every step takes the config as its argument
examples/    japan/ — the finished Japan data (P.json, seg_data.json, scores, moped lines, caches)
docs/        RUNBOOK.md — how to build a country, step by step; DATA-MODEL.md — what the files contain
skill/       route-planner/SKILL.md — master copy of the Claude skill that drives these sessions
work/        (ignored) per-country working directory with all intermediate files and the built page
downloads/   (ignored) OSM extracts
```

Quick start, Japan: `python3 pipeline/01_graph.py config/japan.json && python3 pipeline/build_planner.py config/japan.json`
→ `work/japan/planner.html` (open locally); `python3 pipeline/publish.py config/japan.json` puts it on GitHub Pages.

Quick start, new country: read `docs/RUNBOOK.md`.

Requirements: Python 3.10+, `numpy scipy osmium pykakasi` (pykakasi only for Japanese romanisation),
network access to brouter.de (routing) and nominatim.openstreetmap.org (geocoding), OSM extracts from
Geofabrik. Node + Playwright only for the optional smoke test.
