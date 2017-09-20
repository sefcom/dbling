# -*- coding: utf-8 -*-

from api_connectors.google import GoogleAPI
from util import print_json


class PeopleAPI(GoogleAPI):

    _service_name = 'people'
    _version = 'v1'

    # TODO paging
    def get_contacts(self):
        """
        returns list of contacts for the authenticated user

        :return: JSON
        """
        contacts = self.service.people().connections().list(resourceName='people/me',
                                                            personFields='names,emailAddresses').execute()
        return contacts

    def get_all(self):
        """
        method used for testing

        :return: nothing
        """
        if True:
            contacts = self.get_contacts()
            print_json(contacts)
