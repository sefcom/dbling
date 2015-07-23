
import requests
from time import sleep


def verify_crx_availability(crx_id):
    """
    Return whether the extension ID is even available on the Chrome Web Store.
    This does not imply the CRX can be downloaded anonymously, since some
    require payment or other exclusive access. Such determinations must be
    made elsewhere.

    There is a small chance that this may raise a requests.ConnectionError,
    which indicates that something went wrong while attempting to make the web
    request.

    :param crx_id: The extension ID to test. Must pass the test of the
        validate_crx_id() function.
    :type crx_id: str
    :return: Whether the extension can be reached with a web request to the
        Chrome Web Store.
    :rtype: bool
    """
    # Check that the form of the ID is valid
    validate_crx_id(crx_id)

    # Check that the ID is for a valid extension
    tries = 0
    while True:
        tries += 1
        try:
            r = requests.get('https://chrome.google.com/webstore/detail/%s' % crx_id, allow_redirects=False)
        except requests.ConnectionError:
            if tries < 5:
                sleep(2)  # Problem may resolve itself by waiting for a bit before retrying
            else:
                raise
        else:
            return r.status_code == 301


def validate_crx_id(crx_id):
    """
    Check that the Chrome extension ID has three important properties:

    1. It must be a string
    2. It must have alpha characters only (strictly speaking, these should be
       lowercase and only from a-p, but checking for this is a little
       overboard)
    3. It must be 32 characters long

    :param crx_id:
    :return:
    """
    assert isinstance(crx_id, str)
    assert crx_id.isalnum()
    assert len(crx_id) == 32
