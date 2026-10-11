"""Exp 2b: suppression mechanisms for the static false positives (in-process analyzer = same engine as LSP)."""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
PROJ = HERE / "proj"
H = "*** Settings ***\nLibrary    Browser\nLibrary    RequestsLibrary\nResource    shop.resource\n\n*** Test Cases ***\nLive\n"
CASES = {
 "inline_ignore": "    Set Test Variable    \\${pw}    x\n    Log    ${pw}    # robotcode: ignore[VariableNotFound]\n",
 "own_line_ignore_block": "    # robotcode: ignore[VariableNotFound]\n    Set Suite Variable    ${A}    1\n    Log    ${A}\n    Log    ${usrname}\n",
 "own_line_ignore_then_reset": "    # robotcode: ignore[VariableNotFound]\n    Set Suite Variable    ${A}    1\n    Log    ${A}\n    # robotcode: reset[VariableNotFound]\n    Log    ${usrname}\n",
 "VAR_scope_test": "    VAR    ${u}    standard_user    scope=TEST\n    Log    ${u}\n",
 "VAR_in_resource_kw": "    Create Token With VAR\n    Log    ${TOKEN2}\n",
 "set_test_var_unescaped_dict_list": "    Set Test Variable    @{L}    a    b\n    Log    ${L}[0]\n",
 "cli_var_no_config": "    Log    ${CLI_VAR}\n",
 "get_variable_value": "    ${x}=    Get Variable Value    ${maybe}    default\n",
 "variable_should_exist": "    Variable Should Exist    ${maybe}\n",
 "run_keyword_if_var": "    IF    $maybe_undefined    Log    x\n",
}
def main():
    from warm_analyzer import WarmAnalyzer
    res = {}
    variants = {
        "default": WarmAnalyzer(PROJ),
        "helper_vars": WarmAnalyzer(PROJ, variables={"CLI_VAR": "x"}),
        "toml_ignore_VariableNotFound": WarmAnalyzer(PROJ, extra_ignore=["VariableNotFound"]),
    }
    f = PROJ / "tests" / "_supp.robot"
    for name, wa in variants.items():
        for cid, body in CASES.items():
            f.write_text(H + body)
            r = wa.check(f)
            ds = [f"L{d['line']} {d['code']}: {d['msg'][:70]}" for d in r["diags"]]
            res[f"{name}/{cid}"] = ds
            print(f"{name:<30} {cid:<32} {ds}")
        # planted check under this variant
        f.write_text(H + "    Log    ${usrname}\n")
        r = wa.check(f)
        print(f"{name:<30} {'PLANTED undefined var':<32} {[d['code'] for d in r['diags']]}")
        res[f"{name}/planted"] = [d["code"] for d in r["diags"]]
    f.unlink()
    (HERE / "results" / "exp2b_suppress.json").write_text(json.dumps(res, indent=1))
if __name__ == "__main__":
    main()
