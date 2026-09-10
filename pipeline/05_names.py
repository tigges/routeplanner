"""Step 5 — two names for every facility and sight: local (OSM name) and English (OSM name:en, else a
romanisation when config.lang.romanise is set, else the local name, else a generic label).
Facility entries become [km, off, en, local] (local only when different); sights [km, en, kind, d, local].
Runs on seg_data.json / seg_scores.json, or with --moped on the moped files."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
cfg, W = load_cfg(); moped = '--moped' in sys.argv
SD = jload(W, 'moped_sd.json' if moped else 'seg_data.json'); SC = jload(W, 'moped_sc.json' if moped else 'seg_scores.json', {})
rom = cfg['lang'].get('romanise')
if rom == 'pykakasi':
    import pykakasi; kk = pykakasi.kakasi(); JA = re.compile(r'[぀-ヿ一-鿿]')
    def romanise(s):
        if not JA.search(s): return s
        out = ' '.join(x['hepburn'] for x in kk.convert(s)); out = re.sub(r'\s+', ' ', out).replace('( ', '(').replace(' )', ')').strip()
        return ' '.join(w[:1].upper() + w[1:] for w in out.split(' '))
else:
    def romanise(s): return s
LABEL = {'convenience': 'Convenience store', 'supermarket': 'Supermarket', 'bakery': 'Bakery', 'greengrocer': 'Greengrocer',
         'butcher': 'Butcher', 'hotel': 'Hotel', 'guest_house': 'Guest house', 'hostel': 'Hostel', 'apartment': 'Apartment',
         'chalet': 'Chalet', 'motel': 'Motel', 'love_hotel': 'Hotel', 'camp_site': 'Campsite', 'caravan_site': 'Caravan site',
         'public_bath': 'Bath house', 'spa': 'Spa', 'hot_spring': 'Hot spring', 'station': 'Station', 'restaurant': 'Restaurant',
         'fast_food': 'Fast food', 'cafe': 'Café', 'food_court': 'Food court', 'toilets': 'Toilets',
         'bicycle': 'Bike shop', 'bicycle_repair_station': 'Repair stand', 'laundry': 'Laundry', 'dry_cleaning': 'Laundry',
         'drinking_water': 'Drinking water', 'water_tap': 'Water tap'}
n = 0
for sid, sd in SD.items():
    for cat, lst in sd.get('fac', {}).items():
        out = []
        for e in lst:
            if len(e) == 5:                                # raw from step 2: [km, off, name_en, name, subtype]
                en_raw, loc, sub = e[2], e[3], e[4]
                en = en_raw or (romanise(loc) if loc else '') or LABEL.get(sub, sub.replace('_', ' ').title())
                e = [e[0], e[1], en] + ([loc] if loc and loc != en else [])
            out.append(e); n += 1
        sd['fac'][cat] = sorted(out)
for v in SC.values():
    for e in v['sight_list']:
        if len(e) < 5: e.append(None)
        if rom and e[4] is None and romanise(e[1]) != e[1]: e[4] = e[1]; e[1] = romanise(e[1])   # local-only name
jdump(W, 'moped_sd.json' if moped else 'seg_data.json', SD, compact=True)
if SC: jdump(W, 'moped_sc.json' if moped else 'seg_scores.json', SC)
print('names finished on', n, 'facility entries')
