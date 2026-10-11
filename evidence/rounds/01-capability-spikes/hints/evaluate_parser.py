"""Measure how reliably (keyword, args, error) can be recovered from each robotcode output form.

Ground truth: corpus agent_call (keyword+args); expected failing line = the mistake line.
Reference error text: the repl-server's structured KeywordResultData.message (exact RF message).

  python evaluate_parser.py   -> results/parser_eval.json + results/parser_eval.md
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from corpus import CORPUS  # noqa: E402
from parse_robotcode import (  # noqa: E402
    parse_plain, parse_plain_v2, parse_replserver, parse_results_json, top_failures_k,
)

RUNS = HERE / "runs"
OUT = HERE / "results"


def norm_kw(s):
    return re.sub(r"[\s_]+", "", (s or "")).lower().split(".")[-1] if s else ""


def norm_ws(s):
    return re.sub(r"\s+", " ", s or "").strip()


def expected_line(m):
    lines = m["preamble"] + m["steps"]
    return len(lines) - (2 if m["id"] == "M41" else 1)


def main():
    OUT.mkdir(exist_ok=True)
    rows = []
    for m in CORPUS:
        d = RUNS / m["id"]
        plain_txt = (d / "plain" / "stdout.txt").read_text()
        k_txt = (d / "k" / "stdout.txt").read_text()
        stdin = (d / "plain" / "stdin.txt").read_text().splitlines()
        cells = json.loads((d / "replserver" / "cells.json").read_text())
        try:
            rj = json.loads((d / "plain" / "results_log.json").read_text())
        except Exception:  # noqa: BLE001
            rj = {}
        srcs = {
            "replserver": parse_replserver(cells),
            "results_json": parse_results_json(rj),
            "k": top_failures_k(k_txt),
            "plain+input": parse_plain(plain_txt, stdin),
            "plain v2+input": parse_plain_v2(plain_txt, stdin),
            "plain(error only)": parse_plain(plain_txt, None),
        }
        ref = srcs["replserver"][0]["error"] if srcs["replserver"] else None
        exp_kw, exp_args = m["agent_call"]["keyword"], m["agent_call"]["arguments"]
        exp_line = None if m["id"] == "M18" else expected_line(m)
        row = {"id": m["id"], "title": m["title"], "ref_error": ref, "sources": {}}
        for name, steps in srcs.items():
            first = steps[0] if steps else None
            r = {"n_fail": len(steps)}
            if first:
                r.update(
                    keyword=first.get("keyword"), args=first.get("args"), error=first.get("error"),
                    confidence=first.get("confidence"),
                    keyword_ok=norm_kw(first.get("keyword")) == norm_kw(exp_kw),
                    args_ok=first.get("args") == exp_args,
                    error_exact=(first.get("error") or "").rstrip() == (ref or "").rstrip(),
                    error_norm=norm_ws(first.get("error")) == norm_ws(ref),
                )
                if name in ("plain+input", "plain v2+input"):
                    r["line_ok"] = first.get("line_index") == exp_line
            row["sources"][name] = r
        rows.append(row)
    (OUT / "parser_eval.json").write_text(json.dumps(rows, indent=2))

    # summary table
    names = ["replserver", "results_json", "k", "plain+input", "plain v2+input", "plain(error only)"]
    failing = [r for r in rows if r["ref_error"]]
    lines = ["| source | mistakes w/ failure found | keyword ok | args ok | error == ref (exact) | error == ref (ws-normalised) |",
             "|---|---|---|---|---|---|"]
    for n in names:
        found = sum(1 for r in failing if r["sources"][n]["n_fail"] > 0)
        kw = sum(1 for r in failing if r["sources"][n].get("keyword_ok"))
        ar = sum(1 for r in failing if r["sources"][n].get("args_ok"))
        ex = sum(1 for r in failing if r["sources"][n].get("error_exact"))
        nw = sum(1 for r in failing if r["sources"][n].get("error_norm"))
        N = len(failing)
        lines.append(f"| {n} | {found}/{N} | {kw}/{N} | {ar}/{N} | {ex}/{N} | {nw}/{N} |")
    detail = ["", "| id | plain+input conf | line ok | kw | args | err(norm) | k kw/args/err | results_json kw/args/err |",
              "|---|---|---|---|---|---|---|---|"]
    for r in failing:
        p = r["sources"]["plain+input"]
        k = r["sources"]["k"]
        j = r["sources"]["results_json"]
        f = lambda x: "Y" if x else "n"  # noqa: E731
        detail.append(f"| {r['id']} | {p.get('confidence')} | {f(p.get('line_ok'))} | {f(p.get('keyword_ok'))} | "
                      f"{f(p.get('args_ok'))} | {f(p.get('error_norm'))} | "
                      f"{f(k.get('keyword_ok'))}/{f(k.get('args_ok'))}/{f(k.get('error_norm'))} | "
                      f"{f(j.get('keyword_ok'))}/{f(j.get('args_ok'))}/{f(j.get('error_norm'))} |")
    (OUT / "parser_eval.md").write_text("\n".join(lines + detail) + "\n")
    print("\n".join(lines + detail))


if __name__ == "__main__":
    main()
