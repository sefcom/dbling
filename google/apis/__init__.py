from apis.drive import DriveAPI
from apis.admin import ReportsAPI, DirectoryAPI
from apis.gmail import GmailAPI
from apis.people import PeopleAPI
from apis.plus import PlusAPI

__all__ = ['DriveAPI', 'GSuiteDirectoryAPI', 'AdminAPI', 'GmailAPI', 'PeopleAPI', 'PlusAPI']


def get_api(api, **kwargs):
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
