#!/usr/bin/env bash
# Minimal bash+jq step client for a `rfrepl.py start`-ed REPL:  rfrepl_step.sh DIR 'CELL'
# Same wire protocol as rfrepl.py step (comment markers + listener JSONL).
set -u
D=$1; cell=$2; T=${STEP_TIMEOUT:-120}
read -r pid _ < "$D/repl.pid" 2>/dev/null; kill -0 "${pid:-0}" 2>/dev/null || { echo '{"status":"DEAD"}'; exit 3; }
exec 9>>"$D/lock"; flock 9                              # serialize concurrent callers
n=$(( $(<"$D/seq") + 1 )); echo $n > "$D/seq"; id=b$n
off=$(stat -c %s "$D/steps.jsonl")
body=$(printf '%s\n' "$cell" | grep -v '^[[:space:]]*$')
printf '# rfmcp-step: %s\n%s\n\n# rfmcp-end: %s\n' "$id" "$body" "$id" > "$D/in.fifo"
end="\"t\": \"end\", \"id\": \"$id\""; SECONDS=0
until tail -c +$((off + 1)) "$D/steps.jsonl" | grep -qF "$end"; do
  (( SECONDS >= T )) && { echo "{\"id\":\"$id\",\"status\":\"TIMEOUT\"}"; exit 4; }
  sleep 0.002
done
tail -c +$((off + 1)) "$D/steps.jsonl" | jq -sc --arg id "$id" '
  [.[] | select(.t=="step" and .id==$id)] as $s
  | {id:$id, status:(if ($s|length)==0 then "NOOP" elif any($s[]; .status=="FAIL") then "FAIL" else "PASS" end),
     steps:[$s[] | {name, args, status, message, return, values} | with_entries(select(.value != null and .value != [] and .value != ""))]}'
