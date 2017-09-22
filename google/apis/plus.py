# -*- coding: utf-8 -*-

from apis.google import GoogleAPI
from util import print_json


class PlusAPI(GoogleAPI):

    _service_name = 'plus'
    _version = 'v1'

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
