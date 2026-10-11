"""Signature-only stub for Browser 20.5.0 (generated from libdoc JSON)."""
from datetime import timedelta
from enum import Enum
from typing import Any
from robot.api.deco import keyword, library

AreaFields = Enum('AreaFields', [('top', '1'), ('left', '2'), ('bottom', '3'), ('right', '4'), ('ALL', '5')])
AriaSnapshotMode = Enum('AriaSnapshotMode', [('default', '1'), ('ai', '2')])
AriaSnapshotReturnType = Enum('AriaSnapshotReturnType', [('dict', '1'), ('yaml', '2'), ('parsed', '3')])
AssertionOperator = Enum('AssertionOperator', [('equal', '=='), ('equals', '=='), ('==', '=='), ('should be', '=='), ('inequal', '!='), ('!=', '!='), ('should not be', '!='), ('less than', '<'), ('<', '<'), ('greater than', '>'), ('>', '>'), ('<=', '<='), ('>=', '>='), ('contains', '*='), ('not contains', 'not contains'), ('*=', '*='), ('starts', '^='), ('^=', '^='), ('should start with', '^='), ('ends', '$='), ('should end with', '$='), ('$=', '$='), ('matches', '$'), ('validate', 'validate'), ('then', 'then'), ('evaluate', 'then')])
AutoClosingLevel = Enum('AutoClosingLevel', [('SUITE', '1'), ('TEST', '2'), ('MANUAL', '3'), ('KEEP', '4')])
BoundingBoxFields = Enum('BoundingBoxFields', [('width', '1'), ('height', '2'), ('x', '3'), ('y', '4'), ('ALL', '5')])
CLockAdvanceType = Enum('CLockAdvanceType', [('fast_forward', '1'), ('run_for', '2')])
ClockType = Enum('ClockType', [('fixed', '1'), ('system', '2'), ('install', '3')])
ColorScheme = Enum('ColorScheme', [('dark', '1'), ('light', '2'), ('no-preference', '3'), ('null', '4')])
ConditionInputs = Enum('ConditionInputs', [('attribute', 'get_attribute'), ('attribute_names', 'get_attribute_names'), ('bounding_box', 'get_bounding_box'), ('browser_catalog', 'get_browser_catalog'), ('checkbox_state', 'get_checkbox_state'), ('classes', 'get_classes'), ('client_size', 'get_client_size'), ('download_state', 'get_download_state'), ('element_count', 'get_element_count'), ('element_states', 'get_element_states'), ('page_source', 'get_page_source'), ('property', 'get_property'), ('scroll_position', 'get_scroll_position'), ('scroll_size', 'get_scroll_size'), ('select_options', 'get_select_options'), ('selected_options', 'get_selected_options'), ('style', 'get_style'), ('table_cell_index', 'get_table_cell_index'), ('table_row_index', 'get_table_row_index'), ('text', 'get_text'), ('title', 'get_title'), ('url', 'get_url'), ('viewport_size', 'get_viewport_size')])
CookieSameSite = Enum('CookieSameSite', [('Strict', 'Strict'), ('Lax', 'Lax'), ('None', 'None')])
CookieType = Enum('CookieType', [('dictionary', '1'), ('dict', '1'), ('string', '2'), ('str', '2')])
CoverageType = Enum('CoverageType', [('js', '1'), ('css', '2'), ('all', '3')])
DialogAction = Enum('DialogAction', [('accept', '1'), ('dismiss', '2')])
ElementRole = Enum('ElementRole', [('ALERT', '1'), ('ALERTDIALOG', '2'), ('APPLICATION', '3'), ('ARTICLE', '4'), ('BANNER', '5'), ('BLOCKQUOTE', '6'), ('BUTTON', '7'), ('CAPTION', '8'), ('CELL', '9'), ('CHECKBOX', '10'), ('CODE', '11'), ('COLUMNHEADER', '12'), ('COMBOBOX', '13'), ('COMPLEMENTARY', '14'), ('CONTENTINFO', '15'), ('DEFINITION', '16'), ('DELETION', '17'), ('DIALOG', '18'), ('DIRECTORY', '19'), ('DOCUMENT', '20'), ('EMPHASIS', '21'), ('FEED', '22'), ('FIGURE', '23'), ('FORM', '24'), ('GENERIC', '25'), ('GRID', '26'), ('GRIDCELL', '27'), ('GROUP', '28'), ('HEADING', '29'), ('IMG', '30'), ('INSERTION', '31'), ('LINK', '32'), ('LIST', '33'), ('LISTBOX', '34'), ('LISTITEM', '35'), ('LOG', '36'), ('MAIN', '37'), ('MARQUEE', '38'), ('MATH', '39'), ('METER', '40'), ('MENU', '41'), ('MENUBAR', '42'), ('MENUITEM', '43'), ('MENUITEMCHECKBOX', '44'), ('MENUITEMRADIO', '45'), ('NAVIGATION', '46'), ('NONE', '47'), ('NOTE', '48'), ('OPTION', '49'), ('PARAGRAPH', '50'), ('PRESENTATION', '51'), ('PROGRESSBAR', '52'), ('RADIO', '53'), ('RADIOGROUP', '54'), ('REGION', '55'), ('ROW', '56'), ('ROWGROUP', '57'), ('ROWHEADER', '58'), ('SCROLLBAR', '59'), ('SEARCH', '60'), ('SEARCHBOX', '61'), ('SEPARATOR', '62'), ('SLIDER', '63'), ('SPINBUTTON', '64'), ('STATUS', '65'), ('STRONG', '66'), ('SUBSCRIPT', '67'), ('SUPERSCRIPT', '68'), ('SWITCH', '69'), ('TAB', '70'), ('TABLE', '71'), ('TABLIST', '72'), ('TABPANEL', '73'), ('TERM', '74'), ('TEXTBOX', '75'), ('TIME', '76'), ('TIMER', '77'), ('TOOLBAR', '78'), ('TOOLTIP', '79'), ('TREE', '80'), ('TREEGRID', '81'), ('TREEITEM', '82')])
ElementState = Enum('ElementState', [('attached', '1'), ('detached', '2'), ('visible', '4'), ('hidden', '8'), ('enabled', '16'), ('disabled', '32'), ('editable', '64'), ('readonly', '128'), ('selected', '256'), ('deselected', '512'), ('focused', '1024'), ('defocused', '2048'), ('checked', '4096'), ('unchecked', '8192'), ('stable', '16384')])
ForcedColors = Enum('ForcedColors', [('active', '1'), ('none', '2'), ('null', '3')])
FormatingRules = Enum('FormatingRules', [('normalize spaces', '1'), ('strip', '2'), ('apply to expected', '3'), ('case insensitive', '4')])
FormatterKeywords = Enum('FormatterKeywords', [('Get Attribute', '1'), ('Get Browser Catalog', '2'), ('Get Page Source', '3'), ('Get Property', '4'), ('Get Select Options', '5'), ('Get Style', '6'), ('Get Text', '7'), ('Get Title', '8'), ('Get Url', '9'), ('LocalStorage Get Item', '10'), ('SessionStorage Get Item', '11')])
HighlightMode = Enum('HighlightMode', [('border', '1'), ('playwright', '2'), ('both', '3')])
KeyAction = Enum('KeyAction', [('down', '1'), ('up', '2'), ('press', '3')])
KeyboardInputAction = Enum('KeyboardInputAction', [('insertText', '1'), ('type', '2')])
KeyboardModifier = Enum('KeyboardModifier', [('Alt', '1'), ('Control', '2'), ('ControlOrMeta', '3'), ('Meta', '4'), ('Shift', '5')])
Media = Enum('Media', [('screen', 'screen'), ('print', 'print'), ('null', 'null')])
MouseButton = Enum('MouseButton', [('left', '1'), ('middle', '2'), ('right', '3')])
MouseButtonAction = Enum('MouseButtonAction', [('click', '1'), ('down', '2'), ('up', '3')])
NotSet = Enum('NotSet', [('not_set', 'not_set')])
PageLoadStates = Enum('PageLoadStates', [('load', '1'), ('domcontentloaded', '2'), ('networkidle', '3'), ('commit', '4')])
PdfFormat = Enum('PdfFormat', [('Letter', 'Letter'), ('Legal', 'Legal'), ('Tabloid', 'Tabloid'), ('Ledger', 'Ledger'), ('A0', 'A0'), ('A1', 'A1'), ('A2', 'A2'), ('A3', 'A3'), ('A4', 'A4'), ('A5', 'A5'), ('A6', 'A6')])
Permission = Enum('Permission', [('accelerometer', 'accelerometer'), ('accessibility-events', 'accessibility-events'), ('accessibility_events', 'accessibility-events'), ('ambient-light-sensor', 'ambient-light-sensor'), ('ambient_light_sensor', 'ambient-light-sensor'), ('background-sync', 'background-sync'), ('background_sync', 'background-sync'), ('camera', 'camera'), ('clipboard-read', 'clipboard-read'), ('clipboard_read', 'clipboard-read'), ('clipboard-write', 'clipboard-write'), ('clipboard_write', 'clipboard-write'), ('geolocation', 'geolocation'), ('gyroscope', 'gyroscope'), ('local-network-access', 'local-network-access'), ('local_network_access', 'local-network-access'), ('magnetometer', 'magnetometer'), ('midi', 'midi'), ('midi-sysex', 'midi-sysex'), ('midi_sysex', 'midi-sysex'), ('microphone', 'microphone'), ('notifications', 'notifications'), ('payment-handler', 'payment-handler'), ('payment_handler', 'payment-handler')])
PlaywrightLogTypes = Enum('PlaywrightLogTypes', [('disabled', '1'), ('library', '2'), ('playwright', '3'), ('false', '2'), ('true', '3')])
ReducedMotion = Enum('ReducedMotion', [('reduce', 'reduce'), ('no_preference', 'no-preference'), ('null', 'null')])
ReduceMotion = Enum('ReduceMotion', [('reduce', '1'), ('no_preference', '2')])
ReloadPages = Enum('ReloadPages', [('affected', '1'), ('none', '2'), ('all', '3')])
RequestMethod = Enum('RequestMethod', [('HEAD', '1'), ('DELETE', '2'), ('GET', '3'), ('PATCH', '4'), ('POST', '5'), ('PUT', '6')])
Scale = Enum('Scale', [('css', '1'), ('device', '2')])
Scope = Enum('Scope', [('Global', '1'), ('Suite', '2'), ('Test', '3'), ('Task', '3')])
ScreenshotFileTypes = Enum('ScreenshotFileTypes', [('png', '1'), ('jpeg', '2')])
ScreenshotReturnType = Enum('ScreenshotReturnType', [('path', '1'), ('path_string', '2'), ('bytes', '3'), ('base64', '4')])
ScrollBehavior = Enum('ScrollBehavior', [('auto', '1'), ('smooth', '2')])
SelectAttribute = Enum('SelectAttribute', [('value', '1'), ('label', '2'), ('text', '2'), ('index', '3')])
SelectionStrategy = Enum('SelectionStrategy', [('AltText', 'AltText'), ('Label', 'Label'), ('Placeholder', 'Placeholder'), ('TestID', 'TestId'), ('Text', 'Text'), ('Title', 'Title')])
SelectionType = Enum('SelectionType', [('CURRENT', 'CURRENT'), ('ACTIVE', 'CURRENT'), ('ALL', 'ALL'), ('ANY', 'ALL')])
ServiceWorkersPermissions = Enum('ServiceWorkersPermissions', [('allow', '1'), ('block', '2')])
SizeFields = Enum('SizeFields', [('width', '1'), ('height', '2'), ('ALL', '3')])
SupportedBrowsers = Enum('SupportedBrowsers', [('chromium', '1'), ('firefox', '2'), ('webkit', '3')])
TextType = Enum('TextType', [('allInnerTexts', '1'), ('allTextContents', '2'), ('innerText', '3'), ('inputValue', '4'), ('innerHTML', '5')])
TracingGroupMode = Enum('TracingGroupMode', [('Full', '1'), ('Browser', '2'), ('Playwright', '3')])

@library(scope='GLOBAL', version='20.5.0', auto_keywords=False)
class Browser:
    def __init__(self, *_, auto_closing_level: AutoClosingLevel = None, auto_delete_passed_tracing: bool = None, enable_playwright_debug: PlaywrightLogTypes | bool = None, enable_presenter_mode=None, external_browser_executable: dict | None = None, highlight_on_failure: bool = None, jsextension: list | str | None = None, language: str | None = None, playwright_process_host: str | None = None, playwright_process_port: int | None = None, plugins: list | str | None = None, retry_assertions_for: timedelta = None, run_on_failure: str = None, selector_prefix: str | None = None, show_keyword_call_banner: bool | None = None, strict: bool = None, timeout: timedelta = None, tracing_group_mode: TracingGroupMode = None):
        pass

    @keyword('Add Cookie', tags=['BrowserControl', 'Setter'])
    def add_cookie(self, name: str, value: str, url: str | None = None, domain: str | None = None, path: str | None = None, expires=None, httpOnly: bool | None = None, secure: bool | None = None, sameSite: CookieSameSite | None = None):
        """Adds a cookie to the currently active browser context."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Add Locator Handler Click', tags=['PageContent', 'Setter'])
    def add_locator_handler_click(self, selector: str, click_selector: str, *, noWaitAfter: bool = None, times: int | None = None, click_clickCount: int = None, click_delay: int = None, click_force: bool = None):
        """Add a handler function which will activate when ``selector`` is visible and click."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Add Locator Handler Custom', tags=['PageContent', 'Setter'])
    def add_locator_handler_custom(self, selector: str, handler_spec: list, noWaitAfter: bool = None, times: int | None = None):
        """Add a handler function which will activate when ``selector`` is visible and performs handler specification."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Add Style Tag', tags=['PageContent', 'Setter'])
    def add_style_tag(self, content: str):
        """Adds a <style type="text/css"> tag with the content."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Advance Clock', tags=['Clock', 'Setter'])
    def advance_clock(self, time: timedelta, advance_type: CLockAdvanceType = None):
        """Advances the clock by a specified amount of time."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Cancel Download', tags=['BrowserControl', 'Setter'])
    def cancel_download(self, download):
        """Cancels an active download."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Check Checkbox', tags=['PageContent', 'Setter'])
    def check_checkbox(self, selector: str, force: bool = None):
        """Checks the checkbox or selects radio button found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Clear Permissions', tags=['BrowserControl', 'Setter'])
    def clear_permissions(self):
        """Clears all permissions from the current context."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Clear Text', tags=['PageContent', 'Setter'])
    def clear_text(self, selector: str):
        """Clears the text field found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Click', tags=['PageContent', 'Setter'])
    def click(self, selector: str, button: MouseButton = None):
        """Simulates mouse click on the element found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Click With Options', tags=['PageContent', 'Setter'])
    def click_with_options(self, selector: str, button: MouseButton = None, *modifiers, clickCount: int = None, delay: timedelta | None = None, force: bool = None, noWaitAfter: bool = None, position_x: float | None = None, position_y: float | None = None, trial: bool = None):
        """Simulates mouse click on the element found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Close Browser', tags=['BrowserControl', 'Setter'])
    def close_browser(self, browser: SelectionType | str = None):
        """Closes the current browser."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Close Browser Server', tags=['BrowserControl', 'Setter'])
    def close_browser_server(self, wsEndpoint: str):
        """Close a playwright Browser Server identified by its websocket endpoint (wsEndpoint)."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Close Context', tags=['BrowserControl', 'Setter'])
    def close_context(self, context: SelectionType | str = None, browser: SelectionType | str = None, *, save_trace: bool = None):
        """Closes a Context."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Close Page', tags=['BrowserControl', 'Setter'])
    def close_page(self, page=None, context: SelectionType | str = None, browser: SelectionType | str = None, runBeforeUnload: bool = None):
        """Closes the ``page`` in ``context`` in ``browser``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Connect To Browser', tags=['BrowserControl', 'Setter'])
    def connect_to_browser(self, wsEndpoint: str, browser: SupportedBrowsers = None, use_cdp: bool = None, *, timeout: timedelta = None):
        """Connect to a Playwright browser server via playwright websocket or Chrome DevTools Protocol."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Crawl Site', tags=['Crawling'])
    def crawl_site(self, url: str | None = None, page_crawl_keyword=None, max_number_of_page_to_crawl: int = None, max_depth_to_crawl: int = None):
        """Web crawler is a tool to go through all the pages on a specific URL domain. This happens by finding all links going to the same site and opening those. Links pointing to another scheme or host are ignored, as are download links."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Create Credential', tags=['Credential', 'Setter'])
    def create_credential(self, rpId: str, id_: str | None = None, privateKey=None, publicKey=None, userHandle: str | None = None):
        """Creates a credential with the given parameters."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Delete All Cookies', tags=['BrowserControl', 'Setter'])
    def delete_all_cookies(self):
        """Deletes all cookies from the currently active browser context."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Delete Credential', tags=['Credential', 'Setter'])
    def delete_credential(self, id_: str):
        """Deletes the credential with the given id."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Deselect Options', tags=['PageContent', 'Setter'])
    def deselect_options(self, selector: str):
        """Deselects all options from select element found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Download', tags=['Page Content'])
    def download(self, url: str, saveAs: str = None, wait_for_finished: bool = None, download_timeout: timedelta | None = None):
        """Download given url content."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Drag And Drop', tags=['PageContent', 'Setter'])
    def drag_and_drop(self, selector_from: str, selector_to: str, steps: int = None):
        """Executes a Drag&Drop operation from the element selected by ``selector_from`` to the element selected by ``selector_to``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Drag And Drop By Coordinates', tags=['PageContent', 'Setter'])
    def drag_and_drop_by_coordinates(self, from_x: float, from_y: float, to_x: float, to_y: float, steps: int = None):
        """Executes a Drag&Drop operation from a coordinate to another coordinate."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Drag And Drop Relative To', tags=['PageContent', 'Setter'])
    def drag_and_drop_relative_to(self, selector_from: str, x: float = None, y: float = None, steps: int = None):
        """Executes a Drag&Drop operation from the element selected by ``selector_from`` to coordinates relative to the center of that element."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Eat All Cookies', tags=[])
    def eat_all_cookies(self):
        """Eat all cookies for all easter."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Emulate Media', tags=['PageContent', 'Setter'])
    def emulate_media(self, colorScheme: ColorScheme | None = None, forcedColors: ForcedColors | NotSet = None, media: Media | None = None, reducedMotion: ReducedMotion | None = None):
        """Changes the CSS media type."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Evaluate JavaScript', tags=['Getter', 'PageContent', 'Setter'])
    def evaluate_javascript(self, selector: str | None = None, *function, arg: Any = None, all_elements: bool = None):
        """Executes the given JavaScript in the browser page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Fill Secret', tags=['PageContent', 'Setter'])
    def fill_secret(self, selector: str, secret, force: bool = None):
        """Fills the given ``secret`` into the text field found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Fill Text', tags=['PageContent', 'Setter'])
    def fill_text(self, selector: str, txt: str, force: bool = None):
        """Clears and fills the given ``txt`` into the text field found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Focus', tags=['PageContent', 'Setter'])
    def focus(self, selector: str):
        """Moves focus on to the element found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Aria Snapshot', tags=['Assertion', 'Getter', 'PageContent'])
    def get_aria_snapshot(self, selector: str, return_type: AriaSnapshotReturnType = None, assertion_operator: AssertionOperator | None = None, assertion_expected: Any | None = None, message: str | None = None, *, mode: AriaSnapshotMode = None, depth: int | None = None, boxes: bool = None):
        """Returns the aria snapshot of the element found by ``selector``. See `AriaSnapshotReturnType` for more details and examples."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Attribute', tags=['Assertion', 'Getter', 'PageContent'])
    def get_attribute(self, selector: str, attribute: str, assertion_operator: AssertionOperator | None = None, assertion_expected: Any | None = None, message: str | None = None):
        """Returns the HTML ``attribute`` of the element found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Attribute Names', tags=['Assertion', 'Getter', 'PageContent'])
    def get_attribute_names(self, selector: str, assertion_operator: AssertionOperator | None = None, *assertion_expected, message: str | None = None):
        """Returns all HTML attribute names of an element as a list."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get BoundingBox', tags=['Assertion', 'Getter', 'PageContent'])
    def get_boundingbox(self, selector: str, key: BoundingBoxFields = None, assertion_operator: AssertionOperator | None = None, assertion_expected: Any | None = None, message: str | None = None, *, allow_hidden: bool = None):
        """Gets elements size and location as an object ``{x: float, y: float, width: float, height: float}``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Browser Catalog', tags=['Assertion', 'BrowserControl', 'Getter'])
    def get_browser_catalog(self, assertion_operator: AssertionOperator | None = None, assertion_expected: Any | None = None, message: str | None = None):
        """Returns all browsers, open contexts in them and open pages in these contexts."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Browser Ids', tags=['Assertion', 'BrowserControl', 'Getter'])
    def get_browser_ids(self, browser: SelectionType = None, assertion_operator: AssertionOperator | None = None, *assertion_expected, message: str | None = None):
        """Returns a list of ids from open browsers. See `Browser, Context and Page` for more information about Browser and related concepts."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Checkbox State', tags=['Assertion', 'Getter', 'PageContent'])
    def get_checkbox_state(self, selector: str, assertion_operator: AssertionOperator | None = None, assertion_expected: bool | str = None, message: str | None = None):
        """Returns the state of the checkbox found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Classes', tags=['Assertion', 'Getter', 'PageContent'])
    def get_classes(self, selector: str, assertion_operator: AssertionOperator | None = None, *assertion_expected, message: str | None = None):
        """Returns all classes of an element as a list."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Client Size', tags=['Assertion', 'Getter', 'PageContent'])
    def get_client_size(self, selector: str | None = None, key: SizeFields = None, assertion_operator: AssertionOperator | None = None, assertion_expected: Any | None = None, message: str | None = None):
        """Gets elements or pages client size (``clientHeight``, ``clientWidth``) as object {width: float, height: float}."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Console Log', tags=['Assertion', 'BrowserControl', 'Getter'])
    def get_console_log(self, assertion_operator: AssertionOperator | None = None, assertion_expected: Any | None = None, message: str | None = None, *, full: bool = None, last: int | timedelta | None = None):
        """Returns the console log of the active page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Context Ids', tags=['Assertion', 'BrowserControl', 'Getter'])
    def get_context_ids(self, context: SelectionType = None, browser: SelectionType | str = None, assertion_operator: AssertionOperator | None = None, *assertion_expected, message: str | None = None):
        """Returns a list of context ids based on the browser selection. See `Browser, Context and Page` for more information about Context and related concepts."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Cookie', tags=['BrowserControl', 'Getter'])
    def get_cookie(self, cookie: str, return_type: CookieType = None):
        """Returns information about the cookie named ``cookie`` as a Robot Framework dot dictionary or a string."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Cookies', tags=['Getter', 'PageContent'])
    def get_cookies(self, return_type: CookieType = None):
        """Returns cookies from the currently active browser context."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Credential', tags=['Credential', 'Getter'])
    def get_credential(self, id_: str | None = None, rpId: str | None = None):
        """Returns the credential matching the given id and/or rpId."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Device', tags=['BrowserControl', 'Getter'])
    def get_device(self, name: str):
        """Returns a single device descriptor whose name matches ``name`` exactly."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Devices', tags=['BrowserControl', 'Getter'])
    def get_devices(self):
        """Returns a dictionary of all Playwright device descriptors."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Download State', tags=['Assertion', 'Getter', 'PageContent'])
    def get_download_state(self, download, assertion_operator: AssertionOperator | None = None, assertion_expected: Any | None = None, message: str | None = None):
        """Gets the state of a download."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Element', tags=['Getter', 'PageContent'])
    def get_element(self, selector: str):
        """Returns a selector string that points to the element found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Element By', tags=['Getter', 'PageContent'])
    def get_element_by(self, selection_strategy: SelectionStrategy, text, exact: bool = None, all_elements: bool = None):
        """Allows locating elements by their features."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Element By Role', tags=['Getter', 'PageContent'])
    def get_element_by_role(self, role: ElementRole, *, all_elements: bool = None, checked: bool | None = None, disabled: bool | None = None, exact: bool | None = None, expanded: bool | None = None, include_hidden: bool | None = None, level: int | None = None, name=None, pressed: bool | None = None, selected: bool | None = None):
        """Returns a selector string for the element matched by ``role``, or a list of selector strings if ``all_elements`` is set to ``True``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Element Count', tags=['Assertion', 'Getter', 'PageContent'])
    def get_element_count(self, selector: str, assertion_operator: AssertionOperator | None = None, assertion_expected: int | str = None, message: str | None = None):
        """Returns the count of elements found with ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Element States', tags=['Assertion', 'Getter', 'PageContent'])
    def get_element_states(self, selector: str, assertion_operator: AssertionOperator | None = None, *assertion_expected, message: str | None = None, return_names=None):
        """Get the active states from the element found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Elements', tags=['Getter', 'PageContent'])
    def get_elements(self, selector: str):
        """Returns a list of selector strings, one for each element matched by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Page Errors', tags=['Assertion', 'BrowserControl', 'Getter'])
    def get_page_errors(self, assertion_operator: AssertionOperator | None = None, assertion_expected: Any | None = None, message: str | None = None, *, full: bool = None, last: int | timedelta | None = None):
        """Returns the page errors of the active page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Page Ids', tags=['Assertion', 'BrowserControl', 'Getter'])
    def get_page_ids(self, page: SelectionType = None, context: SelectionType | str = None, browser: SelectionType | str = None, assertion_operator: AssertionOperator | None = None, *assertion_expected, message: str | None = None):
        """Returns a list of page ids based on the context and browser selection. See `Browser, Context and Page` for more information about Page and related concepts."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Page Source', tags=['Assertion', 'Getter', 'PageContent'])
    def get_page_source(self, assertion_operator: AssertionOperator | None = None, assertion_expected: Any | None = None, message: str | None = None):
        """Gets the page's HTML source as a string."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Property', tags=['Assertion', 'Getter', 'PageContent'])
    def get_property(self, selector: str, property: str, assertion_operator: AssertionOperator | None = None, assertion_expected: Any | None = None, message: str | None = None):
        """Returns the ``property`` of the element found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Scroll Position', tags=['Assertion', 'Getter', 'PageContent'])
    def get_scroll_position(self, selector: str | None = None, key: AreaFields = None, assertion_operator: AssertionOperator | None = None, assertion_expected: Any | None = None, message: str | None = None):
        """Gets elements or pages current scroll position as object ``{top: float, left: float, bottom: float, right: float}``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Scroll Size', tags=['Assertion', 'Getter', 'PageContent'])
    def get_scroll_size(self, selector: str | None = None, key: SizeFields = None, assertion_operator: AssertionOperator | None = None, assertion_expected: Any | None = None, message: str | None = None):
        """Gets elements or pages scrollable size as object ``{width: float, height: float}``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Select Options', tags=['Assertion', 'Getter', 'PageContent'])
    def get_select_options(self, selector: str, assertion_operator: AssertionOperator | None = None, assertion_expected: Any | None = None, message: str | None = None):
        """Returns attributes of options of a ``select`` element as a list of dictionaries."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Selected Options', tags=['Assertion', 'Getter', 'PageContent'])
    def get_selected_options(self, selector: str, option_attribute: SelectAttribute = None, assertion_operator: AssertionOperator | None = None, *assertion_expected, message: str | None = None):
        """Returns the specified attribute of selected options of the ``select`` element."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Style', tags=['Assertion', 'Getter', 'PageContent'])
    def get_style(self, selector: str, key: str | None = None, assertion_operator: AssertionOperator | None = None, assertion_expected: Any | None = None, message: str | None = None, pseudo_element: str | None = None):
        """Gets the computed style properties of the element selected by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Table Cell Element', tags=['Getter', 'PageContent'])
    def get_table_cell_element(self, table: str, column: str, row: str):
        """Returns a selector string for the cell at the same column and row index as the selected elements."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Table Cell Index', tags=['Assertion', 'Getter', 'PageContent'])
    def get_table_cell_index(self, selector: str, assertion_operator: AssertionOperator | None = None, assertion_expected: int | str = None, message: str | None = None):
        """Returns the index (0 based) of a table cell within its row."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Table Row Index', tags=['Assertion', 'Getter', 'PageContent'])
    def get_table_row_index(self, selector: str, assertion_operator: AssertionOperator | None = None, assertion_expected: int | str = None, message: str | None = None):
        """Returns the index (0 based) of a table row."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Text', tags=['Assertion', 'Getter', 'PageContent'])
    def get_text(self, selector: str, assertion_operator: AssertionOperator | None = None, assertion_expected: Any | None = None, message: str | None = None, *, text_type: TextType | None = None):
        """Returns text attribute of the element found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Title', tags=['Assertion', 'Getter', 'PageContent'])
    def get_title(self, assertion_operator: AssertionOperator | None = None, assertion_expected: Any | None = None, message: str | None = None):
        """Returns the title of the current page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Url', tags=['Assertion', 'Getter', 'PageContent'])
    def get_url(self, assertion_operator: AssertionOperator | None = None, assertion_expected: Any | None = None, message: str | None = None):
        """Returns the current URL."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Viewport Size', tags=['Assertion', 'BrowserControl', 'Getter'])
    def get_viewport_size(self, key: SizeFields = None, assertion_operator: AssertionOperator | None = None, assertion_expected: Any | None = None, message=None):
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
    def go_to(self, url: str, timeout: timedelta | None = None, wait_until: PageLoadStates = None):
        """Navigates to the given ``url``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Grant Permissions', tags=['BrowserControl', 'Setter'])
    def grant_permissions(self, *permissions, origin: str | None = None):
        """Grants permissions to the current context."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Handle Future Dialogs', tags=['PageContent'])
    def handle_future_dialogs(self, action: DialogAction, prompt_input: str = None):
        """Handle next dialog on page with ``action``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Highlight Elements', tags=['PageContent', 'Setter'])
    def highlight_elements(self, selector: str, duration: timedelta = None, width: str = None, style: str = None, color: str = None, *, mode: HighlightMode = None):
        """Adds a highlight to elements matched by the ``selector``. Provides a style adjustment."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Hover', tags=['PageContent', 'Setter'])
    def hover(self, selector: str, position_x: float | None = None, position_y: float | None = None, force: bool = None, *modifiers):
        """Moves the virtual mouse and scrolls to the element found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Http', tags=['HTTP'])
    def http(self, url: str, method: RequestMethod = None, body: str | None = None, headers: dict | None = None):
        """Performs an HTTP request in the current browser context"""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Install Credential', tags=['Credential', 'Setter'])
    def install_credential(self):
        """Installs the virtual WebAuthn authenticator into the context."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Keyboard Input', tags=['PageContent', 'Setter'])
    def keyboard_input(self, action: KeyboardInputAction, input: str, delay: int | timedelta = None):
        """Input text into page with virtual keyboard."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Keyboard Key', tags=['PageContent', 'Setter'])
    def keyboard_key(self, action: KeyAction, key: str, *, delay: timedelta = None):
        """Press a keyboard key on the virtual keyboard or set a key up or down."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Launch Browser Server', tags=['BrowserControl', 'Setter'])
    def launch_browser_server(self, browser: SupportedBrowsers = None, headless: bool = None, *, args: list | None = None, channel: str | None = None, chromiumSandbox: bool = None, devtools: bool = None, downloadsPath: str | None = None, env: dict | None = None, executablePath: str | None = None, firefoxUserPrefs: dict | None = None, handleSIGHUP: bool = None, handleSIGINT: bool = None, handleSIGTERM: bool = None, ignoreDefaultArgs: list | bool | None = None, port: int | None = None, proxy=None, reuse_existing: bool = None, slowMo: timedelta = None, timeout: timedelta = None, wsPath: str | None = None):
        """Launches a new playwright Browser server with specified options."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('LocalStorage Clear', tags=['PageContent', 'Setter'])
    def localstorage_clear(self, frame_selector: str | None = None):
        """Remove all saved data from the local storage."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('LocalStorage Get Item', tags=['Assertion', 'Getter', 'PageContent'])
    def localstorage_get_item(self, key: str, assertion_operator: AssertionOperator | None = None, assertion_expected: Any | None = None, message: str | None = None, frame_selector: str | None = None):
        """Get saved data from the local storage."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('LocalStorage Remove Item', tags=['PageContent', 'Setter'])
    def localstorage_remove_item(self, key: str, frame_selector: str | None = None):
        """Remove saved data with key from the local storage."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('LocalStorage Set Item', tags=['PageContent', 'Setter'])
    def localstorage_set_item(self, key: str, value: str, frame_selector: str | None = None):
        """Save data to the local storage."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Merge Coverage Reports', tags=['Coverage', 'Setter'])
    def merge_coverage_reports(self, input_folder, output_folder, config_file=None, name: str | None = None, reports: list | None = None):
        """Combines multiple raw coverage reports into a single report."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Mouse Button', tags=['PageContent', 'Setter'])
    def mouse_button(self, action: MouseButtonAction, x: float | None = None, y: float | None = None, button: MouseButton = None, clickCount: int = None, delay: int | timedelta = None):
        """Clicks, presses or releases a mouse button."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Mouse Move', tags=['PageContent', 'Setter'])
    def mouse_move(self, x: float, y: float, steps: int = None):
        """Moves the virtual mouse to the given coordinates, instead of to an element found by a selector."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Mouse Move Relative To', tags=['PageContent', 'Setter'])
    def mouse_move_relative_to(self, selector: str, x: float = None, y: float = None, steps: int = None):
        """Moves the mouse cursor relative to the selected element."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Mouse Wheel', tags=['PageContent', 'Setter'])
    def mouse_wheel(self, deltaX: int, deltaY: int):
        """Simulates the user rotation of a mouse wheel."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('New Browser', tags=['BrowserControl', 'Setter'])
    def new_browser(self, browser: SupportedBrowsers = None, headless: bool = None, *, args: list | None = None, channel: str | None = None, chromiumSandbox: bool = None, devtools: bool = None, downloadsPath: str | None = None, env: dict | None = None, executablePath: str | None = None, firefoxUserPrefs: dict | None = None, handleSIGHUP: bool = None, handleSIGINT: bool = None, handleSIGTERM: bool = None, ignoreDefaultArgs: list | bool | None = None, proxy=None, reuse_existing: bool = None, slowMo: timedelta = None, timeout: timedelta = None):
        """Create a new playwright Browser with specified options."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('New Context', tags=['BrowserControl', 'Setter'])
    def new_context(self, *, acceptDownloads: bool = None, baseURL: str | None = None, bypassCSP: bool = None, clientCertificates: list | None = None, colorScheme: ColorScheme | None = None, defaultBrowserType: SupportedBrowsers | None = None, deviceScaleFactor: float | None = None, extraHTTPHeaders: dict | None = None, forcedColors: ForcedColors = None, geolocation=None, hasTouch: bool | None = None, httpCredentials=None, ignoreHTTPSErrors: bool = None, isMobile: bool | None = None, javaScriptEnabled: bool = None, locale: str | None = None, offline: bool = None, permissions: list | None = None, proxy=None, recordHar=None, recordVideo=None, reducedMotion: ReduceMotion = None, screen: dict | None = None, serviceWorkers: ServiceWorkersPermissions | None = None, storageState=None, timezoneId: str | None = None, tracing=None, userAgent: str | None = None, viewport=None):
        """Create a new BrowserContext with specified options."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('New Page', tags=['BrowserControl', 'Setter'])
    def new_page(self, url: str | None = None, wait_until: PageLoadStates = None):
        """Open a new Page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('New Persistent Context', tags=[])
    def new_persistent_context(self, userDataDir: str = None, browser: SupportedBrowsers = None, headless: bool = None, *, acceptDownloads: bool = None, args: list | None = None, baseURL: str | None = None, bypassCSP: bool = None, channel: str | None = None, chromiumSandbox: bool = None, colorScheme: ColorScheme | None = None, defaultBrowserType: SupportedBrowsers | None = None, deviceScaleFactor: float | None = None, devtools: bool = None, downloadsPath: str | None = None, env: dict | None = None, executablePath: str | None = None, extraHTTPHeaders: dict | None = None, forcedColors: ForcedColors = None, geolocation=None, handleSIGHUP: bool = None, handleSIGINT: bool = None, handleSIGTERM: bool = None, hasTouch: bool | None = None, httpCredentials=None, ignoreDefaultArgs: list | bool | None = None, ignoreHTTPSErrors: bool = None, isMobile: bool | None = None, javaScriptEnabled: bool = None, locale: str | None = None, offline: bool = None, permissions: list | None = None, proxy=None, recordHar=None, recordVideo=None, reducedMotion: ReduceMotion = None, screen: dict | None = None, serviceWorkers: ServiceWorkersPermissions | None = None, slowMo: timedelta = None, timeout: timedelta = None, timezoneId: str | None = None, tracing=None, url: str | None = None, userAgent: str | None = None, viewport=None):
        """Opens a new persistent context."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Open Browser', tags=['BrowserControl', 'Setter'])
    def open_browser(self, url: str | None = None, browser: SupportedBrowsers = None, headless: bool = None, pause_on_failure: bool = None, bypassCSP=None):
        """Opens a new browser instance. Use this keyword for quick experiments or debugging sessions."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Pause At', tags=['Clock', 'Setter'])
    def pause_at(self, time):
        """Advances the clock by jumping forward in time and pauses it."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Press Keys', tags=['PageContent', 'Setter'])
    def press_keys(self, selector: str, *keys, press_duration: timedelta = None, key_delay: timedelta = None):
        """Types the given key combination into element found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Promise To', tags=['Wait'])
    def promise_to(self, kw: str, *args):
        """Wrap a Browser library keyword and make it a promise."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Promise To Upload File', tags=['PageContent', 'Setter'])
    def promise_to_upload_file(self, path):
        """Returns a promise that resolves when the file from ``path`` has been uploaded."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Promise To Wait For Download', tags=['BrowserControl', 'Wait'])
    def promise_to_wait_for_download(self, saveAs: str = None, wait_for_finished: bool = None, download_timeout: timedelta | None = None):
        """Returns a promise that waits for the next download event on the page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Record Selector', tags=['PageContent'])
    def record_selector(self, label: str | None = None):
        """Record the selector that is under mouse."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Register Keyword To Run On Failure', tags=['Config'])
    def register_keyword_to_run_on_failure(self, keyword: str | None, *args, scope: Scope = None):
        """Sets the keyword to execute, when a Browser keyword fails."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Reload', tags=['BrowserControl', 'Setter'])
    def reload(self, timeout: timedelta | None = None, waitUntil: PageLoadStates = None):
        """Reloads current active page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Remove Locator Handler', tags=['PageContent', 'Setter'])
    def remove_locator_handler(self, locator: str):
        """Remove the locator handler indicated by ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Resume Clock', tags=['Clock', 'Setter'])
    def resume_clock(self):
        """Resumes the clock."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Save Page As Pdf', tags=['Getter', 'PageContent'])
    def save_page_as_pdf(self, path, *, displayHeaderFooter: bool = None, footerTemplate: str = None, format: PdfFormat = None, headerTemplate: str = None, height: str = None, landscape: bool = None, margin=None, outline: bool = None, pageRanges: str = None, preferCSSPageSize: bool = None, printBackground: bool = None, scale: float = None, tagged: bool = None, width: str = None):
        """Saves page as PDF."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Save Storage State', tags=['BrowserControl', 'Getter'])
    def save_storage_state(self, path=None, *, indexedDB: bool = None, credentials: bool = None):
        """Saves the current active context storage state to a file."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Scroll By', tags=['PageContent', 'Setter'])
    def scroll_by(self, selector: str | None = None, vertical: str = None, horizontal: str = None, behavior: ScrollBehavior = None):
        """Scrolls an element or the page relative from current position by the given values."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Scroll To', tags=['PageContent', 'Setter'])
    def scroll_to(self, selector: str | None = None, vertical: str = None, horizontal: str = None, behavior: ScrollBehavior = None):
        """Scrolls an element or the page to an absolute position based on given coordinates."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Scroll To Element', tags=['PageContent', 'Setter'])
    def scroll_to_element(self, selector: str):
        """This method waits for actionability checks, then tries to scroll element into view, unless it is completely visible."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Select Options By', tags=['PageContent', 'Setter'])
    def select_options_by(self, selector: str, attribute: SelectAttribute, *values):
        """Selects options from select element found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('SessionStorage Clear', tags=['PageContent', 'Setter'])
    def sessionstorage_clear(self, frame_selector: str | None = None):
        """Remove all saved data from the session storage."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('SessionStorage Get Item', tags=['Assertion', 'Getter', 'PageContent'])
    def sessionstorage_get_item(self, key: str, assertion_operator: AssertionOperator | None = None, assertion_expected: Any | None = None, message: str | None = None, frame_selector: str | None = None):
        """Get saved data from the session storage."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('SessionStorage Remove Item', tags=['PageContent', 'Setter'])
    def sessionstorage_remove_item(self, key: str, frame_selector: str | None = None):
        """Remove saved data with key from the session storage."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('SessionStorage Set Item', tags=['PageContent', 'Setter'])
    def sessionstorage_set_item(self, key: str, value: str, frame_selector: str | None = None):
        """Save data to session storage."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Assertion Formatters', tags=['Config'])
    def set_assertion_formatters(self, formatters, scope: Scope = None):
        """Set keywords formatters for assertions."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Browser Timeout', tags=['Config', 'Setter'])
    def set_browser_timeout(self, timeout: timedelta, scope: Scope = None):
        """Sets the timeout used by most input and getter keywords."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Default Run Before Unload', tags=['BrowserControl', 'Setter'])
    def set_default_run_before_unload(self, runBeforeUnload: bool):
        """Set default runBeforeUnload value when `Close Page` is called indirectly."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Geolocation', tags=['BrowserControl', 'Setter'])
    def set_geolocation(self, latitude: float, longitude: float, accuracy: float | None = None):
        """Updates the current context's geolocation."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Highlight On Failure', tags=['Config', 'Setter'])
    def set_highlight_on_failure(self, highlight: bool = None, scope: Scope = None):
        """Controls if the element is highlighted on failure."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Offline', tags=['BrowserControl', 'Setter'])
    def set_offline(self, offline: bool = None):
        """Toggles the current context's offline emulation."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Presenter Mode', tags=['BrowserControl', 'Setter'])
    def set_presenter_mode(self, mode):
        """Sets presenter mode for element highlighting during test execution."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Retry Assertions For', tags=['Config', 'Setter'])
    def set_retry_assertions_for(self, timeout: timedelta, scope: Scope = None):
        """Sets the timeout used in retrying assertions when they fail."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Selector Prefix', tags=['Config', 'Setter'])
    def set_selector_prefix(self, prefix: str | None, scope: Scope = None):
        """Sets the prefix for all selectors in the given scope."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Storage State', tags=['BrowserControl', 'Setter'])
    def set_storage_state(self, path, timeout: timedelta | None = None, reload_pages: ReloadPages = None):
        """Restores a storage state file into the current active context."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Strict Mode', tags=['BrowserControl', 'Setter'])
    def set_strict_mode(self, mode: bool, scope: Scope = None):
        """Controls library strict mode."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Time', tags=['Clock', 'Setter'])
    def set_time(self, time, clock_type: ClockType = None):
        """Sets the time of the browser's internal clock."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Viewport Size', tags=['BrowserControl', 'Setter'])
    def set_viewport_size(self, width: int, height: int):
        """Sets the current page's viewport size to the specified dimensions."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Show Keyword Banner', tags=['Config', 'Setter'])
    def show_keyword_banner(self, show: bool = None, style: str = None, scope: Scope = None):
        """Controls if the keyword banner is shown on page or not."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Start Coverage', tags=['Coverage', 'Experimental', 'Setter'])
    def start_coverage(self, *, config_file=None, coverage_type: CoverageType = None, path=None, raw: bool = None, reportAnonymousScripts: bool = None, resetOnNavigation: bool = None):
        """Starts the coverage for the current page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Stop Coverage', tags=['Coverage', 'Getter'])
    def stop_coverage(self):
        """Stops the coverage for the current page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Switch Browser', tags=['BrowserControl', 'Setter'])
    def switch_browser(self, id: str):
        """Switches the currently active Browser to another open Browser."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Switch Context', tags=['BrowserControl', 'Setter'])
    def switch_context(self, id: str, browser: SelectionType | str = None):
        """Switches the active BrowserContext to another open context."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Switch Page', tags=['BrowserControl', 'Setter'])
    def switch_page(self, id, context: SelectionType | str = None, browser: SelectionType | str = None):
        """Switches the active browser page to another open page by ``id`` or ``NEW``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Take Screenshot', tags=['PageContent'])
    def take_screenshot(self, filename: str | None = None, selector: str | None = None, *, crop=None, disableAnimations: bool = None, fileType: ScreenshotFileTypes = None, fullPage: bool = None, highlight_selector: str | None = None, log_screenshot: bool = None, mask: list | str = None, maskColor: str | None = None, omitBackground: bool = None, quality: int | None = None, scale: Scale | None = None, return_as: ScreenshotReturnType = None, timeout: timedelta | None = None):
        """Takes a screenshot of the current window or element and saves it to disk."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Tap', tags=['PageContent', 'Setter'])
    def tap(self, selector: str, *modifiers, force: bool = None, noWaitAfter: bool = None, position_x: int | None = None, position_y: int | None = None, trial: bool = None):
        """Simulates tap on the element found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Type Secret', tags=['PageContent', 'Setter'])
    def type_secret(self, selector: str, secret, delay: timedelta = None, clear: bool = None):
        """Types the given ``secret`` into the text field found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Type Text', tags=['PageContent', 'Setter'])
    def type_text(self, selector: str, txt: str, delay: timedelta = None, clear: bool = None):
        """Types the given ``txt`` into the text field found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Uncheck Checkbox', tags=['PageContent', 'Setter'])
    def uncheck_checkbox(self, selector: str, force: bool = None):
        """Unchecks the checkbox found by ``selector``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Upload File By Selector', tags=['PageContent', 'Setter'])
    def upload_file_by_selector(self, selector: str, path, *extra_paths):
        """Uploads file from ``path`` to file input element matched by selector."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait For', tags=['Wait'])
    def wait_for(self, *promises):
        """Waits for promises to finish and returns results from them."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait For Alert', tags=['PageContent', 'Wait'])
    def wait_for_alert(self, action: DialogAction, prompt_input: str = None, text: str | None = None, timeout: timedelta | None = None):
        """Returns a promise to wait for next dialog on page, handles it with ``action`` and optionally verifies the dialogs text."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait For Alerts', tags=['PageContent', 'Wait'])
    def wait_for_alerts(self, actions: list, prompt_inputs: list, texts: list, timeout: timedelta | None = None):
        """Returns a promise to wait for multiple dialogs on a page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait For All Promises', tags=['Wait'])
    def wait_for_all_promises(self):
        """Waits for all promises to finish."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait For Condition', tags=['PageContent', 'Wait'])
    def wait_for_condition(self, condition: ConditionInputs, *args, timeout: timedelta | None = None, message: str | None = None):
        """Waits for a condition, defined with Browser getter keywords, to become True."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait For Elements State', tags=['PageContent', 'Wait'])
    def wait_for_elements_state(self, selector: str, state: ElementState = None, timeout: timedelta | None = None, message: str | None = None):
        """Waits for the element found by ``selector`` to satisfy state option."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait For Function', tags=['PageContent', 'Wait'])
    def wait_for_function(self, function: str, selector: str = None, polling: str | timedelta = None, timeout: timedelta | None = None, message: str | None = None):
        """Polls JavaScript expression or function in browser until it returns a (JavaScript) truthy value."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait For Load State', tags=['PageContent', 'Wait'])
    def wait_for_load_state(self, state: PageLoadStates = None, timeout: timedelta | None = None):
        """Waits until the page reaches the required load state."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait For Navigation', tags=['HTTP', 'Wait'])
    def wait_for_navigation(self, url, timeout: timedelta | None = None, wait_until: PageLoadStates = None):
        """Waits until the page has navigated to the given ``url``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait For Request', tags=['HTTP', 'Wait'])
    def wait_for_request(self, matcher=None, timeout: timedelta | None = None):
        """Waits for a request matching ``matcher`` to be made."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait For Response', tags=['HTTP', 'Wait'])
    def wait_for_response(self, matcher=None, timeout: timedelta | None = None):
        """Waits for a response matching ``matcher`` and returns the response as a Robot Framework dictionary."""
        raise NotImplementedError('stub: executes only on the client')
