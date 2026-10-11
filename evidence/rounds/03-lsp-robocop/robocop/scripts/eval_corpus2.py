"""Round 3 / robocop: evaluate the agent-syntax corpus (../corpus2).

Per case: robocop default, robocop agent profile, robotcode analyze, robot dry-run (+ real run for BuiltIn-only
cases); then the auto-fix pipeline on copies:
  fix_safe   = robocop check --fix  (agent profile)
  fix_unsafe = robocop check --fix --unsafe-fixes (agent profile)
  fmt        = robocop format (defaults) applied after fix_safe
and re-validation of the fixed copy (robocop profile, robotcode analyze, dry-run/real run).
Writes ../out/corpus2_eval.json and ../out/corpus2_diffs/*.diff
"""

from __future__ import annotations

import difflib
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
R3 = HERE.parent
CORPUS = R3 / "corpus2"
OUT = R3 / "out"
DIFFS = OUT / "corpus2_diffs"
VENV = Path("~/workspace/robotcode-experiments/.venv/bin")
RC = str(VENV / "robocop")
PROFILE = str(R3 / "configs" / "robocop-agent.toml")


def robocop(files: list[str], profile: bool, extra: list[str] | None = None) -> list[dict]:
    report = OUT / "tmp_report2.json"
    report.unlink(missing_ok=True)
    cmd = [RC, "check", "--no-cache", "--skip-gitignore", "--root", str(CORPUS), "--exit-zero", "--silent",
           "--reports", "json_report", "-c", f"json_report.output_path={report}"]
    if profile:
        cmd += ["--config", PROFILE]
    cmd += [*(extra or []), *files]
    subprocess.run(cmd, cwd=CORPUS, capture_output=True, text=True)
    try:
        issues = json.loads(report.read_text())
    except Exception:  # noqa: BLE001
        issues = []
    targets = {Path(f).as_posix() for f in files}
    return [{"rule": i["rule_id"], "sev": i["severity"], "line": i["line"], "msg": i["description"][:160]}
            for i in issues if Path(i["source"]).as_posix() in targets]


def analyze(file: str) -> list[dict]:
    p = subprocess.run([str(VENV / "robotcode"), "analyze", "code", "--output-format", "json", file],
                       cwd=CORPUS, capture_output=True, text=True)
    try:
        data = json.loads(p.stdout)
    except json.JSONDecodeError:
        return [{"code": "PARSE-FAIL", "sev": 0, "line": 0, "msg": p.stdout[-200:] + p.stderr[-200:]}]
    out = []
    for _f, items in (data.get("diagnostics") or {}).items():
        for d in items:
            out.append({"code": d.get("code"), "sev": d.get("severity"), "line": d["range"]["start"]["line"] + 1,
                        "msg": d.get("message", "").splitlines()[0][:160]})
    return out


def run(file: str, real: bool) -> dict:
    cmd = [str(VENV / "python"), str(HERE / "run_case.py"), file] + (["--real"] if real else [])
    p = subprocess.run(cmd, cwd=CORPUS, capture_output=True, text=True)
    try:
        return json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        return {"rc": -1, "raw": p.stdout[-300:] + p.stderr[-300:]}


def verdict(r: dict) -> str:
    if r.get("rc", -1) != 0:
        return "FAIL"
    warns = [e for e in r.get("errors", []) if e.startswith(("WARN", "ERROR"))]
    return "PASS+warn" if warns else "PASS"


def fix_copy(src: Path, dst: Path, mode: str) -> tuple[str, list[str]]:
    shutil.copy(src, dst)
    rel = dst.relative_to(CORPUS).as_posix()
    if mode in ("safe", "unsafe"):
        cmd = [RC, "check", "--no-cache", "--skip-gitignore", "--root", str(CORPUS), "--exit-zero", "--silent",
               "--config", PROFILE, "--fix"] + (["--unsafe-fixes"] if mode == "unsafe" else []) + [rel]
    else:  # format with defaults
        cmd = [RC, "format", "--no-cache", "--skip-gitignore", "--root", str(CORPUS), "--silent", rel]
    p = subprocess.run(cmd, cwd=CORPUS, capture_output=True, text=True)
    before = src.read_text().splitlines(keepends=True)
    after = dst.read_text().splitlines(keepends=True)
    diff = list(difflib.unified_diff(before, after, f"a/{src.name}", f"b/{dst.name}"))
    return p.stdout[-300:] + p.stderr[-300:], diff


def main() -> None:
    manifest = json.loads((CORPUS / "manifest.json").read_text())
    only = set(sys.argv[1:])
    fixed_dir = CORPUS / "fixed"
    fixed_dir.mkdir(exist_ok=True)
    DIFFS.mkdir(parents=True, exist_ok=True)
    rows = []
    for c in manifest:
        if only and c["id"] not in only:
            continue
        f = c["file"]
        row = dict(c)
        row["robocop_default"] = robocop([f], profile=False)
        row["robocop_agent"] = robocop([f], profile=True)
        row["analyze"] = analyze(f)
        row["dryrun"] = run(f, real=False)
        if c["runnable"]:
            row["real"] = run(f, real=True)
        # fix pipeline
        src = CORPUS / f
        fx = {}
        for mode in ("safe", "unsafe"):
            dst = fixed_dir / f"{c['id']}.{mode}.robot"
            log, diff = fix_copy(src, dst, mode)
            (DIFFS / f"{c['id']}.{mode}.diff").write_text("".join(diff))
            rel = dst.relative_to(CORPUS).as_posix()
            fx[mode] = {
                "changed_lines": sum(1 for d in diff if d[:1] in "+-" and not d.startswith(("+++", "---"))),
                "log": log,
                "robocop_agent_after": robocop([rel], profile=True),
                "analyze_after": analyze(rel),
                "dryrun_after": verdict(run(rel, real=False)),
                "real_after": verdict(run(rel, real=True)) if c["runnable"] else None,
            }
        # format on top of the safe fix
        safe = fixed_dir / f"{c['id']}.safe.robot"
        fmt_dst = fixed_dir / f"{c['id']}.safe_fmt.robot"
        log, diff = fix_copy(safe, fmt_dst, "format")
        (DIFFS / f"{c['id']}.safe_fmt.diff").write_text("".join(diff))
        rel = fmt_dst.relative_to(CORPUS).as_posix()
        fx["format"] = {
            "changed_lines": sum(1 for d in diff if d[:1] in "+-" and not d.startswith(("+++", "---"))),
            "log": log,
            "analyze_after": analyze(rel),
            "dryrun_after": verdict(run(rel, real=False)),
            "real_after": verdict(run(rel, real=True)) if c["runnable"] else None,
        }
        row["fix"] = fx
        rows.append(row)
        print(c["id"], "| default:", sorted({i["rule"] for i in row["robocop_default"]}),
              "| agent:", sorted({i["rule"] for i in row["robocop_agent"]}),
              "| analyze:", sorted({str(i["code"]) for i in row["analyze"]}),
              "| dry:", verdict(row["dryrun"]), "| real:", verdict(row["real"]) if c["runnable"] else "-",
              "| safe-fix d=", fx["safe"]["changed_lines"], "->", sorted({i["rule"] for i in fx["safe"]["robocop_agent_after"]}),
              fx["safe"]["dryrun_after"], fx["safe"]["real_after"],
              "| unsafe d=", fx["unsafe"]["changed_lines"], fx["unsafe"]["real_after"],
              "| fmt d=", fx["format"]["changed_lines"], fx["format"]["real_after"], flush=True)
    name = "corpus2_eval.json" if not only else "corpus2_eval_partial.json"
    (OUT / name).write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
