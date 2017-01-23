#!/usr/bin/env python3
# *-* coding: utf-8 *-*

from __future__ import absolute_import

import asyncio
import logging
from os import path, remove
from time import sleep
from urllib.parse import urlparse, parse_qs

import requests
import uvloop
from lxml import etree
from requests import ConnectionError
from requests.exceptions import ChunkedEncodingError

from common.util import validate_crx_id, get_crx_version, CRX_URL, make_download_headers

__all__ = ['DownloadCRXList', 'save_crx', 'ListDownloadFailedError', 'ExtensionUnavailable', 'BadDownloadURL',
           'VersionExtractError']

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

LOG_PATH = path.join(path.dirname(path.realpath(__file__)), '../log', 'crx.log')
DBLING_DIR = path.abspath(path.join(path.dirname(path.realpath(__file__)), '..'))
DONT_OVERWRITE_DOWNLOADED_CRX = False
CHUNK_SIZE = 512
NUM_HTTP_RETIRES = 5


logging.getLogger('requests').setLevel(logging.WARNING)


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
    sitemap_dir = path.join(DBLING_DIR, 'crawl', 'sitemaps')
    local_sitemap = path.join(sitemap_dir, 'chrome_sitemap.xml')

    def __init__(self, ext_url, *, return_count=False, session=None):
        """Generate list of extension IDs downloaded from Google.

        :param ext_url: Specially crafted URL that will let us download the
            list of extensions.
        :type ext_url: str
        :param return_count: When True, will return a tuple of the form:
            `(crx_id, job_number)`, where `job_number` is the index of the ID
            plus 1. This way, the job number of the last ID returned will be
            the same as `len(DownloadCRXList)`.
        :type return_count: bool
        :param session: Session object to use when downloading the list.
        :type session: requests.Session
        """
        self.ext_url = ext_url
        self.session = session
        self._downloaded_list = False
        self.ret_tup = return_count  # Return a tuple (CRX ID, num)
        self._id_list = []
        self._next_id_index = 0

    def __iter__(self):
        if not self._downloaded_list:
            self.download_ids()
        # Reset the "next ID" index
        self._next_id_index = 0
        return self

    def __next__(self):
        if self._next_id_index >= len(self._id_list) or self._next_id_index > 100:
            raise StopIteration
        crx_id = self._id_list[self._next_id_index]
        self._next_id_index += 1
        if self.ret_tup:
            return crx_id, self._next_id_index
        return crx_id

    def download_ids(self):
        """Starting point for downloading all CRX IDs.

        This function actually creates an event loop and starts the downloads
        asynchronously.

        :return:
        """
        asyncio.get_event_loop().run_until_complete(self._async_download_lists())
        self._downloaded_list = True

    async def _async_download_lists(self):
        logging.info('Downloading the list of extension lists from Google.')

        # Download the first list
        list_list_url = 'https://chrome.google.com/webstore/sitemap'
        resp = _http_get(list_list_url, self.session, stream=False, headers=make_download_headers())
        if resp is None:
            logging.critical('Failed to download list of extensions.')
            raise ListDownloadFailedError('Unable to download list of extensions.')

        # Save the list
        with open(self.local_sitemap, 'wb') as fout:
            for chunk in resp.iter_content(chunk_size=None):
                fout.write(chunk)
        del resp

        # Go through the list, extracting list URLs
        ids = set()
        xml_tree = etree.parse(self.local_sitemap)
        for url_tag in xml_tree.iterfind('*/' + self._ns + 'loc'):
            # Download the URL, get the IDs from it and add them to the set of IDs
            try:
                ids |= await self._dl_parse_id_list(url_tag.text)
            except ListDownloadFailedError:
                # TODO: How to handle this?
                raise

        # Convert IDs to a list, then sort it
        self._id_list = list(ids)
        self._id_list.sort()

    async def _dl_parse_id_list(self, list_url):
        # Get info from the list URL to indicate our progress in the log message
        url_data = parse_qs(urlparse(list_url).query)
        numshards = url_data['numshards'][0]
        shard = ('{:0' + str(len(numshards)) + '}').format(int(url_data['shard'][0]))
        _hl = hl = url_data.get('hl', '')
        if isinstance(_hl, list):
            hl = ' (language: {})'.format(_hl[0])
            _hl = '_{}'.format(_hl[0])
        list_id = '{} of {}{}'.format(shard, numshards, hl)
        logging.info('Downloading list {} from Google.'.format(list_id))
        sitemap = path.join(self.sitemap_dir, 'sitemap{}_{}_{}.xml'.format(_hl, shard, numshards))

        # Download the IDs list
        resp = _http_get(list_url, self.session, stream=False, headers=make_download_headers())
        if resp is None:
            logging.critical('Failed to download list of extensions.')
            raise ListDownloadFailedError('Unable to download extension list {}.'.format(list_id))

        # Save the list
        with open(sitemap, 'wb') as fout:
            for chunk in resp.iter_content(chunk_size=None):
                fout.write(chunk)
        del resp

        # Extract the IDs
        ids = set()
        xml_tree = etree.parse(sitemap)
        for url_tag in xml_tree.iterfind('*/' + self._ns + 'loc'):
            # Get just the URL path (strips the scheme, netloc, params, query, and fragment segments)
            crx_id = urlparse(url_tag.text).path
            # Get the ID (strips everything from the path except the last part)
            crx_id = path.basename(crx_id)
            ids.add(crx_id)

        # Delete the list
        remove(sitemap)

        return ids

    def __len__(self):
        return len(self._id_list)


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
