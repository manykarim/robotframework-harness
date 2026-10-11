#!/usr/bin/env bash
# E1: robotcode libdoc (== RF libdoc passthrough) documentation retrieval: commands, latency, sizes.
set -u
export LC_ALL=C.UTF-8
RC=~/workspace/robotcode-experiments/.venv/bin/robotcode   # RF 7.5, Browser 20.5, Requests
WT=~/workspace/rf-mcp-robotcode/.venv/bin/robotcode         # RF 7.3.2, Selenium
K=~/workspace/rf-mcp-robotcode/experiments/robotcode-remote/round2/keyword_docs
OUT=$K/outputs/e1; mkdir -p $OUT
P=$K/project
cd $P
m() {  # m <name> <cmd...>
  local name=$1; shift
  local s e rc
  s=$(date +%s.%N); "$@" >"$OUT/$name.out" 2>&1; rc=$?; e=$(date +%s.%N)
  local c; c=$(wc -c <"$OUT/$name.out")
  printf '%-40s %6.2fs exit=%-3s %8d chars %7d tok\n' "$name" "$(echo "$e - $s" | bc)" "$rc" "$c" "$((c/4))"
}
echo "## warmup (cold-ish first call)"
m cold_browser_version "$RC" libdoc Browser version
m warm_browser_version "$RC" libdoc Browser version
echo "## show: one / five / glob / whole library / intro"
m show1_browser_click          "$RC" libdoc Browser show Click
m show5_browser                "$RC" libdoc Browser show Click "Fill Text" "Get Text" "Wait For Elements State" "New Page"
m showglob_browser_wait        "$RC" libdoc Browser show "Wait For*"
m showglob_case_insens         "$RC" libdoc Browser show "fill_text"
m show_intro_only_browser      "$RC" libdoc Browser show intro
m show_all_browser             "$RC" libdoc Browser show
m show_all_requests            "$RC" libdoc RequestsLibrary show
m show1_requests_post          "$RC" libdoc RequestsLibrary show "POST On Session"
m show5_requests               "$RC" libdoc RequestsLibrary show "POST On Session" "GET On Session" "Create Session" "Status Should Be" "Request Should Be Successful"
m show_all_builtin             "$RC" libdoc BuiltIn show
m show1_builtin_shouldbe       "$RC" libdoc BuiltIn show "Should Be Equal"
m show_all_collections         "$RC" libdoc Collections show
m show_all_string              "$RC" libdoc String show
m show1_selenium_wt            "$WT" libdoc SeleniumLibrary show "Wait Until Element Is Visible"
m show5_selenium_wt            "$WT" libdoc SeleniumLibrary show "Click Element" "Input Text" "Wait Until Element Is Visible" "Get Text" "Open Browser"
m show_all_selenium_wt         "$WT" libdoc SeleniumLibrary show
echo "## list with patterns (substring of NAME only)"
m list_browser_all             "$RC" libdoc Browser list
m list_browser_multi           "$RC" libdoc Browser list wait text
m list_requests_post           "$RC" libdoc RequestsLibrary list post
m list_requests_json           "$RC" libdoc RequestsLibrary list json
echo "## project resource / python library (path) / library with init args"
m show_resource_path           "$RC" libdoc resources/shop.resource show
m show_pylib_path              "$RC" libdoc libs/ShopApi.py show
m show_pylib_initargs          "$RC" libdoc "libs/ShopApi.py::http://x" show
m show_pylib_pythonpath        "$RC" libdoc -P libs ShopApi show "Create Order"
m show_suite_file              "$RC" libdoc tests/shop.robot show
echo "## machine-readable formats"
m json_stdout_browser          "$RC" libdoc --format JSON --specdocformat RAW Browser /dev/stdout
m json_stdout_requests         "$RC" libdoc --format JSON --specdocformat RAW RequestsLibrary /dev/stdout
m json_stdout_resource         "$RC" libdoc --format JSON --specdocformat RAW resources/shop.resource /dev/stdout
m json_stdout_pylib            "$RC" libdoc --format JSON --specdocformat RAW libs/ShopApi.py /dev/stdout
m robotcode_json_flag          "$RC" --format json libdoc Browser show Click
echo "## robotcode global options effect"
m dry_run                      "$RC" --dry libdoc Browser show Click
