try:
    from apis.drive import DriveAPI
except ImportError:
    import sys
    from os import path
    sys.path.append(path.abspath(path.join(path.dirname(__file__), '..')))
    del sys, path
    from apis.drive import DriveAPI
from apis.admin import ReportsAPI, DirectoryAPI
from apis.gmail import GmailAPI
from apis.people import PeopleAPI
from apis.plus import PlusAPI

__all__ = ['DriveAPI', 'DirectoryAPI', 'ReportsAPI', 'GmailAPI', 'PeopleAPI', 'PlusAPI']


def get_api(api, **kwargs):
    """Shortcut for creating an API object.

    :param str api: Name of the API to instantiate. Acceptable values are:

        - ``'drive'``
        - ``'plus'``
        - ``'people'``
        - ``'dir'``
        - ``'gmail'``
        - ``'reports'``
    :param dict kwargs: Set of keyword arguments to pass to the object's
        constructor.
    :return: An instance of the created object.
    :rtype: DriveAPI or PlusAPI or PeopleAPI or DirectoryAPI or GmailAPI or
        ReportsAPI
    """
    a = {'drive': DriveAPI,
         'plus': PlusAPI,
         'people': PeopleAPI,
         'dir': DirectoryAPI,
         'gmail': GmailAPI,
         'reports': ReportsAPI,
         }
    try:
        return a[api](**kwargs)
    except KeyError:
        raise ValueError('Specified API must be one of:\n{}'.format(list(a.keys())))
