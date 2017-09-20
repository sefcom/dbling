#!/usr/bin/env python3

import util
from api_connectors import *


def main():

    http = util.set_http()

    if not http:
        print('Errors have occurred. Note above for solutions.')
        # yeah its bad practice to return in the middle of a file. but oh well this file is just for testing
        return False
    # Get Drive Data
    if True:
        drive = DriveAPI(http)
        drive.get_all()
    # Get Plus Data
    if False:
        plus = PlusAPI(http)
        plus.get_all()
    # Get People Data
    if False:
        people = PeopleAPI(http)
        people.get_all()
    if False:
        directory = GSuiteDirectoryAPI(http)
        directory.get_all()
    if False:
        gmail = GmailAPI(http)
        gmail.get_all()
    if False:
        reports = AdminAPI(http)
        reports.get_all()
    # Domain wide delegation of authority


def get(api, **kwargs):
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


if __name__ == '__main__':
    main()
