#!/usr/bin/env bash
# Approach C for RequestsLibrary: fresh `robotcode repl` per step. Session objects cannot survive,
# so every step re-runs a prologue (imports + Create Session) and JSON-serialisable variables that
# the cell assigned are saved to DIR/state.json and loaded back with -V on the next step.
#   oneshot_req.sh DIR 'cell'
set -u
RC=${RC:-/home/many/workspace/robotcode-experiments/.venv/bin/robotcode}
D=$(realpath -m "$1"); CELL=$2; mkdir -p "$D"; [ -f "$D/state.json" ] || echo '{}' > "$D/state.json"
# names assigned by this cell: ${x}=  /  VAR  ${x}
NAMES=$(grep -oE '^\s*(\$\{[A-Za-z0-9_]+\})\s*=?\s{2,}|^\s*VAR\s+\$\{[A-Za-z0-9_]+\}' <<<"$CELL" | grep -oE '[A-Za-z0-9_]+\}' | tr -d '}' | sort -u | tr '\n' ' ')
{
  cat "$D/prologue.robot" 2>/dev/null
  printf '%s\n' "$CELL"
  if [ -n "$NAMES" ]; then
    printf '${__n}=    Create List    %s\n' "$(sed 's/ $//; s/ /    /g' <<<"$NAMES")"
    printf '${__v}=    Get Variables    no_decoration=True\n'
    printf 'Evaluate    (lambda p, new: p.write_text(json.dumps({**json.loads(p.read_text()), **new}, default=str)))(pathlib.Path(r"%s/state.json"), {n: $__v[n] for n in $__n if n in $__v and isinstance($__v[n], (str, int, float, bool, list, dict, type(None)))})    modules=json,pathlib\n' "$D"
  fi
} | "$RC" repl --plain --no-history -d "$D" -V "$D/state.json" > "$D/last.txt" 2>&1
grep -v "^\s*$" "$D/last.txt"
grep -q "\[ FAIL \]" "$D/last.txt" && { echo "== FAIL"; exit 1; } || { echo "== PASS"; exit 0; }
