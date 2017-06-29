from api_connectors.drive import DriveAPI
from api_connectors.plus import PlusAPI
from api_connectors.people import PeopleAPI
import util


def main():

    http = util.set_http()

    # Get Drive Data
    if False:
        drive = DriveAPI(http)
        drive.get_all()
    # Get Plus Data
    if True:
        plus = PlusAPI(http)
        plus.get_all()
    # Get People Data
    if True:
        people = PeopleAPI(http)
        people.get_all()

if __name__ == '__main__':
    main()
