"""
Google API Client Library Page
https://developers.google.com/api-client-library/python/reference/pydoc
Python Quick Start Page
https://developers.google.com/drive/v3/web/quickstart/python
"""

import json
from os import path, makedirs
from warnings import warn, simplefilter, catch_warnings

import httplib2
from oauth2client import client, tools
from oauth2client.file import Storage

try:
    import const
except ImportError:
    import sys
    sys.path.append(path.abspath(path.dirname(__file__)))
    import const


class InvalidCredsError(Exception):
    """Raised when HTTP credentials don't work."""


class MissingConfigWarning(Warning):
    """"""


class CalDict(dict):
    """A :class:`dict`-like class for storing hourly data for a year.

    This is intended to have a set of keys that correspond to years. Since
    Python's syntax dictates that objects cannot have attributes with names
    consisting only of numbers (e.g. ``cal.2017``), one solution would be to
    name the year keys ``cal.y2017``, ``cal.y2016``, etc. This is the intended
    convention for :class:`CalDict` objects and aligns with how month and day
    data is named.

    Once you have created an instance of :class:`CalDict`, you can easily
    create the structures necessary to store a year's worth of data like so:

    >>> cal = CalDict()
    >>> cal[2017]

    Just accessing the ``2017`` key (which is an :class:`int`) assigns its value
    to be a :class:`dict` with 12 keys, one for each month, numbered ``1``
    through ``12``. Each of those keys points to a :class:`dict` object with 31
    keys, numbered ``1`` through ``31``. The day keys point to a :class:`list`
    of 24 integers, initialized to ``0``. This allows you to increment the
    value for a particular hour immediately after instantiation, like the
    following, which increments the counter for the 2 PM hour block on August
    31, 2016:

    >>> cal2 = CalDict()
    >>> y, m, d = 2016, 8, 31
    >>> cal2[y][m][d][14] += 1

    Since all months in a :class:`CalDict` instance have 31 days, I recommend
    you use an external method of validating a particular date before storing
    or retrieving data.
    """

    def __getitem__(self, k):
        try:
            return super().__getitem__(k)
        except KeyError:
            # Populate this with months, days, hours
            super().__setitem__(k, {
                m: {d: [0]*24 for d in range(1, 32)}
                for m in range(1, 13)
            })
            return super().__getitem__(k)


class DateRange:
    def __init__(self, start=None, end=None):
        self.start = start
        self.end = end

    def __iter__(self):
        return [self.start, self.end].__iter__()


def get_credentials(scope=None, application_name=None, secret=None, credential_file=None):
    """Create the credential file for accessing the Google APIs.

    https://developers.google.com/drive/v3/web/quickstart/python

    :param str scope: String of Scopes separated by spaces to give access to
        different Google APIs. Defaults to :data:`~google.const.SCOPES`.
    :param str application_name: Name of this Application. Defaults to
        :data:`~google.const.APPLICATION_NAME`.
    :param str secret: The secret file given from Google. Should be named
        ``client_secret.json``. Defaults to
        :data:`~google.const.CLIENT_SECRET_FILE`.
    :param str credential_file: Name of the credential file to be created.
        Defaults to :data:`~google.const.CREDENTIAL_FILE`.
    :return: Credential object.
    :raises InvalidCredsError: if the credential file is missing or invalid.
    """
    # Set default values
    if scope is None:
        scope = const.SCOPES
    if application_name is None:
        application_name = const.APPLICATION_NAME
    if secret is None:
        secret = const.CLIENT_SECRET_FILE
    if credential_file is None:
        credential_file = const.CREDENTIAL_FILE

    cur_dir = path.dirname(path.realpath('__FILE__'))
    secret = str(secret)
    credential_file = str(credential_file)

    # Check that the client secret file is accessible
    secret_file_path = path.join(cur_dir, secret)
    if not path.isfile(secret_file_path):
        raise InvalidCredsError(
            'Client Secret File is missing.\n'
            'Please go to: https://developers.google.com/drive/v3/web/quickstart/python\n'
            'To set up the secret file for OAuth 2.0')

    # Create the directory for credentials (if necessary)
    credential_dir = path.join(cur_dir, '.credentials')
    makedirs(credential_dir, exist_ok=True)

    # Fallback to using the default credential filename if none specified
    if not len(credential_file):
        credential_file = 'test_creds.json'
        warn('Filename for credential file not set. Defaulting to: {}'.format(credential_file),
             MissingConfigWarning)
    credential_path = path.join(credential_dir, credential_file)

    # Store the OAuth credential locally
    store = Storage(credential_path)
    credentials = store.get()
    if not credentials or credentials.invalid:
        flow = client.flow_from_clientsecrets(secret, scope)
        flow.user_agent = application_name
        credentials = tools.run_flow(flow, store)
    return credentials


def set_http(impersonated_user_email=None):
    """Create and return the Http object used to communicate with Google.

    https://developers.google.com/drive/v3/web/quickstart/python

    :param str impersonated_user_email: Email address of the User to be
        impersonated. This uses domain wide delegation to do the impersonation.
    :return: The Http object.
    :rtype: httplib2.Http
    :raises InvalidCredsError: if the credential file is missing or invalid.
    """
    simplefilter('ignore', MissingConfigWarning)
    with catch_warnings(record=True) as w:
        simplefilter('always', MissingConfigWarning)
        credentials = get_credentials()

        if len(w):
            # TODO: Change this to log the message instead of print it
            print('\n{}\n'.format(w.pop().message))

    if impersonated_user_email is not None:
        http = credentials.create_delegated(impersonated_user_email)
    else:
        http = credentials.authorize(httplib2.Http())

    return http


def print_json(obj, sort=False, indent=2):
    """Print the JSON object in a human readable format.

    :param obj: JSON-serializable object.
    :type obj: dict or list
    :param bool sort: Whether to sort the keys before printing.
    :param int indent: Number of spaces to indent.
    :rtype: None
    """
    print(json.dumps(obj, sort_keys=bool(sort), indent=indent if isinstance(indent, int) else None))


def convert_mime_type_and_extension(google_mime_type):
    """Return the conversion type and extension for the given Google MIME type.

    Converts mimeType given from google to one of our choosing for export conversion
    This is necessary to download .g* files.

    Information on MIME types:

    - https://developers.google.com/drive/v3/web/mime-types
    - https://developers.google.com/drive/v3/web/integrate-open

    :param str google_mime_type: mimeType given from Google API
    :return: Tuple in the form (conversion type, extension). If no supported
        conversion is supported for the given MIME type, the tuple will be
        ``(False, False)``.
    :rtype: tuple
    """
    return const.CONVERSION.get(const.EMIM[google_mime_type], (False, False))
