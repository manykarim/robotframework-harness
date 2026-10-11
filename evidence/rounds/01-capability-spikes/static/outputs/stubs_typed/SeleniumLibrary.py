"""Signature-only stub for SeleniumLibrary 6.8.0 (generated from libdoc JSON)."""
from datetime import timedelta
from enum import Enum
from typing import Any
from robot.api.deco import keyword, library


@library(scope='GLOBAL', version='6.8.0', auto_keywords=False)
class SeleniumLibrary:
    def __init__(self, timeout=None, implicit_wait=None, run_on_failure=None, screenshot_root_directory: str | None = None, plugins: str | None = None, event_firing_webdriver: str | None = None, page_load_timeout=None, action_chain_delay=None, language: str | None = None):
        pass

    @keyword('Add Cookie', tags=[])
    def add_cookie(self, name: str, value: str, path: str | None = None, domain: str | None = None, secure: bool | None = None, expiry: str | None = None):
        """Adds a cookie to your current session."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Add Location Strategy', tags=[])
    def add_location_strategy(self, strategy_name: str, strategy_keyword: str, persist: bool = None):
        """Adds a custom location strategy."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Alert Should Be Present', tags=[])
    def alert_should_be_present(self, text: str = None, action: str = None, timeout: timedelta | None = None):
        """Verifies that an alert is present and by default, accepts it."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Alert Should Not Be Present', tags=[])
    def alert_should_not_be_present(self, action: str = None, timeout: timedelta | None = None):
        """Verifies that no alert is present."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Assign Id To Element', tags=[])
    def assign_id_to_element(self, locator, id: str):
        """Assigns a temporary ``id`` to the element specified by ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Capture Element Screenshot', tags=[])
    def capture_element_screenshot(self, locator, filename: str = None):
        """Captures a screenshot from the element identified by ``locator`` and embeds it into log file."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Capture Page Screenshot', tags=[])
    def capture_page_screenshot(self, filename: str = None):
        """Takes a screenshot of the current page and embeds it into a log file."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Checkbox Should Be Selected', tags=[])
    def checkbox_should_be_selected(self, locator):
        """Verifies checkbox ``locator`` is selected/checked."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Checkbox Should Not Be Selected', tags=[])
    def checkbox_should_not_be_selected(self, locator):
        """Verifies checkbox ``locator`` is not selected/checked."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Choose File', tags=[])
    def choose_file(self, locator, file_path: str):
        """Inputs the ``file_path`` into the file input field ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Clear Element Text', tags=[])
    def clear_element_text(self, locator):
        """Clears the value of the text-input-element identified by ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Click Button', tags=[])
    def click_button(self, locator, modifier: bool | str = None):
        """Clicks the button identified by ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Click Element', tags=[])
    def click_element(self, locator, modifier: bool | str = None, action_chain: bool = None):
        """Click the element identified by ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Click Element At Coordinates', tags=[])
    def click_element_at_coordinates(self, locator, xoffset: int, yoffset: int):
        """Click the element ``locator`` at ``xoffset/yoffset``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Click Image', tags=[])
    def click_image(self, locator, modifier: bool | str = None):
        """Clicks an image identified by ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Click Link', tags=[])
    def click_link(self, locator, modifier: bool | str = None):
        """Clicks a link identified by ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Close All Browsers', tags=[])
    def close_all_browsers(self):
        """Closes all open browsers and resets the browser cache."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Close Browser', tags=[])
    def close_browser(self):
        """Closes the current browser."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Close Window', tags=[])
    def close_window(self):
        """Closes currently opened and selected browser window/tab."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Cover Element', tags=[])
    def cover_element(self, locator):
        """Will cover elements identified by ``locator`` with a blue div without breaking page layout."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Create Webdriver', tags=[])
    def create_webdriver(self, driver_name: str, alias: str | None = None, kwargs: dict | None = None, **init_kwargs):
        """Creates an instance of Selenium WebDriver."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Current Frame Should Contain', tags=[])
    def current_frame_should_contain(self, text: str, loglevel: str = None):
        """Verifies that the current frame contains ``text``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Current Frame Should Not Contain', tags=[])
    def current_frame_should_not_contain(self, text: str, loglevel: str = None):
        """Verifies that the current frame does not contain ``text``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Delete All Cookies', tags=[])
    def delete_all_cookies(self):
        """Deletes all cookies."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Delete Cookie', tags=[])
    def delete_cookie(self, name):
        """Deletes the cookie matching ``name``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Double Click Element', tags=[])
    def double_click_element(self, locator):
        """Double clicks the element identified by ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Drag And Drop', tags=[])
    def drag_and_drop(self, locator, target):
        """Drags the element identified by ``locator`` into the ``target`` element."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Drag And Drop By Offset', tags=[])
    def drag_and_drop_by_offset(self, locator, xoffset: int, yoffset: int):
        """Drags the element identified with ``locator`` by ``xoffset/yoffset``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Element Attribute Value Should Be', tags=[])
    def element_attribute_value_should_be(self, locator, attribute: str, expected: None | str, message: str | None = None):
        """Verifies element identified by ``locator`` contains expected attribute value."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Element Should Be Disabled', tags=[])
    def element_should_be_disabled(self, locator):
        """Verifies that element identified by ``locator`` is disabled."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Element Should Be Enabled', tags=[])
    def element_should_be_enabled(self, locator):
        """Verifies that element identified by ``locator`` is enabled."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Element Should Be Focused', tags=[])
    def element_should_be_focused(self, locator):
        """Verifies that element identified by ``locator`` is focused."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Element Should Be Visible', tags=[])
    def element_should_be_visible(self, locator, message: str | None = None):
        """Verifies that the element identified by ``locator`` is visible."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Element Should Contain', tags=[])
    def element_should_contain(self, locator, expected: None | str, message: str | None = None, ignore_case: bool = None):
        """Verifies that element ``locator`` contains text ``expected``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Element Should Not Be Visible', tags=[])
    def element_should_not_be_visible(self, locator, message: str | None = None):
        """Verifies that the element identified by ``locator`` is NOT visible."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Element Should Not Contain', tags=[])
    def element_should_not_contain(self, locator, expected: None | str, message: str | None = None, ignore_case: bool = None):
        """Verifies that element ``locator`` does not contain text ``expected``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Element Text Should Be', tags=[])
    def element_text_should_be(self, locator, expected: None | str, message: str | None = None, ignore_case: bool = None):
        """Verifies that element ``locator`` contains exact the text ``expected``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Element Text Should Not Be', tags=[])
    def element_text_should_not_be(self, locator, not_expected: None | str, message: str | None = None, ignore_case: bool = None):
        """Verifies that element ``locator`` does not contain exact the text ``not_expected``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Execute Async Javascript', tags=[])
    def execute_async_javascript(self, *code):
        """Executes asynchronous JavaScript code with possible arguments."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Execute Javascript', tags=[])
    def execute_javascript(self, *code):
        """Executes the given JavaScript code with possible arguments."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Frame Should Contain', tags=[])
    def frame_should_contain(self, locator, text: str, loglevel: str = None):
        """Verifies that frame identified by ``locator`` contains ``text``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Action Chain Delay', tags=[])
    def get_action_chain_delay(self):
        """Gets the currently stored value for chain_delay_value in timestr format."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get All Links', tags=[])
    def get_all_links(self):
        """Returns a list containing ids of all links found in current page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Browser Aliases', tags=[])
    def get_browser_aliases(self):
        """Returns aliases of all active browser that has an alias as NormalizedDict. The dictionary contains the aliases as keys and the index as value. This can be accessed as dictionary ``${aliases.key}`` or as list ``@{aliases}[0]``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Browser Ids', tags=[])
    def get_browser_ids(self):
        """Returns index of all active browser as list."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Cookie', tags=[])
    def get_cookie(self, name: str):
        """Returns information of cookie with ``name`` as an object."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Cookies', tags=[])
    def get_cookies(self, as_dict: bool = None):
        """Returns all cookies of the current page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Dom Attribute', tags=[])
    def get_dom_attribute(self, locator, attribute: str):
        """Returns the value of ``attribute`` from the element ``locator``. `Get DOM Attribute` keyword only returns attributes declared within the element's HTML markup.  If the requested attribute is not there, the keyword returns ${None}."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Element Attribute', tags=[])
    def get_element_attribute(self, locator, attribute: str):
        """Returns the value of ``attribute`` from the element ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Element Count', tags=[])
    def get_element_count(self, locator):
        """Returns the number of elements matching ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Element Size', tags=[])
    def get_element_size(self, locator):
        """Returns width and height of the element identified by ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Horizontal Position', tags=[])
    def get_horizontal_position(self, locator):
        """Returns the horizontal position of the element identified by ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get List Items', tags=[])
    def get_list_items(self, locator, values: bool = None):
        """Returns all labels or values of selection list ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Location', tags=[])
    def get_location(self):
        """Returns the current browser window URL."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Locations', tags=[])
    def get_locations(self, browser: str = None):
        """Returns and logs URLs of all windows of the selected browser."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Property', tags=[])
    def get_property(self, locator, property: str):
        """Returns the value of ``property`` from the element ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Selected List Label', tags=[])
    def get_selected_list_label(self, locator):
        """Returns the label of selected option from selection list ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Selected List Labels', tags=[])
    def get_selected_list_labels(self, locator):
        """Returns labels of selected options from selection list ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Selected List Value', tags=[])
    def get_selected_list_value(self, locator):
        """Returns the value of selected option from selection list ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Selected List Values', tags=[])
    def get_selected_list_values(self, locator):
        """Returns values of selected options from selection list ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Selenium Implicit Wait', tags=[])
    def get_selenium_implicit_wait(self):
        """Gets the implicit wait value used by Selenium."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Selenium Page Load Timeout', tags=[])
    def get_selenium_page_load_timeout(self):
        """Gets the time to wait for a page load to complete before raising a timeout exception."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Selenium Speed', tags=[])
    def get_selenium_speed(self):
        """Gets the delay that is waited after each Selenium command."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Selenium Timeout', tags=[])
    def get_selenium_timeout(self):
        """Gets the timeout that is used by various keywords."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Session Id', tags=[])
    def get_session_id(self):
        """Returns the currently active browser session id."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Source', tags=[])
    def get_source(self):
        """Returns the entire HTML source of the current page or frame."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Table Cell', tags=[])
    def get_table_cell(self, locator, row: int, column: int, loglevel: str = None):
        """Returns contents of a table cell."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Text', tags=[])
    def get_text(self, locator):
        """Returns the text value of the element identified by ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Title', tags=[])
    def get_title(self):
        """Returns the title of the current page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Value', tags=[])
    def get_value(self, locator):
        """Returns the value attribute of the element identified by ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Vertical Position', tags=[])
    def get_vertical_position(self, locator):
        """Returns the vertical position of the element identified by ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get WebElement', tags=[])
    def get_webelement(self, locator):
        """Returns the first WebElement matching the given ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get WebElements', tags=[])
    def get_webelements(self, locator):
        """Returns a list of WebElement objects matching the ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Window Handles', tags=[])
    def get_window_handles(self, browser: str = None):
        """Returns all child window handles of the selected browser as a list."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Window Identifiers', tags=[])
    def get_window_identifiers(self, browser: str = None):
        """Returns and logs id attributes of all windows of the selected browser."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Window Names', tags=[])
    def get_window_names(self, browser: str = None):
        """Returns and logs names of all windows of the selected browser."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Window Position', tags=[])
    def get_window_position(self):
        """Returns current window position."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Window Size', tags=[])
    def get_window_size(self, inner: bool = None):
        """Returns current window width and height as integers."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Window Titles', tags=[])
    def get_window_titles(self, browser: str = None):
        """Returns and logs titles of all windows of the selected browser."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Go Back', tags=[])
    def go_back(self):
        """Simulates the user clicking the back button on their browser."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Go To', tags=[])
    def go_to(self, url):
        """Navigates the current browser window to the provided ``url``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Handle Alert', tags=[])
    def handle_alert(self, action: str = None, timeout: timedelta | None = None):
        """Handles the current alert and returns its message."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Input Password', tags=[])
    def input_password(self, locator, password: str, clear: bool = None):
        """Types the given password into the text field identified by ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Input Text', tags=[])
    def input_text(self, locator, text: str, clear: bool = None):
        """Types the given ``text`` into the text field identified by ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Input Text Into Alert', tags=[])
    def input_text_into_alert(self, text: str, action: str = None, timeout: timedelta | None = None):
        """Types the given ``text`` into an input field in an alert."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('List Selection Should Be', tags=[])
    def list_selection_should_be(self, locator, *expected):
        """Verifies selection list ``locator`` has ``expected`` options selected."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('List Should Have No Selections', tags=[])
    def list_should_have_no_selections(self, locator):
        """Verifies selection list ``locator`` has no options selected."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Location Should Be', tags=[])
    def location_should_be(self, url: str, message: str | None = None):
        """Verifies that the current URL is exactly ``url``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Location Should Contain', tags=[])
    def location_should_contain(self, expected: str, message: str | None = None):
        """Verifies that the current URL contains ``expected``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Log Location', tags=[])
    def log_location(self):
        """Logs and returns the current browser window URL."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Log Source', tags=[])
    def log_source(self, loglevel: str = None):
        """Logs and returns the HTML source of the current page or frame."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Log Title', tags=[])
    def log_title(self):
        """Logs and returns the title of the current page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Maximize Browser Window', tags=[])
    def maximize_browser_window(self):
        """Maximizes current browser window."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Minimize Browser Window', tags=[])
    def minimize_browser_window(self):
        """Minimizes current browser window."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Mouse Down', tags=[])
    def mouse_down(self, locator):
        """Simulates pressing the left mouse button on the element ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Mouse Down On Image', tags=[])
    def mouse_down_on_image(self, locator):
        """Simulates a mouse down event on an image identified by ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Mouse Down On Link', tags=[])
    def mouse_down_on_link(self, locator):
        """Simulates a mouse down event on a link identified by ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Mouse Out', tags=[])
    def mouse_out(self, locator):
        """Simulates moving the mouse away from the element ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Mouse Over', tags=[])
    def mouse_over(self, locator):
        """Simulates hovering the mouse over the element ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Mouse Up', tags=[])
    def mouse_up(self, locator):
        """Simulates releasing the left mouse button on the element ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Open Browser', tags=[])
    def open_browser(self, url: str | None = None, browser: str = None, alias: str | None = None, remote_url: bool | str = None, desired_capabilities: dict | None | str = None, ff_profile_dir=None, options: Any = None, service_log_path: str | None = None, executable_path: str | None = None, service: Any = None):
        """Opens a new browser instance to the optional ``url``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Open Context Menu', tags=[])
    def open_context_menu(self, locator):
        """Opens the context menu on the element identified by ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Page Should Contain', tags=[])
    def page_should_contain(self, text: str, loglevel: str = None):
        """Verifies that current page contains ``text``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Page Should Contain Button', tags=[])
    def page_should_contain_button(self, locator, message: str | None = None, loglevel: str = None):
        """Verifies button ``locator`` is found from current page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Page Should Contain Checkbox', tags=[])
    def page_should_contain_checkbox(self, locator, message: str | None = None, loglevel: str = None):
        """Verifies checkbox ``locator`` is found from the current page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Page Should Contain Element', tags=[])
    def page_should_contain_element(self, locator, message: str | None = None, loglevel: str = None, limit: int | None = None):
        """Verifies that element ``locator`` is found on the current page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Page Should Contain Image', tags=[])
    def page_should_contain_image(self, locator, message: str | None = None, loglevel: str = None):
        """Verifies image identified by ``locator`` is found from current page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Page Should Contain Link', tags=[])
    def page_should_contain_link(self, locator, message: str | None = None, loglevel: str = None):
        """Verifies link identified by ``locator`` is found from current page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Page Should Contain List', tags=[])
    def page_should_contain_list(self, locator, message: str | None = None, loglevel: str = None):
        """Verifies selection list ``locator`` is found from current page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Page Should Contain Radio Button', tags=[])
    def page_should_contain_radio_button(self, locator, message: str | None = None, loglevel: str = None):
        """Verifies radio button ``locator`` is found from current page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Page Should Contain Textfield', tags=[])
    def page_should_contain_textfield(self, locator, message: str | None = None, loglevel: str = None):
        """Verifies text field ``locator`` is found from current page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Page Should Not Contain', tags=[])
    def page_should_not_contain(self, text: str, loglevel: str = None):
        """Verifies the current page does not contain ``text``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Page Should Not Contain Button', tags=[])
    def page_should_not_contain_button(self, locator, message: str | None = None, loglevel: str = None):
        """Verifies button ``locator`` is not found from current page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Page Should Not Contain Checkbox', tags=[])
    def page_should_not_contain_checkbox(self, locator, message: str | None = None, loglevel: str = None):
        """Verifies checkbox ``locator`` is not found from the current page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Page Should Not Contain Element', tags=[])
    def page_should_not_contain_element(self, locator, message: str | None = None, loglevel: str = None):
        """Verifies that element ``locator`` is not found on the current page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Page Should Not Contain Image', tags=[])
    def page_should_not_contain_image(self, locator, message: str | None = None, loglevel: str = None):
        """Verifies image identified by ``locator`` is not found from current page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Page Should Not Contain Link', tags=[])
    def page_should_not_contain_link(self, locator, message: str | None = None, loglevel: str = None):
        """Verifies link identified by ``locator`` is not found from current page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Page Should Not Contain List', tags=[])
    def page_should_not_contain_list(self, locator, message: str | None = None, loglevel: str = None):
        """Verifies selection list ``locator`` is not found from current page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Page Should Not Contain Radio Button', tags=[])
    def page_should_not_contain_radio_button(self, locator, message: str | None = None, loglevel: str = None):
        """Verifies radio button ``locator`` is not found from current page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Page Should Not Contain Textfield', tags=[])
    def page_should_not_contain_textfield(self, locator, message: str | None = None, loglevel: str = None):
        """Verifies text field ``locator`` is not found from current page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Press Key', tags=[])
    def press_key(self, locator, key: str):
        """Simulates user pressing key on element identified by ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Press Keys', tags=[])
    def press_keys(self, locator=None, *keys):
        """Simulates the user pressing key(s) to an element or on the active browser."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Print Page As Pdf', tags=[])
    def print_page_as_pdf(self, filename: str = None, background: bool | None = None, margin_bottom: float | None = None, margin_left: float | None = None, margin_right: float | None = None, margin_top: float | None = None, orientation: str | None = None, page_height: float | None = None, page_ranges: list | None = None, page_width: float | None = None, scale: float | None = None, shrink_to_fit: bool | None = None):
        """Print the current page as a PDF"""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Radio Button Should Be Set To', tags=[])
    def radio_button_should_be_set_to(self, group_name: str, value: str):
        """Verifies radio button group ``group_name`` is set to ``value``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Radio Button Should Not Be Selected', tags=[])
    def radio_button_should_not_be_selected(self, group_name: str):
        """Verifies radio button group ``group_name`` has no selection."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Register Keyword To Run On Failure', tags=[])
    def register_keyword_to_run_on_failure(self, keyword: str | None):
        """Sets the keyword to execute, when a SeleniumLibrary keyword fails."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Reload Page', tags=[])
    def reload_page(self):
        """Simulates user reloading page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Remove Location Strategy', tags=[])
    def remove_location_strategy(self, strategy_name: str):
        """Removes a previously added custom location strategy."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Scroll Element Into View', tags=[])
    def scroll_element_into_view(self, locator):
        """Scrolls the element identified by ``locator`` into view."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Select All From List', tags=[])
    def select_all_from_list(self, locator):
        """Selects all options from multi-selection list ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Select Checkbox', tags=[])
    def select_checkbox(self, locator):
        """Selects the checkbox identified by ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Select Frame', tags=[])
    def select_frame(self, locator):
        """Sets frame identified by ``locator`` as the current frame."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Select From List By Index', tags=[])
    def select_from_list_by_index(self, locator, *indexes):
        """Selects options from selection list ``locator`` by ``indexes``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Select From List By Label', tags=[])
    def select_from_list_by_label(self, locator, *labels):
        """Selects options from selection list ``locator`` by ``labels``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Select From List By Value', tags=[])
    def select_from_list_by_value(self, locator, *values):
        """Selects options from selection list ``locator`` by ``values``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Select Radio Button', tags=[])
    def select_radio_button(self, group_name: str, value: str):
        """Sets the radio button group ``group_name`` to ``value``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Action Chain Delay', tags=[])
    def set_action_chain_delay(self, value: timedelta):
        """Sets the duration of delay in ActionChains() used by SeleniumLibrary."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Browser Implicit Wait', tags=[])
    def set_browser_implicit_wait(self, value: timedelta):
        """Sets the implicit wait value used by Selenium."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Focus To Element', tags=[])
    def set_focus_to_element(self, locator):
        """Sets the focus to the element identified by ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Screenshot Directory', tags=[])
    def set_screenshot_directory(self, path: None | str):
        """Sets the directory for captured screenshots."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Selenium Implicit Wait', tags=[])
    def set_selenium_implicit_wait(self, value: timedelta):
        """Sets the implicit wait value used by Selenium."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Selenium Page Load Timeout', tags=[])
    def set_selenium_page_load_timeout(self, value: timedelta):
        """Sets the page load timeout value used by Selenium."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Selenium Speed', tags=[])
    def set_selenium_speed(self, value: timedelta):
        """Sets the delay that is waited after each Selenium command."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Selenium Timeout', tags=[])
    def set_selenium_timeout(self, value: timedelta):
        """Sets the timeout that is used by various keywords."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Window Position', tags=[])
    def set_window_position(self, x: int, y: int):
        """Sets window position using ``x`` and ``y`` coordinates."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Set Window Size', tags=[])
    def set_window_size(self, width: int, height: int, inner: bool = None):
        """Sets current windows size to given ``width`` and ``height``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Simulate Event', tags=[])
    def simulate_event(self, locator, event: str):
        """Simulates ``event`` on the element identified by ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Submit Form', tags=[])
    def submit_form(self, locator=None):
        """Submits a form identified by ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Switch Browser', tags=[])
    def switch_browser(self, index_or_alias: str):
        """Switches between active browsers using ``index_or_alias``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Switch Window', tags=[])
    def switch_window(self, locator: list | str = None, timeout: str | None = None, browser: str = None):
        """Switches to browser window matching ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Table Cell Should Contain', tags=[])
    def table_cell_should_contain(self, locator, row: int, column: int, expected: str, loglevel: str = None):
        """Verifies table cell contains text ``expected``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Table Column Should Contain', tags=[])
    def table_column_should_contain(self, locator, column: int, expected: str, loglevel: str = None):
        """Verifies table column contains text ``expected``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Table Footer Should Contain', tags=[])
    def table_footer_should_contain(self, locator, expected: str, loglevel: str = None):
        """Verifies table footer contains text ``expected``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Table Header Should Contain', tags=[])
    def table_header_should_contain(self, locator, expected: str, loglevel: str = None):
        """Verifies table header contains text ``expected``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Table Row Should Contain', tags=[])
    def table_row_should_contain(self, locator, row: int, expected: str, loglevel: str = None):
        """Verifies that table row contains text ``expected``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Table Should Contain', tags=[])
    def table_should_contain(self, locator, expected: str, loglevel: str = None):
        """Verifies table contains text ``expected``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Textarea Should Contain', tags=[])
    def textarea_should_contain(self, locator, expected: str, message: str | None = None):
        """Verifies text area ``locator`` contains text ``expected``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Textarea Value Should Be', tags=[])
    def textarea_value_should_be(self, locator, expected: str, message: str | None = None):
        """Verifies text area ``locator`` has exactly text ``expected``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Textfield Should Contain', tags=[])
    def textfield_should_contain(self, locator, expected: str, message: str | None = None):
        """Verifies text field ``locator`` contains text ``expected``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Textfield Value Should Be', tags=[])
    def textfield_value_should_be(self, locator, expected: str, message: str | None = None):
        """Verifies text field ``locator`` has exactly text ``expected``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Title Should Be', tags=[])
    def title_should_be(self, title: str, message: str | None = None):
        """Verifies that the current page title equals ``title``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Unselect All From List', tags=[])
    def unselect_all_from_list(self, locator):
        """Unselects all options from multi-selection list ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Unselect Checkbox', tags=[])
    def unselect_checkbox(self, locator):
        """Removes the selection of checkbox identified by ``locator``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Unselect Frame', tags=[])
    def unselect_frame(self):
        """Sets the main frame as the current frame."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Unselect From List By Index', tags=[])
    def unselect_from_list_by_index(self, locator, *indexes):
        """Unselects options from selection list ``locator`` by ``indexes``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Unselect From List By Label', tags=[])
    def unselect_from_list_by_label(self, locator, *labels):
        """Unselects options from selection list ``locator`` by ``labels``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Unselect From List By Value', tags=[])
    def unselect_from_list_by_value(self, locator, *values):
        """Unselects options from selection list ``locator`` by ``values``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait For Condition', tags=[])
    def wait_for_condition(self, condition: str, timeout: timedelta | None = None, error: str | None = None):
        """Waits until ``condition`` is true or ``timeout`` expires."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait For Expected Condition', tags=[])
    def wait_for_expected_condition(self, condition, *args, timeout: float | None = None):
        """Waits until ``condition`` is true or ``timeout`` expires."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait Until Element Contains', tags=[])
    def wait_until_element_contains(self, locator, text: str, timeout: timedelta | None = None, error: str | None = None):
        """Waits until the element ``locator`` contains ``text``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait Until Element Does Not Contain', tags=[])
    def wait_until_element_does_not_contain(self, locator, text: str, timeout: timedelta | None = None, error: str | None = None):
        """Waits until the element ``locator`` does not contain ``text``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait Until Element Is Enabled', tags=[])
    def wait_until_element_is_enabled(self, locator, timeout: timedelta | None = None, error: str | None = None):
        """Waits until the element ``locator`` is enabled."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait Until Element Is Not Visible', tags=[])
    def wait_until_element_is_not_visible(self, locator, timeout: timedelta | None = None, error: str | None = None):
        """Waits until the element ``locator`` is not visible."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait Until Element Is Visible', tags=[])
    def wait_until_element_is_visible(self, locator, timeout: timedelta | None = None, error: str | None = None):
        """Waits until the element ``locator`` is visible."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait Until Location Contains', tags=[])
    def wait_until_location_contains(self, expected: str, timeout: timedelta | None = None, message: str | None = None):
        """Waits until the current URL contains ``expected``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait Until Location Does Not Contain', tags=[])
    def wait_until_location_does_not_contain(self, location: str, timeout: timedelta | None = None, message: str | None = None):
        """Waits until the current URL does not contains ``location``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait Until Location Is', tags=[])
    def wait_until_location_is(self, expected: str, timeout: timedelta | None = None, message: str | None = None):
        """Waits until the current URL is ``expected``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait Until Location Is Not', tags=[])
    def wait_until_location_is_not(self, location: str, timeout: timedelta | None = None, message: str | None = None):
        """Waits until the current URL is not ``location``."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait Until Page Contains', tags=[])
    def wait_until_page_contains(self, text: str, timeout: timedelta | None = None, error: str | None = None):
        """Waits until ``text`` appears on the current page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait Until Page Contains Element', tags=[])
    def wait_until_page_contains_element(self, locator, timeout: timedelta | None = None, error: str | None = None, limit: int | None = None):
        """Waits until the element ``locator`` appears on the current page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait Until Page Does Not Contain', tags=[])
    def wait_until_page_does_not_contain(self, text: str, timeout: timedelta | None = None, error: str | None = None):
        """Waits until ``text`` disappears from the current page."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Wait Until Page Does Not Contain Element', tags=[])
    def wait_until_page_does_not_contain_element(self, locator, timeout: timedelta | None = None, error: str | None = None, limit: int | None = None):
        """Waits until the element ``locator`` disappears from the current page."""
        raise NotImplementedError('stub: executes only on the client')
