# *-* coding: utf-8 *-*
"""Context manager for easily using a pymemcache mutex.

The `acquire_lock` context manager makes it easy to use :mod:`pymemcache` (which
uses memcached) to create a mutex for a certain portion of code. Of course,
this requires the :mod:`pymemcache` library to be installed, which in turn
requires `memcached <https://memcached.org>`_ to be installed.
"""

import json
import logging
from contextlib import contextmanager
from time import sleep

from pymemcache.client.base import Client

__all__ = ['acquire_lock', 'LockUnavailable']


class LockUnavailable(Exception):
    """Raised when a cached lock is already in use."""


def json_serializer(key, value):
    # Borrowed from the pymemcache docs: https://pymemcache.readthedocs.io/en/latest/getting_started.html#serialization
    if type(value) == str:
        return value, 1
    return json.dumps(value), 2


def json_deserializer(key, value, flags):
    # Borrowed from the pymemcache docs: https://pymemcache.readthedocs.io/en/latest/getting_started.html#serialization
    if flags == 1:
        return value
    if flags == 2:
        return json.loads(value)
    raise Exception("Unknown serialization format")


cache_client = Client(('localhost', 11211), serializer=json_serializer, deserializer=json_deserializer)


@contextmanager
def acquire_lock(lock_id, wait=0, max_retries=0):
    """Acquire a lock on the given lock ID, or raise an exception.

    This context manager can be used as a mutex by doing something like the
    following:

    >>> from time import sleep
    >>> job_done = False
    >>> while not job_done:
    ...     try:
    ...         with acquire_lock('some id'):
    ...             sensitive_function()
    ...             job_done = True
    ...     except LockUnavailable:
    ...         # Sleep for a couple seconds while the other code runs and
    ...         # hopefully completes
    ...         sleep(2)

    In the above example, ``sensitive_function()`` should only be run if no
    other code is also running it. A more concise way of writing the above
    example would be to use the other parameters, like this:

    >>> with acquire_lock('some id', wait=2):
    ...     sensitive_function()

    :param lock_id: The ID for this lock. See :mod:`pymemcache`'s documentation
        on `key constraints
        <https://pymemcache.readthedocs.io/en/latest/getting_started.html#key-constraints>`_
        for more info.
    :type lock_id: str or bytes
    :param int wait: Indicates how many seconds after failing to acquire the
        lock to wait (sleep) before retrying. When set to 0 (default), will
        immediately raise a `LockUnavailable` exception.
    :param int max_retries: Maximum number of times to retry to acquire the
        lock before raising a `LockUnavailable` exception. When set to 0
        (default), will always retry. Has essentially no effect if ``wait`` is
        0.
    :raises LockUnavailable: when a lock with the same ID already exists and
        ``wait`` is set to 0.
    """
    assert isinstance(lock_id, str) or isinstance(lock_id, bytes)
    if (not isinstance(wait, int)) or wait < 0:
        wait = 0
    if (not isinstance(max_retries, int)) or max_retries < 0:
        max_retries = 0

    # Get lock
    retries = 0
    while retries <= max_retries:
        if cache_client.add(lock_id, str('Locked by dbling')):  # We got the lock
            break
        if wait == 0:
            raise LockUnavailable
        if max_retries > 0:
            retries += 1
        logging.info('Unable to acquire lock "{}". Will retry in {} seconds.'.format(lock_id, wait))
        sleep(wait)

    # Tell the `with` statement to execute
    yield

    # Release lock, don't wait for the reply
    cache_client.delete(lock_id, noreply=True)
