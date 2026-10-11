"""Warm in-process robocop: repeated robocop.run.check_files(return_result=True) calls in one Python process.

usage: python warm_api.py <file.robot> <profile.toml>   -> prints one JSON line
"""

from __future__ import annotations

import contextlib
import io
import json
import statistics
import sys
import time
from pathlib import Path

t_import0 = time.perf_counter()
from robocop.run import check_files  # noqa: E402

t_import = time.perf_counter() - t_import0


def call(src: Path, profile: str | None, **kw) -> tuple[float, list]:
    kw.setdefault("cache", False)
    buf = io.StringIO()
    t0 = time.perf_counter()
    with contextlib.redirect_stdout(buf):
        diags = check_files(
            sources=[str(src)], root=src.parent, configuration_file=Path(profile) if profile else None,
            return_result=True, silent=True, skip_gitignore=True, exit_zero=True, **kw,
        )
    return time.perf_counter() - t0, diags


def series(src: Path, profile: str | None, n: int = 8, edit: bool = False, **kw) -> dict:
    original = src.read_text()
    ts, counts = [], []
    try:
        for k in range(n):
            if edit:
                src.write_text(original + f"\n# edit {k}\n")
            dt, diags = call(src, profile, **kw)
            ts.append(dt)
            counts.append(len([d for d in diags if Path(str(d.source.path)).name == src.name]))
    finally:
        src.write_text(original)
    return {"first_s": round(ts[0], 3), "warm_median_s": round(statistics.median(ts[1:]), 3),
            "warm_min_s": round(min(ts[1:]), 3), "issues": counts[-1]}


def main() -> None:
    src = Path(sys.argv[1]).resolve()
    profile = sys.argv[2]
    out = {"import_s": round(t_import, 3)}
    out["agent_profile"] = series(src, profile)
    out["agent_profile_edit_each_call"] = series(src, profile, edit=True)
    out["default_rules"] = series(src, None)
    cdir = src.parent.parent / "cache_warm_api"
    out["agent_profile_persistent_cache_edit_each_call"] = series(src, profile, edit=True, cache=True,
                                                                  cache_dir=cdir)
    out["agent_profile_no_analyze_libraries"] = series(src, profile, analyze_libraries=False)
    print(json.dumps(out))


if __name__ == "__main__":
    main()
