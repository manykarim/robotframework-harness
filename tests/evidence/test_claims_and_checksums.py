"""evidence/check_claims.py and evidence/checksums.py: the archive reproduces its claims, edits are caught."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

EVIDENCE = Path(__file__).resolve().parents[2] / "evidence"
ROUND7 = "rounds/07-v31-v32"
V31SUB = f"{ROUND7}/results/results_live_v31sub.jsonl"

pytestmark = pytest.mark.skipif(not (EVIDENCE / "rounds").is_dir(), reason="evidence archive not imported")


def test_all_claims_reproduce(check_claims, capsys) -> None:
    assert check_claims.main([]) == 0, capsys.readouterr().out


def test_claim_sources_are_quoted_verbatim(check_claims, capsys) -> None:
    assert check_claims.main(["--check-sources"]) == 0, capsys.readouterr().out


@pytest.mark.slow
@pytest.mark.skipif(sys.version_info < (3, 12), reason="sum() float summation changed in 3.12; research ran on 3.12+")
def test_reports_regenerate(check_claims, capsys) -> None:
    assert check_claims.main(["--reports"]) == 0, capsys.readouterr().out


def test_every_readme_claim_is_indexed(check_claims) -> None:
    claims = check_claims.load_claims()
    readme_ids = {c["id"] for c in claims if any(s["file"] == "../README.md" for s in c.get("sources", []))}
    assert {"readme-pooled-harness", "readme-pooled-rfmcp", "readme-sessions", "readme-qwen-rfmcp",
            "readme-qwen-harness"} <= readme_ids


def _copy_round7(tmp_path: Path) -> Path:
    root = tmp_path / "evidence"
    shutil.copytree(EVIDENCE / ROUND7 / "results", root / ROUND7 / "results")
    shutil.copyfile(EVIDENCE / "claims.yaml", root / "claims.yaml")
    return root


def test_editing_one_result_row_fails_the_check(check_claims, tmp_path: Path, capsys) -> None:
    root = _copy_round7(tmp_path)
    args = ["--root", str(root), "--claims", str(root / "claims.yaml"), "--only", "readme-pooled-harness"]
    assert check_claims.main(args) == 0
    path = root / V31SUB
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    for i, line in enumerate(lines):  # flip the first passing harness row to a failure
        row = json.loads(line)
        if row["arm"] == "hookpkg31" and row["primary_pass"]:
            row["primary_pass"] = False
            lines[i] = json.dumps(row) + "\n"
            break
    path.write_text("".join(lines), encoding="utf-8")
    capsys.readouterr()
    assert check_claims.main(args) == 1
    out = capsys.readouterr().out
    assert "FAIL readme-pooled-harness" in out and "passes: expected 58, computed 57" in out


def test_contaminated_policy(check_claims) -> None:
    claim = {"files": [f"{ROUND7}/results/results_live_v31sub.jsonl", f"{ROUND7}/results/results_live_v31or.jsonl"],
             "compute": {"metric": "pass_rate", "filter": {"arms": ["mcp"]}, "contaminated": "keep"}}
    keep = check_claims.compute(claim, EVIDENCE)
    claim["compute"]["contaminated"] = "drop"
    drop = check_claims.compute(claim, EVIDENCE)
    assert (keep["passes"], keep["n"]) == (47, 68) and (drop["passes"], drop["n"]) == (46, 67)


def test_statistics_match_published_values(check_claims) -> None:
    assert round(check_claims.fisher_exact(58, 12, 47, 21), 3) == 0.073
    assert round(check_claims.sign_test(8, 0), 3) == 0.008
    lo, hi = check_claims.wilson(58, 70)
    assert (round(lo, 2), round(hi, 2)) == (0.72, 0.90)


def test_checksums_verify(checksums, capsys) -> None:
    assert checksums.main(["--verify"]) == 0, capsys.readouterr().out


def test_checksums_catch_edits_and_unlisted_files(checksums, tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    shutil.copytree(EVIDENCE / ROUND7, root / ROUND7)
    checksums.write(root)
    assert checksums.verify(root) == []
    (root / V31SUB).write_bytes((root / V31SUB).read_bytes() + b"\n")
    (root / ROUND7 / "results" / "extra.jsonl").write_text("{}\n", encoding="utf-8")
    problems = checksums.verify(root)
    assert f"checksums.sha256: checksum mismatch {V31SUB}" in problems
    assert f"{ROUND7}/checksums.sha256: checksum mismatch results/results_live_v31sub.jsonl" in problems
    assert any("not listed" in p and p.endswith("results/extra.jsonl") for p in problems)


def test_round7_folder_is_auditable() -> None:
    """Spec scenario 'a round can be audited'."""
    r7 = EVIDENCE / ROUND7
    for rel in ("findings_v31.md", "config.json", "scenarios.json", "checksums.sha256", "README.md",
                "results/results_live_v31sub.jsonl", "results/results_live_v31or.jsonl",
                "results/results_live_v32.jsonl", "reports/report_live_v31sub.txt", "reports/report_live_v32.txt",
                "excluded/excluded_credits_402.jsonl"):
        assert (r7 / rel).is_file(), rel
    cfg = json.loads((r7 / "config.json").read_text(encoding="utf-8"))
    assert cfg["dates_utc"] == ["2026-10-10"]
    assert all(run["agents"] and run["models"] and run["reps"] for run in cfg["runs"])
    scen = json.loads((r7 / "scenarios.json").read_text(encoding="utf-8"))
    assert {s["id"] for s in scen["scenarios"]} == {"tricentis_quote", "carconfig_order", "demoshop_order",
                                                   "demoshop_debug", "tricentis_debug"}
    assert all(s["graders"] for s in scen["scenarios"])
    excluded = [json.loads(ln) for ln in (r7 / "excluded/excluded_credits_402.jsonl").read_text("utf-8").splitlines()]
    assert len(excluded) == 76 and {e["reason"] for e in excluded} == {"credits_402"}
    assert all((r7 / b).is_file() for e in excluded for b in e["backups"])


def test_archived_files_are_not_gitignored(checksums) -> None:
    """Root .gitignore hides results/, output.xml, log.html, report.html, site/; evidence/.gitignore re-includes them."""
    git = shutil.which("git")
    if git is None or not (EVIDENCE.parent / ".git").exists():
        pytest.skip("not a git checkout")
    paths = "\n".join(p.relative_to(EVIDENCE.parent).as_posix() for p in checksums.covered_files(EVIDENCE))
    proc = subprocess.run([git, "check-ignore", "--no-index", "--stdin"], input=paths, capture_output=True,
                          text=True, cwd=EVIDENCE.parent)
    assert proc.stdout.strip() == "", f"archived files hidden by .gitignore:\n{proc.stdout[:2000]}"
