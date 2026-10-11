#!/usr/bin/env bash
# Latency of `robotcode analyze code`: cold (cache cleared) vs warm, with/without --cache-namespaces.
# Usage: bash timing.sh <env-bin-dir> <label>
set -u
export LC_ALL=C
BIN=${1:-/home/many/workspace/robotcode-experiments/.venv/bin}
LABEL=${2:-rcexp}
RC="$BIN/robotcode"
cd "$(dirname "$0")/../corpus" || exit 1
t() {  # t <label> <cmd...> ; prints "label seconds exit"
  local lbl=$1; shift
  local s e rc
  s=$(date +%s.%N); "$@" >/dev/null 2>&1; rc=$?; e=$(date +%s.%N)
  printf '%-58s %6.2fs exit=%s\n' "$lbl" "$(echo "$e - $s" | bc)" "$rc"
}
echo "# env=$LABEL $($RC --version)  $(date -Iseconds)"
t "startup floor: robotcode --version" "$RC" --version

for f in cases/v09_browser_ok.robot cases/v10_requests_ok.robot cases/v01_builtin_ok.robot; do
  "$RC" analyze cache clear >/dev/null 2>&1; rm -rf .robotcode_cache
  t "cold  single $f" "$RC" analyze code "$f"
  t "warm1 single $f" "$RC" analyze code "$f"
  t "warm2 single $f" "$RC" analyze code "$f"
done

if [ "$LABEL" = "wt" ]; then
  "$RC" analyze cache clear >/dev/null 2>&1; rm -rf .robotcode_cache
  t "cold  single cases/v11_selenium_ok.robot" "$RC" analyze code cases/v11_selenium_ok.robot
  t "warm1 single cases/v11_selenium_ok.robot" "$RC" analyze code cases/v11_selenium_ok.robot
fi

rm -rf .robotcode_cache
t "cold  corpus (all cases/, no ns cache)" "$RC" analyze code cases
t "warm  corpus (all cases/, no ns cache)" "$RC" analyze code cases
t "warm  corpus (all cases/, no ns cache) #2" "$RC" analyze code cases
rm -rf .robotcode_cache
t "cold  corpus --cache-namespaces" "$RC" analyze code --cache-namespaces cases
t "warm  corpus --cache-namespaces" "$RC" analyze code --cache-namespaces cases
t "warm  corpus --cache-namespaces #2" "$RC" analyze code --cache-namespaces cases
t "warm  single browser --cache-namespaces" "$RC" analyze code --cache-namespaces cases/v09_browser_ok.robot
echo "# cache info after runs"
"$RC" analyze cache info 2>&1 | head -30
