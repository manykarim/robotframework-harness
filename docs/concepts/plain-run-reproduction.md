# Plain-run reproduction

When the agent runs `robot` (or `robotcode robot`), the post-tool hook reads the result:

1. **One line per failing test**, with the failing keyword and the message, instead of the full console output.
2. **The first failure is reproduced live.** The harness opens the suite in the live session and stops at the failing
   line, with the page state captured. The agent can fix that line with its edit tool, and only that part reruns.
3. **Races are named.** If the failure does **not** reproduce live, the agent is told:
   `NOT reproduced live … timing race: wait for the state the step needs before it`. After that, reproductions stop
   for the session, so the agent doesn't loop on a race.

```text
robot -d results tests/truck.robot: 3 tests, 1 passed, 2 failed
  Truck insurance quote: line 41 Select Options By    id=insurancesum    label    7.000.000,00
    -> option '7.000.000,00' not found (options: 3.000.000,00 | 5.000.000,00 | 7.000.000,00 €)
Reproduced live: stopped at tests/truck.robot:41 (page captured in .rf/state/latest/)
```

## Why

- Repairing an existing suite is half of real test work. In the live A/B rounds the hook arms did best on the debug
  scenarios (round 6: v2 0.71 and v3 0.67 vs rf-mcp 0.50).
- Reproducing the failure live means the agent sees the actual page at the failing step, instead of guessing from a
  log line.

## Configure

`RFH_REPRODUCE=0` turns live reproduction off. The failure summary stays.
