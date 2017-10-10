# -*- coding: utf-8 -*-

from apis.google import GoogleAPI
from util import print_json


class PeopleAPI(GoogleAPI):
    """Class to interact with Google People APIs. """

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
