"""Generate the static-validation corpus (broken steps/suites + valid controls).

Each case is written to ../corpus/cases/<id>.robot and described in
../corpus/manifest.json (expected verdict + the error class we planted).

"step" cases mimic what a remote rf-mcp would do for a single execute_step:
wrap ONE step in a temp suite that carries the session's imports.
"suite" cases mimic a whole build_test_suite output.

env:
  rcexp -> ~/workspace/robotcode-experiments/.venv (Browser 20.5, Requests 0.9.7, no Selenium)
  wt    -> rf-mcp worktree venv (SeleniumLibrary + Browser + Requests)
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASES = HERE.parent / "corpus" / "cases"


def step(imports: list[str], body: str, pre: str = "") -> str:
    """Wrap a single step (plus optional earlier session steps) in a temp suite."""
    settings = "\n".join(imports)
    lines = [ln for ln in (pre + "\n" + body).splitlines() if ln.strip()]
    steps = "\n".join("    " + ln for ln in lines)
    return f"*** Settings ***\n{settings}\n\n*** Test Cases ***\nStep\n{steps}\n"


LIB_BUILTIN: list[str] = []
LIB_BROWSER = ["Library    Browser"]
LIB_REQ = ["Library    RequestsLibrary"]
LIB_SEL = ["Library    SeleniumLibrary"]
RES = ["Resource    common.resource"]

CASES_DEF: list[dict] = [
    # ---------------- broken single steps ----------------
    dict(id="b01_typo_keyword", kind="step", env="rcexp", expect="error", cls="keyword-typo",
         src=step(LIB_BUILTIN, "Shuold Be Equal    a    a")),
    dict(id="b02_too_few_args", kind="step", env="rcexp", expect="error", cls="arg-count",
         src=step(LIB_BUILTIN, "Should Be Equal    a")),
    dict(id="b03_too_many_args", kind="step", env="rcexp", expect="error", cls="arg-count",
         src=step(LIB_BUILTIN, "Log    a    INFO    False    False    False    NONE    x    y")),
    dict(id="b04_unknown_named_arg", kind="step", env="rcexp", expect="error", cls="named-arg",
         src=step(LIB_BUILTIN, "Should Be Equal    a    a    msg=hello    ignor_case=True")),
    dict(id="b05_undefined_variable", kind="step", env="rcexp", expect="error", cls="variable",
         src=step(LIB_BUILTIN, "Log    ${undefined_var}")),
    dict(id="b06_missing_library_import", kind="step", env="rcexp", expect="error", cls="import",
         src=step(LIB_BUILTIN, "Convert To Upper Case    abc")),
    dict(id="b07_browser_kw_with_selenium_only", kind="step", env="wt", expect="error", cls="wrong-library",
         src=step(LIB_SEL, "Fill Text    id=user    bob")),
    dict(id="b08_ambiguous_two_custom_libs", kind="step", env="rcexp", expect="error", cls="ambiguous",
         src=step(["Library    LibA", "Library    LibB"], "Do Thing    x")),
    dict(id="b09_ambiguous_browser_selenium", kind="step", env="wt", expect="error", cls="ambiguous",
         src=step(LIB_BROWSER + LIB_SEL, "Get Text    id=foo")),
    dict(id="b10_bad_embedded_call", kind="step", env="rcexp", expect="error", cls="embedded",
         src=step(RES, "The User Adds many Items To The Cart")),
    dict(id="b11_invalid_for", kind="step", env="rcexp", expect="error", cls="syntax-for",
         src=step(LIB_BUILTIN, "FOR    ${i}    IN RANG    3\n    Log    ${i}\nEND")),
    dict(id="b12_for_missing_end", kind="step", env="rcexp", expect="error", cls="syntax-for",
         src=step(LIB_BUILTIN, "FOR    ${i}    IN RANGE    3\n    Log    ${i}")),
    dict(id="b13_invalid_if", kind="step", env="rcexp", expect="error", cls="syntax-if",
         src=step(LIB_BUILTIN, "IF\n    Log    no condition\nELSE\n    Log    else\nELSE IF    True\n    Log    x\nEND")),
    dict(id="b14_wrong_setting_name", kind="suite", env="rcexp", expect="error", cls="setting",
         src="*** Settings ***\nTest Setupp    Log    setup\n\n*** Test Cases ***\nT\n    [Tag]    smoke\n    Log    x\n"),
    dict(id="b15_resource_path_wrong", kind="suite", env="rcexp", expect="error", cls="import",
         src="*** Settings ***\nResource    resources/nonexist.resource\n\n*** Test Cases ***\nT\n    Log    x\n"),
    dict(id="b16_browser_missing_arg", kind="step", env="rcexp", expect="error", cls="arg-count",
         src=step(LIB_BROWSER, "Fill Text    id=user")),
    dict(id="b17_browser_positional_after_named", kind="step", env="rcexp", expect="error", cls="named-arg",
         src=step(LIB_BROWSER, "New Page    url=https://example.org    wait_untl=load")),
    dict(id="b18_requests_missing_url", kind="step", env="rcexp", expect="error", cls="arg-count",
         src=step(LIB_REQ, "Create Session    api")),
    dict(id="b19_requests_on_session_missing_url", kind="step", env="rcexp", expect="error", cls="arg-count(kwargs-sig)",
         src=step(LIB_REQ, "POST On Session    api")),
    dict(id="b20_single_space_separator", kind="step", env="rcexp", expect="error", cls="keyword-typo",
         src=step(LIB_BUILTIN, "Log hello world")),
    dict(id="b21_library_not_installed", kind="step", env="rcexp", expect="error", cls="import",
         src=step(["Library    NonExistentLib"], "Log    x")),
    dict(id="b22_library_init_args", kind="step", env="rcexp", expect="error", cls="import-args",
         src=step(["Library    Collections    extra_arg"], "Log    x")),
    dict(id="b23_wrong_library_prefix", kind="step", env="rcexp", expect="error", cls="keyword-typo",
         src=step(["Library    String"], "Strng.Convert To Upper Case    abc")),
    dict(id="b24_unclosed_variable", kind="step", env="rcexp", expect="error", cls="variable-syntax",
         src=step(LIB_BUILTIN, "Log    ${unclosed")),
    dict(id="b25_return_in_test", kind="step", env="rcexp", expect="error", cls="syntax",
         src=step(LIB_BUILTIN, "RETURN    1")),
    dict(id="b26_unknown_section", kind="suite", env="rcexp", expect="error", cls="syntax",
         src="*** Varibles ***\n${X}    1\n\n*** Test Cases ***\nT\n    Log    x\n"),
    dict(id="b27_assertion_operator_typo", kind="step", env="rcexp", expect="error", cls="type-conversion",
         src=step(LIB_BROWSER, "Get Text    id=foo    ===    bar")),
    dict(id="b28_int_conversion", kind="step", env="rcexp", expect="error", cls="type-conversion",
         src=step(["Library    LibA"], "Only In A    abc")),
    dict(id="b29_user_kw_too_many_args", kind="step", env="rcexp", expect="error", cls="arg-count",
         src=step(RES, "Login As    bob    pw    extra")),
    dict(id="b30_selenium_kw_in_browser_session", kind="step", env="rcexp", expect="error", cls="wrong-library",
         src=step(LIB_BROWSER, "Input Text    id=user    bob")),
    dict(id="b31_empty_test", kind="suite", env="rcexp", expect="error", cls="syntax",
         src="*** Test Cases ***\nEmpty Test\n\nOther\n    Log    x\n"),
    dict(id="b32_duplicate_test", kind="suite", env="rcexp", expect="warn", cls="duplicate",
         src="*** Test Cases ***\nSame\n    Log    x\nSame\n    Log    y\n"),
    dict(id="b33_keyword_only_missing", kind="step", env="rcexp", expect="error", cls="named-arg",
         src=step(["Library    Process"], "Start Process")),
    # ---------------- valid controls ----------------
    dict(id="v01_builtin_ok", kind="step", env="rcexp", expect="ok", cls="control",
         src=step(LIB_BUILTIN, "Should Be Equal    a    a    msg=hello    ignore_case=True")),
    dict(id="v02_bdd_user_keyword", kind="step", env="rcexp", expect="ok", cls="control-bdd",
         src=step(RES, "Given The User Is Logged In\nWhen The User Adds 3 Items To The Cart\nThen The Cart Should Contain \"Backpack\"\nAnd Login As    bob")),
    dict(id="v03_bdd_on_library_kw", kind="step", env="rcexp", expect="ok", cls="control-bdd",
         src=step(LIB_BROWSER, "When Click    id=login")),
    dict(id="v04_assign_then_use", kind="step", env="rcexp", expect="ok", cls="control-variable",
         pre="${x}=    Set Variable    1", src=None),
    dict(id="v05_dynamic_set_test_variable", kind="step", env="rcexp", expect="ok", cls="control-variable(dynamic)",
         src=step(LIB_BUILTIN, "Set Test Variable    \\${dyn}    1\nLog    ${dyn}")),
    dict(id="v06_cli_variable", kind="step", env="rcexp", expect="ok", cls="control-variable(cli -v)",
         src=step(LIB_BUILTIN, "Log    ${FROM_CLI}")),
    dict(id="v07_search_order_resolves_ambiguity", kind="step", env="rcexp", expect="ok", cls="control-ambiguous",
         src=step(["Library    LibA", "Library    LibB"], "Set Library Search Order    LibA\nDo Thing    x")),
    dict(id="v08_qualified_name", kind="step", env="rcexp", expect="ok", cls="control-ambiguous",
         src=step(["Library    LibA", "Library    LibB"], "LibB.Do Thing    x")),
    dict(id="v09_browser_ok", kind="step", env="rcexp", expect="ok", cls="control-browser",
         src=step(LIB_BROWSER, "New Page    https://example.org    wait_until=load\nFill Text    id=user    bob\nGet Text    id=foo    ==    bar")),
    dict(id="v10_requests_ok", kind="step", env="rcexp", expect="ok", cls="control-requests",
         src=step(LIB_REQ, "Create Session    api    https://restful-booker.herokuapp.com\n${resp}=    POST On Session    api    /auth    json=${{{'username': 'admin'}}}    expected_status=200")),
    dict(id="v11_selenium_ok", kind="step", env="wt", expect="ok", cls="control-selenium",
         src=step(LIB_SEL, "Open Browser    https://example.org    headlesschrome\nInput Text    id=user    bob")),
    dict(id="v12_robot_toml_variable", kind="step", env="rcexp", expect="ok", cls="control-variable(robot.toml)",
         src=step(LIB_BUILTIN, "Log    ${BASE_URL}")),
    dict(id="v13_suite_variable_env_var", kind="step", env="rcexp", expect="ok", cls="control-variable(env)",
         src=step(LIB_BUILTIN, "Log    %{HOME}")),
    dict(id="v14_var_syntax_rf7", kind="step", env="rcexp", expect="ok", cls="control-syntax",
         src=step(LIB_BUILTIN, "VAR    ${v}    hello    scope=TEST\nIF    $v == 'hello'\n    Log    ${v}\nEND\nFOR    ${i}    IN RANGE    2\n    Log    ${i}\nEND\nTRY\n    Fail    x\nEXCEPT    x\n    Log    caught\nEND")),
    dict(id="v15_timeout_named_kw_only", kind="step", env="rcexp", expect="ok", cls="control-named",
         src=step(["Library    Process"], "Start Process    echo    hi    shell=True    alias=p")),
]


def main() -> None:
    CASES.mkdir(parents=True, exist_ok=True)
    for old in CASES.glob("*.robot"):
        old.unlink()
    manifest = []
    for c in CASES_DEF:
        if c["id"] == "v04_assign_then_use":
            c["src"] = step(LIB_BUILTIN, "Log    ${x}", pre=c["pre"])
        path = CASES / f"{c['id']}.robot"
        path.write_text(c["src"], encoding="utf-8")
        manifest.append({k: v for k, v in c.items() if k not in ("src", "pre")} | {"file": f"cases/{path.name}"})
    (CASES.parent / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"wrote {len(manifest)} cases: "
          f"{sum(1 for c in manifest if c['expect'] != 'ok')} broken, "
          f"{sum(1 for c in manifest if c['expect'] == 'ok')} valid")


if __name__ == "__main__":
    main()
