"""Signature-only stub for Browser 20.5.0 (generated from libdoc JSON)."""
from robot.api.deco import keyword, library


@library(scope='GLOBAL', version='20.5.0', auto_keywords=False)
class Browser:
    def __init__(self, *_, auto_closing_level=None, auto_delete_passed_tracing=None, enable_playwright_debug=None, enable_presenter_mode=None, external_browser_executable=None, highlight_on_failure=None, jsextension=None, language=None, playwright_process_host=None, playwright_process_port=None, plugins=None, retry_assertions_for=None, run_on_failure=None, selector_prefix=None, show_keyword_call_banner=None, strict=None, timeout=None, tracing_group_mode=None):
        pass

    @keyword('Add Cookie', tags=['BrowserControl', 'Setter'])
    def add_cookie(self, name, value, url=None, domain=None, path=None, expires=None, httpOnly=None, secure=None, sameSite=None):
        """Adds a cookie to the currently active browser context."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Add Locator Handler Click', tags=['PageContent', 'Setter'])
    def add_locator_handler_click(self, selector, click_selector, *, noWaitAfter=None, times=None, click_clickCount=None, click_delay=None, click_force=None):
        """Add a handler function which will activate when ``selector`` is visible and click."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Add Locator Handler Custom', tags=['PageContent', 'Setter'])
    def add_locator_handler_custom(self, selector, handler_spec, noWaitAfter=None, times=None):
        """Add a handler function which will activate when ``selector`` is visible and performs handler specification."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Add Style Tag', tags=['PageContent', 'Setter'])
    def add_style_tag(self, content):
        """Adds a <style type="text/css"> tag with the content."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Advance Clock', tags=['Clock', 'Setter'])
    def advance_clock(self, time, advance_type=None):
        """Advances the clock by a specified amount of time."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Cancel Download', tags=['BrowserControl', 'Setter'])
    def cancel_download(self, download):
        """Cancels an active download."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Check Checkbox', tags=['PageContent', 'Setter'])
    def check_checkbox(self, selector, force=None):
        """Checks the checkbox or selects radio button found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Clear Permissions', tags=['BrowserControl', 'Setter'])
    def clear_permissions(self):
        """Clears all permissions from the current context."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Clear Text', tags=['PageContent', 'Setter'])
    def clear_text(self, selector):
        """Clears the text field found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Click', tags=['PageContent', 'Setter'])
    def click(self, selector, button=None):
        """Simulates mouse click on the element found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Click With Options', tags=['PageContent', 'Setter'])
    def click_with_options(self, selector, button=None, *modifiers, clickCount=None, delay=None, force=None, noWaitAfter=None, position_x=None, position_y=None, trial=None):
        """Simulates mouse click on the element found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Close Browser', tags=['BrowserControl', 'Setter'])
    def close_browser(self, browser=None):
        """Closes the current browser."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Close Browser Server', tags=['BrowserControl', 'Setter'])
    def close_browser_server(self, wsEndpoint):
        """Close a playwright Browser Server identified by its websocket endpoint (wsEndpoint)."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Close Context', tags=['BrowserControl', 'Setter'])
    def close_context(self, context=None, browser=None, *, save_trace=None):
        """Closes a Context."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Close Page', tags=['BrowserControl', 'Setter'])
    def close_page(self, page=None, context=None, browser=None, runBeforeUnload=None):
        """Closes the ``page`` in ``context`` in ``browser``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Connect To Browser', tags=['BrowserControl', 'Setter'])
    def connect_to_browser(self, wsEndpoint, browser=None, use_cdp=None, *, timeout=None):
        """Connect to a Playwright browser server via playwright websocket or Chrome DevTools Protocol."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Crawl Site', tags=['Crawling'])
    def crawl_site(self, url=None, page_crawl_keyword=None, max_number_of_page_to_crawl=None, max_depth_to_crawl=None):
        """Web crawler is a tool to go through all the pages on a specific URL domain. This happens by finding all links going to the same site and opening those. Links pointing to another scheme or host are ignored, as are download links."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Create Credential', tags=['Credential', 'Setter'])
    def create_credential(self, rpId, id_=None, privateKey=None, publicKey=None, userHandle=None):
        """Creates a credential with the given parameters."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Delete All Cookies', tags=['BrowserControl', 'Setter'])
    def delete_all_cookies(self):
        """Deletes all cookies from the currently active browser context."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Delete Credential', tags=['Credential', 'Setter'])
    def delete_credential(self, id_):
        """Deletes the credential with the given id."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Deselect Options', tags=['PageContent', 'Setter'])
    def deselect_options(self, selector):
        """Deselects all options from select element found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Download', tags=['Page Content'])
    def download(self, url, saveAs=None, wait_for_finished=None, download_timeout=None):
        """Download given url content."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Drag And Drop', tags=['PageContent', 'Setter'])
    def drag_and_drop(self, selector_from, selector_to, steps=None):
        """Executes a Drag&Drop operation from the element selected by ``selector_from`` to the element selected by ``selector_to``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Drag And Drop By Coordinates', tags=['PageContent', 'Setter'])
    def drag_and_drop_by_coordinates(self, from_x, from_y, to_x, to_y, steps=None):
        """Executes a Drag&Drop operation from a coordinate to another coordinate."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Drag And Drop Relative To', tags=['PageContent', 'Setter'])
    def drag_and_drop_relative_to(self, selector_from, x=None, y=None, steps=None):
        """Executes a Drag&Drop operation from the element selected by ``selector_from`` to coordinates relative to the center of that element."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Eat All Cookies', tags=[])
    def eat_all_cookies(self):
        """Eat all cookies for all easter."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Emulate Media', tags=['PageContent', 'Setter'])
    def emulate_media(self, colorScheme=None, forcedColors=None, media=None, reducedMotion=None):
        """Changes the CSS media type."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Evaluate JavaScript', tags=['Getter', 'PageContent', 'Setter'])
    def evaluate_javascript(self, selector=None, *function, arg=None, all_elements=None):
        """Executes the given JavaScript in the browser page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Fill Secret', tags=['PageContent', 'Setter'])
    def fill_secret(self, selector, secret, force=None):
        """Fills the given ``secret`` into the text field found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Fill Text', tags=['PageContent', 'Setter'])
    def fill_text(self, selector, txt, force=None):
        """Clears and fills the given ``txt`` into the text field found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Focus', tags=['PageContent', 'Setter'])
    def focus(self, selector):
        """Moves focus on to the element found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Aria Snapshot', tags=['Assertion', 'Getter', 'PageContent'])
    def get_aria_snapshot(self, selector, return_type=None, assertion_operator=None, assertion_expected=None, message=None, *, mode=None, depth=None, boxes=None):
        """Returns the aria snapshot of the element found by ``selector``. See `AriaSnapshotReturnType` for more details and examples."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Attribute', tags=['Assertion', 'Getter', 'PageContent'])
    def get_attribute(self, selector, attribute, assertion_operator=None, assertion_expected=None, message=None):
        """Returns the HTML ``attribute`` of the element found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Attribute Names', tags=['Assertion', 'Getter', 'PageContent'])
    def get_attribute_names(self, selector, assertion_operator=None, *assertion_expected, message=None):
        """Returns all HTML attribute names of an element as a list."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get BoundingBox', tags=['Assertion', 'Getter', 'PageContent'])
    def get_boundingbox(self, selector, key=None, assertion_operator=None, assertion_expected=None, message=None, *, allow_hidden=None):
        """Gets elements size and location as an object ``{x: float, y: float, width: float, height: float}``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Browser Catalog', tags=['Assertion', 'BrowserControl', 'Getter'])
    def get_browser_catalog(self, assertion_operator=None, assertion_expected=None, message=None):
        """Returns all browsers, open contexts in them and open pages in these contexts."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Browser Ids', tags=['Assertion', 'BrowserControl', 'Getter'])
    def get_browser_ids(self, browser=None, assertion_operator=None, *assertion_expected, message=None):
        """Returns a list of ids from open browsers. See `Browser, Context and Page` for more information about Browser and related concepts."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Checkbox State', tags=['Assertion', 'Getter', 'PageContent'])
    def get_checkbox_state(self, selector, assertion_operator=None, assertion_expected=None, message=None):
        """Returns the state of the checkbox found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Classes', tags=['Assertion', 'Getter', 'PageContent'])
    def get_classes(self, selector, assertion_operator=None, *assertion_expected, message=None):
        """Returns all classes of an element as a list."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Client Size', tags=['Assertion', 'Getter', 'PageContent'])
    def get_client_size(self, selector=None, key=None, assertion_operator=None, assertion_expected=None, message=None):
        """Gets elements or pages client size (``clientHeight``, ``clientWidth``) as object {width: float, height: float}."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Console Log', tags=['Assertion', 'BrowserControl', 'Getter'])
    def get_console_log(self, assertion_operator=None, assertion_expected=None, message=None, *, full=None, last=None):
        """Returns the console log of the active page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Context Ids', tags=['Assertion', 'BrowserControl', 'Getter'])
    def get_context_ids(self, context=None, browser=None, assertion_operator=None, *assertion_expected, message=None):
        """Returns a list of context ids based on the browser selection. See `Browser, Context and Page` for more information about Context and related concepts."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Cookie', tags=['BrowserControl', 'Getter'])
    def get_cookie(self, cookie, return_type=None):
        """Returns information about the cookie named ``cookie`` as a Robot Framework dot dictionary or a string."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Cookies', tags=['Getter', 'PageContent'])
    def get_cookies(self, return_type=None):
        """Returns cookies from the currently active browser context."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Credential', tags=['Credential', 'Getter'])
    def get_credential(self, id_=None, rpId=None):
        """Returns the credential matching the given id and/or rpId."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Device', tags=['BrowserControl', 'Getter'])
    def get_device(self, name):
        """Returns a single device descriptor whose name matches ``name`` exactly."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Devices', tags=['BrowserControl', 'Getter'])
    def get_devices(self):
        """Returns a dictionary of all Playwright device descriptors."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Download State', tags=['Assertion', 'Getter', 'PageContent'])
    def get_download_state(self, download, assertion_operator=None, assertion_expected=None, message=None):
        """Gets the state of a download."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Element', tags=['Getter', 'PageContent'])
    def get_element(self, selector):
        """Returns a selector string that points to the element found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Element By', tags=['Getter', 'PageContent'])
    def get_element_by(self, selection_strategy, text, exact=None, all_elements=None):
        """Allows locating elements by their features."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Element By Role', tags=['Getter', 'PageContent'])
    def get_element_by_role(self, role, *, all_elements=None, checked=None, disabled=None, exact=None, expanded=None, include_hidden=None, level=None, name=None, pressed=None, selected=None):
        """Returns a selector string for the element matched by ``role``, or a list of selector strings if ``all_elements`` is set to ``True``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Element Count', tags=['Assertion', 'Getter', 'PageContent'])
    def get_element_count(self, selector, assertion_operator=None, assertion_expected=None, message=None):
        """Returns the count of elements found with ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Element States', tags=['Assertion', 'Getter', 'PageContent'])
    def get_element_states(self, selector, assertion_operator=None, *assertion_expected, message=None, return_names=None):
        """Get the active states from the element found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Elements', tags=['Getter', 'PageContent'])
    def get_elements(self, selector):
        """Returns a list of selector strings, one for each element matched by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Page Errors', tags=['Assertion', 'BrowserControl', 'Getter'])
    def get_page_errors(self, assertion_operator=None, assertion_expected=None, message=None, *, full=None, last=None):
        """Returns the page errors of the active page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Page Ids', tags=['Assertion', 'BrowserControl', 'Getter'])
    def get_page_ids(self, page=None, context=None, browser=None, assertion_operator=None, *assertion_expected, message=None):
        """Returns a list of page ids based on the context and browser selection. See `Browser, Context and Page` for more information about Page and related concepts."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Page Source', tags=['Assertion', 'Getter', 'PageContent'])
    def get_page_source(self, assertion_operator=None, assertion_expected=None, message=None):
        """Gets the page's HTML source as a string."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Property', tags=['Assertion', 'Getter', 'PageContent'])
    def get_property(self, selector, property, assertion_operator=None, assertion_expected=None, message=None):
        """Returns the ``property`` of the element found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Scroll Position', tags=['Assertion', 'Getter', 'PageContent'])
    def get_scroll_position(self, selector=None, key=None, assertion_operator=None, assertion_expected=None, message=None):
        """Gets elements or pages current scroll position as object ``{top: float, left: float, bottom: float, right: float}``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Scroll Size', tags=['Assertion', 'Getter', 'PageContent'])
    def get_scroll_size(self, selector=None, key=None, assertion_operator=None, assertion_expected=None, message=None):
        """Gets elements or pages scrollable size as object ``{width: float, height: float}``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Select Options', tags=['Assertion', 'Getter', 'PageContent'])
    def get_select_options(self, selector, assertion_operator=None, assertion_expected=None, message=None):
        """Returns attributes of options of a ``select`` element as a list of dictionaries."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Selected Options', tags=['Assertion', 'Getter', 'PageContent'])
    def get_selected_options(self, selector, option_attribute=None, assertion_operator=None, *assertion_expected, message=None):
        """Returns the specified attribute of selected options of the ``select`` element."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Style', tags=['Assertion', 'Getter', 'PageContent'])
    def get_style(self, selector, key=None, assertion_operator=None, assertion_expected=None, message=None, pseudo_element=None):
        """Gets the computed style properties of the element selected by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Table Cell Element', tags=['Getter', 'PageContent'])
    def get_table_cell_element(self, table, column, row):
        """Returns a selector string for the cell at the same column and row index as the selected elements."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Table Cell Index', tags=['Assertion', 'Getter', 'PageContent'])
    def get_table_cell_index(self, selector, assertion_operator=None, assertion_expected=None, message=None):
        """Returns the index (0 based) of a table cell within its row."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Table Row Index', tags=['Assertion', 'Getter', 'PageContent'])
    def get_table_row_index(self, selector, assertion_operator=None, assertion_expected=None, message=None):
        """Returns the index (0 based) of a table row."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Text', tags=['Assertion', 'Getter', 'PageContent'])
    def get_text(self, selector, assertion_operator=None, assertion_expected=None, message=None, *, text_type=None):
        """Returns text attribute of the element found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Title', tags=['Assertion', 'Getter', 'PageContent'])
    def get_title(self, assertion_operator=None, assertion_expected=None, message=None):
        """Returns the title of the current page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Url', tags=['Assertion', 'Getter', 'PageContent'])
    def get_url(self, assertion_operator=None, assertion_expected=None, message=None):
        """Returns the current URL."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Viewport Size', tags=['Assertion', 'BrowserControl', 'Getter'])
    def get_viewport_size(self, key=None, assertion_operator=None, assertion_expected=None, message=None):
        """Returns the current viewport dimensions."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Go Back', tags=['BrowserControl', 'Setter'])
    def go_back(self):
        """Navigates to the previous page in history."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Go Forward', tags=['BrowserControl', 'Setter'])
    def go_forward(self):
        """Navigates to the next page in history."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Go To', tags=['BrowserControl', 'Setter'])
    def go_to(self, url, timeout=None, wait_until=None):
        """Navigates to the given ``url``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Grant Permissions', tags=['BrowserControl', 'Setter'])
    def grant_permissions(self, *permissions, origin=None):
        """Grants permissions to the current context."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Handle Future Dialogs', tags=['PageContent'])
    def handle_future_dialogs(self, action, prompt_input=None):
        """Handle next dialog on page with ``action``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Highlight Elements', tags=['PageContent', 'Setter'])
    def highlight_elements(self, selector, duration=None, width=None, style=None, color=None, *, mode=None):
        """Adds a highlight to elements matched by the ``selector``. Provides a style adjustment."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Hover', tags=['PageContent', 'Setter'])
    def hover(self, selector, position_x=None, position_y=None, force=None, *modifiers):
        """Moves the virtual mouse and scrolls to the element found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Http', tags=['HTTP'])
    def http(self, url, method=None, body=None, headers=None):
        """Performs an HTTP request in the current browser context"""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Install Credential', tags=['Credential', 'Setter'])
    def install_credential(self):
        """Installs the virtual WebAuthn authenticator into the context."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Keyboard Input', tags=['PageContent', 'Setter'])
    def keyboard_input(self, action, input, delay=None):
        """Input text into page with virtual keyboard."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Keyboard Key', tags=['PageContent', 'Setter'])
    def keyboard_key(self, action, key, *, delay=None):
        """Press a keyboard key on the virtual keyboard or set a key up or down."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Launch Browser Server', tags=['BrowserControl', 'Setter'])
    def launch_browser_server(self, browser=None, headless=None, *, args=None, channel=None, chromiumSandbox=None, devtools=None, downloadsPath=None, env=None, executablePath=None, firefoxUserPrefs=None, handleSIGHUP=None, handleSIGINT=None, handleSIGTERM=None, ignoreDefaultArgs=None, port=None, proxy=None, reuse_existing=None, slowMo=None, timeout=None, wsPath=None):
        """Launches a new playwright Browser server with specified options."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('LocalStorage Clear', tags=['PageContent', 'Setter'])
    def localstorage_clear(self, frame_selector=None):
        """Remove all saved data from the local storage."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('LocalStorage Get Item', tags=['Assertion', 'Getter', 'PageContent'])
    def localstorage_get_item(self, key, assertion_operator=None, assertion_expected=None, message=None, frame_selector=None):
        """Get saved data from the local storage."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('LocalStorage Remove Item', tags=['PageContent', 'Setter'])
    def localstorage_remove_item(self, key, frame_selector=None):
        """Remove saved data with key from the local storage."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('LocalStorage Set Item', tags=['PageContent', 'Setter'])
    def localstorage_set_item(self, key, value, frame_selector=None):
        """Save data to the local storage."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Merge Coverage Reports', tags=['Coverage', 'Setter'])
    def merge_coverage_reports(self, input_folder, output_folder, config_file=None, name=None, reports=None):
        """Combines multiple raw coverage reports into a single report."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Mouse Button', tags=['PageContent', 'Setter'])
    def mouse_button(self, action, x=None, y=None, button=None, clickCount=None, delay=None):
        """Clicks, presses or releases a mouse button."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Mouse Move', tags=['PageContent', 'Setter'])
    def mouse_move(self, x, y, steps=None):
        """Moves the virtual mouse to the given coordinates, instead of to an element found by a selector."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Mouse Move Relative To', tags=['PageContent', 'Setter'])
    def mouse_move_relative_to(self, selector, x=None, y=None, steps=None):
        """Moves the mouse cursor relative to the selected element."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Mouse Wheel', tags=['PageContent', 'Setter'])
    def mouse_wheel(self, deltaX, deltaY):
        """Simulates the user rotation of a mouse wheel."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('New Browser', tags=['BrowserControl', 'Setter'])
    def new_browser(self, browser=None, headless=None, *, args=None, channel=None, chromiumSandbox=None, devtools=None, downloadsPath=None, env=None, executablePath=None, firefoxUserPrefs=None, handleSIGHUP=None, handleSIGINT=None, handleSIGTERM=None, ignoreDefaultArgs=None, proxy=None, reuse_existing=None, slowMo=None, timeout=None):
        """Create a new playwright Browser with specified options."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('New Context', tags=['BrowserControl', 'Setter'])
    def new_context(self, *, acceptDownloads=None, baseURL=None, bypassCSP=None, clientCertificates=None, colorScheme=None, defaultBrowserType=None, deviceScaleFactor=None, extraHTTPHeaders=None, forcedColors=None, geolocation=None, hasTouch=None, httpCredentials=None, ignoreHTTPSErrors=None, isMobile=None, javaScriptEnabled=None, locale=None, offline=None, permissions=None, proxy=None, recordHar=None, recordVideo=None, reducedMotion=None, screen=None, serviceWorkers=None, storageState=None, timezoneId=None, tracing=None, userAgent=None, viewport=None):
        """Create a new BrowserContext with specified options."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('New Page', tags=['BrowserControl', 'Setter'])
    def new_page(self, url=None, wait_until=None):
        """Open a new Page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('New Persistent Context', tags=[])
    def new_persistent_context(self, userDataDir=None, browser=None, headless=None, *, acceptDownloads=None, args=None, baseURL=None, bypassCSP=None, channel=None, chromiumSandbox=None, colorScheme=None, defaultBrowserType=None, deviceScaleFactor=None, devtools=None, downloadsPath=None, env=None, executablePath=None, extraHTTPHeaders=None, forcedColors=None, geolocation=None, handleSIGHUP=None, handleSIGINT=None, handleSIGTERM=None, hasTouch=None, httpCredentials=None, ignoreDefaultArgs=None, ignoreHTTPSErrors=None, isMobile=None, javaScriptEnabled=None, locale=None, offline=None, permissions=None, proxy=None, recordHar=None, recordVideo=None, reducedMotion=None, screen=None, serviceWorkers=None, slowMo=None, timeout=None, timezoneId=None, tracing=None, url=None, userAgent=None, viewport=None):
        """Opens a new persistent context."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Open Browser', tags=['BrowserControl', 'Setter'])
    def open_browser(self, url=None, browser=None, headless=None, pause_on_failure=None, bypassCSP=None):
        """Opens a new browser instance. Use this keyword for quick experiments or debugging sessions."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Pause At', tags=['Clock', 'Setter'])
    def pause_at(self, time):
        """Advances the clock by jumping forward in time and pauses it."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Press Keys', tags=['PageContent', 'Setter'])
    def press_keys(self, selector, *keys, press_duration=None, key_delay=None):
        """Types the given key combination into element found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Promise To', tags=['Wait'])
    def promise_to(self, kw, *args):
        """Wrap a Browser library keyword and make it a promise."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Promise To Upload File', tags=['PageContent', 'Setter'])
    def promise_to_upload_file(self, path):
        """Returns a promise that resolves when the file from ``path`` has been uploaded."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Promise To Wait For Download', tags=['BrowserControl', 'Wait'])
    def promise_to_wait_for_download(self, saveAs=None, wait_for_finished=None, download_timeout=None):
        """Returns a promise that waits for the next download event on the page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Record Selector', tags=['PageContent'])
    def record_selector(self, label=None):
        """Record the selector that is under mouse."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Register Keyword To Run On Failure', tags=['Config'])
    def register_keyword_to_run_on_failure(self, keyword, *args, scope=None):
        """Sets the keyword to execute, when a Browser keyword fails."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Reload', tags=['BrowserControl', 'Setter'])
    def reload(self, timeout=None, waitUntil=None):
        """Reloads current active page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Remove Locator Handler', tags=['PageContent', 'Setter'])
    def remove_locator_handler(self, locator):
        """Remove the locator handler indicated by ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Resume Clock', tags=['Clock', 'Setter'])
    def resume_clock(self):
        """Resumes the clock."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Save Page As Pdf', tags=['Getter', 'PageContent'])
    def save_page_as_pdf(self, path, *, displayHeaderFooter=None, footerTemplate=None, format=None, headerTemplate=None, height=None, landscape=None, margin=None, outline=None, pageRanges=None, preferCSSPageSize=None, printBackground=None, scale=None, tagged=None, width=None):
        """Saves page as PDF."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Save Storage State', tags=['BrowserControl', 'Getter'])
    def save_storage_state(self, path=None, *, indexedDB=None, credentials=None):
        """Saves the current active context storage state to a file."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Scroll By', tags=['PageContent', 'Setter'])
    def scroll_by(self, selector=None, vertical=None, horizontal=None, behavior=None):
        """Scrolls an element or the page relative from current position by the given values."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Scroll To', tags=['PageContent', 'Setter'])
    def scroll_to(self, selector=None, vertical=None, horizontal=None, behavior=None):
        """Scrolls an element or the page to an absolute position based on given coordinates."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Scroll To Element', tags=['PageContent', 'Setter'])
    def scroll_to_element(self, selector):
        """This method waits for actionability checks, then tries to scroll element into view, unless it is completely visible."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Select Options By', tags=['PageContent', 'Setter'])
    def select_options_by(self, selector, attribute, *values):
        """Selects options from select element found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('SessionStorage Clear', tags=['PageContent', 'Setter'])
    def sessionstorage_clear(self, frame_selector=None):
        """Remove all saved data from the session storage."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('SessionStorage Get Item', tags=['Assertion', 'Getter', 'PageContent'])
    def sessionstorage_get_item(self, key, assertion_operator=None, assertion_expected=None, message=None, frame_selector=None):
        """Get saved data from the session storage."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('SessionStorage Remove Item', tags=['PageContent', 'Setter'])
    def sessionstorage_remove_item(self, key, frame_selector=None):
        """Remove saved data with key from the session storage."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('SessionStorage Set Item', tags=['PageContent', 'Setter'])
    def sessionstorage_set_item(self, key, value, frame_selector=None):
        """Save data to session storage."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Assertion Formatters', tags=['Config'])
    def set_assertion_formatters(self, formatters, scope=None):
        """Set keywords formatters for assertions."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Browser Timeout', tags=['Config', 'Setter'])
    def set_browser_timeout(self, timeout, scope=None):
        """Sets the timeout used by most input and getter keywords."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Default Run Before Unload', tags=['BrowserControl', 'Setter'])
    def set_default_run_before_unload(self, runBeforeUnload):
        """Set default runBeforeUnload value when `Close Page` is called indirectly."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Geolocation', tags=['BrowserControl', 'Setter'])
    def set_geolocation(self, latitude, longitude, accuracy=None):
        """Updates the current context's geolocation."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Highlight On Failure', tags=['Config', 'Setter'])
    def set_highlight_on_failure(self, highlight=None, scope=None):
        """Controls if the element is highlighted on failure."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Offline', tags=['BrowserControl', 'Setter'])
    def set_offline(self, offline=None):
        """Toggles the current context's offline emulation."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Presenter Mode', tags=['BrowserControl', 'Setter'])
    def set_presenter_mode(self, mode):
        """Sets presenter mode for element highlighting during test execution."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Retry Assertions For', tags=['Config', 'Setter'])
    def set_retry_assertions_for(self, timeout, scope=None):
        """Sets the timeout used in retrying assertions when they fail."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Selector Prefix', tags=['Config', 'Setter'])
    def set_selector_prefix(self, prefix, scope=None):
        """Sets the prefix for all selectors in the given scope."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Storage State', tags=['BrowserControl', 'Setter'])
    def set_storage_state(self, path, timeout=None, reload_pages=None):
        """Restores a storage state file into the current active context."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Strict Mode', tags=['BrowserControl', 'Setter'])
    def set_strict_mode(self, mode, scope=None):
        """Controls library strict mode."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Time', tags=['Clock', 'Setter'])
    def set_time(self, time, clock_type=None):
        """Sets the time of the browser's internal clock."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Viewport Size', tags=['BrowserControl', 'Setter'])
    def set_viewport_size(self, width, height):
        """Sets the current page's viewport size to the specified dimensions."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Show Keyword Banner', tags=['Config', 'Setter'])
    def show_keyword_banner(self, show=None, style=None, scope=None):
        """Controls if the keyword banner is shown on page or not."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Start Coverage', tags=['Coverage', 'Experimental', 'Setter'])
    def start_coverage(self, *, config_file=None, coverage_type=None, path=None, raw=None, reportAnonymousScripts=None, resetOnNavigation=None):
        """Starts the coverage for the current page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Stop Coverage', tags=['Coverage', 'Getter'])
    def stop_coverage(self):
        """Stops the coverage for the current page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Switch Browser', tags=['BrowserControl', 'Setter'])
    def switch_browser(self, id):
        """Switches the currently active Browser to another open Browser."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Switch Context', tags=['BrowserControl', 'Setter'])
    def switch_context(self, id, browser=None):
        """Switches the active BrowserContext to another open context."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Switch Page', tags=['BrowserControl', 'Setter'])
    def switch_page(self, id, context=None, browser=None):
        """Switches the active browser page to another open page by ``id`` or ``NEW``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Take Screenshot', tags=['PageContent'])
    def take_screenshot(self, filename=None, selector=None, *, crop=None, disableAnimations=None, fileType=None, fullPage=None, highlight_selector=None, log_screenshot=None, mask=None, maskColor=None, omitBackground=None, quality=None, scale=None, return_as=None, timeout=None):
        """Takes a screenshot of the current window or element and saves it to disk."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Tap', tags=['PageContent', 'Setter'])
    def tap(self, selector, *modifiers, force=None, noWaitAfter=None, position_x=None, position_y=None, trial=None):
        """Simulates tap on the element found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Type Secret', tags=['PageContent', 'Setter'])
    def type_secret(self, selector, secret, delay=None, clear=None):
        """Types the given ``secret`` into the text field found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Type Text', tags=['PageContent', 'Setter'])
    def type_text(self, selector, txt, delay=None, clear=None):
        """Types the given ``txt`` into the text field found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Uncheck Checkbox', tags=['PageContent', 'Setter'])
    def uncheck_checkbox(self, selector, force=None):
        """Unchecks the checkbox found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Upload File By Selector', tags=['PageContent', 'Setter'])
    def upload_file_by_selector(self, selector, path, *extra_paths):
        """Uploads file from ``path`` to file input element matched by selector."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait For', tags=['Wait'])
    def wait_for(self, *promises):
        """Waits for promises to finish and returns results from them."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait For Alert', tags=['PageContent', 'Wait'])
    def wait_for_alert(self, action, prompt_input=None, text=None, timeout=None):
        """Returns a promise to wait for next dialog on page, handles it with ``action`` and optionally verifies the dialogs text."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait For Alerts', tags=['PageContent', 'Wait'])
    def wait_for_alerts(self, actions, prompt_inputs, texts, timeout=None):
        """Returns a promise to wait for multiple dialogs on a page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait For All Promises', tags=['Wait'])
    def wait_for_all_promises(self):
        """Waits for all promises to finish."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait For Condition', tags=['PageContent', 'Wait'])
    def wait_for_condition(self, condition, *args, timeout=None, message=None):
        """Waits for a condition, defined with Browser getter keywords, to become True."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait For Elements State', tags=['PageContent', 'Wait'])
    def wait_for_elements_state(self, selector, state=None, timeout=None, message=None):
        """Waits for the element found by ``selector`` to satisfy state option."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait For Function', tags=['PageContent', 'Wait'])
    def wait_for_function(self, function, selector=None, polling=None, timeout=None, message=None):
        """Polls JavaScript expression or function in browser until it returns a (JavaScript) truthy value."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait For Load State', tags=['PageContent', 'Wait'])
    def wait_for_load_state(self, state=None, timeout=None):
        """Waits until the page reaches the required load state."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait For Navigation', tags=['HTTP', 'Wait'])
    def wait_for_navigation(self, url, timeout=None, wait_until=None):
        """Waits until the page has navigated to the given ``url``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait For Request', tags=['HTTP', 'Wait'])
    def wait_for_request(self, matcher=None, timeout=None):
        """Waits for a request matching ``matcher`` to be made."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait For Response', tags=['HTTP', 'Wait'])
    def wait_for_response(self, matcher=None, timeout=None):
        """Waits for a response matching ``matcher`` and returns the response as a Robot Framework dictionary."""
        raise NotImplementedError('stub: executes only on the client')
