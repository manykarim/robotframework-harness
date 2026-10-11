*** Settings ***
Documentation     Guarded SeleniumLibrary steps (research prototype, precheck mode).
...               Emits ONE line per step:   GUARD {json}
...               Key difference to Browser: SeleniumLibrary is NOT strict - with several matches it
...               silently acts on the FIRST one; bare CSS needs the css: prefix; default strategy = id/name.
Library           Collections
Library           OperatingSystem

*** Variables ***
${GUARD_PRE}          0.5s
${GUARD_K}            8
${GUARD_SHOT}         png
${_GUARD_JS_M}        ${EMPTY}
${_GUARD_JS_P}        ${EMPTY}

*** Keywords ***
Guarded
    [Arguments]    ${action}    ${locator}    @{args}    ${pre}=${GUARD_PRE}
    ${t0}=    Evaluate    time.perf_counter()    modules=time
    ${rof}=    Register Keyword To Run On Failure    Nothing
    ${r}=    Guard Core    ${action}    ${locator}    ${args}    ${pre}
    IF    not $r['ok']    Guard Diagnose    ${r}    ${locator}
    ${r}[ms]=    Evaluate    round((time.perf_counter() - $t0) * 1000)    modules=time
    ${json}=    Evaluate    json.dumps($r, ensure_ascii=False, default=str)    modules=json
    Register Keyword To Run On Failure    ${rof}
    Log To Console    GUARD ${json}
    RETURN    ${r}

Guard Core
    [Arguments]    ${action}    ${locator}    ${args}    ${pre}
    ${k}=    Evaluate    $action.lower()
    ${kind}=    Evaluate    'fill' if ('input' in $k or 'text' in $k and 'get' not in $k) else 'read' if $k.startswith(('get ', 'element should', 'wait ')) else 'click'
    &{r}=    Create Dictionary    v=${1}    ok=${FALSE}    kw=${action}    sel=${locator}    phase=pre    lib=SeleniumLibrary
    TRY
        ${n}=    Get Element Count    ${locator}
    EXCEPT    AS    ${e}
        Set To Dictionary    ${r}    cls=INVALID_SELECTOR    err=${{ str($e).splitlines()[0][:220] }}
        RETURN    ${r}
    END
    IF    ${n} == 0
        TRY
            Wait Until Page Contains Element    ${locator}    timeout=${pre}
        EXCEPT
            No Operation
        END
        ${n}=    Get Element Count    ${locator}
    END
    Set To Dictionary    ${r}    count=${n}
    IF    ${n} == 0
        Set To Dictionary    ${r}    cls=NOT_FOUND
        RETURN    ${r}
    END
    IF    ${n} > 1    Set To Dictionary    ${r}    warn=MULTI_MATCH_FIRST_USED
    ${el}=    Get WebElement    ${locator}
    ${st}=    Execute Javascript    return (function(e){var s=getComputedStyle(e),r=e.getBoundingClientRect();var o={visible:s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0,enabled:!e.disabled,editable:(e.isContentEditable||((e.tagName==='INPUT'||e.tagName==='TEXTAREA')&&!e.readOnly&&!e.disabled))};if(o.visible){var x=r.left+r.width/2,y=r.top+r.height/2;if(x>=0&&y>=0&&x<=innerWidth&&y<=innerHeight){var t=document.elementFromPoint(x,y);if(t&&t!==e&&!e.contains(t)&&!t.contains(e)){o.covered_by=t.tagName.toLowerCase()+(t.id?'#'+t.id:'')+(typeof t.className==='string'&&t.className?'.'+t.className.trim().split(/\\s+/).slice(0,2).join('.'):'');}}}return o;})(arguments[0]);    ARGUMENTS    ${el}
    Set To Dictionary    ${r}    states=${st}
    ${need}=    Evaluate    ['visible', 'enabled', 'editable'] if $kind == 'fill' else ['visible', 'enabled'] if $kind == 'click' else []
    ${missing}=    Evaluate    [s for s in $need if not $st.get(s)]
    IF    $missing
        ${cls}=    Evaluate    {'visible': 'NOT_VISIBLE', 'enabled': 'DISABLED', 'editable': 'NOT_EDITABLE'}[$missing[0]]
        Set To Dictionary    ${r}    cls=${cls}    missing=${missing}
        RETURN    ${r}
    END
    IF    $kind == 'click' and $st.get('covered_by')
        Set To Dictionary    ${r}    cls=COVERED
        RETURN    ${r}
    END
    Set To Dictionary    ${r}    phase=action
    TRY
        ${ret}=    Run Keyword    ${action}    ${locator}    @{args}
    EXCEPT    AS    ${e}
        ${s}=    Evaluate    str($e)
        ${cls}=    Evaluate    'COVERED' if 'would receive the click' in $s or 'intercepted' in $s else 'NOT_INTERACTABLE' if 'not interactable' in $s else 'STALE' if 'stale' in $s.lower() else 'NOT_FOUND' if 'did not match' in $s else 'ACTION_ERROR'
        Set To Dictionary    ${r}    cls=${cls}    err=${{ $s.splitlines()[0][:260] }}
        RETURN    ${r}
    END
    IF    $ret is not None    Set To Dictionary    ${r}    ret=${{ str($ret)[:200] }}
    Set To Dictionary    ${r}    phase=post
    IF    $kind == 'fill' and $args and 'password' not in $k
        ${val}=    Get Value    ${locator}
        IF    str($val).strip() != str($args[0]).strip()
            Set To Dictionary    ${r}    cls=VALUE_MISMATCH    actual=${{ str($val)[:80] }}
            RETURN    ${r}
        END
        Set To Dictionary    ${r}    value_ok=${TRUE}
    END
    Set To Dictionary    ${r}    ok=${TRUE}    phase=done
    RETURN    ${r}

Guard Load JS
    IF    $_GUARD_JS_M    RETURN
    ${src}=    Get File    ${CURDIR}${/}guard.js
    ${m}    ${p}=    Evaluate    [x.strip() for x in $src.split('//--SPLIT--')]
    Set Global Variable    ${_GUARD_JS_M}    ${m}
    Set Global Variable    ${_GUARD_JS_P}    ${p}

Guard Diagnose
    [Arguments]    ${r}    ${locator}
    Guard Load JS
    ${u}=    Get Location
    Set To Dictionary    ${r}    url=${u}
    IF    $r.get('count', 0)
        ${els}=    Get WebElements    ${locator}
        ${m}=    Execute Javascript    return (${_GUARD_JS_M})(Array.from(arguments[0]), {k: 6, lib: 'selenium'});    ARGUMENTS    ${els}
        Set To Dictionary    ${r}    matches=${m}
    ELSE
        ${alts}=    Evaluate    (lambda s: (['css:' + s] if s[:1] in '[#.' or re.match(r'^[a-z]+[\\[.#]', s) else []) + (['xpath:' + s[6:]] if s.startswith('xpath=') else []) + (['id:' + s[3:]] if s.startswith('id=') else []) + (['xpath://*[normalize-space()="%s"]' % s[5:].strip('"'), 'link:' + s[5:].strip('"')] if s.startswith('text=') else []) + (['css:' + s[4:]] if s.startswith('css=') else []))($locator)    modules=re
        ${out}=    Create List
        FOR    ${a}    IN    @{alts}
            TRY
                ${c}=    Get Element Count    ${a}
            EXCEPT
                ${c}=    Set Variable    err
            END
            Append To List    ${out}    ${{ {'loc': $a, 'n': $c} }}
        END
        IF    $out    Set To Dictionary    ${r}    alts=${out}
        ${toks}=    Evaluate    [t for t in re.split(r'[^a-z0-9]+', $locator.lower()) if len(t) >= 2 and t not in ('css', 'xpath', 'id', 'text', 'data', 'test', 'name', 'link', 'button', 'input')]    modules=re
        ${p}=    Execute Javascript    return (${_GUARD_JS_P})(JSON.parse(arguments[0]));    ARGUMENTS    ${{ json.dumps({'q': $toks, 'k': int($GUARD_K), 'lib': 'selenium'}) }}
        Evaluate    $p.pop('frames', None)
        Set To Dictionary    ${r}    page=${p}
    END
    IF    $GUARD_SHOT != 'none'
        ${shot}=    Capture Page Screenshot    ${OUTPUT DIR}${/}guard-sl-{index}.png
        Set To Dictionary    ${r}    shot=${shot}
    END
