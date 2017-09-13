# -*- coding: utf-8 -*-

from apiclient import discovery


class GoogleAPI:

    _service_name = NotImplemented
    _version = NotImplemented

    def __init__(self, http):
        if NotImplemented in (self._service_name, self._version):
            raise ValueError('Implementing classes of GoogleAPI must set a value for _service_name and _version.')
        self.service = discovery.build(serviceName=self._service_name, version=self._version, http=http)

    def get_all(self):
        raise NotImplementedError
