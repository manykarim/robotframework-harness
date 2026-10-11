"""E4: unreleased `robotcode doc` (robotcode main c1cf903, 2026-10-01) — latency, sizes, JSON shape."""
import json, subprocess, time, os
from pathlib import Path
K = Path("~/workspace/rf-mcp-robotcode/experiments/robotcode-remote/round2/keyword_docs")
RC = "/tmp/claude-1000/-home-~-workspace-rf-mcp/1fce9b83-a4c5-4548-8f0f-3be83ba63c56/scratchpad/rcmain-venv/bin/robotcode"
OUT = K / "outputs/e4"; OUT.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, NO_COLOR="1", LC_ALL="C.UTF-8")
CASES = [
    ("help_root", ["--help"]),
    ("kw1_text", ["doc", "keyword", "Browser", "Click"]),
    ("kw1_json", ["--format", "json", "doc", "keyword", "Browser", "Click"]),
    ("kw5_text", ["doc", "keyword", "Browser", "Click", "Fill Text", "Get Text", "Wait For Elements State", "New Page"]),
    ("kw5_json", ["--format", "json", "doc", "keyword", "Browser", "Click", "Fill Text", "Get Text", "Wait For Elements State", "New Page"]),
    ("kw_glob_json", ["--format", "json", "doc", "keyword", "BuiltIn", "Should Be*"]),
    ("kw_missing_suggest", ["doc", "keyword", "Browser", "Click Element"]),
    ("kw_requests_post", ["doc", "keyword", "RequestsLibrary", "POST On Session"]),
    ("kws_browser_all_text", ["doc", "keywords", "Browser"]),
    ("kws_browser_all_json", ["--format", "json", "doc", "keywords", "Browser"]),
    ("kws_browser_wait_text", ["doc", "keywords", "Browser", "wait"]),
    ("kws_requests_json_pat", ["doc", "keywords", "RequestsLibrary", "json"]),
    ("kws_requests_post_text", ["doc", "keywords", "RequestsLibrary", "post"]),
    ("kws_tag_filter", ["doc", "keywords", "Browser", "--tag", "Setter"]),
    ("kws_selenium_all_text", ["doc", "keywords", "SeleniumLibrary"]),
    ("kws_builtin_all_text", ["doc", "keywords", "BuiltIn"]),
    ("lib_browser_text", ["doc", "lib", "Browser"]),
    ("lib_browser_json", ["--format", "json", "doc", "lib", "Browser"]),
    ("lib_requests_text", ["doc", "lib", "RequestsLibrary"]),
    ("lib_resource", ["doc", "lib", "resources/shop.resource"]),
    ("lib_pylib_noargs", ["doc", "lib", "libs/ShopApi.py"]),
    ("lib_pylib_args", ["doc", "lib", "libs/ShopApi.py::http://x"]),
    ("kws_suite_file", ["doc", "keywords", "tests/shop.robot"]),
    ("browse_piped", ["doc", "browse", "resources/shop.resource"]),
    ("kw_text_search_attempt", ["doc", "keywords", "Browser", "visible"]),
]
rows = []
for name, args in CASES:
    s = time.perf_counter()
    p = subprocess.run([RC, *args], capture_output=True, text=True, cwd=K / "project", env=env)
    w = time.perf_counter() - s
    (OUT / f"{name}.out").write_text(p.stdout + ("\n--- STDERR ---\n" + p.stderr if p.stderr else ""))
    rows.append({"case": name, "wall_s": round(w, 2), "rc": p.returncode, "stdout_chars": len(p.stdout), "tok": len(p.stdout) // 4, "stderr": p.stderr[:160]})
    print(f'{name:26} {w:5.2f}s rc={p.returncode} {len(p.stdout):8d} ch {len(p.stdout)//4:7d} tok  {p.stderr.strip()[:110]}')
(OUT / "e4.json").write_text(json.dumps(rows, indent=1))
