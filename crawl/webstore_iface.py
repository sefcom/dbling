#!/usr/bin/env python3
# *-* coding: utf-8 *-*


import logging
from os import path
from lxml import etree
import requests
from requests.exceptions import ChunkedEncodingError
from time import sleep

__all__ = ['download_crx_list', 'ListDownloadFailedError']

LOG_PATH = path.join(path.dirname(path.realpath(__file__)), '../log', 'crx.log')
DBLING_DIR = path.abspath(path.join(path.dirname(path.realpath(__file__)), '..'))
DONT_OVERWRITE_DOWNLOADED_CRX = False
CHUNK_SIZE = 512
NUM_HTTP_RETIRES = 5


class ListDownloadFailedError(ConnectionError):
    """Raised when the list download fails."""


def download_crx_list(ext_url, session=None, show_progress=False):
    """Generate list of extension IDs downloaded from Google.

    :param ext_url:
    :param session:
    :type session: requests.Session
    :param show_progress:
    :return:
    """
    logging.info('Downloading list of extensions from Google.')
    resp = _http_get(ext_url, session, stream=False)
    if resp is None:
        logging.critical('Failed to download list of extensions.')
        raise ListDownloadFailedError('Unable to download list of extensions.')

    # Save the list
    local_sitemap = path.join(DBLING_DIR, 'src', 'chrome_sitemap.xml')
    with open(local_sitemap, 'wb') as fout:
        for chunk in resp.iter_content(chunk_size=None):
            fout.write(chunk)
    del resp

    logging.debug('Download finished. Parsing XML and yielding extension IDs.')
    xml_tree_root = etree.parse(local_sitemap).getroot()  # Downloads for us from the URL
    ns = '{http://www.sitemaps.org/schemas/sitemap/0.9}'

    count = 0
    for url_elm in xml_tree_root.iterfind(ns + 'url'):
        yield path.basename(url_elm.findtext(ns + 'loc'))[:32]  # This is the CRX ID
        count += 1
        if show_progress and not count % 1000:
            print('.', end='', flush=True)

    if show_progress:
        print(count, flush=True)
    logging.debug('Done parsing list of extensions.')


class RetryRequest(object):
    """Wraps functions that make HTTP requests, retries on failure."""

    def __init__(self, f):
        self.f = f

    def __call__(self, *args, **kwargs):
        resp = None
        for i in range(NUM_HTTP_RETIRES):
            try:
                resp = self.f(*args, **kwargs)
            except ChunkedEncodingError:
                sleep(10 * (i+1))
            else:
                break
        return resp


@RetryRequest
def _http_get(url, session=None, stream=True):
    """

    :param url:
    :param session:
    :return:
    """
    if session is None:
        return requests.get(url, stream=stream)
    elif isinstance(session, requests.Session):
        return session.get(url, stream=stream)
