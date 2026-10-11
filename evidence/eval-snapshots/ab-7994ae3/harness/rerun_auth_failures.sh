#!/usr/bin/env bash
# Wait for the main live run to finish, drop Claude cells that failed with the
# OAuth-expiry error ("Failed to authenticate"), verify Claude auth, then resume
# the harness so exactly those cells are re-run. Log: rerun_auth_failures.log
set -u
cd "$(dirname "$0")"
MAIN_PID="${1:?main harness pid}"
LOG=rerun_auth_failures.log
exec >>"$LOG" 2>&1
echo "[$(date '+%F %T')] waiting for main run pid $MAIN_PID"
while kill -0 "$MAIN_PID" 2>/dev/null; do sleep 60; done
echo "[$(date '+%F %T')] main run ended"

cp results_live.jsonl "results_live.before_auth_rerun.$(date +%Y%m%d%H%M%S).jsonl"
python3 - <<'EOF'
import json, gzip
keep, dropped = [], []
for line in open("results_live.jsonl"):
    r = json.loads(line)
    bad = False
    if r.get("agent") == "claude":
        t = r.get("transcript")
        try:
            data = gzip.open(t, "rt", errors="replace").read() if t else ""
        except OSError:
            data = ""
        bad = "Failed to authenticate" in data
    (dropped if bad else keep).append(line)
open("results_live.jsonl", "w").writelines(keep)
print(f"kept {len(keep)} rows, dropped {len(dropped)} auth-failure rows")
EOF

if ! timeout 120 claude -p "Reply with the single word PONG" --model claude-haiku-4-5 2>&1 | grep -q PONG; then
  echo "[$(date '+%F %T')] Claude auth check FAILED - not re-running (run /login, then re-run this script)"
  exit 2
fi
echo "[$(date '+%F %T')] Claude auth OK - resuming harness"
python3 harness.py run --scenarios live --reps 3 --arms neither,mcp,skillpkg \
  --agents claude,codex,opencode --max-turns 80 --browser-concurrency 3 >> run_live.log 2>&1
echo "[$(date '+%F %T')] rerun finished (exit $?)"
python3 - <<'EOF'
import json, gzip
n = bad = 0
for line in open("results_live.jsonl"):
    r = json.loads(line); n += 1
    if r.get("agent") == "claude" and r.get("transcript"):
        try:
            if "Failed to authenticate" in gzip.open(r["transcript"], "rt", errors="replace").read():
                bad += 1
        except OSError:
            pass
print(f"rows={n} remaining_auth_failures={bad}")
EOF
echo "[$(date '+%F %T')] done"
