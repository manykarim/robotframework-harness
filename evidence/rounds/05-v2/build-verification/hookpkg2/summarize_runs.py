"""Print a compact summary of verify/runs/*.json (real agent sessions run by agents_run.py)."""
import json
import sys

for f in sys.argv[1:]:
    try:
        d = json.load(open(f))
    except Exception as e:
        print(f, "ERR", e)
        continue
    for k, r in d.items():
        print("==", k, {x: r.get(x) for x in ('wall_s', 'timed_out', 'tool_calls', 'rfmcp_cli_calls', 'plain_order',
                                              'plain_checkout', 'processes_left_after_exit',
                                              'stray_processes_after_exit', 'creds_deleted', 'kwdoc_reads',
                                              'latest_reads', 'repl_calls')})
        print('   evidence', {k2: v for k2, v in (r.get('evidence_in_transcript') or {}).items() if v})
        h = r['hooks']
        print('   v2', h.get('v2'), 'denials', h.get('denials'), 'rewrites', h.get('rewrites'), 'stop',
              h.get('stop_blocks'), 'lines', h.get('auto_executed_lines'), 'nonpass', h.get('non_pass_lines'),
              'errors', h.get('errors'))
        print('   lat', {e: v['median'] for e, v in (h.get('latency_ms') or {}).items()})
