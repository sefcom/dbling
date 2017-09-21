from api_connectors.drive import DriveAPI
from api_connectors.g_suite_directory_v1 import GSuiteDirectoryAPI
from api_connectors.admin import AdminAPI
from api_connectors.gmail import GmailAPI
from api_connectors.people import PeopleAPI
from api_connectors.plus import PlusAPI

__all__ = ['DriveAPI', 'GSuiteDirectoryAPI', 'AdminAPI', 'GmailAPI', 'PeopleAPI', 'PlusAPI']


def get_api(api, **kwargs):
    a = {'drive': DriveAPI,
         'plus': PlusAPI,
         'people': PeopleAPI,
         'dir': GSuiteDirectoryAPI,
         'gmail': GmailAPI,
         'admin': AdminAPI,
         }
    try:
        return a[api](**kwargs)
    except KeyError:
        raise ValueError('Specified API must be one of:\n{}'.format(list(a.keys())))
