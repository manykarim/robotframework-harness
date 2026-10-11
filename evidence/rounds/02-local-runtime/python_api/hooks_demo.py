"""Q5 demo: rf-mcp hints + Browser guard inside the helper; guard overhead (server-side ms)."""
import json, os, statistics, subprocess, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
PY = sys.argv[1]
wd = HERE / "work" / "hooks"; wd.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, PYTHONPATH=str(HERE))
def c(*a, d=".rf"):
    p = subprocess.run([PY, "-m", "rfmcp_local", "--dir", d, *a], cwd=wd, env=env, capture_output=True, text=True, timeout=120)
    return json.loads(p.stdout.strip().splitlines()[-1])
LOGIN = ["Import Library  Browser  timeout=3s", "New Browser  chromium  headless=True", "New Page  https://www.saucedemo.com",
         'Fill Text  [data-test="username"]  standard_user', 'Fill Text  [data-test="password"]  secret_sauce', 'Click  [data-test="login-button"]']
out = {}
for d, hooks in ((".rf_plain", "redact,hints"), (".rf_guard", "redact,hints,guard")):
    out[d] = {"start": c("start", "--hooks", hooks, "--fast-timeout", "1s", d=d)}
    for cell in LOGIN:
        r = c("step", cell, d=d); assert r["ok"], r
    cases = {"strict": "Click  text=Add to cart", "selenium_locator": "Fill Text  id:user-name  x",
             "missing": 'Click  [data-test="checkout-btn"]', "js_misuse": "Evaluate JavaScript  ${None}  document.title"}
    for name, cell in cases.items():
        t = time.perf_counter(); r = c("step", cell, d=d); r["wall_ms"] = round((time.perf_counter() - t) * 1000)
        out[d][name] = r
    ms = {}
    for name, cell in (("click_ok", 'Click  [data-test="shopping-cart-link"]'), ("get_text", 'Get Text  [data-test="title"]'),
                       ("fill", 'Fill Text  [data-test="firstName"]  Robo')):
        if name == "fill":
            c("step", 'Click  [data-test="checkout"]', d=d)
        xs = []
        for _ in range(10):
            r = c("step", cell, d=d); xs.append(r["steps"][-1]["ms"])
        ms[name] = round(statistics.median(xs), 1)
    out[d]["median_step_ms"] = ms
    out[d]["stop"] = c("stop", d=d)
(HERE / "results" / "hooks_demo.json").write_text(json.dumps(out, indent=1))
for d in out:
    print("==", d, out[d]["median_step_ms"])
    for k in ("strict", "selenium_locator", "missing", "js_misuse"):
        s = out[d][k]["steps"][-1]
        print(f"  {k}: wall={out[d][k]['wall_ms']}ms status={s['status']} refused={json.dumps(s.get('refused'))[:160]} msg={str(s.get('msg'))[:110]!r}")
        for h in s.get("hints", []): print("     hint:", h["title"], "|", (h["message"] or "")[:120])
