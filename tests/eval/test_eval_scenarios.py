"""check-scenarios: the ported scenario definitions, graders and fixtures are IDENTICAL to round 7."""

from __future__ import annotations

import subprocess
import sys

from eval_helpers import EVAL, SRC_HARNESS_DIR, needs, posix_only

pytestmark = posix_only


@needs(SRC_HARNESS_DIR / "harness.py")
def test_check_scenarios_reports_identical_to_round7():
    p = subprocess.run([sys.executable, str(EVAL / "harness.py"), "check-scenarios"], capture_output=True, text=True,
                       timeout=180)
    assert p.returncode == 0, p.stdout + p.stderr
    lines = [ln for ln in p.stdout.splitlines() if ln.split(" ", 1)[0] in ("IDENTICAL", "DIFFERENT", "MISSING")]
    assert len(lines) == 9                       # 4 round-1 + 5 live scenarios
    assert all(ln.startswith("IDENTICAL") for ln in lines), lines
    assert all("DIFFERENT" not in ln and "MISSING" not in ln for ln in lines), lines
    assert "ALL IDENTICAL: 9 scenarios" in p.stdout
    live = [ln for ln in lines if any(s in ln for s in ("tricentis", "carconfig", "demoshop"))]
    assert all("fixture IDENTICAL" in ln and "reference IDENTICAL" in ln for ln in live)


def test_scenario_hash_detects_any_definition_change():
    import harness as H

    mine = H.dump_scenarios(EVAL / "harness.py")
    d = next(x for x in mine["scenarios"] if x["id"] == "demoshop_order")
    base = H.scenario_hash(d)
    assert base == H.scenario_hash(dict(d))                         # stable
    assert base == H.scenario_hash(dict(reversed(list(d.items()))))  # key order does not matter
    for field, value in [("prompt", d["prompt"] + " "), ("timeout_s", d["timeout_s"] + 1),
                         ("graders", d["graders"][:-1]), ("fixture", "other")]:
        assert H.scenario_hash(dict(d, **{field: value})) != base, field


def test_tree_hash_sees_content_and_names(tmp_path):
    import harness as H

    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.robot").write_text("one")
    h1 = H.tree_hash(tmp_path / "a")
    (tmp_path / "a" / "x.robot").write_text("two")
    assert H.tree_hash(tmp_path / "a") != h1
    assert H.tree_hash(tmp_path / "missing") is None


def test_check_scenarios_fails_against_a_modified_reference(tmp_path):
    src = (EVAL / "harness.py").read_text(encoding="utf-8")
    marker = '"Write a Browser-library Robot Framework test at tests/shop_order.robot that places'
    assert marker in src
    (tmp_path / "harness.py").write_text(src.replace(marker, marker.replace("places", "submits")), encoding="utf-8")
    for dep in ("openrouter.py", "validity.py", "value_graders.py"):
        (tmp_path / dep).write_text((EVAL / dep).read_text(encoding="utf-8"), encoding="utf-8")
    p = subprocess.run([sys.executable, str(EVAL / "harness.py"), "check-scenarios", "--against",
                        str(tmp_path / "harness.py")], capture_output=True, text=True, timeout=180,
                       env={"PATH": "/usr/bin:/bin", "AB_FIXTURES_DIR": str(EVAL / "fixtures"),
                            "AB_FIXTURES_LIVE_DIR": str(EVAL / "fixtures_live")})
    assert p.returncode == 1, p.stdout + p.stderr
    assert "DIFFERENT demoshop_order" in p.stdout and "prompt" in p.stdout
