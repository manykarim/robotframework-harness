*** Settings ***
Library    OperatingSystem

*** Keywords ***
Measure Page
    [Arguments]    ${label}
    ${rf}=    Get File    ${CURDIR}${/}rfmcp_actionable_elements.js
    ${rf}=    Evaluate    $rf.split('*/', 1)[1].strip()
    ${el}=    Evaluate JavaScript    css=html    ${rf}
    ${el80}=    Evaluate    $el[:80]
    ${el80c}=    Evaluate    [{k: v for k, v in e.items() if v is not None and v != ''} for e in $el80]
    ${j_rf}=    Evaluate    json.dumps({'elements': $el80c, 'count': len($el80c), 'collection_method': 'browser_js'})    modules=json
    Guard Load JS
    ${p8}=    Evaluate JavaScript    ${NONE}    ${_GUARD_JS_P}    arg=${{ {'q': [], 'k': 8} }}
    ${p80}=    Evaluate JavaScript    ${NONE}    ${_GUARD_JS_P}    arg=${{ {'q': [], 'k': 80} }}
    ${j_p8}=    Evaluate    json.dumps($p8)    modules=json
    ${j_p80}=    Evaluate    json.dumps($p80)    modules=json
    ${a}=    Get Aria Snapshot    css=body
    ${ai}=    Get Aria Snapshot    css=body    mode=ai
    ${src}=    Get Page Source
    Create File    ${OUTPUT DIR}${/}${label}.page.html    ${src}
    Create File    ${OUTPUT DIR}${/}${label}.rfmcp_actionable.json    ${j_rf}
    Create File    ${OUTPUT DIR}${/}${label}.guard_page80.json    ${j_p80}
    Create File    ${OUTPUT DIR}${/}${label}.aria.yaml    ${a}
    Create File    ${OUTPUT DIR}${/}${label}.aria_ai.yaml    ${ai}
    ${n_all}=    Get Length    ${el}
    Log To Console    SIZE|${label}|rfmcp_actionable_n=${n_all}|rfmcp_actionable_json80=${{len($j_rf)}}|guard_cand8=${{len($j_p8)}}|guard_cand80=${{len($j_p80)}}|guard_total=${p80}[total]|aria=${{len($a)}}|aria_ai=${{len($ai)}}|page_source=${{len($src)}}
