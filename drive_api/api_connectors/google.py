# -*- coding: utf-8 -*-

from apiclient import discovery
from maya import get_localzone

from util import set_http


class GoogleAPI:

    _service_name = NotImplemented
    _version = NotImplemented

    def __init__(self, http=None, impersonated_user_email=None, timezone=None):
        if NotImplemented in (self._service_name, self._version):
            raise ValueError('Implementing classes of GoogleAPI must set a value for _service_name and _version.')

        if http is None:
            http = set_http(impersonated_user_email=impersonated_user_email)

        # By default, set the timezone to whatever the local timezone is. Otherwise set it to what the user specified.
        if timezone is None or not isinstance(timezone, str):
            self.tz = str(get_localzone())
        else:
            self.tz = timezone

        self.service = discovery.build(serviceName=self._service_name, version=self._version, http=http)

    def get_all(self):
        raise NotImplementedError
