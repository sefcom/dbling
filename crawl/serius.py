# *-* coding: utf-8 *-*
from json import dumps, loads
from json.decoder import JSONDecodeError
from unicodedata import category as unicat

from pymemcache.client.base import Client

__all__ = ['Cacher', 'DeserializeError', 'make_keyable']

HOST = 'localhost'
PORT = 12321


class DeserializeError(ValueError):
    """Raised when deserializer finds an invalid format flag."""


def json_serializer(key, value):
    """Serialize value into JSON.

    Based on the code in the documentation at:
    https://pymemcache.readthedocs.io/en/latest/apidoc/pymemcache.client.base.html

    :param key: The key. Not used in this function.
    :param value: Any serializable object.
    :return: JSON of the object
    :rtype: str
    """
    if isinstance(value, str):
        return value, 1
    return dumps(value), 2


def json_deserializer(key, value, flag):
    """Deserialize value back to original format.

    :param key: The key. Not used in this function.
    :param value: The JSON of the original value.
    :type value: str
    :param flag: The flag set in the serializer function. 1 means it was
        already a string. 2 means it was serialized to JSON.
    :return: The original value stored at the memcache key ``key``.
    """
    opts = {1: lambda v: v,
            2: lambda v: loads(v)}
    try:
        opts[flag](value)
    except (KeyError, JSONDecodeError):
        raise DeserializeError('Unknown serialization format.')


def make_keyable(key):
    """Remove all whitespace and control characters w/max length 250."""
    return (''.join(ch for ch in key if unicat(ch)[0] not in 'CZ'))[:250]


Cacher = Client((HOST, PORT), serializer=json_serializer, deserializer=json_deserializer)
