#!/bin/bash
# runs steps 02-06 for one config over the extracts that exist; log to work/<slug>/data.log
cfg=$1; slug=$(python3 -c "import json,sys;print(json.load(open('$cfg'))['slug'])")
ex=$(python3 -c "import json,os;print(' '.join(os.path.basename(p) for p in json.load(open('$cfg'))['osm']['extracts'] if os.path.exists(p)))")
set -- $ex; n=$#
i=0; for x in $ex; do i=$((i+1)); echo "== 02 $x ($i/$n) $(date +%T)"; if [ $i -lt $n ]; then python3 pipeline/02_facilities.py $cfg --extract $x; else python3 pipeline/02_facilities.py $cfg --extract $x --merge; fi; done
for x in $ex; do echo "== 03 $x $(date +%T)"; python3 pipeline/03_scores.py $cfg --extract $x; done
echo "== 03 final $(date +%T)"; python3 pipeline/03_scores.py $cfg
echo "== 04 $(date +%T)"; python3 pipeline/04_beds.py $cfg
echo "== 05 $(date +%T)"; python3 pipeline/05_names.py $cfg
echo "== 06 $(date +%T)"; python3 pipeline/06_candnames.py $cfg
echo "== ALL DONE $slug $(date +%T)"
