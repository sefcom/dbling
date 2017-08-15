from api_connectors.drive import DriveAPI
from api_connectors.plus import PlusAPI
from api_connectors.people import PeopleAPI
from api_connectors.g_suite_directory_v1 import GSuiteDirectoryAPI
from api_connectors.gmail import GmailAPI
from api_connectors.g_suite_reports_v1 import GSuiteReportsAPI

import util


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
        reports = GSuiteReportsAPI(http)
        reports.get_all()
    # Domain wide delegation of authority


if __name__ == '__main__':
    main()