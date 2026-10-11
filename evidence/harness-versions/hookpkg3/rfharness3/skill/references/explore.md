# Unknown pages and custom widgets

EXPLORING AN UNKNOWN LIVE PAGE + CUSTOM WIDGETS   (verified on Browser 19.12 and 20.5)

Open it and LOOK before writing any selector: write the Settings + `New Page    ${URL}` first; the hook runs it
and writes the page state (rewritten after every run that navigated or failed):
  .rf/state/latest/controls.txt   # every field/button/link: label, id, name, data-test, hidden?, native/custom, => selector
  .rf/state/latest/aria.yaml      # texts, roles, accessible names, one section per iframe Read messages from the page (Get Text) instead of guessing.

Selectors, most stable first: data-test=x / data-testid=x > id=x (not generated ones like id=r12, ember34) >
  role=textbox[name="E-mail"] / role=button[name="Save"] (name = label / aria-label / text) > text="Save" >
  short attribute CSS input[name="email"] > xpath. Avoid long CSS chains, nth-child, generated class names.
  By label/placeholder: ${e}=    Get Element By    Label    E-mail   then   Fill Text    ${e}    me@x.org

Cookie banner / overlay: close it first (Click    text=Accept all). The hook's probe reports COVERED. A click that
  fails with "intercepts pointer events" is covered too; Click With Options ... force=True does NOT help (the click
  lands on the overlay, passes, and nothing happens).

Styled radio / checkbox (the real <input> is hidden, a label/span is drawn instead): Check Checkbox / Click on the
  input waits for visibility and fails (the hook's probe: NOT_VISIBLE + the label to click). Click the visible label:
      Click    label[for="opt-yes"]         Click    label:has(#newsletter)         Click    text=Round trip
  Assert on the input (works while hidden): Get Checkbox State    id=opt-yes    ==    checked

Dropdowns:
  native <select> (aria: combobox WITH option children; controls: "native select"):
      Select Options By    id=country    label    Germany          (or value    de  /  index    2)
      Get Selected Options    id=country    label    ==    Germany  (attribute BEFORE the operator)
  custom dropdown (button/div, role=combobox/listbox; Select Options By fails "Element is not a <select> element"):
      Click    id=country-picker    ->  .rf/state/latest/aria.yaml  ->  Click    role=option[name="Germany"]   (or text=Germany)
      Get Text    id=country-picker    ==    Germany

Dates (add `Library    DateTime`): never hard-code a date that expires.
      ${d}=    Get Current Date    increment=7 days    result_format=%Y-%m-%d       # today + 7
      ${r}=    Add Time To Date    ${d}    14 days    result_format=%m/%d/%Y         # from another date
  <input type=date>: Fill Text    id=start    ${d}   with %Y-%m-%d (shown localized). Text fields: the format of
  their placeholder/label (%d.%m.%Y, %m/%d/%Y ...). Calendar pop-ups: try Fill Text on the input first; else open it
  and click the day (.rf/state/latest/aria.yaml).

JavaScript alert/confirm/prompt: without a handler they are DISMISSED (confirm() -> false, nothing happens).
      Handle Future Dialogs    action=accept    prompt_input=My text   # ONCE per page, BEFORE the click; stays active
      ${p}=    Promise To    Wait For Alert    action=accept    text=Delete item?   /  Click ...  /  Wait For    ${p}
  One handler per page: a 2nd Handle Future Dialogs (Browser 19.x) or mixing it with Wait For Alert -> two handlers
  -> the Playwright process crashes and every later test fails. Different answers on one page: one
  `Promise To    Wait For Alert` per dialog (accept/dismiss, prompt_input=...) and no Handle Future Dialogs there.
  In-page modals (role=dialog) are normal elements.

New tab / popup:  Click    text=Help   ->   ${prev}=    Switch Page    NEW   ...   Switch Page    ${prev}

Async UI: values do not wait; assertion operators retry only 1 s -> Wait For Condition    Text    id=status
  contains    Done    timeout=15s / Wait For Elements State    id=spinner    hidden    timeout=15s (references/waits.md).
Form ignores a filled value ("required" while text is shown): Fill Text fires `input` but not `change`; leave the
  field: Press Keys    id=email    Tab
