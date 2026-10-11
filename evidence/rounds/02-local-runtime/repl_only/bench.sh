#!/usr/bin/env bash
# bench.sh CLIENT DIR N 'CELL' LABEL  -> one wall-clock sample per separate process invocation
CLIENT=$1; D=$2; N=$3; CELL=$4; LABEL=$5; OUT=${OUTJSON:-/dev/null}
HERE=$(cd "$(dirname "$0")" && pwd)
samples=()
for i in $(seq 1 "$N"); do
  t0=$(date +%s%N)
  if [ "$CLIENT" = py ]; then r=$(${PY:-python3} "$HERE/rfrepl.py" step --dir "$D" "$CELL"); else r=$("$HERE/rfrepl_step.sh" "$D" "$CELL"); fi
  t1=$(date +%s%N)
  st=$(jq -r .status <<<"$r")
  samples+=("$(( (t1 - t0) / 1000 ))")
  [ "$st" = PASS ] || echo "!! $LABEL #$i status=$st $r" >&2
done
printf '%s\n' "${samples[@]}" | python3 -c "
import sys,statistics,json
v=sorted(int(x)/1000 for x in sys.stdin if x.strip())
p90=v[min(len(v)-1,int(round(0.9*len(v)))-1)]
r={'label':'$LABEL','client':'$CLIENT','n':len(v),'median_ms':round(statistics.median(v),1),'p90_ms':round(p90,1),'min_ms':round(v[0],1),'max_ms':round(v[-1],1)}
print(json.dumps(r))
open('$OUT','a').write(json.dumps(r)+'\n') if '$OUT'!='/dev/null' else None
"
