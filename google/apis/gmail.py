# -*- coding: utf-8 -*-

from apis.google import GoogleAPI
from util import print_json


class GmailAPI(GoogleAPI):
    """Class to interact with Google Gmail APIs.
    """

    _service_name = 'gmail'
    _version = 'v1'

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

