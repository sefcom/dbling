#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import stat
from datetime import datetime, date, timedelta
from os import path
from subprocess import check_output

from munch import *

from common.centroid import USED_FIELDS
from common.clr import add_color_log_levels
from common.const import mode_to_unix, USED_TO_DB

__all__ = ['validate_crx_id', 'MalformedExtId', 'add_color_log_levels', 'get_crx_version', 'calc_chrome_version',
           'get_id_version']


PROGRESS_PERIOD = 100


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
    try:
        assert isinstance(crx_id, str)
        assert crx_id.isalnum()
        assert len(crx_id) == 32
    except AssertionError:
        raise MalformedExtId


class MalformedExtId(Exception):
    """Raised when an ID doesn't have the correct form."""


def get_crx_version(crx_path):
    """
    From the path to a CRX, extract and return the version number as a string.

    The return value from the download() function is in the form:
    <extension ID>_<version>.crx

    The <version> part of that format is "x_y_z" for version "x.y.z". To
    convert to the latter, we need to 1) get the basename of the path, 2) take
    off the trailing ".crx", 3) remove the extension ID and '_' after it, and
    4) replace all occurrences of '_' with '.'.

    :param crx_path: The full path to the downloaded CRX, as returned by the
                     download() function.
    :type crx_path: str
    :return: The version number in the form "x.y.z".
    :rtype: str
    """
    # TODO: This approach has some issues with catching some outliers that don't match the regular pattern
    ver_str = path.basename(crx_path).split('.crx')[0].split('_', 1)[1]
    return ver_str.replace('_', '.')


def get_id_version(crx_path):
    """From the path to a CRX, extract and return the ID and version as strings.

    :param crx_path: The full path to the downloaded CRX.
    :type crx_path: str
    :return: The ID and version number as a tuple: (id, num)
    :rtype: tuple
    """
    crx_id, ver_str = path.basename(crx_path).split('.crx')[0].split('_', 1)
    ver_str = ver_str.replace('_', '.')
    return crx_id, ver_str


def separate_mode_type(mode):
    """
    Separate out the values for the mode (permissions) and the file type from
    the given mode.

    Both returned values are integers. The mode is just the permissions
    (usually displayed in the octal format), and the type corresponds to the
    standard VFS types:

    * 0: Unknown file
    * 1: Regular file
    * 2: Directory
    * 3: Character device
    * 4: Block device
    * 5: Named pipe (identified by the Python stat library as a FIFO)
    * 6: Socket
    * 7: Symbolic link

    :param mode: The mode value to be separated.
    :type mode: int
    :return: Tuple of ints in the form: (mode, type)
    :rtype: tuple
    """
    m = stat.S_IMODE(mode)
    t = stat.S_IFMT(mode)
    return m, mode_to_unix(t)


def calc_chrome_version(last_version, release_date, release_period=10):
    """
    Calculate the most likely version number of Chrome is based on the last
    known version number and its release date, based on the number of weeks
    (release_period) it usually takes to release the next major version. A
    list of releases and their dates is available at
    https://en.wikipedia.org/wiki/Google_Chrome_release_history.

    :param last_version: Last known version number, e.g. "43.0". Should only
                         have the major and minor version numbers and exclude
                         the build and patch numbers.
    :type last_version: str
    :param release_date: Release date of the last known version number. Must
                         be a list of three integers: [YYYY, MM, DD].
    :type release_date: list
    :param release_period: Typical number of weeks between releases.
    :type release_period: int
    :return: The most likely current version number of Chrome in the same
             format required of the last_version parameter.
    :rtype: str
    """
    base_date = date(release_date[0], release_date[1], release_date[2])
    today = date.today()
    td = int((today - base_date) / timedelta(weeks=release_period))
    return str(float(last_version) + td)


def make_download_headers():
    # TODO: Make this actually generate a random user-agent string
    head = {'Upgrade-Insecure-Requests': '1',
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2883.87 '
                          'Safari/537.36'}
    return head


def dt_dict_now():
    now = datetime.today()
    val = {'year': now.year,
           'month': now.month,
           'day': now.day,
           'hour': now.hour,
           'minute': now.minute,
           'second': now.second,
           'microsecond': now.microsecond,
           }
    return val


def dict_to_dt(dt_dict):
    return datetime(**dt_dict)


def cent_vals_to_dict(cent_vals):
    # Match up the field names with their values for easier insertion to the DB later
    cent_dict = {}
    for k, v in zip((USED_FIELDS + ('_c_size',)), cent_vals):
        cent_dict[USED_TO_DB[k]] = v
    return cent_dict


class MunchyMunch:
    def __init__(self, f):
        """Wrapper class to munchify crx_obj parameter.

        This wrapper converts either the kwarg `crx_obj` or the first
        positional argument (tests in that order) to a Munch object, which
        allows us to refer to keys in the Munch dictionary as if they were
        attributes. See the docs on the munch library for more information.

        :param f: The function to wrap.
        """
        self.f = f
        self.__module__ = self.f.__module__
        self.__name__ = self.f.__name__  # TODO: This is giving tasks odd names

    def __call__(self, *args, **kwargs):
        kw_done = False
        if len(kwargs):
            crx_obj = munchify(kwargs.get('crx_obj'))
            if crx_obj is not None and isinstance(crx_obj, Munch):
                kwargs['crx_obj'] = crx_obj
                kw_done = True
        if not kw_done and len(args):
            args = (munchify(args[0]),) + args[1:]
        return self.f(*args, **kwargs)


def byte_len(s):
    """Return the length of `s` in number of bytes.

    :param str|bytes s: The string or bytes to test.
    :return: The length of `s` in bytes.
    :rtype: int
    :raises: TypeError if `s` is not a str or bytes.
    """
    if isinstance(s, str):
        return len(s.encode())
    elif isinstance(s, bytes):
        return len(s)
    else:
        raise TypeError('Cannot determine byte length for type {}'.format(type(s)))


def ttl_files_in_dir(dir_path, pat='.'):
    """Count the files in the given directory.

    Will count all files except `.` and `..`, including any files whose names
    begin with `.` (using the `-A` option of `ls`).

    :param str dir_path: Path to the directory.
    :param str pat: Pattern the files should match when searching. This is
        passed to `grep`, so when the default remains ".", it will match all
        files and thus not filter out anything.
    :return: The number of files in the directory.
    :rtype: int
    :raises: NotADirectoryError When `dir_path` is not a directory.
    """
    if not path.isdir(dir_path):
        raise NotADirectoryError

    # In a subprocess, count list the files in the dir and count them, convert output to an int
    ttl = int(check_output('ls -A -U --color=never {} | grep {} | wc -l'.format(dir_path, pat), shell=True).strip())

    return ttl
