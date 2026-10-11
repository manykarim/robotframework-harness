"""Round 3 / robocop: noise of the default rule set vs the agent profile on agent-written suites.

../noise_corpus holds 36 agent-written .robot files (rf-mcp eval runs, ab-eval runs, robotcode stepwise
recordings). Uses the worktree venv robocop (has Browser, SeleniumLibrary, RequestsLibrary installed).
Writes ../out/noise.json and prints a summary.
"""

from __future__ import annotations

import collections
import json
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
R3 = HERE.parent
N = R3 / "noise_corpus"
OUT = R3 / "out"
RC = "~/workspace/rf-mcp-robotcode/.venv/bin/robocop"
PROFILE = str(R3 / "configs" / "robocop-agent.toml")


def run(mode: str) -> tuple[list[dict], float, str]:
    report = OUT / f"noise_{mode}.json"
    report.unlink(missing_ok=True)
    cmd = [RC, "check", "--no-cache", "--skip-gitignore", "--root", str(N), "--exit-zero",
           "--reports", "json_report", "-c", f"json_report.output_path={report}",
           "-c", "print_issues.output_format=simple"]
    if mode == "agent":
        cmd += ["--config", PROFILE]
    elif mode == "minimal":
        cmd += ["--config", str(R3 / "configs" / "minimal_only.toml")]
    t0 = time.perf_counter()
    p = subprocess.run(cmd + ["."], cwd=N, capture_output=True, text=True)
    dt = time.perf_counter() - t0
    return json.loads(report.read_text()), dt, p.stdout


def main() -> None:
    files = sorted(str(p.relative_to(N)) for p in N.rglob("*.robot"))
    loc = sum(len(p.read_text().splitlines()) for p in N.rglob("*.robot"))
    res = {"files": len(files), "loc": loc}
    for mode in ("default", "minimal", "agent"):
        issues, dt, stdout = run(mode)
        by_rule = collections.Counter(f"{i['rule_id']} {i['rule_name']}" for i in issues)
        by_prefix = collections.Counter("".join(ch for ch in i["rule_id"] if ch.isalpha()) for i in issues)
        by_sev = collections.Counter(i["severity"] for i in issues)
        per_file = collections.Counter(i["source"] for i in issues)
        res[mode] = {
            "issues": len(issues), "elapsed_s": round(dt, 2), "stdout_chars": len(stdout),
            "by_sev": dict(by_sev), "by_prefix": dict(by_prefix.most_common()),
            "top_rules": by_rule.most_common(25),
            "files_with_issues": len(per_file),
            "median_per_file": sorted(per_file.values())[len(per_file) // 2] if per_file else 0,
            "issues_list": [{k: i[k] for k in ("source", "line", "rule_id", "severity", "description")}
                            for i in issues] if mode == "agent" else None,
        }
        print(f"== {mode}: {len(issues)} issues in {len(per_file)}/{len(files)} files, {dt:.1f}s, "
              f"sev={dict(by_sev)}")
        print("   prefixes:", dict(by_prefix.most_common()))
        for r, n in by_rule.most_common(12):
            print(f"   {n:4d} {r}")
    (OUT / "noise.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
