"""Reproduce the file-proc scenario against current rf-mcp (in-process) and save the suite two ways:
(a) build_test_suite(output_path=...)  (b) the old agent path: execute_step("Create File", [path, rf_text])."""
import asyncio, json, os, sys
from pathlib import Path

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)

from robotmcp import server  # noqa: E402


def fn(tool):
    return getattr(tool, "fn", tool)


async def main():
    sid = "f1repro"
    work = OUT / "work"
    work.mkdir(exist_ok=True)
    report = str(work / "report.txt")
    r = await fn(server.manage_session)(action="init", session_id=sid, libraries=["OperatingSystem", "BuiltIn"])
    print("init", r.get("success"))
    steps = [
        ("Create Directory", [str(work)], None),
        ("Create File", [report, "line1\nline2\nline3"], None),           # agent passed a JSON "\n" -> real newlines
        ("Append To File", [report, "\nline4"], None),
        ("Get File", [report], "file_content"),
        ("Should Contain", ["${file_content}", "line1"], None),
        ("Should Contain", ["${file_content}", "line4"], None),
        ("File Should Exist", [report], None),
    ]
    for kw, args, assign in steps:
        kwargs = dict(keyword=kw, arguments=args, session_id=sid)
        if assign:
            kwargs["assign_to"] = assign
        res = await fn(server.execute_step)(**kwargs)
        print(f"{kw:18} success={res.get('success')} {str(res.get('error') or '')[:120]}")

    a_path = OUT / "suite_output_path.robot"
    built = await fn(server.build_test_suite)(test_name="File Processing Test", session_id=sid, output_path=str(a_path))
    rf_text = built.get("rf_text") or ""
    (OUT / "rf_text_returned.robot").write_text(rf_text, encoding="utf-8")
    print("build success", built.get("success"), "written:", a_path.exists())

    b_path = OUT / "suite_via_create_file.robot"
    res = await fn(server.execute_step)(keyword="Create File", arguments=[str(b_path), rf_text], session_id=sid, record=False)
    print("save via Create File success", res.get("success"))


loop = asyncio.new_event_loop()
try:
    loop.run_until_complete(main())
finally:
    loop.close()
