"""Fail when the package version, the plugin manifest and the marketplace entry disagree (release invariant)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def versions() -> dict[str, str]:
    init = (ROOT / "src" / "rf_harness" / "__init__.py").read_text(encoding="utf-8")
    m = re.search(r'__version__\s*=\s*"([^"]+)"', init)
    found = {"package": m.group(1) if m else "<missing>"}
    plugin = ROOT / "plugins" / "rf-harness" / ".claude-plugin" / "plugin.json"
    found["plugin.json"] = json.loads(plugin.read_text(encoding="utf-8")).get("version", "<missing>")
    market = ROOT / ".claude-plugin" / "marketplace.json"
    if market.is_file():
        data = json.loads(market.read_text(encoding="utf-8"))
        for p in data.get("plugins", []):
            if p.get("name") == "rf-harness":
                found["marketplace.json"] = p.get("version", "<missing>")
    return found


def main() -> int:
    found = versions()
    if len(set(found.values())) != 1:
        print("version mismatch: " + ", ".join(f"{k}={v}" for k, v in found.items()), file=sys.stderr)
        return 1
    print("versions consistent: " + next(iter(found.values())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
