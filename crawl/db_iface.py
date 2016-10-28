# *-* coding: utf-8 *-*

from __future__ import absolute_import

import logging

from celery import Task
from sqlalchemy import select, update, and_
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.orm import scoped_session, sessionmaker

from common.chrome_db import DB_ENGINE, extension, id_list
from common.util import MunchyMunch, dict_to_dt
from crawl.celery import app

__all__ = ['add_new_crx_to_db', 'db_download_complete', 'db_extract_complete', 'db_profile_complete',
           'DuplicateDownload', 'SqlAlchemyTask']

DB_SESSION = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=DB_ENGINE))
READ_ONLY = True


class DuplicateDownload(Exception):
    """Raised when the DB already has a version of the extension."""


class SqlAlchemyTask(Task):  # TODO: Retry with delay if MySQL connection isn't available
    """An abstract Celery Task that ensures that the connection the the
    database is closed on task completion"""
    # Some code borrowed from http://www.prschmid.com/2013/04/using-sqlalchemy-with-celery-tasks.html

    abstract = True

    def run(self, *args, **kwargs):
        """The body of the task executed by workers."""
        raise NotImplementedError('Tasks must define the run method.')

    def after_return(self, status, retval, task_id, args, kwargs, einfo):
        DB_SESSION.remove()


@app.task(base=SqlAlchemyTask)
def add_new_crx_to_db(crx_obj, log_progress=False):
    """Create entry in the table of CRX IDs.

    If the CRX is already in the list of IDs, no changes are made to the DB.

    :param crx_obj: All current information about the CRX, which must include
        at least the `id`.
    :type crx_obj: dict
    :param log_progress: Whether to log this action. Typically only set to True
        when testing, and then only for every 1K entries or so.
    :type log_progress: bool
    :rtype: None
    """
    db_session = DB_SESSION()

    try:
        db_session.execute(id_list.insert().values(ext_id=crx_obj['id']))
    except IntegrityError:
        # Duplicate entry. No problem.
        if log_progress:
            logging.warning('%s  ID already in list of CRXs.' % crx_obj['id'])
    else:
        _commit_it()
        if log_progress:
            logging.warning('%s  Added ID to list of CRXs.' % crx_obj['id'])


@app.task(base=SqlAlchemyTask)
@MunchyMunch
def db_download_complete(crx_obj):
    db_session = DB_SESSION()

    # Check if the same version is already in the database
    s = select([extension.c.downloaded, extension.c.extracted, extension.c.profiled]).\
        where(and_(extension.c.ext_id == crx_obj.id, extension.c.version == crx_obj.version))
    row = db_session.execute(s).fetchone()
    if row:
        # Entry exists. First update the last known available datetime.
        update(extension).where(and_(extension.c.ext_id == crx_obj.id,
                                     extension.c.version == crx_obj.version)). \
            values(last_known_available=dict_to_dt(crx_obj.dt_avail))
        _commit_it()

        # If the extension doesn't need any more processing, raise an error indicating this
        if None not in list(row):
            raise DuplicateDownload

    # TODO: Add a new entry to the DB

    return crx_obj


@app.task(base=SqlAlchemyTask)
@MunchyMunch
def db_extract_complete(crx_obj, update_dt_avail=True):
    db_session = DB_SESSION()
    return crx_obj


@app.task(base=SqlAlchemyTask)
@MunchyMunch
def db_profile_complete(crx_obj, update_dt_avail=True):
    """Update DB that profiling is now complete, including centroid data.

    Adds the following keys to `crx_obj.cent_dict`:

    - `ext_id`: Corresponds to `crx_obj.id`.
    - `version`:  Corresponds to `crx_obj.version`.
    - `last_known_available`:  Corresponds to `crx_obj.dt_avail`.
    - `downloaded`:  Corresponds to `crx_obj.dt_downloaded`.
    - `extracted`:  Corresponds to `crx_obj.dt_extracted`.
    - `profiled`:  Corresponds to `crx_obj.dt_profiled`.

    :param crx_obj: Previously collected information about the extension.
    :type crx_obj: munch.Munch
    :param update_dt_avail: If re-profiling, this should be set to True.
    :type update_dt_avail: bool
    :return: Updated version of `crx_obj`.
    :rtype: munch.Munch
    """
    db_session = DB_SESSION()
    # import sqlalchemy; assert isinstance(db_session, sqlalchemy.orm.session.Session)

    # If we already have this version in the database, update the last known available datetime
    s = select([extension]).where(and_(extension.c.ext_id == crx_obj.id,
                                       extension.c.version == crx_obj.version))
    row = db_session.execute(s).fetchone()
    if row:
        if update_dt_avail:
            update(extension).where(and_(extension.c.ext_id == crx_obj.id,
                                         extension.c.version == crx_obj.version)). \
                values(last_known_available=crx_obj.dt_avail)
            _commit_it()
            crx_obj.msgs.append('|Updated an existing extension entry in the DB')
        else:
            # We must be re-profiling, so update the profiled date
            crx_obj.cent_dict['profiled'] = dict_to_dt(crx_obj.dt_profiled)
            db_session.execute(extension.insert().values(crx_obj.cent_dict))
            _commit_it()
            crx_obj.msgs.append('*Re-profiled an extension and updated its entry in the DB')
    else:
        # Add entry to the database
        crx_obj.cent_dict['ext_id'] = crx_obj.id
        crx_obj.cent_dict['version'] = crx_obj.version
        crx_obj.cent_dict['profiled'] = dict_to_dt(crx_obj.dt_profiled)
        if update_dt_avail:
            crx_obj.cent_dict['last_known_available'] = dict_to_dt(crx_obj.dt_avail)
        db_session.execute(extension.insert().values(crx_obj.cent_dict))
        _commit_it()
        crx_obj.msgs.append('+Successfully added a new extension entry in the DB')

    logging.debug('{}  Database entry complete', crx_obj.id)

    return crx_obj


def _commit_it():
    if READ_ONLY:
        return
    db_session = DB_SESSION()
    try:
        db_session.commit()
    except InvalidRequestError:
        pass
