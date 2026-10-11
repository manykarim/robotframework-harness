"""Exp 4b: warm in-process check latency vs live-file size (one appended line per check)."""
import json, statistics, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from live_steps import HEADER
def main():
    from warm_analyzer import WarmAnalyzer
    wa = WarmAnalyzer(HERE / "proj")
    f = HERE / "proj" / ".rf" / "scale.robot"
    out = {}
    for n in (20, 100, 300, 1000):
        body = "".join(f"    ${{t{i}}}=    Get Title\n    Log    ${{t{i}}}\n" if i % 2 else f"    Click    id=b{i}\n" for i in range(n))
        text = HEADER + body
        f.write_text(text)
        wa.check(f, text=text)
        ms = []
        for k in range(10):
            text += f"    Log    extra {k}\n"
            r = wa.check(f, text=text)
            ms.append(r["ms"])
        t = time.perf_counter(); 
        from robot.api import get_model
        f.write_text(text); get_model(str(f)); parse_ms = (time.perf_counter() - t) * 1000
        out[n] = {"lines": text.count("\n"), "check_median_ms": statistics.median(ms), "check_max_ms": max(ms), "rf_parse_ms": round(parse_ms, 1)}
        print(n, out[n], flush=True)
    f.unlink()
    (HERE / "results" / "exp4b_scaling.json").write_text(json.dumps(out, indent=1))
if __name__ == "__main__":
    main()
