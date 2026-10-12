"""Release invariant: the package version, the plugin manifest and the marketplace entries describe the same release.

- Without `--tag`: the RELEASE PART must be equal everywhere. Pre-release suffixes of the package version (`rcN`,
  `aN`, `bN`, `.devN`) are stripped, because plugin manifests only carry plain release versions (a release candidate
  such as 1.0.0rc1 is a PyPI dry run of 1.0.0).
- With `--tag vX`: additionally the package version must equal X exactly (the release workflow's first check).

    python scripts/check_versions.py                 # CI
    python scripts/check_versions.py --tag v1.0.0    # release workflow
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRE_RE = re.compile(r"(?:\.?(?:a|b|rc)\d+)?(?:\.dev\d+)?$")


def release_part(version: str) -> str:
    """1.0.0rc1 -> 1.0.0, 1.2.0.dev3 -> 1.2.0, 1.0.0 -> 1.0.0."""
    return PRE_RE.sub("", version.strip())


def versions() -> dict[str, str]:
    init = (ROOT / "src" / "rf_harness" / "__init__.py").read_text(encoding="utf-8")
    m = re.search(r'__version__\s*=\s*"([^"]+)"', init)
    found = {"package": m.group(1) if m else "<missing>"}
    plugin = ROOT / "plugins" / "rf-harness" / ".claude-plugin" / "plugin.json"
    found["plugin.json"] = json.loads(plugin.read_text(encoding="utf-8")).get("version", "<missing>")
    market = ROOT / ".claude-plugin" / "marketplace.json"
    if market.is_file():
        data = json.loads(market.read_text(encoding="utf-8"))
        if "metadata" in data:
            found["marketplace.json metadata"] = data["metadata"].get("version", "<missing>")
        for p in data.get("plugins", []):
            if p.get("name") == "rf-harness":
                found["marketplace.json plugin"] = p.get("version", "<missing>")
    return found


def check(found: dict[str, str], tag: str | None = None) -> list[str]:
    problems = []
    parts = {k: (release_part(v) if k == "package" else v) for k, v in found.items()}
    if len(set(parts.values())) != 1:
        problems.append("release versions differ: " + ", ".join(f"{k}={v}" for k, v in found.items()))
    if tag is not None:
        want = tag[1:] if tag.startswith("v") else tag
        if found.get("package") != want:
            problems.append(f"tag {tag} does not match the package version {found.get('package')}")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--tag", help="release tag, e.g. v1.0.0 or v1.0.0rc1")
    args = ap.parse_args([] if argv is None else argv)
    found = versions()
    problems = check(found, args.tag)
    for p in problems:
        print(p, file=sys.stderr)
    if problems:
        return 1
    print(f"versions consistent: {found['package']}" + (f" (tag {args.tag})" if args.tag else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
