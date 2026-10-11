#!/usr/bin/env bash
# rfstep.sh: bash-only repl-server client (bash /dev/tcp + head -c; jq optional for pretty output)
# usage: rfstep.sh PORT 'Keyword  arg'
PORT=$1; CELL=$2
json_escape() { local s=$1; s=${s//\\/\\\\}; s=${s//\"/\\\"}; s=${s//$'\n'/\\n}; s=${s//$'\t'/\\t}; printf '%s' "$s"; }
BODY="{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"executeCell\",\"params\":{\"source\":\"$(json_escape "$CELL")\",\"language_id\":\"robotframework\"}}"
exec 3<>/dev/tcp/127.0.0.1/$PORT || exit 3
printf 'Content-Length: %d\r\n\r\n%s' "$(printf '%s' "$BODY" | wc -c)" "$BODY" >&3
LEN=0
while IFS= read -r line <&3; do line=${line%$'\r'}; [[ -z $line ]] && break; [[ $line =~ ^Content-Length:\ *([0-9]+) ]] && LEN=${BASH_REMATCH[1]}; done
head -c "$LEN" <&3
exec 3>&-
