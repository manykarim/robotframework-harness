"""Contract tests for rf_harness.runtime.robotcode_adapter against the installed robotcode (pinned >=2.7,<2.8).

These pin exactly what the runtime uses from robotcode internals: embedding a REPL interpreter (BaseInterpreter +
run_repl), `robotcode libdoc` and the analyzer behind the static gate. REPL and analyzer run in a subprocess: run_repl
starts a whole Robot Framework execution (process-global state) and the analyzer spawns worker processes.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from rf_harness.runtime import robotcode_adapter as rc


def _run_isolated(code: str, cwd: Path, timeout: float = 180) -> dict:
    """run `code` in a fresh interpreter (own process group, killed afterwards); its last stdout line is JSON."""
    kw: dict = {"start_new_session": True} if os.name == "posix" else {}
    p = subprocess.Popen([sys.executable, "-c", textwrap.dedent(code)], cwd=str(cwd), stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, env={**os.environ, "PYTHONUNBUFFERED": "1"}, **kw)
    try:
        out, err = p.communicate(timeout=timeout)
    finally:
        if os.name == "posix":
            try:
                os.killpg(p.pid, signal.SIGKILL)  # analyzer / libdoc workers
            except OSError:
                pass
        if p.poll() is None:
            p.kill()
    lines = [x for x in out.splitlines() if x.startswith("{")]
    assert p.returncode == 0 and lines, f"rc={p.returncode}\nstdout:\n{out[-2000:]}\nstderr:\n{err[-3000:]}"
    return json.loads(lines[-1])


def test_installed_robotcode_is_in_the_supported_range():
    ver = rc.robotcode_version()
    assert ver, "robotcode is not installed"
    assert rc.is_supported(), f"robotcode {ver} is outside {rc.SUPPORTED_RANGE}"


@pytest.mark.parametrize(("ver", "ok"), [("2.7.0", True), ("2.7.13", True), ("2.8.0", False), ("2.6.9", False),
                                         ("3.0", False), ("", False), ("garbage", False)])
def test_is_supported_parses_versions(ver, ok):
    assert rc.is_supported(ver) is ok


def test_every_adapter_name_resolves_to_the_robotcode_object():
    for name in rc._NAMES:
        assert getattr(rc, name) is not None, name
    interp = rc.BaseInterpreter
    for method in ("get_test_body_from_string", "run_keyword", "get_input", "run_input", "log_message", "message",
                   "start_keyword", "end_keyword"):
        assert callable(getattr(interp, method, None)), f"BaseInterpreter.{method} is gone"
    assert callable(rc.run_repl)
    assert {"CHANGED"} <= {m for m in dir(rc.FileChangeType)}


def test_unknown_names_raise_attribute_error():
    with pytest.raises(AttributeError):
        rc.NoSuchThing  # noqa: B018


def test_only_the_adapter_imports_robotcode():
    runtime = Path(rc.__file__).parent
    offenders = []
    for f in sorted(runtime.glob("*.py")):
        if f.name == "robotcode_adapter.py":
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            s = line.strip()
            if s.startswith(("import robotcode", "from robotcode")):
                offenders.append(f"{f.name}:{i}: {s}")
    assert not offenders, offenders


def test_repl_interpreter_embeds_and_runs_builtin_keywords(tmp_path):
    res = _run_isolated("""
        import json, sys
        from pathlib import Path
        from rf_harness.runtime import robotcode_adapter as rc

        class One(rc.BaseInterpreter):
            def __init__(self):
                super().__init__()
                self.todo = ["${x}=    Set Variable    42", "Should Be Equal    ${x}    42",
                             "Should Be Equal    ${x}    43"]
                self.results = []

            def get_input(self):
                return iter(())

            def run_input(self):
                if not self.todo:
                    raise EOFError
                test, errors = self.get_test_body_from_string(self.todo.pop(0))
                kw = test.body[0]
                try:
                    ret = self.run_keyword(kw)
                    self.results.append({"kw": kw.name, "status": "PASS", "ret": ret, "errors": errors})
                except Exception as e:  # ExecutionFailed for the failing assertion
                    self.results.append({"kw": kw.name, "status": "FAIL", "msg": str(e), "errors": errors})

            def log_message(self, message, level, html=False, timestamp=None):
                pass

            def message(self, message, level, html=False, timestamp=None):
                pass

        it = One()
        out = Path.cwd() / "out"
        rc.run_repl(it, rc.new_application(Path.cwd()), variable=(), variablefile=(), pythonpath=(),
                    outputdir=str(out), output=None, log=None, report=None, source=Path.cwd() / "__rfh__.robot")
        sys.__stdout__.write(json.dumps({"results": it.results}, default=str) + "\\n")
        """, tmp_path)["results"]
    assert [r["status"] for r in res] == ["PASS", "PASS", "FAIL"], res
    assert res[0]["kw"] == "Set Variable" and res[0]["ret"] == "42"
    assert "42 != 43" in res[2]["msg"]
    assert all(not r["errors"] for r in res)


def test_libdoc_spec_and_show_for_builtin(tmp_path):
    spec = tmp_path / "BuiltIn.json"
    r = rc.libdoc(["--specdocformat", "raw", "BuiltIn", str(spec)], timeout=120)
    assert r.returncode == 0, r.stderr[-1000:]
    data = json.loads(spec.read_text(encoding="utf-8"))
    kws = {k["name"]: k for k in data["keywords"]}
    assert data["name"] == "BuiltIn"
    assert {"Should Be Equal", "Log", "Set Variable"} <= set(kws)
    assert [a["name"] for a in kws["Should Be Equal"]["args"]][:2] == ["first", "second"]
    show = rc.libdoc(["BuiltIn", "show", "Log"], timeout=120)
    assert show.returncode == 0, show.stderr[-1000:]
    assert "Log" in show.stdout and "message" in show.stdout


def test_robotcode_command_prefers_the_cli_next_to_the_interpreter():
    cmd = rc.robotcode_command()
    assert cmd[-1].endswith(("robotcode", "robotcode.exe")) or cmd[-2:] == ["-m", "robotcode"]


def test_analyzer_reports_an_unknown_keyword_with_its_location(tmp_path):
    suite = tmp_path / "tiny.robot"
    suite.write_text("*** Test Cases ***\nT\n    Log    known\n    Clik Somewhere    id=x\n", encoding="utf-8")
    res = _run_isolated(f"""
        import json, sys
        from pathlib import Path
        from rf_harness.runtime import robotcode_adapter as rc
        from rf_harness.runtime.analyzer import WarmAnalyzer

        wa = WarmAnalyzer(Path.cwd())
        first = wa.check(Path({str(suite)!r}), min_severity=1)
        fixed = wa.check(Path({str(suite)!r}), text=Path({str(suite)!r}).read_text().replace("Clik Somewhere", "Log"),
                         min_severity=1)
        uri = rc.document_uri(Path({str(suite)!r}))
        ev = rc.changed_file_events([{str(suite)!r}])
        sys.__stdout__.write(json.dumps({{"first": first, "fixed": fixed, "uri": str(uri),
                                          "event": [str(ev[0].uri), int(ev[0].type)]}}) + "\\n")
        """, tmp_path)
    diags = res["first"]["diags"]
    assert [(d["line"], d["code"]) for d in diags] == [(4, "KeywordNotFound")], diags
    assert "Clik Somewhere" in diags[0]["msg"] and diags[0]["col"] == 5
    assert res["fixed"]["diags"] == [] and res["fixed"]["ok"]
    assert res["uri"].startswith("file:") and res["uri"].endswith("tiny.robot")
    assert res["event"][0].endswith("tiny.robot") and res["event"][1] == int(rc.FileChangeType.CHANGED)
