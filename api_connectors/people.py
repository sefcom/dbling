from util import print_json
from apiclient import discovery


class PeopleAPI:

    def __init__(self, http):
        self.service = discovery.build('people', 'v1', http=http)

    # TODO paging
    def get_contacts(self):
        contacts = self.service.people().connections().list(resourceName='people/me',
                                                            personFields='names,emailAddresses').execute()
        return contacts

    # Permission issue, use plus instead
    def get_profile(self):
        profile = self.service.people().get(resourceName='people/me', personFields='names,emailAddresses').execute()
        return profile

    def get_all(self):
        if True:
            contacts = self.get_contacts()
            print_json(contacts)

