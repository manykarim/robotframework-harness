"""Whitespace-only / special-character arguments through execute_step -> build_test_suite(output_path)."""
import asyncio, sys
from pathlib import Path
from robotmcp import server

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
fn = lambda t: getattr(t, "fn", t)


async def main():
    sid = "wsrepro"
    await fn(server.manage_session)(action="init", session_id=sid, libraries=["String", "BuiltIn", "Collections"])
    steps = [
        ("Set Variable", ["61.000,00 €"], "price"),                     # value with a no-break space
        ("Replace String", ["${price}", " ", " "], "price_norm"),      # search NBSP, replace with plain space
        ("Should Be Equal", ["${price_norm}", "61.000,00 €"], None),
        ("Replace String", ["${price}", ",00", ""], "no_cents"),            # empty replacement argument
        ("Should Be Equal", ["${no_cents}", "61.000 €"], None),
        ("Catenate", ["SEPARATOR=", "a", " ", "b"], "joined"),              # single-space argument
        ("Should Be Equal", ["${joined}", "a b"], None),
        ("Should Be Equal", ["#notacomment", "#notacomment"], None),         # leading '#'
    ]
    for kw, args, assign in steps:
        kwargs = dict(keyword=kw, arguments=args, session_id=sid)
        if assign:
            kwargs["assign_to"] = assign
        res = await fn(server.execute_step)(**kwargs)
        print(f"{kw:16} {args!r:50} success={res.get('success')} {str(res.get('error') or '')[:90]}")
    p = OUT / "ws_suite.robot"
    built = await fn(server.build_test_suite)(test_name="Whitespace Args", session_id=sid, output_path=str(p))
    print("build", built.get("success"), p.exists())


loop = asyncio.new_event_loop()
try:
    loop.run_until_complete(main())
finally:
    loop.close()
