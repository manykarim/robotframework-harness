#!/usr/bin/env bash
# print the PID listening on 127.0.0.1:$1 (only processes of the current user)
ss -ltnp 2>/dev/null | awk -v p=":$1" '$4 ~ p"$" {match($0,/pid=[0-9]+/); print substr($0,RSTART+4,RLENGTH-4)}' | head -1
