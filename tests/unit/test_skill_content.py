"""The shipped skill must not contain evaluation-scenario fixtures (that would contaminate the A/B evidence) and must
keep the harness contract the hooks rely on."""

import re
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2] / "plugins" / "rf-harness" / "skills" / "rf-harness"

# sites, data and selectors of the live evaluation scenarios (eval/harness.py)
FIXTURE_RE = re.compile(
    r"tricentis|sampleapp|platinum|demoshop|carconfig|makrocode|flowline|horizon portable|cascade water|lovelace"
    r"|morgan\.lee|musterfrau|selectplatinum|choosePrice|ab-[0-9a-f]{10}",
    re.I,
)


def _files():
    return sorted(p for p in SKILL.rglob("*.md"))


def test_skill_has_no_scenario_fixtures():
    hits = [f"{p.relative_to(SKILL)}:{i}: {line.strip()[:80]}"
            for p in _files() for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
            if FIXTURE_RE.search(line)]
    assert hits == []


def test_skill_frontmatter_and_contract():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\nname: rf-harness\n")
    for needle in (".rf/state/latest/", ".rf/docs/", "robot -d results", "label:has(#id)", "[rfh]"):
        assert needle in text, needle
    assert not re.search(r"rfh3\d|rfharness3|RFH3\d", text)
