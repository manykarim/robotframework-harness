# Browser library (Playwright): locators, iframes, shadow DOM

BROWSER LIBRARY (Playwright) -- LOCATORS, IFRAMES, SHADOW DOM

VERIFIED CORE (checked live on Browser 19.12 and 20.5):
- Strategies: css (default, no prefix needed), id=, text=, xpath= (or start with // ), data-test=/data-testid=.
- IFRAMES: Browser has NO "select frame" keyword. Put the frame selector in front and pierce it with >>>
      Fill Text    id=editor-frame >>> id=title    Draft
      Click        iframe[name="payment"] >>> text=Submit order
  Several steps in one frame:  Set Selector Prefix    id=editor-frame >>>   ...   Set Selector Prefix    ${EMPTY}
  .rf/state/latest/aria.yaml includes iframe content (Browser < 20.5: one section per iframe headed with the frame
  selector to prefix; >= 20.5: `Get Aria Snapshot    css=body    mode=ai` inlines it); controls.txt lists iframe
  controls with the full `frame >>> selector`.
- SHADOW DOM: css=, text= and id= pierce OPEN shadow roots automatically -> write the inner selector as if
  there were no shadow root:  Click    css=#shadow-btn  /  Get Text    text=Shadow says hi
  xpath does NOT pierce shadow roots; css:light= / text:light= deliberately do not pierce; closed roots unreachable.
- ROLE selectors work too: role=button[name="Sign in"] (exact accessible name; case-sensitive).
- STRICT MODE: a selector matching >1 element fails. Make it unique, or pick one: `css=.item >> nth=0` (zero-based).
- A cell STARTING with # is an RF comment: write `\#submit`, `css=#submit` or `id=submit`.
- Before acting on an unknown page: read .rf/state/latest/controls.txt / aria.yaml (written after each run that navigated or failed), then build a selector.
  ARIA lines like `button "Sign in"` are NOT selectors -> use text="Sign in" / css=button >> text=Sign in.
- Element keywords auto-wait up to the browser timeout (default 10 s) for the ELEMENT; values do not
  (getters with an operator retry only 1 s -> references/waits.md). The hook's probe refuses a step early (NOT RUN):
  NOT_FOUND (nothing matched within the short live timeout; inside an iframe -> prints the `frame >>> selector` fix;
  otherwise re-checked with the normal timeout -> SLOW or MISSING),
  NOT_VISIBLE (hidden styled input -> prints the label to click), COVERED (overlay/cookie banner -> close it).
- Custom widgets, dropdowns, dates, dialogs, new tabs, cookie banners: references/explore.md.

--- browser locator reference ---
locator_strategies:
  css: CSS selector (default strategy) - e.g., 'css=.class > #login_btn' or just '.class > #login_btn'
  xpath: XPath expression - e.g., 'xpath=//input[@id="login_btn"]' or '//input[@id="login_btn"]'
  text: Browser text engine (exact/partial/regex) - e.g., 'text=Login' or "Login"
  id: Element ID attribute - e.g., 'id=login_btn'
  css:light: CSS without shadow DOM piercing - e.g., 'css:light=article div'
  text:light: Text without shadow DOM piercing - e.g., 'text:light=Login'
  data-testid: data-testid attribute - e.g., 'data-testid=submit-button'
  data-test-id: data-test-id attribute - e.g., 'data-test-id=submit-button'
  data-test: data-test attribute - e.g., 'data-test=submit-button'
  id:light: ID without shadow DOM piercing - e.g., 'id:light=login_btn'
selector_patterns:
  explicit: strategy=value (e.g., 'css=.button', 'xpath=//button')
  implicit_css: Plain selectors default to CSS (e.g., '.button' becomes 'css=.button')
  implicit_xpath: Selectors starting with // or .. become XPath (e.g., '//button')
  implicit_text: Quoted selectors become text (e.g., '"Login"' becomes 'text=Login')
  cascaded: Multiple strategies with >> separator (e.g., 'text=Hello >> ../.. >> .select_button')
  iframe_piercing: Frame piercing with >>> (e.g., 'id=iframe >>> id=btn')
  element_reference: Element reference with element= (e.g., '${ref} >> .child')
common_examples:
  CSS (default): .button-primary
  CSS explicit: css=.button-primary
  CSS with ID: \#submit-btn
  XPath: //input[@type='submit']
  XPath implicit: //button[contains(text(), 'Login')]
  Text substring (case-insensitive): text=Login ; exact: text="Login"
  Text implicit: "Login"
  Text regex: text=/^Log(in|out)$/i
  ID: id=submit-button
  Cascaded: text=Hello >> ../.. >> .select_button
  iFrame piercing: id=myframe >>> .inner-button
selector_format_rules:
  Default strategy: CSS - plain selectors are treated as CSS
  Explicit format: strategy=value (spaces around = are ignored)
  XPath detection: Selectors starting with // or .. become XPath automatically
  Text detection: Quoted selectors ("text" or 'text') become text selectors
  Cascading: Use >> to chain selectors (css=div >> text=Login >> .button)
  iFrame access: Use >>> to pierce iFrames (id=frame >>> id=element)
  Element refs: Use element=${ref} >> .child for element references
strict_mode_info:
  description: Browser Library uses strict mode by default
  strict_true: Keyword fails if selector finds multiple elements
  strict_false: Keyword succeeds even with multiple matches (uses first)
  how_to_change: Use 'Set Strict Mode' keyword or library import parameter
shadow_dom_support:
  automatic_piercing: CSS and text engines automatically pierce open shadow roots
  light_engines: Use css:light= or text:light= to disable shadow DOM piercing
  closed_shadow_roots: Closed shadow roots cannot be accessed
tips:
  - Browser Library uses CSS selectors by default (no prefix needed)
  - Use \# instead of # for ID selectors (Robot Framework escaping)
  - XPath: Start with // or .. for automatic detection
  - Text: Use quotes for exact text matching or regex patterns
  - Cascaded selectors: Chain with >> for complex element paths
  - iFrames: Use >>> to access elements inside frames
  - Shadow DOM: CSS pierces automatically, use :light for light DOM only
  - Strict mode: Controls behavior when multiple elements match
strict_mode_violation:
  issue: Selector matches multiple elements but strict mode is enabled
  solutions:
    - Make selector more specific to match only one element
    - Use 'Set Strict Mode    False' to allow multiple matches
    - Add more specific CSS selectors or attributes
    - Use nth-child() or other CSS pseudo-selectors for specific elements
  examples:
    - Instead of '.button' use '.button.primary' or '.button:nth-child(1)'
    - Instead of 'div' use 'div.container > div.content'
    - Add unique attributes like '[data-testid="submit-btn"]'
element_not_found_suggestions:
  - Verify element exists on current page
  - Check if element loads asynchronously (use Wait For Elements State)
  - Try different selector strategies (CSS, XPath, text, ID)
  - Check if element is inside an iFrame (use >>> syntax)
  - Verify element is not in closed shadow DOM
  - Use browser developer tools to inspect element
  - Check if element appears after user interaction
timeout_suggestions:
  - Increase timeout with explicit waits
  - Use 'Wait For Elements State' before interaction
  - Check if element loads dynamically
  - Verify selector syntax is correct
  - Use 'Wait For Load State' to ensure page is ready
shadow_dom_guidance:
  issue: Element may be in shadow DOM
  solutions:
    - Use regular CSS (automatic shadow piercing): 'css=.my-element'
    - Use text selectors (automatic shadow piercing): 'text=Button Text'
    - Avoid css:light= for shadow DOM elements
    - Check if shadow root is closed (not accessible)
  note: Browser Library automatically pierces open shadow roots with CSS and text engines
iframe_guidance:
  issue: Element may be inside an iFrame
  solutions:
    - Use frame piercing syntax: 'id=myframe >>> .inner-element'
    - There is no 'select frame' step in Browser: put the frame selector in front, `<frame> >>> <inner>`
    - Use 'Set Selector Prefix' for multiple operations in same frame
  examples:
    - Click    id=login-frame >>> input[name='username']
    - Set Selector Prefix    id=content-frame >>>
Click    .submit-button    (prefix MUST end with >>>; reset: Set Selector Prefix    ${EMPTY})

--- common locator patterns ---

   Browser library (Playwright-backed):
     id=submit                       — by id attribute (equivalent to css=[id="submit"])
     css=button.primary              — CSS selector
     text=Sign in                    — substring match, case-insensitive (use text="Sign in" for exact)
     xpath=//input[@type='submit']   — XPath fallback
     id=item >> nth=2                — Playwright cascaded nth filter (zero-based; also via intent_action nth=2)
     // and ..                       — auto-routed to xpath (no prefix needed)
     "Quoted string"                 — auto-routed to exact text= (no prefix needed)
   For ARIA role + accessible name, use Browser's dedicated keywords
   (Get Element By Role, Click With Options) — the role engine ALSO works as a selector string: role=button[name="Sign in"] (verified live).

   SeleniumLibrary (= or : both work; : is the doc-preferred form):
     id=submit                       — by id attribute
     name=username                   — by name attribute
     css=button.primary              — CSS selector
     xpath=//input[@type='submit']   — XPath
     link=Click here                 — full link text
     partial link=Click              — partial link text (space inside the prefix)
     css=tr:nth-of-type(3)           — 1-based CSS nth 

   PICKING A LOCATOR
   - Prefer id= when available (stable, fast).
   - Fall back to css= or text= for elements without stable ids.
   - Use xpath= only when CSS/text cannot express the predicate.
   - When multiple elements match, disambiguate with `>> nth=N` (zero-based).
