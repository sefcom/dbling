from util import print_json
from apiclient import discovery


class GmailAPI:

    def __init__(self, http):
        self.service = discovery.build('gmail', 'v1', http=http)

