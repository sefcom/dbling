# -*- coding: utf-8 -*-

from api_connectors.google import GoogleAPI
from util import print_json


class GmailAPI(GoogleAPI):

    _service_name = 'gmail'
    _version = 'v1'

    def __init__(self, http):
        """
        Sets service object to make API calls to Google

        :param http: http object
        """
        super().__init__(http)

    def get_labels(self):
        """
        returns a list of mailbox labels

        :return: JSON
        """
        results = self.service.users().labels().list(userId='me').execute()
        return results

    def get_all(self):
        """
        method used for testing

        :return: nothing
        """
        if True:
            labels = self.get_labels()
            print_json(labels)

