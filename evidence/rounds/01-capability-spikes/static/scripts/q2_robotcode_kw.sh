#!/usr/bin/env bash
# Q2: keyword discovery/docs via robotcode CLI (client side). Captures output, size, latency.
set -u
export LC_ALL=C
RCEXP=~/workspace/robotcode-experiments/.venv/bin
WT=~/workspace/rf-mcp-robotcode/.venv/bin
OUT="$(cd "$(dirname "$0")/.." && pwd)/outputs/q2"
mkdir -p "$OUT/specs"
cd "$(dirname "$0")/../corpus" || exit 1

m() {  # m <name> <cmd...>  -> writes $OUT/<name>.out, prints name secs chars
  local name=$1; shift
  local s e rc
  s=$(date +%s.%N); "$@" >"$OUT/$name.out" 2>&1; rc=$?; e=$(date +%s.%N)
  printf '%-44s %6.2fs exit=%-3s %8d chars\n' "$name" "$(echo "$e - $s" | bc)" "$rc" "$(wc -c <"$OUT/$name.out")"
}

echo "## environment/version checks"
m discover_info_text        "$RCEXP/robotcode" discover info
m discover_info_json        "$RCEXP/robotcode" --format json discover info
m libdoc_browser_version    "$RCEXP/robotcode" libdoc Browser version
m libdoc_selenium_version   "$WT/robotcode" libdoc SeleniumLibrary version
m pip_list_json_uv          uv pip list --python "$RCEXP/python" --format json
m importlib_versions        "$RCEXP/python" -c "import importlib.metadata as m,json;print(json.dumps({d.metadata['Name']:d.version for d in m.distributions() if d.metadata['Name'].lower().startswith('robotframework')}))"

echo "## libdoc list/show"
m libdoc_browser_list       "$RCEXP/robotcode" libdoc Browser list
m libdoc_browser_list_glob  "$RCEXP/robotcode" libdoc Browser list "*Text*"
m libdoc_browser_show_filltext "$RCEXP/robotcode" libdoc Browser show "Fill Text"
m libdoc_browser_show_click "$RCEXP/robotcode" libdoc Browser show "Click"
m libdoc_browser_show_gettext "$RCEXP/robotcode" libdoc Browser show "Get Text"
m libdoc_requests_show_post "$RCEXP/robotcode" libdoc RequestsLibrary show "POST On Session"
m libdoc_selenium_show_wait "$WT/robotcode" libdoc SeleniumLibrary show "Wait Until Element Is Visible"
m libdoc_selenium_show_click "$WT/robotcode" libdoc SeleniumLibrary show "Click Element"

echo "## libdoc JSON specs (default HTML docs vs RAW)"
for lib in Browser RequestsLibrary BuiltIn Collections String; do
  m "spec_${lib}_json_html" "$RCEXP/robotcode" libdoc --format JSON "$lib" "$OUT/specs/${lib}.html.json"
  m "spec_${lib}_json_raw"  "$RCEXP/robotcode" libdoc --format JSON --specdocformat RAW "$lib" "$OUT/specs/${lib}.raw.json"
done
m spec_SeleniumLibrary_json_html "$WT/robotcode" libdoc --format JSON SeleniumLibrary "$OUT/specs/SeleniumLibrary.html.json"
m spec_SeleniumLibrary_json_raw  "$WT/robotcode" libdoc --format JSON --specdocformat RAW SeleniumLibrary "$OUT/specs/SeleniumLibrary.raw.json"
m spec_common_resource_raw "$RCEXP/robotcode" libdoc --format JSON --specdocformat RAW resources/common.resource "$OUT/specs/common.resource.raw.json"

echo "## REPL .kw search (piped, plain)"
mkdir -p "$OUT/repl_out"
REPLIN=$'Import Library    Browser\nImport Library    RequestsLibrary\n.kw click\n.kw fill text\n.kw post\n.kw wait\n.kw get text\n.exit\n'
s=$(date +%s.%N); printf '%s' "$REPLIN" | "$RCEXP/robotcode" repl --plain --no-history -d "$OUT/repl_out" >"$OUT/repl_kw_search.out" 2>&1; e=$(date +%s.%N)
printf '%-44s %6.2fs %8d chars\n' repl_kw_search "$(echo "$e - $s" | bc)" "$(wc -c <"$OUT/repl_kw_search.out")"
REPLIN2=$'Import Library    Browser\n.doc Fill Text\n.exit\n'
s=$(date +%s.%N); printf '%s' "$REPLIN2" | "$RCEXP/robotcode" repl --plain --no-history -d "$OUT/repl_out" >"$OUT/repl_doc.out" 2>&1; e=$(date +%s.%N)
printf '%-44s %6.2fs %8d chars\n' repl_doc_filltext "$(echo "$e - $s" | bc)" "$(wc -c <"$OUT/repl_doc.out")"

echo "## spec file sizes (bytes)"
ls -l "$OUT/specs" | awk 'NR>1{printf "%-40s %9d\n",$9,$5}'
