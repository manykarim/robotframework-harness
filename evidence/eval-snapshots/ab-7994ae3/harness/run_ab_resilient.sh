#!/usr/bin/env bash
# Self-healing A/B runner (round 6+). Safe to (re)start at any time: completed cells are skipped by the harness.
#
#   ./run_ab_resilient.sh TAG ARMS REPS [AGENTS] [SCENARIOS] [extra harness args ...]
#   ./run_ab_resilient.sh v3 hookpkg2,hookpkg3 3                       # live scenarios, claude,codex,opencode
#   ./run_ab_resilient.sh v3b mcp,hookpkg3 5 claude,opencode tricentis_quote,tricentis_debug
#
#   ./run_ab_resilient.sh v31or hookpkg31 2 claude,cc-or:* live --claude-model claude-haiku-5-5 \
#       --or-models deepseek/deepseek-v4.1-flash,qwen/qwen3.8-flash,z-ai/glm-5.3-flash,google/gemini-3.8-flash \
#       --or-budget-usd 150                                          # OpenRouter agents (cc-or:<short>, oc-or:<short>)
#
# Every start: (1) back up the results file and drop aborted rows + Claude "Failed to authenticate" rows and
# OpenRouter auth-failure rows (they are re-run), (2) check Claude auth when a subscription `claude` agent is in the
# batch (with the --claude-model of the extra args) and the OpenRouter key when cc-or/oc-or agents are (exit 2 + log
# line on failure), (3) run the harness (`--max-turns 80 --browser-concurrency 3 --tag TAG` + the extra args), then
# clean + re-run up to AB_MAX_PASSES (3) times. Extra args (e.g. --or-models, --or-budget-usd, --claude-model) are
# passed to every harness pass AND used to count the expected cells.
# Exit 0 = every expected cell has an ok row; 2 = auth failed; 3 = another instance of this TAG is running;
# 4 = OpenRouter budget exhausted (harness exit 4; remaining OpenRouter cells not run -- no restart);
# 1 = still incomplete after the passes (systemd restarts it).
#
# Intended launch (SIGTERM-killed runs restart automatically; completion (0) and auth failure (2) do not):
#   cd <harness dir>
#   systemd-run --user --unit=ab-v3 -p Restart=always -p RestartSec=60 -p "RestartPreventExitStatus=0 2 4" \
#     -p StartLimitIntervalSec=0 --working-directory="$PWD" --setenv=PATH="$PATH" --setenv=HOME="$HOME" \
#     ./run_ab_resilient.sh v3 hookpkg2,hookpkg3 3
# (the OpenRouter key is NOT passed to systemd: the harness reads it at runtime from ~/workspace/rf-mcp/.env
#  or --or-env-file)
#   journalctl --user -u ab-v3 -f   |   tail -f run_ab_v3.log run_live_v3.log   |   systemctl --user stop ab-v3
#
# Env overrides (testing): AB_HARNESS_CMD (default "python3 harness.py"), AB_AUTH_CMD (default: claude -p PONG check),
# AB_RESULTS (default results_live_TAG.jsonl), AB_EXPECTED (expected cell count; default computed from harness.py),
# AB_MAX_PASSES (3), AB_MIN_FREE_GB (1.5), AB_CLAUDE_MODEL (auth-check model; default: --claude-model or
# claude-haiku-4-5).
set -u
cd "$(dirname "$0")" || exit 1
TAG=${1:?usage: run_ab_resilient.sh TAG ARMS REPS [AGENTS] [SCENARIOS] [extra harness args]}
ARMS=${2:?arms}
REPS=${3:?reps}
AGENTS=${4:-claude,codex,opencode}
SCEN=${5:-live}
shift $(( $# < 5 ? $# : 5 ))
EXTRA=("$@")
EXTRA_JSON=$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1:]))' "${EXTRA[@]}")
CLAUDE_AUTH_MODEL=${AB_CLAUDE_MODEL:-$(python3 -c '
import sys
a = sys.argv[1:]
m = next((a[i + 1] for i, x in enumerate(a[:-1]) if x == "--claude-model"), None)
m = m or next((x.split("=", 1)[1] for x in a if x.startswith("--claude-model=")), None)
print(m or "claude-haiku-4-5")' "${EXTRA[@]}")}
RES=${AB_RESULTS:-results_live_${TAG}.jsonl}
LOG=run_ab_${TAG}.log
HLOG=run_live_${TAG}.log
HARNESS=${AB_HARNESS_CMD:-python3 harness.py}
MAXPASS=${AB_MAX_PASSES:-3}
exec >>"$LOG" 2>&1
log() { echo "[$(date '+%F %T')] [pid $$] $*"; }

exec 9>".run_ab_${TAG}.lock"
if ! flock -n 9; then
  log "another run_ab_resilient.sh for tag $TAG holds .run_ab_${TAG}.lock - exiting (3)"; exit 3
fi
HP=""
on_signal() {
  log "signal received - stopping the harness (running cells are marked aborted; a restart resumes them)"
  if [ -n "$HP" ]; then kill -TERM "$HP" 2>/dev/null; wait "$HP" 2>/dev/null; fi
  exit 143
}
trap on_signal TERM INT

clean() {   # backup + drop aborted / Claude auth-failure rows -> prints the number dropped
  RES="$RES" python3 - <<'EOF'
import gzip, json, os, shutil, time
res = os.environ["RES"]
if not os.path.exists(res):
    print(0); raise SystemExit
lines = open(res, encoding="utf-8").read().splitlines(True)
keep, drop = [], 0
for line in lines:
    try:
        r = json.loads(line)
    except ValueError:
        drop += 1                      # a torn last line of a killed run
        continue
    bad = r.get("status") == "aborted"
    ag = str(r.get("agent") or "")
    if not bad and (ag.startswith("cc-or:") or ag.startswith("oc-or:")):     # OpenRouter auth / credit failures
        blob = (r.get("stderr_tail") or "") + json.dumps(r.get("agent_info") or {})
        bad = any(s in blob for s in ("Failed to authenticate", "No auth credentials", "User not found",
                                      "Invalid API key", "Insufficient credits", '"api_error_status": 401',
                                      '"api_error_status": 402'))
        if not bad and r.get("transcript"):       # Claude Code reports "API Error: 402 ..." only in the transcript
            try:
                tx = gzip.open(r["transcript"], "rt", errors="replace").read()
                bad = any(s in tx for s in ("API Error: 402", "requires more credits", "API Error: 401",
                                            "Insufficient credits"))
            except OSError:
                pass
    if not bad and r.get("agent") == "claude":
        if "Failed to authenticate" in (r.get("stderr_tail") or "") + json.dumps(r.get("agent_info") or {}):
            bad = True
        elif r.get("transcript"):
            try:
                bad = "Failed to authenticate" in gzip.open(r["transcript"], "rt", errors="replace").read()
            except OSError:
                pass
    if bad:
        drop += 1
    else:
        keep.append(line)
if drop:
    bak = f"{res[:-6] if res.endswith('.jsonl') else res}.bak.{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
    shutil.copyfile(res, bak)
    tmp = res + ".tmp"
    open(tmp, "w", encoding="utf-8").writelines(keep)
    os.replace(tmp, res)
print(drop)
EOF
}

status() {  # "<ok unique cells> <expected cells>"
  RES="$RES" TAG="$TAG" ARMS="$ARMS" REPS="$REPS" AGENTS="$AGENTS" SCEN="$SCEN" EXTRA_JSON="$EXTRA_JSON" python3 - <<'EOF'
import json, os
res = os.environ["RES"]
ok = set()
if os.path.exists(res):
    for line in open(res, encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("status") == "ok":
            ok.add(r.get("key"))
exp = os.environ.get("AB_EXPECTED")
if not exp:
    import harness
    cells = harness.cli_cells(int(os.environ["REPS"]), os.environ["AGENTS"], os.environ["SCEN"], os.environ["ARMS"],
                              json.loads(os.environ.get("EXTRA_JSON") or "[]"))
    exp = len(cells)
    ok &= {harness.cell_key(a, arm, s.id, rep) for a, arm, s, rep in cells}
print(len(ok), exp)
EOF
}

or_ok() {    # OpenRouter key present + /api/v1/key answers (key read at runtime; never printed)
  case ",$AGENTS," in *,cc-or*|*,oc-or*) ;; *) return 0 ;; esac
  EXTRA_JSON="$EXTRA_JSON" timeout 60 python3 - <<'EOF'
import json, os, sys
import openrouter as OR
a = json.loads(os.environ.get("EXTRA_JSON") or "[]")
f = next((a[i + 1] for i, x in enumerate(a[:-1]) if x == "--or-env-file"), None)
if f:
    from pathlib import Path
    OR.ENV_FILE = Path(f)
k = OR.load_key()
if not (k and OR.key_info(k).get("usage") is not None):
    sys.exit(1)
bal = OR.account_balance(k)
if bal is not None and bal < float(os.environ.get("AB_MIN_OR_BALANCE", "0.5")):
    print(f"OpenRouter ACCOUNT balance too low: ${bal:.2f} (key limit is not the only limit; top up credits)",
          file=sys.stderr)
    sys.exit(1)
sys.exit(0)
EOF
}

auth_ok() {
  or_ok || { log "OpenRouter key check FAILED (OPENROUTER_API_KEY missing or rejected)"; return 1; }
  case ",$AGENTS," in *,claude,*) ;; *) return 0 ;; esac
  if [ -n "${AB_AUTH_CMD:-}" ]; then
    bash -c "$AB_AUTH_CMD" >/dev/null 2>&1
    return $?
  fi
  timeout 120 claude -p "Reply with the single word PONG" --model "$CLAUDE_AUTH_MODEL" 2>&1 | grep -q PONG
}

disk_ok() {
  local free_kb min_kb
  free_kb=$(df -Pk . | awk 'NR==2 {print $4}')
  min_kb=$(python3 -c "print(int(float('${AB_MIN_FREE_GB:-1.5}') * 1024 * 1024))")
  [ "${free_kb:-0}" -ge "$min_kb" ]
}

log "start: tag=$TAG arms=$ARMS reps=$REPS agents=$AGENTS scenarios=$SCEN extra=${EXTRA[*]:-} results=$RES"
D=$(clean); log "start cleanup: dropped $D aborted/auth-failure rows"
read -r OK EXP < <(status); OK=${OK:-0}; EXP=${EXP:-0}
log "status: $OK/$EXP cells ok"
if [ "${EXP:-0}" -gt 0 ] && [ "$OK" -ge "$EXP" ]; then log "already complete"; exit 0; fi
if ! auth_ok; then
  log "auth check FAILED - stopping (exit 2). Claude: run /login; OpenRouter: check the key; then restart."; exit 2
fi
for pass in $(seq 1 "$MAXPASS"); do
  if ! disk_ok; then log "free disk below ${AB_MIN_FREE_GB:-1.5} GB - not starting the harness (exit 1)"; exit 1; fi
  log "pass $pass: starting harness"
  # shellcheck disable=SC2086
  $HARNESS run --scenarios "$SCEN" --reps "$REPS" --arms "$ARMS" --agents "$AGENTS" --max-turns 80 \
    --browser-concurrency 3 --tag "$TAG" "${EXTRA[@]}" >> "$HLOG" 2>&1 &
  HP=$!
  wait $HP
  RC=$?
  log "pass $pass: harness exited ($RC)"
  if [ "$RC" -eq 4 ]; then
    D=$(clean); read -r OK EXP < <(status)
    log "OpenRouter budget exhausted: ${OK:-0}/${EXP:-0} cells ok, remaining OpenRouter cells not run - exit 4 (no restart)"
    exit 4
  fi
  D=$(clean)
  read -r OK EXP < <(status); OK=${OK:-0}; EXP=${EXP:-0}
  log "pass $pass: dropped $D aborted/auth-failure rows; $OK/$EXP cells ok"
  if [ "${EXP:-0}" -gt 0 ] && [ "$OK" -ge "$EXP" ]; then log "done: complete ($OK/$EXP)"; exit 0; fi
  if ! auth_ok; then
    log "Claude auth check FAILED - stopping (exit 2). Run /login (claude), then restart this unit/script."; exit 2
  fi
done
log "still incomplete after $MAXPASS passes ($OK/$EXP) - exit 1 (systemd restarts after RestartSec)"
exit 1
