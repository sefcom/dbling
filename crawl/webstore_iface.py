#!/usr/bin/env python3
# *-* coding: utf-8 *-*

from __future__ import absolute_import

import logging
from os import path
from lxml import etree
import requests
from requests.exceptions import ChunkedEncodingError
from requests import ConnectionError
from time import sleep

from common.util import validate_crx_id, get_crx_version, CRX_URL

__all__ = ['DownloadCRXList', 'save_crx', 'ListDownloadFailedError', 'ExtensionUnavailable', 'BadDownloadURL',
           'FileExistsError', 'VersionExtractError']

LOG_PATH = path.join(path.dirname(path.realpath(__file__)), '../log', 'crx.log')
DBLING_DIR = path.abspath(path.join(path.dirname(path.realpath(__file__)), '..'))
DONT_OVERWRITE_DOWNLOADED_CRX = False
CHUNK_SIZE = 512
NUM_HTTP_RETIRES = 5


logging.getLogger('requests').setLevel(logging.WARNING)


if not hasattr(__builtins__, 'FileExistsError'):
    # Python 2.7 compatibility
    class FileExistsError(OSError):
        """Raised when trying to create a file or directory which already exists. Corresponds to errno EEXIST."""


class ListDownloadFailedError(ConnectionError):
    """Raised when the list download fails."""


class ExtensionUnavailable(Exception):
    """Raised when an extension isn't downloadable."""


class BadDownloadURL(Exception):
    """Raised when the ID is valid but we can't download the extension."""


class VersionExtractError(Exception):
    """Raised when extracting the version number from the URL fails."""


class DownloadCRXList:
    # Namespace tag used by the downloaded list (XML file)
    _ns = '{http://www.sitemaps.org/schemas/sitemap/0.9}'
    local_sitemap = path.join(DBLING_DIR, 'src', 'chrome_sitemap.xml')

    def __init__(self, ext_url, session=None):
        """Generate list of extension IDs downloaded from Google.

        :param ext_url: Specially crafted URL that will let us download the
            list of extensions.
        :type ext_url: str
        :param session: Session object to use when downloading the list.
        :type session: requests.Session
        """
        self.ext_url = ext_url
        self.session = session
        self._count = 0  # Number of extension IDs in the downloaded list
        self._current_count = 0  # Number of iterations for current run. Reset to 0 by reset_stale()
        self._downloaded_list = False
        self._elm_iter = None
        self._stale = False  # Prevents fresh download when True
        self.ret_tup = False  # Return a tuple (CRX ID, num)
        self._testing = False

    def __iter__(self):
        if self._testing:
            # Favor not downloading if we're testing
            do_download = not (self._stale or self._downloaded_list)
        else:
            do_download = not self._stale or not self._downloaded_list
        if do_download:
            self.do_download()

        xml_tree_root = etree.parse(self.local_sitemap).getroot()

        # Initialize the iterator from etree
        self._elm_iter = xml_tree_root.iterfind(self._ns + 'url').__iter__()
        return self

    def __next__(self):
        if not self._downloaded_list or self._elm_iter is None:
            # This exception should only ever happen if the calling code wasn't using this class as a traditional
            # generator, i.e. calling the functions directly.
            raise Exception('You must call __iter__ before calling __next__.')

        if self._testing and self._current_count >= 10:
            raise StopIteration
        try:
            url_elm = self._elm_iter.__next__()
        except StopIteration:
            # We're getting our data from an iterator, so when it's done, we should be done, signified by raising a
            # StopIteration exception.
            logging.debug('Done parsing list of extensions.')
            raise

        # Count this iteration
        self._current_count += 1
        self.count += 1  # Only actually increments if not stale

        # Leverage os.path's basename function to grab the last part of the source URL of the extension
        crx_id = path.basename(url_elm.findtext(self._ns + 'loc'))[:32]

        if self.ret_tup:
            return crx_id, self._current_count
        else:
            return crx_id

    def do_download(self):
        logging.info('Downloading list of extensions from Google.')
        resp = _http_get(self.ext_url, self.session, stream=False)
        if resp is None:
            logging.critical('Failed to download list of extensions.')
            raise ListDownloadFailedError('Unable to download list of extensions.')

        # Save the list
        with open(self.local_sitemap, 'wb') as fout:
            for chunk in resp.iter_content(chunk_size=None):
                fout.write(chunk)
        del resp
        self._downloaded_list = True
        logging.debug('Download finished. Ready to parse the XML and yield extension IDs.')

    def reset_stale(self, ret_tup=False):
        self._stale = True
        self._current_count = 0
        self.ret_tup = bool(ret_tup)
        return self.__iter__()

    @property
    def count(self):
        return self._count

    @count.setter
    def count(self, val):
        if not self.count_finalized:
            self._count = val

    @count.deleter
    def count(self):
        pass

    @property
    def count_finalized(self):
        return self._stale

    def __len__(self):
        return self.count


def save_crx(crx_obj, download_url, save_path=None, session=None):
    """Download the CRX, save in the `save_path` directory.

    The saved file will have the format: `<extension ID>_<version>.crx`

    If `save_path` isn't given, this will default to a directory called
    "downloads" in the CWD.

    Adds the following keys to `crx_obj`:

    - `version`: Version number of the extension, as obtained from the final
      URL of the download. This may differ from the version listed in the
      extension's manifest.
    - `filename`: The basename of the CRX file (not the full path)
    - `full_path`: The location (full path) of the downloaded CRX file

    :param crx_obj: Previously collected information about the extension.
    :type crx_obj: munch.Munch
    :param download_url: The URL template that already contains the correct
        Chrome version information and '{}' where the ID goes.
    :type download_url: str
    :param save_path: Directory where the CRX should be saved.
    :type save_path: str|None
    :param session: Optional `Session` object to use for HTTP requests.
    :type session: None|requests.Session
    :return: Updated version of `crx_obj` with `version`, `filename`, and
        `full_path` information added. If the download wasn't successful, not
        all of these may have been added, depending on when it failed.
    :rtype: munch.Munch
    """

    # Check that the ID has a valid form
    validate_crx_id(crx_obj.id)

    # Ensure the extension is still available in the Web Store
    url = CRX_URL % crx_obj.id
    resp = _http_get(url, session)
    _ensure_redirect(resp)
    resp.close()

    # If the URL we got back was the same one we requested, the download failed
    if url == resp.url:
        raise BadDownloadURL

    # Make the new request to actually download the extension
    resp = _http_get(download_url.format(crx_obj.id), session, stream=True)

    try:
        crx_obj.version = get_crx_version(resp.url.rsplit('extension', 1)[-1])
    except IndexError:
        raise VersionExtractError('{}  Problem with extracting CRX version from URL\nURL: {}\nSplit URL: {}'.
                                  format(crx_obj.id, resp.url, resp.url.rsplit('extension', 1)[-1]))
    crx_obj.filename = '{}_{}.crx'.format(crx_obj.id, crx_obj.version)  # <ID>_<version>

    if save_path is None:
        save_path = path.join('.', 'downloads')
    crx_obj.full_path = path.abspath(path.join(save_path, crx_obj.filename))

    if path.exists(crx_obj.full_path):
        err = FileExistsError()
        err.errno = ''
        err.strerror = 'Cannot save CRX to path that already exists'
        err.filename = crx_obj.full_path
        raise err

    with open(crx_obj.full_path, 'wb') as fout:
        # Write the binary response to the file 512 bytes at a time
        for chunk in resp.iter_content(chunk_size=512):
            fout.write(chunk)
    resp.close()

    return crx_obj


def _ensure_redirect(resp):
    """Check that a redirect occurred.

    :param resp: The response object from GET-ting the extension's URL.
    :type resp: requests.Response
    :return: None
    :rtype: None
    """
    if not len(resp.history):
        raise ExtensionUnavailable('No redirect occurred while fetching URL %s' % resp.url)


class RetryRequest:
    """Wraps functions that make HTTP requests, retries on failure."""

    def __init__(self, f):
        self.f = f

    def __call__(self, *args, **kwargs):
        resp = None
        for i in range(NUM_HTTP_RETIRES):
            try:
                resp = self.f(*args, **kwargs)
            except (ChunkedEncodingError, ConnectionError):
                sleep(10 * (i+1))
            else:
                break
        resp.raise_for_status()  # If there was an HTTP error, raise it
        return resp


@RetryRequest
def _http_get(url, session=None, stream=True, **kwargs):
    """Make a GET request with the URL.

    Any errors from the HTTP request (non 200 codes) will raise an HTTPError.

    :param url: The URL to GET.
    :type url: str
    :param session: Optional `Session` object to use to make the GET request.
    :type session: None|requests.Session
    :param stream: If `False`, the response content will be immediately
        downloaded.
    :type stream: bool
    :param kwargs: Optional arguments that `request` takes.
    :type kwargs: dict
    :return: The `Response` object containing the server's response to the
        HTTP request.
    :rtype: requests.Response
    """
    if isinstance(session, requests.Session):
        return session.get(url, stream=stream, **kwargs)
    else:
        return requests.get(url, stream=stream, **kwargs)
