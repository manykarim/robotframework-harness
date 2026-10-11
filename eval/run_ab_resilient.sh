#!/usr/bin/env bash
# Self-healing evaluation runner (ported from the round-7 research runner). Safe to (re)start at any time: completed
# cells (status ok) are skipped by the harness; invalid / aborted cells are rerun.
#
#   ./run_ab_resilient.sh TAG ARMS REPS [AGENTS] [SCENARIOS] [extra harness args ...]
#   ./run_ab_resilient.sh gate1 prototype-v32,rf-harness 3                    # live scenarios, claude,codex,opencode
#   ./run_ab_resilient.sh gate1or prototype-v32,rf-harness 3 cc-or:qwen3.8-flash live \
#       --or-models qwen/qwen3.8-flash --or-budget-usd 20                     # OpenRouter route, per-run budget $20
#
# Every start: (1) clean the results file (validity.py clean: drop aborted rows and torn lines, re-label ok rows whose
# transcript shows a provider failure (HTTP 401/402, credits, auth) or a Codex backend outage as `invalid`; backup
# <results>.bak.<time>.jsonl when anything changed), (2) when OpenRouter agents (cc-or / oc-or) are scheduled: check
# the key and the ACCOUNT balance (openrouter.py balance-check; below AB_MIN_OR_BALANCE, default 0.5 USD -> exit 5),
# (3) check Claude auth when a subscription `claude` agent is scheduled (exit 2), (4) run the harness
# (`--max-turns 80 --browser-concurrency 3 --tag TAG --out-dir OUT` + the extra args), then clean + re-check the
# balance + re-run up to AB_MAX_PASSES (3) times. Extra args are passed to every pass AND used to count the cells.
#
# Exit codes: 0 every expected cell has an ok row | 1 still incomplete (a supervisor may restart) | 2 authentication
# failed | 3 another runner holds this TAG's lock | 4 OpenRouter run budget exhausted | 5 OpenRouter account balance
# or key limit below the minimum (top up, then restart) | 6 an arm is unavailable / misconfigured.
#
# Intended launch (restarts only after SIGTERM / incomplete):
#   systemd-run --user --unit=rfh-eval-gate1 -p Restart=always -p RestartSec=60 \
#     -p "RestartPreventExitStatus=0 2 3 4 5 6" -p StartLimitIntervalSec=0 --working-directory="$PWD" \
#     --setenv=PATH="$PATH" --setenv=HOME="$HOME" eval/run_ab_resilient.sh gate1 prototype-v32,rf-harness 3
# (the OpenRouter key is not passed to systemd: the harness reads OPENROUTER_API_KEY from the env or the .env file,
#  see --or-env-file; it is never written to results, logs or transcripts)
#
# Env overrides: AB_OUT_DIR (results/logs dir, default <eval>/runs), AB_HARNESS_CMD (default "python3 harness.py"),
# AB_AUTH_CMD (default: claude -p PONG check), AB_RESULTS (default $AB_OUT_DIR/results_live_TAG.jsonl), AB_EXPECTED
# (expected cell count; default computed from harness.py), AB_MAX_PASSES (3), AB_MIN_FREE_GB (1.5), AB_MIN_OR_BALANCE
# (0.5), AB_CLAUDE_MODEL (auth-check model; default: --claude-model or claude-haiku-5-5).
set -u
cd "$(dirname "$0")" || exit 1
TAG=${1:?usage: run_ab_resilient.sh TAG ARMS REPS [AGENTS] [SCENARIOS] [extra harness args]}
ARMS=${2:?arms}
REPS=${3:?reps}
AGENTS=${4:-claude,codex,opencode}
SCEN=${5:-live}
shift $(( $# < 5 ? $# : 5 ))
EXTRA=("$@")
OUT=${AB_OUT_DIR:-runs}
mkdir -p "$OUT" || exit 1
EXTRA_JSON=$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1:]))' "${EXTRA[@]}")
CLAUDE_AUTH_MODEL=${AB_CLAUDE_MODEL:-$(python3 -c '
import sys
a = sys.argv[1:]
m = next((a[i + 1] for i, x in enumerate(a[:-1]) if x == "--claude-model"), None)
m = m or next((x.split("=", 1)[1] for x in a if x.startswith("--claude-model=")), None)
print(m or "claude-haiku-5-5")' "${EXTRA[@]}")}
OR_ENV_FILE=$(python3 -c '
import sys
a = sys.argv[1:]
print(next((a[i + 1] for i, x in enumerate(a[:-1]) if x == "--or-env-file"), ""))' "${EXTRA[@]}")
RES=${AB_RESULTS:-$OUT/results_live_${TAG}.jsonl}
LOG=$OUT/run_ab_${TAG}.log
HLOG=$OUT/run_live_${TAG}.log
HARNESS=${AB_HARNESS_CMD:-python3 harness.py}
MAXPASS=${AB_MAX_PASSES:-3}
exec >>"$LOG" 2>&1
log() { echo "[$(date '+%F %T')] [pid $$] $*"; }

exec 9>"$OUT/.run_ab_${TAG}.lock"
if ! flock -n 9; then
  log "another run_ab_resilient.sh for tag $TAG holds $OUT/.run_ab_${TAG}.lock - exiting (3)"; exit 3
fi
HP=""
on_signal() {
  log "signal received - stopping the harness (running cells are marked aborted; a restart resumes them)"
  if [ -n "$HP" ]; then kill -TERM "$HP" 2>/dev/null; wait "$HP" 2>/dev/null; fi
  exit 143
}
trap on_signal TERM INT

clean() {   # -> "<dropped> <relabelled>"
  python3 validity.py clean "$RES"
}

status() {  # "<ok unique cells> <expected cells>"
  RES="$RES" ARMS="$ARMS" REPS="$REPS" AGENTS="$AGENTS" SCEN="$SCEN" EXTRA_JSON="$EXTRA_JSON" python3 - <<'EOF'
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

uses_or() { case ",$AGENTS," in *,cc-or*|*,oc-or*) return 0 ;; *) return 1 ;; esac; }

balance_rc() {   # 0 ok / no OpenRouter agents, 1 key missing or rejected, 5 balance or key limit too low
  uses_or || return 0
  if [ -n "$OR_ENV_FILE" ]; then
    timeout 60 python3 openrouter.py balance-check --min "${AB_MIN_OR_BALANCE:-0.5}" --env-file "$OR_ENV_FILE"
  else
    timeout 60 python3 openrouter.py balance-check --min "${AB_MIN_OR_BALANCE:-0.5}"
  fi
}

check_balance() {   # exits 2 (no usable key) or 5 (balance) when the OpenRouter account cannot pay for cells
  local rc
  balance_rc; rc=$?
  if [ "$rc" -eq 5 ]; then
    log "OpenRouter account balance / key limit below \$${AB_MIN_OR_BALANCE:-0.5} - stopping (exit 5); top up, then restart"
    exit 5
  elif [ "$rc" -ne 0 ]; then
    log "OpenRouter key check FAILED (OPENROUTER_API_KEY missing or rejected) - stopping (exit 2)"
    exit 2
  fi
}

auth_ok() {
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
read -r D R < <(clean); log "start cleanup: dropped ${D:-0} aborted/torn rows, ${R:-0} rows re-labelled invalid"
read -r OK EXP < <(status); OK=${OK:-0}; EXP=${EXP:-0}
log "status: $OK/$EXP cells ok"
if [ "${EXP:-0}" -gt 0 ] && [ "$OK" -ge "$EXP" ]; then log "already complete"; exit 0; fi
check_balance
if ! auth_ok; then
  log "Claude auth check FAILED - stopping (exit 2). Run /login (claude), then restart."; exit 2
fi
for pass in $(seq 1 "$MAXPASS"); do
  if ! disk_ok; then log "free disk below ${AB_MIN_FREE_GB:-1.5} GB - not starting the harness (exit 1)"; exit 1; fi
  check_balance
  log "pass $pass: starting harness"
  # shellcheck disable=SC2086
  $HARNESS run --scenarios "$SCEN" --reps "$REPS" --arms "$ARMS" --agents "$AGENTS" --max-turns 80 \
    --browser-concurrency 3 --tag "$TAG" --out-dir "$OUT" "${EXTRA[@]}" >> "$HLOG" 2>&1 &
  HP=$!
  wait $HP
  RC=$?
  HP=""
  log "pass $pass: harness exited ($RC)"
  read -r D R < <(clean); read -r OK EXP < <(status); OK=${OK:-0}; EXP=${EXP:-0}
  log "pass $pass: dropped ${D:-0} aborted/torn rows, ${R:-0} re-labelled invalid; $OK/$EXP cells ok"
  case "$RC" in
    2) log "authentication failure seen in a session - stopping (exit 2). Fix the login, then restart."; exit 2 ;;
    4) log "OpenRouter run budget exhausted: $OK/$EXP cells ok, remaining OpenRouter cells not run - exit 4"; exit 4 ;;
    5) log "OpenRouter balance / key limit / HTTP 402 stopped OpenRouter cells - exit 5 (top up, then restart)"; exit 5 ;;
    6) log "an arm is unavailable or misconfigured (see $HLOG) - exit 6"; exit 6 ;;
  esac
  if [ "${EXP:-0}" -gt 0 ] && [ "$OK" -ge "$EXP" ]; then log "done: complete ($OK/$EXP)"; exit 0; fi
  if ! auth_ok; then
    log "Claude auth check FAILED - stopping (exit 2). Run /login (claude), then restart this unit/script."; exit 2
  fi
done
log "still incomplete after $MAXPASS passes ($OK/$EXP) - exit 1 (a supervisor may restart after a delay)"
exit 1
