#!/usr/bin/env python3
"""extract_facilities.py — attach cycle-touring facilities to Across Japan route segments (project copy)."""
import argparse, csv, json, math, os, sys
import xml.etree.ElementTree as ET
from collections import defaultdict
import numpy as np
import osmium
from scipy.spatial import cKDTree

R_EARTH_KM = 6371.0088
RULES = [
    (None, None, "michi_no_eki"),
    ("shop", {"convenience", "supermarket", "bakery", "greengrocer", "butcher"}, "food_shop"),
    ("amenity", {"restaurant", "fast_food", "cafe", "food_court"}, "food_eat"),
    ("amenity", {"drinking_water"}, "water"),
    ("man_made", {"water_tap"}, "water"),
    ("amenity", {"toilets"}, "toilets"),
    ("tourism", {"hotel", "guest_house", "hostel", "motel", "apartment", "chalet"}, "lodging"),
    ("amenity", {"love_hotel"}, "lodging"),
    ("tourism", {"camp_site", "caravan_site"}, "camping"),
    ("amenity", {"public_bath", "spa"}, "bath"),
    ("natural", {"hot_spring"}, "bath"),
    ("shop", {"laundry", "dry_cleaning"}, "laundry"),
    ("shop", {"bicycle"}, "bike"),
    ("amenity", {"bicycle_repair_station"}, "bike"),
    ("highway", {"rest_area", "services"}, "rest"),
    ("amenity", {"shelter"}, "rest"),
    ("amenity", {"pharmacy", "hospital", "clinic", "doctors"}, "medical"),
    ("railway", {"station"}, "rail"),
    ("amenity", {"atm", "bank", "post_office"}, "money"),
]
EXTRA_TAGS = ["opening_hours", "phone", "website", "brand", "operator", "internet_access", "shower", "bath:type", "fee",
              "drinking_water", "toilets", "capacity", "tents", "backcountry", "wheelchair", "cuisine", "vending"]

def is_michi_no_eki(tags):
    return "道の駅" in ((tags.get("name") or "") + (tags.get("name:ja") or ""))

def classify(tags):
    for key, values, category in RULES:
        if key is None:
            if is_michi_no_eki(tags):
                return category, tags.get("highway") or tags.get("amenity") or "unknown"
            continue
        v = tags.get(key)
        if v is not None and v in values:
            return category, v
    return None

def _coords_from_geojson(obj):
    t = obj.get("type")
    if t == "FeatureCollection":
        for f in obj.get("features", []): yield from _coords_from_geojson(f)
    elif t == "Feature": yield from _coords_from_geojson(obj.get("geometry") or {})
    elif t == "LineString": yield [(c[1], c[0]) for c in obj["coordinates"]]
    elif t == "MultiLineString":
        for part in obj["coordinates"]: yield [(c[1], c[0]) for c in part]

def load_line(path):
    with open(path, encoding="utf-8") as fh: obj = json.load(fh)
    flat = [pt for part in _coords_from_geojson(obj) for pt in part]
    if len(flat) < 2: raise ValueError(f"{path}: fewer than 2 points")
    return flat

def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2-p1)/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(math.radians(lon2-lon1)/2)**2
    return 2 * R_EARTH_KM * math.asin(math.sqrt(a))

def densify(pts, max_gap_km):
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        d = haversine_km(a[0], a[1], b[0], b[1]); n = int(d // max_gap_km)
        for i in range(1, n + 1):
            f = i / (n + 1); out.append((a[0] + (b[0]-a[0])*f, a[1] + (b[1]-a[1])*f))
        out.append(b)
    return out

def cumulative_km(pts):
    km = [0.0]
    for a, b in zip(pts, pts[1:]): km.append(km[-1] + haversine_km(a[0], a[1], b[0], b[1]))
    return km

class RouteIndex:
    def __init__(self, segments, corridor_km):
        self.corridor_km = corridor_km
        lats, lons, meta = [], [], []
        for seg_id, pts in segments.items():
            pts = densify(pts, corridor_km / 4.0); kms = cumulative_km(pts)
            for (la, lo), km in zip(pts, kms): lats.append(la); lons.append(lo); meta.append((seg_id, km))
        self.lat0 = float(np.mean(lats)); self.meta = meta
        self.tree = cKDTree(self._project(np.asarray(lats), np.asarray(lons)))
        self.bbox = (min(lats), min(lons), max(lats), max(lons)); pad = corridor_km / 100.0
        self.pad_bbox = (self.bbox[0]-pad, self.bbox[1]-pad, self.bbox[2]+pad, self.bbox[3]+pad)
    def _project(self, lat, lon):
        k = math.pi * R_EARTH_KM / 180.0
        return np.column_stack([lon * k * math.cos(math.radians(self.lat0)), lat * k])
    def in_bbox(self, lat, lon):
        s, w, n, e = self.pad_bbox; return s <= lat <= n and w <= lon <= e
    def hits(self, lat, lon):
        xy = self._project(np.array([lat]), np.array([lon]))[0]
        idx = self.tree.query_ball_point(xy, self.corridor_km)
        if not idx: return []
        best = {}
        for i in idx:
            seg_id, km = self.meta[i]; d = float(np.hypot(*(self.tree.data[i] - xy)))
            if seg_id not in best or d < best[seg_id][1]: best[seg_id] = (km, d)
        return [(s, round(km, 3), round(d, 3)) for s, (km, d) in sorted(best.items())]

def scan(pbf, index, sink, seen):
    fp = (osmium.FileProcessor(pbf, osmium.osm.NODE | osmium.osm.WAY).with_locations().with_filter(osmium.filter.EmptyTagFilter()))
    for o in fp:
        hit = classify(o.tags)
        if hit is None: continue
        if o.is_node(): lat, lon, otype = o.location.lat, o.location.lon, "n"
        else:
            if len(o.nodes) < 2: continue
            pts = [(nd.location.lat, nd.location.lon) for nd in o.nodes if nd.location.valid()]
            if not pts: continue
            lat = sum(p[0] for p in pts)/len(pts); lon = sum(p[1] for p in pts)/len(pts); otype = "w"
        if not index.in_bbox(lat, lon): continue
        key = f"{otype}{o.id}"
        if key in seen: continue
        matches = index.hits(lat, lon)
        if not matches: continue
        seen.add(key); category, subtype = hit; tags = dict(o.tags)
        extras = {k: tags[k] for k in EXTRA_TAGS if k in tags}
        if category != "michi_no_eki" and is_michi_no_eki(tags): extras["michi_no_eki"] = "yes"
        for seg_id, km_along, offset_km in matches:
            sink.append({"segment_id": seg_id, "km_along": km_along, "offset_km": offset_km, "category": category, "subtype": subtype,
                         "name": tags.get("name", ""), "name_en": tags.get("name:en", ""), "lat": round(lat, 6), "lon": round(lon, 6),
                         "osm": key, "extras": json.dumps(extras, ensure_ascii=False) if extras else ""})

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--segments-dir", required=True); ap.add_argument("--pbf", nargs="+", required=True)
    ap.add_argument("--corridor", type=float, default=2.0); ap.add_argument("--out", default="facilities.csv")
    args = ap.parse_args()
    paths = {os.path.splitext(fn)[0].replace("__", "#"): os.path.join(args.segments_dir, fn) for fn in sorted(os.listdir(args.segments_dir)) if fn.endswith(".geojson")}
    segments = {sid: load_line(p) for sid, p in paths.items()}
    print(f"{len(segments)} segments, corridor ±{args.corridor} km", file=sys.stderr, flush=True)
    index = RouteIndex(segments, args.corridor)
    rows, seen = [], set()
    for pbf in args.pbf:
        print(f"scanning {os.path.basename(pbf)} ...", file=sys.stderr, flush=True); scan(pbf, index, rows, seen)
        print(f"  {len(seen):,} facilities so far", file=sys.stderr, flush=True)
    rows.sort(key=lambda r: (r["segment_id"], r["km_along"]))
    fields = ["segment_id", "km_along", "offset_km", "category", "subtype", "name", "name_en", "lat", "lon", "osm", "extras"]
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields); w.writeheader(); w.writerows(rows)
    by_cat = defaultdict(int)
    for r in rows: by_cat[r["category"]] += 1
    print(f"{len(seen):,} facilities, {len(rows):,} rows -> {args.out}", file=sys.stderr)
    for cat, n in sorted(by_cat.items(), key=lambda kv: -kv[1]): print(f"  {cat:<12} {n:>6}", file=sys.stderr)

if __name__ == "__main__": main()
