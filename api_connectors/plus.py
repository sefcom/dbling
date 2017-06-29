from util import print_json
from apiclient import discovery


class PlusAPI:

    def __init__(self, http):

        self.service = discovery.build('plus', 'v1', http=http)

    def get_me(self):
        me = self.service.people().get(userId='me').execute()
        return me

    def get_all(self):
        me = self.get_me()
        print_json(me)
