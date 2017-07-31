from api_connectors.drive import DriveAPI
from api_connectors.plus import PlusAPI
from api_connectors.people import PeopleAPI
from api_connectors.g_suite_admin import GSuiteAdminAPI

import util


def main():

    http = util.set_http()

    if not http:
        print("If using domain wide authority please supply an email to impersonate.")

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
        admin = GSuiteAdminAPI(http)
        admin.get_all()

    # Domain wide delegation of authority




if __name__ == '__main__':
    main()
