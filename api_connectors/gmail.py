from util import print_json
from apiclient import discovery


class GmailAPI:

    def __init__(self, http):
        self.service = discovery.build('gmail', 'v1', http=http)

    def get_labels(self):
        results = self.service.users().labels().list(userId='me').execute()
        return results

    def get_all(self):
        if True:
            labels = self.get_labels()
            print_json(labels)

