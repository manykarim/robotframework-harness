import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location("check_versions", ROOT / "scripts" / "check_versions.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_versions_are_consistent():
    assert _load().main() == 0


def test_mismatch_is_detected(tmp_path, monkeypatch):
    mod = _load()
    (tmp_path / "src" / "rf_harness").mkdir(parents=True)
    (tmp_path / "src" / "rf_harness" / "__init__.py").write_text('__version__ = "1.2.3"\n')
    (tmp_path / "plugins" / "rf-harness" / ".claude-plugin").mkdir(parents=True)
    (tmp_path / "plugins" / "rf-harness" / ".claude-plugin" / "plugin.json").write_text(json.dumps({"version": "1.2.4"}))
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    assert mod.main() == 1


def test_release_part():
    mod = _load()
    assert mod.release_part("1.0.0rc1") == "1.0.0"
    assert mod.release_part("1.2.0.dev3") == "1.2.0"
    assert mod.release_part("1.0.0b2") == "1.0.0"
    assert mod.release_part("1.0.0") == "1.0.0"


def test_tag_rules():
    mod = _load()
    final = {"package": "1.0.0", "plugin.json": "1.0.0", "marketplace.json plugin": "1.0.0"}
    rc = {"package": "1.0.0rc1", "plugin.json": "1.0.0", "marketplace.json plugin": "1.0.0"}
    assert mod.check(final, "v1.0.0") == []
    assert mod.check(rc, "v1.0.0rc1") == []                    # candidate: plugin manifests keep the release part
    assert mod.check(rc) == []                                 # CI: release parts agree
    assert mod.check(final, "v1.0.1")                          # mismatched tag
    assert mod.check(rc, "v1.0.0")                             # final tag on a candidate version
    assert mod.check({**final, "plugin.json": "0.9.0"}, "v1.0.0")   # manifest drift


def test_cli_with_tag(capsys):
    mod = _load()
    version = mod.versions()["package"]
    assert mod.main(["--tag", f"v{version}"]) == 0
    assert mod.main(["--tag", "v0.0.0"]) == 1
