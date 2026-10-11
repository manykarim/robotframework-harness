#!/usr/bin/env bash
# Q3: `robotcode results ...` on generated-suite runs: size (chars ~ tokens*4), latency, content.
set -u
export LC_ALL=C
RC=~/workspace/robotcode-experiments/.venv/bin/robotcode
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/outputs/q3"
mkdir -p "$OUT"
cd "$ROOT/corpus" || exit 1
UI="$ROOT/outputs/run/output.xml"
API="$ROOT/outputs/run_api/output.xml"

m() {
  local name=$1; shift
  local s e rc
  s=$(date +%s.%N); "$@" >"$OUT/$name.out" 2>&1; rc=$?; e=$(date +%s.%N)
  printf '%-40s %6.2fs exit=%-3s %8d chars ~%6d tok\n' "$name" "$(echo "$e - $s" | bc)" "$rc" \
    "$(wc -c <"$OUT/$name.out")" "$(( $(wc -c <"$OUT/$name.out") / 4 ))"
}
for pair in "ui:$UI" "api:$API"; do
  tag=${pair%%:*}; f=${pair#*:}
  echo "## $tag  ($f, $(wc -c <"$f") bytes output.xml)"
  m "${tag}_summary_text"          "$RC" results summary -o "$f"
  m "${tag}_summary_failed_text"   "$RC" results summary --failed -o "$f"
  m "${tag}_summary_failed_json"   "$RC" --format json results summary --failed -o "$f"
  m "${tag}_show_failed_json"      "$RC" --format json results show --status fail --message-chars 0 -o "$f"
  m "${tag}_log_failed_text"       "$RC" results log --failed -o "$f"
  m "${tag}_log_failed_json"       "$RC" --format json results log --failed -o "$f"
  m "${tag}_log_failed_json_d2"    "$RC" --format json results log --failed --max-depth 2 -o "$f"
  m "${tag}_log_all_json"          "$RC" --format json results log -o "$f"
  m "${tag}_log_failed_extract"    "$RC" --format json results log --failed --extract "$OUT/extracted_$tag" -o "$f"
done
m diff_ui_vs_api_json "$RC" --format json results diff "$UI" "$API"
