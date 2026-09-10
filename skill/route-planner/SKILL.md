---
name: route-planner
description: "Build or extend a country cycle-tour journey planner (segment graph + OSM data + published planner page) using the tigges/routeplanner repository. Use for a new country, a new trunk or detour, an extra data layer (vehicles, signed cycle routes), or a republish."
---

# Route planner (tigges/routeplanner)

The planner is a segment graph (towns as nodes, routed road segments, forks with alternatives) plus
OpenStreetMap data cut along every segment, assembled into one self-contained HTML page. Everything is
driven by `config/<country>.json`. Japan is the finished reference; a new country is a config plus OSM extracts.

## Start of any session
1. Clone fresh every session: `git clone https://github.com/tigges/routeplanner` (public). Run `git log --oneline -5`
   to see where things stand. Never patch against an older copy, a project file or a previous sandbox.
2. Read `docs/RUNBOOK.md` and, for data questions, `docs/DATA-MODEL.md`. The runbook is the authority: where it
   and this skill disagree, follow the runbook and say so. Don't rebuild anything the runbook says is cached or shipped.
3. Check the country's project docs for decisions already taken; don't reopen them.

## New country
- Agree the route strategy in conversation first: start, end, base trunk (towns 40–120 km apart), the
  alternative trunks worth pricing, ferries. Legs are scored by the pipeline, not hand-picked.
- Copy `config/switzerland.example.json`, fill nodes (lat/lon on a road), trunks, names, vehicle table.
- Run `01_graph` → `build_planner` first and publish a minimal planner; then `02`–`06`, republish.
  Optional layers only when asked: `07` (cities), `08`/`09` (moped), `10`/`11` (signed cycle routes, see below).

## Map data and long jobs
- Download OSM extracts straight from Geofabrik inside the sandbox (`curl -L`, a few seconds per file); fetch only
  the regions the work touches. Charles no longer needs to stage files.
- Background jobs die when a tool call ends unless started with `setsid nohup … &`; then poll with `sleep`.
  In the foreground keep each call under ~280 s: steps 02, 03 and 11 take `--extract <file>` for one region per run.
- Rough timings on Japan: a region takes 3–7 min per scanning step; Nominatim naming ~1 s per day end.

## Extending a country
Edit the config (new trunk = list of towns from a fork town to a rejoin town) and re-run the steps in
order; unchanged segments keep their data, caches make routing free.
- Signed cycle routes: `10_cycleroutes.py` finds, for weak legs, a line through nearby signed routes (a report).
  Pick legs by how much signed-route share they gain (aim for 10+ points), not by extra length alone; most
  candidates gain little. List them in `signedRoutes.legs` and run `11_signed.py` for the page switch, or
  put a single leg in `viaBase` to make its signed line the default (viaBase currently works only for a country
  with a prebuilt graph, i.e. Japan).
- Anything that took long to compute must end up in the repository (config or `examples/<country>/`); `work/`
  is not committed and the sandbox is temporary.

## Test, publish, hand over
- Test the built page in a headless browser before handing it over (Playwright is available; `tools/smoke.js`
  exists): the changed controls in each state, the default journey's days/km, no console errors.
- Publish with `python3 pipeline/publish.py config/<country>.json` → `docs/<slug>/index.html` and the hub; GitHub
  Pages serves `https://tigges.github.io/routeplanner/<slug>/`. (The old Artifact-tool publishing is retired.)
- Hand Charles one patch: `git add -A`, then `git diff --cached --binary > /mnt/user-data/outputs/<name>.patch`.
  Check it with `git apply --check` on a fresh clone, then give him PowerShell commands one per line:
  `cd $env:USERPROFILE\Downloads\routeplanner`, `git pull`, `git apply ..\<name>.patch`, `git add -A`,
  `git commit -m "…"`, `git push`. Never `git commit -am` — it silently leaves new files behind.
- After his push, check GitHub and the live page yourself. Only tell him something is saved once it's on GitHub.

## This skill
The master copy lives in the repository at `skill/route-planner/SKILL.md`. When a session learns something that
belongs here, change that file in the same patch as the work, and give Charles a fresh `route-planner.zip`
(the folder `route-planner/` with this file inside) to swap into his installed skill.

## Rules learned on Japan
- Minimal interface, data first. Days are computed; never hard-code a day list.
- Fork comparison is pairwise against the default on the stretch that differs.
- Keep local names next to English/romanised ones; romanisation is approximate.
- Cities ≤ 25 km off a line may become forks; 25–80 km are train rest-day options; further = a new trunk.
- Measure before recommending: say what was assumed; report numbers (km, climb, cycle-route %, busy %, sights) rather than adjectives.
- Work in small pieces and stop at a clear point Charles can check.
- Plain everyday English in replies; no jargon.
