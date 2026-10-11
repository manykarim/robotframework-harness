"""The product's own state paths are not contamination; another arm's markers and state paths still are."""


def test_rf_harness_own_state_dirs_are_not_cross_hits(tmp_path):
    import harness as H

    for d in ("hook", "exec", "lint"):
        (tmp_path / ".rf" / d).mkdir(parents=True)
    (tmp_path / ".rf" / "harness.json").write_text("{}")
    res = H.contamination("rf-harness", [], tmp_path, 0)
    assert res["hook_cross_hits"] == 0 and res["contaminated"] is False


def test_foreign_prototype_state_and_marker_are_cross_hits(tmp_path):
    import harness as H

    (tmp_path / ".rf" / "hook32").mkdir(parents=True)
    calls = [{"kind": "shell", "input": "python3 ~/rfharness32/hook.py"}]
    res = H.contamination("rf-harness", calls, tmp_path, 0)
    assert res["hook_cross_hits"] >= 2 and res["contaminated"] is True


def test_product_state_in_mcp_arm_is_contamination(tmp_path):
    import harness as H

    (tmp_path / ".rf" / "hook").mkdir(parents=True)
    assert H.contamination("mcp", [], tmp_path, 1)["contaminated"] is True
