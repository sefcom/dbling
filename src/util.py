
import logging
from os import path
import re
from time import sleep

import requests

import clr


SLICE_PAT = re.compile('.*(/home.*)')


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


def add_color_log_levels(center=False):
    if center:
        c = 'CRITICAL'.center(8)
        e = 'ERROR'.center(8)
        w = 'WARNING'.center(8)
        i = 'INFO'.center(8)
        d = 'DEBUG'.center(8)
        n = 'NOTSET'.center(8)
    else:
        c = 'CRITICAL'
        e = 'ERROR'
        w = 'WARNING'
        i = 'INFO'
        d = 'DEBUG'
        n = 'NOTSET'
    logging.addLevelName(50, clr.black(clr.red(c, True)))
    logging.addLevelName(40, clr.black(clr.magenta(e, True)))
    logging.addLevelName(30, clr.black(clr.yellow(w, True)))
    logging.addLevelName(20, clr.black(clr.blue(i, True)))
    logging.addLevelName(10, clr.black(clr.green(d, True)))
    logging.addLevelName(0, clr.black(clr.white(n, True)))


def get_dir_depth(filename, slice_path=False):
    """
    Calculate how many directories deep the filename is.

    :param filename: The path to be split and counted.
    :type filename: str
    :return: The number of directory levels in the filename.
    :rtype: int
    """
    if slice_path:
        m = re.search(SLICE_PAT, filename)
        if m:
            filename = m.group(1)
    dir_depth = 0
    _head = filename
    while True:
        prev_head = _head
        _head, _tail = path.split(_head)
        if prev_head == _head:
            break
        if len(_tail) == 0:
            continue
        dir_depth += 1
        if len(_head) == 0:
            break
    return dir_depth
