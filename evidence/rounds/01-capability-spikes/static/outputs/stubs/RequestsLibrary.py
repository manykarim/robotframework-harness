"""Signature-only stub for RequestsLibrary 0.9.7 (generated from libdoc JSON)."""
from robot.api.deco import keyword, library


@library(scope='GLOBAL', version='0.9.7', auto_keywords=False)
class RequestsLibrary:

    @keyword('Create Client Cert Session', tags=[])
    def create_client_cert_session(self, alias, url, headers=None, cookies=None, client_certs=None, timeout=None, proxies=None, verify=None, debug=None, max_retries=None, backoff_factor=None, disable_warnings=None, retry_status_list=None, retry_method_list=None):
        """Create Session: create a HTTP session to a server"""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Create Custom Session', tags=[])
    def create_custom_session(self, alias, url, auth, headers=None, cookies=None, timeout=None, proxies=None, verify=None, debug=None, max_retries=None, backoff_factor=None, disable_warnings=None, retry_status_list=None, retry_method_list=None):
        """Create Session: create a HTTP session to a server"""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Create Digest Session', tags=[])
    def create_digest_session(self, alias, url, auth, headers=None, cookies=None, timeout=None, proxies=None, verify=None, debug=None, max_retries=None, backoff_factor=None, disable_warnings=None, retry_status_list=None, retry_method_list=None):
        """Create Session: create a HTTP session to a server"""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Create Ntlm Session', tags=[])
    def create_ntlm_session(self, alias, url, auth, headers=None, cookies=None, timeout=None, proxies=None, verify=None, debug=None, max_retries=None, backoff_factor=None, disable_warnings=None, retry_status_list=None, retry_method_list=None):
        """Create Session: create a HTTP session to a server"""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Create Session', tags=[])
    def create_session(self, alias, url, headers=None, cookies=None, auth=None, timeout=None, proxies=None, verify=None, debug=None, max_retries=None, backoff_factor=None, disable_warnings=None, retry_status_list=None, retry_method_list=None):
        """Create Session: create a HTTP session to a server"""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('DELETE', tags=[])
    def delete(self, *args, **kwargs):
        """Sends a DELETE request."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Delete All Sessions', tags=[])
    def delete_all_sessions(self):
        """Removes all the session objects"""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('DELETE On Session', tags=[])
    def delete_on_session(self, *args, **kwargs):
        """Sends a DELETE request on a previously created HTTP Session."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Delete Request', tags=[])
    def delete_request(self, alias, uri, data=None, json=None, params=None, headers=None, allow_redirects=None, timeout=None):
        """*DEPRECATED* Please use `DELETE On Session` instead."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('GET', tags=[])
    def get(self, *args, **kwargs):
        """Sends a GET request."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get File For Streaming Upload', tags=[])
    def get_file_for_streaming_upload(self, path):
        """Opens and returns a file descriptor of a specified file to be passed as ``data`` parameter to other requests keywords."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('GET On Session', tags=[])
    def get_on_session(self, *args, **kwargs):
        """Sends a GET request on a previously created HTTP Session."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Get Request', tags=[])
    def get_request(self, alias, uri, headers=None, data=None, json=None, params=None, allow_redirects=None, timeout=None):
        """*DEPRECATED* Please use `GET On Session` instead."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('HEAD', tags=[])
    def head(self, *args, **kwargs):
        """Sends a HEAD request."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('HEAD On Session', tags=[])
    def head_on_session(self, *args, **kwargs):
        """Sends a HEAD request on a previously created HTTP Session."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Head Request', tags=[])
    def head_request(self, alias, uri, headers=None, allow_redirects=None, timeout=None):
        """*DEPRECATED* Please use `HEAD On Session` instead."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('OPTIONS', tags=[])
    def options(self, *args, **kwargs):
        """Sends a OPTIONS request."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('OPTIONS On Session', tags=[])
    def options_on_session(self, *args, **kwargs):
        """Sends a OPTIONS request on a previously created HTTP Session."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Options Request', tags=[])
    def options_request(self, alias, uri, headers=None, allow_redirects=None, timeout=None):
        """*DEPRECATED* Please use `OPTIONS On Session` instead."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('PATCH', tags=[])
    def patch(self, *args, **kwargs):
        """Sends a PUT request."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('PATCH On Session', tags=[])
    def patch_on_session(self, *args, **kwargs):
        """Sends a PATCH request on a previously created HTTP Session."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Patch Request', tags=[])
    def patch_request(self, alias, uri, data=None, json=None, params=None, headers=None, files=None, allow_redirects=None, timeout=None):
        """*DEPRECATED* Please use `PATCH On Session` instead."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('POST', tags=[])
    def post(self, *args, **kwargs):
        """Sends a POST request."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('POST On Session', tags=[])
    def post_on_session(self, *args, **kwargs):
        """Sends a POST request on a previously created HTTP Session."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Post Request', tags=[])
    def post_request(self, alias, uri, data=None, json=None, params=None, headers=None, files=None, allow_redirects=None, timeout=None):
        """*DEPRECATED* Please use `POST On Session` instead."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('PUT', tags=[])
    def put(self, *args, **kwargs):
        """Sends a PUT request."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('PUT On Session', tags=[])
    def put_on_session(self, *args, **kwargs):
        """Sends a PUT request on a previously created HTTP Session."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Put Request', tags=[])
    def put_request(self, alias, uri, data=None, json=None, params=None, files=None, headers=None, allow_redirects=None, timeout=None):
        """*DEPRECATED* Please use `PUT On Session` instead."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Request Should Be Successful', tags=[])
    def request_should_be_successful(self, response=None):
        """Fails if response status code is a client or server error (4xx, 5xx)."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Session Exists', tags=[])
    def session_exists(self, alias):
        """Return True if the session has been already created"""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Status Should Be', tags=[])
    def status_should_be(self, expected_status, response=None, msg=None):
        """Fails if response status code is different than the expected."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('To Json', tags=[])
    def to_json(self, content, pretty_print=None):
        """*DEPRECATED* Please use ${resp.json()} instead. Have a look at the improved HTML output as pretty printing replacement."""
        raise NotImplementedError('stub: executes only on the client')

    @keyword('Update Session', tags=[])
    def update_session(self, alias, headers=None, cookies=None):
        """Updates HTTP Session Headers and Cookies."""
        raise NotImplementedError('stub: executes only on the client')
