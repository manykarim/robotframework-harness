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
