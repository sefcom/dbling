from apiclient import discovery

from util import print_json


class PlusAPI:

    def __init__(self, http):
        """
        Sets service object to make API calls to Google

        :param http: http object
        """
        self.service = discovery.build('plus', 'v1', http=http)

    def get_me(self):
        """
        returns Google+ information for the current user

        :return:
        """
        me = self.service.people().get(userId='me').execute()
        return me

    def get_all(self):
        """
        method used for testing

        :return: nothing
        """
        me = self.get_me()
        print_json(me)
