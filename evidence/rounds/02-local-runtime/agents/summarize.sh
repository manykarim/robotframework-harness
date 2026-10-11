#!/usr/bin/env bash
cd ~/workspace/rf-mcp-robotcode/experiments/robotcode-remote/round2/agents
for f in runs/*/s[1-9]_*/result.json; do python3 -c "
import json,sys;d=json.load(open('$f'));print(d['agent'],d['scenario'],'rc',d['rc'],'to',d['timed_out'],'wall',d['session_wall_s'],'alive3',d['alive_3s_after_session'],'alive10',d['alive_10s_after_session'],'trans',[ (t['t'],len(t['pids'])) for t in d['daemon_transitions']])"; done
