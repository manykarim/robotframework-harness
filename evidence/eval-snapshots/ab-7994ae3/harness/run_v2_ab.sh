#!/usr/bin/env bash
# Round 5 A/B: hookpkg (v1) vs hookpkg2 (v2) on the live scenarios.
# Runs the batch, then drops cells broken by Claude OAuth expiry or harness aborts and resumes (max 2 extra passes).
# Log: run_v2_ab.log (wrapper) + run_live_v2.log (harness). Results: results_live_v2.jsonl
set -u
cd "$(dirname "$0")"
LOG=run_v2_ab.log
exec >>"$LOG" 2>&1
ARGS=(run --scenarios live --reps 3 --arms hookpkg,hookpkg2 --agents claude,codex,opencode
      --max-turns 80 --browser-concurrency 3 --tag v2)
for pass in 1 2 3; do
  echo "[$(date '+%F %T')] pass $pass: starting harness"
  python3 harness.py "${ARGS[@]}" >> run_live_v2.log 2>&1
  echo "[$(date '+%F %T')] pass $pass: harness exited ($?)"
  [ -f results_live_v2.jsonl ] || { echo "no results file"; exit 1; }
  cp results_live_v2.jsonl "results_live_v2.pass${pass}.bak.jsonl"
  DROPPED=$(python3 - <<'EOF'
import json, gzip
keep, drop = [], 0
for line in open("results_live_v2.jsonl"):
    r = json.loads(line)
    bad = r.get("status") == "aborted"
    if not bad and r.get("agent") == "claude" and r.get("transcript"):
        try:
            bad = "Failed to authenticate" in gzip.open(r["transcript"], "rt", errors="replace").read()
        except OSError:
            pass
    if bad:
        drop += 1
    else:
        keep.append(line)
open("results_live_v2.jsonl", "w").writelines(keep)
print(drop)
EOF
)
  echo "[$(date '+%F %T')] pass $pass: dropped $DROPPED auth-failure/aborted rows"
  [ "$DROPPED" = "0" ] && break
  if ! timeout 120 claude -p "Reply with the single word PONG" --model claude-haiku-4-5 2>&1 | grep -q PONG; then
    echo "[$(date '+%F %T')] Claude auth check FAILED - stopping (run /login, then restart this script)"; exit 2
  fi
done
echo "[$(date '+%F %T')] done: $(wc -l < results_live_v2.jsonl) rows"
