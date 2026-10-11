"""Build the coverage table (results/coverage.md) from results/hints_comparison.json.

  python build_table.py
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
rows = json.loads((HERE / "results" / "hints_comparison.json").read_text())


def short(hs):
    if hs is None:
        return "-"
    if not hs:
        return "(none)"
    abbrev = {
        "Element not found — inspect the page": "ElementNotFound",
        "Selector matches multiple elements": "StrictMode",
        "Click intercepted by overlapping element": "ClickIntercepted",
        "Element is outside the visible viewport": "OutsideViewport",
        "Element not interactable": "NotInteractable",
        "Invalid selector syntax": "InvalidSelector",
        "Evaluate JavaScript: argument-shape mismatch": "EvalJS-shape",
        "Keyword Not Found: Use find_keywords to discover": "KwNotFound",
        "Keyword Correction: BuiltIn.Create List": "KwCorrection",
        "Keyword Ambiguity: Specify full library.keyword name": "KwAmbiguity",
        "Operation timed out": "Timeout",
        "RequestsLibrary: Handle HTTPError responses": "Req:HTTPError(plugin)",
        "RequestsLibrary: Alias first, then relative path": "Req:AliasFirst",
        "RequestsLibrary: Provide a full URL or use sessions": "Req:FullURL(plugin)",
        "RequestsLibrary: Use Create Session + Get On Session": "Req:CreateSession",
        "RequestsLibrary: Headers must be a DICTIONARY, not a string": "Req:HeadersDict",
        "RequestsLibrary: Pass named args as 'name=value'": "Req:NamedArgs",
        "RequestsLibrary: POST/PUT payload guidance": "Req:Payload",
        "Dictionary Access: Use bracket notation, not dot notation": "DictBracket",
        "Method Call Syntax: Call methods with parentheses": "MethodParens",
        "Evaluate: Use Python booleans or json.loads": "Eval-bool",
        "Evaluate: Use $var inside expressions": "Eval-$var",
        "Process argument may be parsed as a named argument": "ProcessEqArg",
        "pre_validation_failure": "PV:failure",
        "visibility_hint": "PV:visible",
        "enabled_hint": "PV:enabled",
        "pre_validate_timeout_hint": "PV:timeout",
    }
    out = []
    for h in hs:
        if h.startswith("Browser library does not support"):
            out.append("RolePrefix")
        else:
            out.append(abbrev.get(h, h[:30]))
    return ", ".join(out)


def klass(r):
    nat = r["native"] or {}
    k = (r["remote"].get("k") or {}).get("hints")
    e0 = (r["remote"].get("error only") or {}).get("hints")
    if nat.get("success"):
        return "env", "native rf-mcp did not fail (managed search order / auto-import / lib installed)"
    if nat.get("pre_validation"):
        return "c", "native diagnosis came from the live pre-validation gate (element states)"
    if k is None:
        return "?", "no failure parsed"
    if k == nat.get("hints"):
        if not k:
            return "gap", "no hint in native rf-mcp either"
        if e0 == k:
            return "a0", "identical, even from error text alone"
        return "a", "identical with parsed keyword/args/libraries"
    return "diff", "differs"


lines = ["| id | mistake | robotcode error (first line) | native rf-mcp hints | robotcode -k -> generate_hints | plain+input | error only | class |",
         "|---|---|---|---|---|---|---|---|"]
counts = {}
for r in rows:
    c, why = klass(r)
    counts[c] = counts.get(c, 0) + 1
    k = r["remote"].get("k") or {}
    err = (k.get("error_head") or "").replace("|", "\\|")
    lines.append(
        f"| {r['id']} | {r['title']} | `{err[:90]}` | {short((r['native'] or {}).get('hints'))} | "
        f"{short(k.get('hints'))} | {short((r['remote'].get('plain+input') or {}).get('hints'))} | "
        f"{short((r['remote'].get('error only') or {}).get('hints'))} | {c} |")
legend = ["", "Class legend: a0 = identical hints from the error text alone; a = identical once keyword/args/libraries are parsed; "
          "c = native used live pre-validation state; env = native rf-mcp's managed environment prevented the failure; "
          "gap = neither produces a hint; diff = differs.", "", "Counts: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))]
(HERE / "results" / "coverage.md").write_text("\n".join(lines + legend) + "\n")
print("\n".join(lines + legend))
