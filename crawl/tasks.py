# *-* coding: utf-8 *-*

import logging
from uuid import uuid4 as uuid

from crawl.celery import app
from crawl.serius import Cacher, make_keyable
# from crawl.db import db_session,SqlAlchemyTask
from crawl.webstore_iface import *
from crawl.crx_conf import conf as _conf
from crawl.util import calc_chrome_version

STAT_PREFIX = 'dbling:'
CHROME_VERSION = calc_chrome_version(_conf['version'], _conf['release_date'])
DOWNLOAD_URL = _conf['url']


@app.task
def start_list_download(show_progress=False):
    _run_id = uuid()
    count = 0
    for crx in download_crx_list(_conf['extension_list_url'], show_progress=show_progress):
        # Add to database
        # Add to download queue
        logging.info(crx)
        count += 1
        if count > 10:
            logging.warning('Wahoo! I\'m gettin outta here!')
            break

    # email that _run_id has completed
    pass


@app.task
def log_it(action, crx_id, lvl=logging.DEBUG):
    logging.log(lvl, '%s  %s complete' % (crx_id, action))


@app.task
def stat(stat_type):
    """Use memcached to store/retrieve the current stats dictionary.

    See https://www.tutorialspoint.com/memcached/index.htm for good documentation.

    :param stat_type: The string describing the statistic.
    :type stat_type: str
    """
    cache_key = make_keyable('{}{}'.format(STAT_PREFIX, stat_type))
    ret = Cacher.incr(cache_key, 1, noreply=False)

    # incr returns None if the key wasn't found, so let's add it
    if ret is None:
        # add() will be False if the key already exists, meaning we hit a race condition
        if not Cacher.add(cache_key, 1, noreply=False):
            stat.retry(stat_type)
        else:
            # Add this key to the list of keys
            if not Cacher.append(STAT_PREFIX + 'KEYS', '{}\n'.format(stat_type), noreply=False):
                # Key must not have already existed... Here we go again.
                if not Cacher.add(STAT_PREFIX + 'KEYS', '{}\n'.format(stat_type)):
                    # At this point, why even check for race conditions?
                    Cacher.append(STAT_PREFIX + 'KEYS', '{}\n'.format(stat_type), noreply=False)


def save_stats():
    """Retrieve stats from memcached and save them to disk."""
    # TODO: Retrieve stats
    # TODO: Delete caches
    raise NotImplementedError




# # Example database-using task
# @app.task(base=SqlAlchemyTask)
# def get_from_db(user_id):
#     user = db_session.query(User).filter(id=user_id).one()
#     # do something with the user
