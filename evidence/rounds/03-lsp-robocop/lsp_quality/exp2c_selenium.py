"""Exp 2c (wt env): Browser + SeleniumLibrary ambiguity, Set Library Search Order, global search order config."""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from live_steps import SELENIUM_HEADER, SELENIUM_STEPS
PROJ = HERE / "proj"
def main():
    from warm_analyzer import WarmAnalyzer
    out = {}
    f = PROJ / "tests" / "_sel.robot"
    for name, wa in {"default": WarmAnalyzer(PROJ), "global_search_order_Browser": WarmAnalyzer(PROJ, search_order=["Browser"])}.items():
        for sid, probe, lines, expect in SELENIUM_STEPS:
            text = SELENIUM_HEADER + "\n".join(lines) + "\n"
            f.write_text(text)
            r = wa.check(f)
            ds = [f"L{d['line']} {d['code']}: {d['msg'][:90]}" for d in r["diags"]]
            out[f"{name}/{sid}"] = ds
            print(f"{name:<28} {sid} expect={expect:<17} {r['ms']:>7}ms {ds}")
        # common non-ambiguous Selenium-only and Browser-only kws
        f.write_text(SELENIUM_HEADER + "    Click    id=x\n    Click Element    id=x\n    Input Text    id=x    y\n    Fill Text    id=x    y\n")
        r = wa.check(f)
        print(name, "click/clickelement/inputtext/filltext:", [f"L{d['line']} {d['code']}" for d in r["diags"]])
    f.unlink()
    (HERE / "results" / "exp2c_selenium.json").write_text(json.dumps(out, indent=1))
if __name__ == "__main__":
    main()
