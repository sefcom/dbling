from util import print_json
from apiclient import discovery


class GmailAPI:

    def __init__(self, http):
        """
        Sets service object to make API calls to Google
        :param http: http object
        """
        self.service = discovery.build('gmail', 'v1', http=http)

    def get_labels(self):
        """
        returns a list of mailbox labesl
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

