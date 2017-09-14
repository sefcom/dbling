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
from munch import Munch
from oauth2client import client, tools
from oauth2client.file import Storage

import const


class InvalidCredsError(Exception):
    """Raised when HTTP credentials don't work."""


class MissingConfigWarning(Warning):
    """"""


class CalMunch(Munch):
    """A :class:`dict`-like class for storing hourly data for a whole year.

    This is intended to have a set of keys that correspond to years. Since
    Python's syntax dictates that objects cannot have attributes with names
    consisting only of numbers (e.g. ``cal.2017``), one solution would be to
    name the year keys ``cal.y2017``, ``cal.y2016``, etc. This is the intended
    convention for :class:`CalMunch` objects and aligns with how month and day
    data is named.

    Once you have created an instance of :class:`CalMunch`, you can easily
    create the structures necessary to store a year's worth of data like so:

    >>> cal = CalMunch()
    >>> cal.y2017

    Just accessing the ``y2017`` attribute assigns it to be a
    :class:`~munch.Munch` object with 12 keys, one for each month, named
    ``m01``, ``m02``, ... ``m12``. Each of those keys points to a
    :class:`~munch.Munch` object with 31 keys, named ``d01`` through ``d31``.
    The day keys point to a list of 24 integers, initialized to ``0``. This
    allows you to increment the value for a particular hour immediately after
    instantiation, like the following, which increments the counter for the
    2 PM hour block on August 31, 2016:

    >>> cal2 = CalMunch()
    >>> cal2.y2016.m08.d31[14] += 1
    """

    def __getattr__(self, k):
        try:
            # Throws exception if not in prototype chain
            return object.__getattribute__(self, k)
        except AttributeError:
            try:
                return self[k]
            except KeyError:
                # Populate this with months, days, hours
                self[k] = Munch({
                    'm{:02}'.format(x): Munch({
                        'd{:02}'.format(y): [0]*24 for y in range(1, 32)
                    }) for x in range(1, 13)
                })
                return self[k]


def get_credentials(scope=const.SCOPES, application_name=const.APPLICATION_NAME, secret=const.CLIENT_SECRET_FILE,
                    credential_file=const.CREDENTIAL_FILE):
    """Create the credential file for accessing the Google APIs.

    https://developers.google.com/drive/v3/web/quickstart/python

    :param str scope: String of Scopes separated by spaces to give access to
        different Google APIs.
    :param str application_name: Name of this Application.
    :param str secret: The secret file given from Google. Should be named
        ``client_secret.json``.
    :param str credential_file: Name of the credential file to be created.
    :return: Credential object.
    :raises InvalidCredsError: if the credential file is missing or invalid.
    """
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


def set_http(is_domain_wide=False, impersonated_user_email=None):
    """Create and return the http object used to communicate with Google.

    https://developers.google.com/drive/v3/web/quickstart/python

    :param boolean is_domain_wide: Turn to True if using domain wide delegation
        to impersonate a user
    :param str impersonated_user_email: Email address of the User to be
        impersonated.
    :return: http object or False if incorrect parameters are given.
    :raises InvalidCredsError: if the credential file is missing or invalid.
    """
    simplefilter('ignore', MissingConfigWarning)
    with catch_warnings(record=True) as w:
        simplefilter('always', MissingConfigWarning)
        credentials = get_credentials()

        if len(w):
            print('\n{}\n'.format(w.pop().message))

    if is_domain_wide:
        if impersonated_user_email is None:
            print('If using domain wide authority please supply an email to impersonate.')
            http = False
        else:
            http = credentials.create_delegated(impersonated_user_email)
    else:
        http = credentials.authorize(httplib2.Http())

    return http


# Was going to fix and make this better. Google APIs return json so just made a simple print_json method.
def pretty_print(obj):
    """
    Method to print json

    :param obj: JSON object
    :return: nothing
    """
    if type(obj) == dict:
        for k, v in obj.items():
            if hasattr(v, '__iter__'):
                print(k)
                pretty_print(v)
            else:
                print('%s : %s' % (k, v))
    elif type(obj) == list:
        for v in obj:
            if hasattr(v, '__iter__'):
                pretty_print(v)
            else:
                print(v)
    else:
        print(obj)


def print_json(obj):
    """Print the JSON object in a human readable format.

    :param obj: JSON object
    :type obj: dict or list
    :rtype: None
    """
    print(json.dumps(obj, sort_keys=True, indent=2))


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
