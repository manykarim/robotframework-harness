#!/usr/bin/env bash
# E2: robotcode repl --plain dot-commands (.kw/.doc/.imports) driven non-interactively via stdin.
set -u
export LC_ALL=C.UTF-8 PAGER=cat
RC=~/workspace/robotcode-experiments/.venv/bin/robotcode
K=~/workspace/rf-mcp-robotcode/experiments/robotcode-remote/round2/keyword_docs
OUT=$K/outputs/e2; mkdir -p $OUT/rout
cd $K/project
IMPORTS=$'Import Library    Browser\nImport Library    RequestsLibrary\nImport Library    ${CURDIR}/libs/ShopApi.py    base_url=http://x\nImport Resource    ${CURDIR}/resources/shop.resource\n'
r() { # r <name> <dot-commands...>
  local name=$1; shift
  local input="$IMPORTS"; for c in "$@"; do input+="$c"$'\n'; done; input+=$'.exit\n'
  local s e; s=$(date +%s.%N)
  printf '%s' "$input" | "$RC" repl --plain --no-history -d $OUT/rout -o NONE -r NONE -l NONE >"$OUT/$name.out" 2>&1
  e=$(date +%s.%N); local c; c=$(wc -c <"$OUT/$name.out")
  printf '%-30s %6.2fs %8d chars %6d tok\n' "$name" "$(echo "$e - $s" | bc)" "$c" "$((c/4))"
}
r baseline_imports_only
r imports                '.imports'
r kw_exact_click         '.kw Click'
r kw_exact_lower         '.kw fill text'
r kw_exact_qualified     '.kw RequestsLibrary.POST On Session'
r kw_substring_post      '.kw post'
r kw_text_post_json      '.kw post json'
r kw_text_wait_visible   '.kw wait until visible'
r kw_resource_userkw     '.kw Login As User'
r kw_pylib_initargs      '.kw Create Order'
r kw_list_all            '.kw'
r doc_resource           '.doc shop'
r doc_pylib              '.doc ShopApi'
r doc_requests           '.doc RequestsLibrary'
r doc_browser            '.doc Browser'
r doc_unimported         '.doc Collections'
r five_kw_one_session    '.kw Click' '.kw Fill Text' '.kw Get Text' '.kw Wait For Elements State' '.kw New Page'
# session-defined user keyword? REPL has no *** Keywords *** input; check what happens
r help_kw                '.help kw'
