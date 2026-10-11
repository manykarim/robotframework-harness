#!/usr/bin/env python3
"""Secret check for evaluation outputs before they are uploaded or archived (stdlib only).

    python3 eval/secret_scan.py DIR [DIR ...] [--env OPENROUTER_API_KEY,ANTHROPIC_API_KEY,...]

Fails (exit 1) when any file under DIR (plain text or .gz) contains
  * the literal value of a secret environment variable (default: the harness' SECRET_ENV list) or its first 12
    characters (a truncated key is still a leak), or
  * a key-shaped token: OpenRouter `sk-or-...`, Anthropic `sk-ant-...`, OpenAI `sk-proj-...` / `sk-...` (32+ chars),
    GitHub `ghp_` / `gho_` / `github_pat_`, AWS `AKIA...`.
Only file paths, line numbers and the finding TYPE are printed, never the matched text. Exit 0 = clean.

The full scrubber of the evidence archive is evidence/scrub.py (owned by the evidence tooling); the eval workflow runs
both. This check needs no configuration and is what the workflow relies on when evidence/scrub.py is absent.
"""
from __future__ import annotations

import argparse
import gzip
import os
import re
import sys
from pathlib import Path

DEFAULT_ENV = ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "CODEX_API_KEY",
               "GITHUB_TOKEN", "GH_TOKEN", "COPILOT_GITHUB_TOKEN")
PATTERNS = [
    ("openrouter-key", re.compile("sk-" + "or-" + r"[A-Za-z0-9_\-]{16,}")),
    ("anthropic-key", re.compile("sk-" + "ant-" + r"[A-Za-z0-9_\-]{16,}")),
    ("openai-key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{32,}")),
    ("github-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})")),
    ("aws-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
]
PREFIX_LEN = 12
MAX_BYTES = 64 * 1024 * 1024


def secret_values(names: list[str]) -> list[tuple[str, str]]:
    """(env name, needle) pairs: the full value and its first PREFIX_LEN characters (values shorter than 8 skipped)."""
    out = []
    for n in names:
        v = (os.environ.get(n) or "").strip()
        if len(v) < 8:
            continue
        out.append((n, v))
        if len(v) > PREFIX_LEN:
            out.append((f"{n} (prefix)", v[:PREFIX_LEN]))
    return out


def _read(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_BYTES:
            return None
        data = gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()
        return data.decode("utf-8", errors="replace")
    except (OSError, EOFError, gzip.BadGzipFile):
        return None


def scan(dirs: list[Path], names: list[str]) -> list[dict]:
    needles = secret_values(names)
    findings = []
    for d in dirs:
        files = [d] if d.is_file() else sorted(p for p in d.rglob("*") if p.is_file())
        for f in files:
            text = _read(f)
            if text is None:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                for name, needle in needles:
                    if needle in line:
                        findings.append({"file": str(f), "line": lineno, "type": f"env:{name}"})
                for name, rx in PATTERNS:
                    if rx.search(line):
                        findings.append({"file": str(f), "line": lineno, "type": name})
    return findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="fail when eval outputs contain secrets (prints locations only)")
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--env", default=",".join(DEFAULT_ENV), help="secret env var names whose values must not appear")
    args = ap.parse_args(argv)
    paths = [Path(p) for p in args.paths]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        print(f"secret_scan: nothing to scan at {', '.join(missing)}")
    found = scan([p for p in paths if p.exists()], [n for n in args.env.split(",") if n])
    for f in found[:200]:
        print(f"SECRET {f['type']}: {f['file']}:{f['line']}")
    print(f"secret_scan: {len(found)} finding(s) in {', '.join(str(p) for p in paths)}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
