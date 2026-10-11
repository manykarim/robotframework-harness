*** Settings ***
Documentation     Guarded Browser steps for robotcode REPL / robot runs (research prototype).
...               pre-check -> action -> post-verify -> compact diagnostics on failure.
...               Emits exactly ONE machine-readable line per step:   GUARD {json}
...               Needs: Library Browser imported by the caller (any options).
Library           Collections
Library           OperatingSystem

*** Variables ***
${GUARD_PRE}               500ms
${GUARD_MODE}              precheck
${GUARD_ACTION_TIMEOUT}    1500ms
${GUARD_EXPECT_TIMEOUT}    2s
${GUARD_K}                 8
${GUARD_SHOT}              jpeg
${GUARD_ARIA}              0
${GUARD_FAIL}              ${FALSE}
${_GUARD_JS_M}             ${EMPTY}
${_GUARD_JS_P}             ${EMPTY}

*** Keywords ***
Guarded
    [Documentation]    Guarded    <Browser action>    <selector>    <action args...>    expect=<kind:value>    pre=500ms
    ...    expect kinds: url:<substring> | visible:<sel> | hidden:<sel> | text:<sel> *= <substring> | count:<sel> == <n>
    [Arguments]    ${action}    ${selector}    @{args}    ${expect}=${EMPTY}    ${pre}=${GUARD_PRE}    ${wait}=${GUARD_EXPECT_TIMEOUT}    ${mode}=${GUARD_MODE}
    ${t0}=    Evaluate    time.perf_counter()    modules=time
    ${lvl}=    Set Log Level    NONE
    ${rof}=    Register Keyword To Run On Failure    ${NONE}
    IF    $mode == 'fast'
        ${r}=    Guard Core Fast    ${action}    ${selector}    ${args}    ${expect}    ${GUARD_ACTION_TIMEOUT}    ${wait}
    ELSE
        ${r}=    Guard Core    ${action}    ${selector}    ${args}    ${expect}    ${pre}    ${wait}
    END
    ${t1}=    Evaluate    time.perf_counter()    modules=time
    IF    not $r['ok']    Guard Diagnose    ${r}    ${selector}
    ${r}[ms]=    Evaluate    round((time.perf_counter() - $t0) * 1000)    modules=time
    IF    not $r['ok']
        ${r}[diag_ms]=    Evaluate    round((time.perf_counter() - $t1) * 1000)    modules=time
    END
    ${json}=    Evaluate    json.dumps($r, ensure_ascii=False, default=str)    modules=json
    Register Keyword To Run On Failure    ${rof}
    Set Log Level    ${lvl}
    Log To Console    GUARD ${json}
    IF    $GUARD_FAIL and not $r['ok']    Fail    GUARD ${r}[cls] ${selector}
    RETURN    ${r}

Guard Core
    [Arguments]    ${action}    ${selector}    ${args}    ${expect}    ${pre}    ${wait}
    ${kind}=    Evaluate    (lambda k: 'read' if k.startswith(('get ', 'wait ')) else 'fill' if any(w in k for w in ('fill', 'type ', 'clear text', 'input')) else 'check' if 'check' in k else 'select' if 'select' in k else 'hover' if k.startswith(('hover', 'focus', 'scroll', 'press')) else 'click')($action.lower())
    ${req}=    Evaluate    {'click': ['visible', 'enabled'], 'fill': ['visible', 'enabled', 'editable'], 'check': ['visible', 'enabled'], 'select': ['visible', 'enabled'], 'hover': ['visible'], 'read': ['attached']}[$kind]
    &{r}=    Create Dictionary    v=${1}    ok=${FALSE}    kw=${action}    sel=${selector}    phase=pre
    # ---- 1. resolve: count (non-strict, no wait) -------------------------------------------
    TRY
        ${n}=    Get Element Count    ${selector}
    EXCEPT    AS    ${e}
        ${short}=    Guard Short Error    ${e}
        Set To Dictionary    ${r}    cls=INVALID_SELECTOR    err=${short}
        RETURN    ${r}
    END
    IF    ${n} == 0
        TRY
            Wait For Elements State    ${selector}    attached    ${pre}
        EXCEPT    AS    ${e}
            No Operation
        END
        ${n}=    Get Element Count    ${selector}
    END
    Set To Dictionary    ${r}    count=${n}
    IF    ${n} == 0
        Set To Dictionary    ${r}    cls=NOT_FOUND
        RETURN    ${r}
    END
    IF    ${n} > 1
        ${nv}=    Get Element Count    ${selector} >> visible=true
        Set To Dictionary    ${r}    cls=MULTI_MATCH    visible_count=${nv}
        RETURN    ${r}
    END
    # ---- 2. actionability states (Playwright semantics), short retry -----------------------
    ${old_retry}=    Set Retry Assertions For    ${pre}
    TRY
        ${st}=    Get Element States    ${selector}    contains    @{req}
    EXCEPT    AS    ${e}
        ${st}=    Get Element States    ${selector}
    FINALLY
        Set Retry Assertions For    ${old_retry}
    END
    ${missing}=    Evaluate    [s for s in $req if s not in $st]
    ${st_short}=    Evaluate    [s for s in $st if s in ('visible', 'hidden', 'enabled', 'disabled', 'editable', 'readonly', 'checked', 'unchecked', 'focused')]
    Set To Dictionary    ${r}    states=${st_short}
    IF    $missing
        ${cls}=    Evaluate    {'visible': 'NOT_VISIBLE', 'enabled': 'DISABLED', 'editable': 'NOT_EDITABLE'}.get($missing[0], 'NOT_ACTIONABLE')
        Set To Dictionary    ${r}    cls=${cls}    missing=${missing}
        RETURN    ${r}
    END
    # ---- 3. trial click: hit-test (covered / outside viewport / unstable) ------------------
    IF    $kind == 'click'
        ${old_to}=    Set Browser Timeout    ${pre}
        TRY
            Click With Options    ${selector}    trial=${TRUE}
        EXCEPT    AS    ${e}
            ${short}=    Guard Short Error    ${e}
            ${cls}=    Evaluate    'COVERED' if 'intercepts pointer events' in $short else 'OUT_OF_VIEWPORT' if 'outside of the viewport' in $short else 'NOT_VISIBLE' if 'not visible' in $short else 'NOT_STABLE' if 'not stable' in $short else 'NOT_CLICKABLE'
            Set To Dictionary    ${r}    cls=${cls}    err=${short}
        FINALLY
            Set Browser Timeout    ${old_to}
        END
        IF    'cls' in $r    RETURN    ${r}
    END
    # ---- 4. the action ----------------------------------------------------------------------
    Set To Dictionary    ${r}    phase=action
    ${url0}=    Get Url
    ${pos}    ${named}=    Evaluate    (lambda a, rx: ([x for x in a if not rx.match(x)], {x.split('=', 1)[0]: x.split('=', 1)[1] for x in a if rx.match(x)}))($args, re.compile(r'^(force|delay|clear|trial|noWaitAfter|position_x|position_y|clickCount|button|timeout)='))    modules=re
    TRY
        ${ret}=    Run Keyword    ${action}    ${selector}    @{pos}    &{named}
    EXCEPT    AS    ${e}
        ${short}=    Guard Short Error    ${e}
        ${cls}=    Evaluate    'COVERED' if 'intercepts pointer events' in $short else 'MULTI_MATCH' if 'strict mode violation' in $short else 'INVALID_SELECTOR' if ('SyntaxError' in $short or 'while parsing' in $short) else 'TIMEOUT' if 'Timeout' in $short else 'ACTION_ERROR'
        Set To Dictionary    ${r}    cls=${cls}    err=${short}
        RETURN    ${r}
    END
    IF    $ret is not None    Set To Dictionary    ${r}    ret=${{ str($ret)[:200] }}
    ${r}=    Guard Post    ${r}    ${kind}    ${action}    ${selector}    ${pos}    ${url0}    ${expect}    ${wait}
    RETURN    ${r}

Guard Post
    [Arguments]    ${r}    ${kind}    ${action}    ${selector}    ${pos}    ${url0}    ${expect}    ${wait}
    # ---- 5. post-action verification ---------------------------------------------------------
    Set To Dictionary    ${r}    phase=post
    IF    $kind == 'fill' and $pos and 'secret' not in $action.lower()
        ${val}=    Get Property    ${selector}    value
        ${ok}=    Evaluate    str($val).strip() == str($pos[0]).strip()
        Set To Dictionary    ${r}    value_ok=${ok}
        IF    not $ok
            Set To Dictionary    ${r}    cls=VALUE_MISMATCH    actual=${{ str($val)[:80] }}
            RETURN    ${r}
        END
    ELSE IF    $kind == 'check'
        ${checked}=    Get Checkbox State    ${selector}
        ${want}=    Evaluate    not $action.lower().startswith('uncheck')
        IF    $checked != $want
            Set To Dictionary    ${r}    cls=CHECK_MISMATCH    checked=${checked}
            RETURN    ${r}
        END
    ELSE IF    $kind == 'select' and $pos
        ${labels}=    Get Selected Options    ${selector}    label
        ${values}=    Get Selected Options    ${selector}    value
        ${sel_all}=    Evaluate    [str(x) for x in ($labels if isinstance($labels, list) else [$labels]) + ($values if isinstance($values, list) else [$values])]
        ${want}=    Evaluate    [p for p in $pos if p not in ('value', 'label', 'text', 'index')]
        ${miss}=    Evaluate    [w for w in $want if w not in $sel_all]
        IF    $miss
            Set To Dictionary    ${r}    cls=SELECT_MISMATCH    selected=${labels}
            RETURN    ${r}
        END
    END
    ${url1}=    Get Url
    IF    $url1 != $url0    Set To Dictionary    ${r}    nav=${url1}
    IF    $expect
        ${eok}    ${emsg}=    Guard Expect    ${expect}    ${wait}
        IF    not $eok
            Set To Dictionary    ${r}    cls=EXPECT_FAILED    expect=${expect}    err=${emsg}
            RETURN    ${r}
        END
        Set To Dictionary    ${r}    expect_ok=${TRUE}
    END
    Set To Dictionary    ${r}    ok=${TRUE}    phase=done
    RETURN    ${r}


Guard Core Fast
    [Documentation]    Optimistic mode: run the action with a short timeout; Playwright's own actionability
    ...    checks (attached/visible/enabled/editable/stable/receives-events/strict) do the pre-check.
    ...    Diagnostics run only on failure.
    [Arguments]    ${action}    ${selector}    ${args}    ${expect}    ${atimeout}    ${wait}
    ${kind}=    Evaluate    (lambda k: 'read' if k.startswith(('get ', 'wait ')) else 'fill' if any(w in k for w in ('fill', 'type ', 'clear text', 'input')) else 'check' if 'check' in k else 'select' if 'select' in k else 'hover' if k.startswith(('hover', 'focus', 'scroll', 'press')) else 'click')($action.lower())
    &{r}=    Create Dictionary    v=${1}    ok=${FALSE}    kw=${action}    sel=${selector}    phase=action    mode=fast
    ${pos}    ${named}=    Evaluate    (lambda a, rx: ([x for x in a if not rx.match(x)], {x.split('=', 1)[0]: x.split('=', 1)[1] for x in a if rx.match(x)}))($args, re.compile(r'^(force|delay|clear|trial|noWaitAfter|position_x|position_y|clickCount|button|timeout)='))    modules=re
    ${url0}=    Get Url
    ${old_to}=    Set Browser Timeout    ${atimeout}
    TRY
        ${ret}=    Run Keyword    ${action}    ${selector}    @{pos}    &{named}
    EXCEPT    AS    ${e}
        ${cls}=    Guard Classify    ${e}
        ${short}=    Guard Short Error    ${e}
        Set To Dictionary    ${r}    cls=${cls}    err=${short}
    FINALLY
        Set Browser Timeout    ${old_to}
    END
    IF    'cls' in $r
        TRY
            ${n}=    Get Element Count    ${selector}
        EXCEPT
            ${n}=    Set Variable    ${NONE}
        END
        Set To Dictionary    ${r}    count=${n}
        IF    $n == 0 and $r['cls'] in ('TIMEOUT', 'ACTION_ERROR')    Set To Dictionary    ${r}    cls=NOT_FOUND
        IF    $n is not None and $n > 1 and $r['cls'] in ('TIMEOUT', 'ACTION_ERROR')    Set To Dictionary    ${r}    cls=MULTI_MATCH
        RETURN    ${r}
    END
    IF    $ret is not None    Set To Dictionary    ${r}    ret=${{ str($ret)[:200] }}
    ${r}=    Guard Post    ${r}    ${kind}    ${action}    ${selector}    ${pos}    ${url0}    ${expect}    ${wait}
    RETURN    ${r}

Guard Classify
    [Documentation]    Map a Playwright/Browser error (incl. call log) to a failure class; the LAST state line wins.
    [Arguments]    ${e}
    ${cls}=    Evaluate    (lambda s: 'INVALID_SELECTOR' if re.search(r'SyntaxError|while parsing|Unknown engine|is not a valid selector', s) else 'MULTI_MATCH' if 'strict mode violation' in s else (lambda hits: hits[-1][1] if hits else ('NOT_FOUND' if ('Timeout' in s and 'waiting for' in s and 'resolved to' not in s) else 'TIMEOUT' if 'Timeout' in s else 'ACTION_ERROR'))(sorted([(m.start(), c) for c, rx in (('COVERED', 'intercepts pointer events'), ('DISABLED', r'element is not enabled|element is disabled'), ('NOT_EDITABLE', 'element is not editable'), ('OUT_OF_VIEWPORT', 'outside of the viewport'), ('NOT_VISIBLE', r'element is not visible|resolved to hidden'), ('NOT_STABLE', 'element is not stable')) for m in re.finditer(rx, s)])))(str($e))    modules=re
    RETURN    ${cls}

Guard Expect
    [Arguments]    ${expect}    ${wait}
    ${k}    ${v}=    Evaluate    $expect.split(':', 1)
    ${old_retry}=    Set Retry Assertions For    ${wait}
    TRY
        IF    $k == 'url'
            Get Url    *=    ${v}
        ELSE IF    $k in ('visible', 'hidden', 'detached', 'attached', 'enabled')
            Wait For Elements State    ${v}    ${k}    ${wait}
        ELSE IF    $k == 'text'
            ${s}    ${t}=    Evaluate    [x.strip() for x in $v.rsplit(' *= ', 1)]
            Get Text    ${s}    *=    ${t}
        ELSE IF    $k == 'count'
            ${s}    ${t}=    Evaluate    [x.strip() for x in $v.rsplit(' == ', 1)]
            Get Element Count    ${s}    ==    ${t}
        ELSE
            Fail    unknown expect kind '${k}'
        END
    EXCEPT    AS    ${e}
        ${short}=    Guard Short Error    ${e}
        RETURN    ${FALSE}    ${short}
    FINALLY
        Set Retry Assertions For    ${old_retry}
    END
    RETURN    ${TRUE}    ${EMPTY}

Guard Short Error
    [Arguments]    ${e}
    ${s}=    Evaluate    (lambda s: ' | '.join([s.splitlines()[0][:220]] + [l.strip()[:200] for l in s.splitlines()[1:] if re.search(r'intercepts pointer|resolved to|not visible|not enabled|not editable|outside of the viewport|detached|navigat|aka locator', l)][:3]))(str($e))    modules=re
    RETURN    ${s}

Guard Load JS
    IF    $_GUARD_JS_M
        RETURN
    END
    ${src}=    Get File    ${CURDIR}${/}guard.js
    ${m}    ${p}=    Evaluate    [x.strip() for x in $src.split('//--SPLIT--')]
    Set Global Variable    ${_GUARD_JS_M}    ${m}
    Set Global Variable    ${_GUARD_JS_P}    ${p}

Guard Alternatives
    [Documentation]    Pure string rewrites of a failing selector (Selenium-style, bare word, case) - counted live.
    [Arguments]    ${sel}
    ${alts}=    Evaluate    (lambda s, re: (lambda m: ([{'id': 'id=' + m.group(2), 'name': '[name="%s"]' % m.group(2), 'css': 'css=' + m.group(2), 'xpath': 'xpath=' + m.group(2), 'link': 'text="%s"' % m.group(2), 'partial link': 'text=' + m.group(2), 'class': '.' + m.group(2), 'tag': m.group(2)}[m.group(1).lower()]] if m else []))(re.match(r'^(id|name|css|xpath|link|partial link|class|tag)[:=](.+)$', s, re.I) if not re.match(r'^(id|css|xpath)=', s) else None) + (['id=' + s, '[name="%s"]' % s, '[data-test="%s"]' % s, 'text=' + s] if re.match(r'^[A-Za-z][\\w-]*$', s) else []) + ([re.sub(r'(\\[name="[^"]*")\\]', r'\\1 i]', s)] if s.startswith('role=') and ' i]' not in s else []) + (['[data-test*="%s"]' % re.split(r'[-_]', m2.group(1))[0]] if (m2 := re.match(r'^\\[data-test(?:id)?="([^"]+)"\\]$', s)) else []))($sel, re)    modules=re
    ${out}=    Create List
    FOR    ${a}    IN    @{alts}
        TRY
            ${c}=    Get Element Count    ${a}
        EXCEPT
            ${c}=    Set Variable    err
        END
        Append To List    ${out}    ${{ {'loc': $a, 'n': $c} }}
    END
    RETURN    ${out}

Guard Verify Locs
    [Documentation]    Live-verify the first ${max} suggested locators: adds n=<match count> (1 = unique, usable as-is).
    [Arguments]    ${items}    ${max}
    FOR    ${it}    IN    @{items}[:${max}]
        IF    not $it.get('loc') or '(x' in $it['loc'] or 'nth=?' in $it['loc']    CONTINUE
        TRY
            ${c}=    Get Element Count    ${it}[loc]
        EXCEPT
            ${c}=    Set Variable    err
        END
        Set To Dictionary    ${it}    n=${c}
    END

Guard Diagnose
    [Arguments]    ${r}    ${selector}
    Guard Load JS
    ${u}=    Get Url
    ${ti}=    Get Title
    Set To Dictionary    ${r}    url=${u}    title=${ti}
    ${n}=    Evaluate    $r.get('count', 0)
    IF    $n and $n >= 1 and $r['phase'] != 'post'
        TRY
            ${m}=    Evaluate JavaScript    ${selector}    ${_GUARD_JS_M}    all_elements=${TRUE}    arg=${{ {'k': 6} }}
            IF    $r['cls'] == 'MULTI_MATCH'    Guard Verify Locs    ${m}    3
            Set To Dictionary    ${r}    matches=${m}
        EXCEPT    AS    ${e}
            Set To Dictionary    ${r}    matches_err=${{ str($e)[:120] }}
        END
    END
    IF    $r['cls'] in ('NOT_FOUND', 'INVALID_SELECTOR', 'TIMEOUT')
        ${alts}=    Guard Alternatives    ${selector}
        IF    $alts    Set To Dictionary    ${r}    alts=${alts}
        ${toks}=    Evaluate    [t for t in re.split(r'[^a-z0-9]+', $selector.lower()) if len(t) >= 2 and t not in ('css', 'xpath', 'id', 'text', 'role', 'data', 'test', 'testid', 'name', 'nth', 'visible', 'true', 'false', 'div', 'span', 'button', 'input', 'link', 'internal')]    modules=re
        TRY
            ${p}=    Evaluate JavaScript    ${NONE}    ${_GUARD_JS_P}    arg=${{ {'q': $toks, 'k': int($GUARD_K)} }}
            Guard Verify Locs    ${p}[cand]    3
            ${in_frames}=    Create List
            FOR    ${f}    IN    @{p}[frames]
                TRY
                    ${fc}=    Get Element Count    ${f} >>> ${selector}
                EXCEPT
                    ${fc}=    Set Variable    ${0}
                END
                IF    $fc    Append To List    ${in_frames}    ${{ {'loc': $f + ' >>> ' + $selector, 'n': $fc} }}
            END
            IF    $in_frames    Set To Dictionary    ${r}    in_frames=${in_frames}
            Evaluate    $p.pop('frames', None)
            Set To Dictionary    ${r}    page=${p}
        EXCEPT    AS    ${e}
            Set To Dictionary    ${r}    page_err=${{ str($e)[:120] }}
        END
    END
    IF    int($GUARD_ARIA) > 0
        TRY
            ${a}=    Get Aria Snapshot    css=body
            Set To Dictionary    ${r}    aria=${{ $a[:int($GUARD_ARIA)] }}
        EXCEPT
            No Operation
        END
    END
    IF    $GUARD_SHOT != 'none'
        TRY
            ${shot}=    Take Screenshot    filename=${OUTPUT DIR}${/}guard-{index}    fileType=${GUARD_SHOT}    quality=${{ 60 if $GUARD_SHOT == 'jpeg' else None }}    log_screenshot=${FALSE}
            Set To Dictionary    ${r}    shot=${shot}
        EXCEPT    AS    ${e}
            Set To Dictionary    ${r}    shot_err=${{ str($e)[:120] }}
        END
    END
