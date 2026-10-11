"""The generated CLI/environment references stay current, and a variable used in code or docs must be registered."""

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _gen():
    spec = importlib.util.spec_from_file_location("gen_reference", ROOT / "scripts" / "gen_reference.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_references_are_current():
    assert _gen().main(["--check"]) == 0


def test_unregistered_variable_fails_the_check(monkeypatch):
    mod = _gen()
    monkeypatch.setattr(mod, "_used_names", lambda: {"RFH_NOT_REGISTERED_ANYWHERE"})
    assert mod.main(["--check"]) == 1


def test_docs_only_name_registered_variables():
    from rf_harness import config

    unknown = set()
    for page in (ROOT / "docs").rglob("*.md"):
        for name in re.findall(r"\bRFH_[A-Z][A-Z0-9_]*\b", page.read_text(encoding="utf-8")):
            if not name.endswith("_") and name not in config.VARIABLES:
                unknown.add(f"{page.relative_to(ROOT)}: {name}")
    assert not unknown, sorted(unknown)


def test_every_concept_page_links_evidence():
    missing = [p.name for p in sorted((ROOT / "docs" / "concepts").glob("*.md"))
               if "../../evidence/" not in p.read_text(encoding="utf-8")]
    assert missing == []
