#!/usr/bin/env python3
# *-* coding: utf-8 *-*
"""
Usage: crx.py [options]

Options:
 -b ID   Process extensions beginning at ID. Can be a single letter.
 -p      Use periods to show progress in the thousands.
 -q QMAX, --queue-max=QMAX
         Set the maximum number of items in the queue. [Default: 25]
 -s      Use a "stale" version of the database, i.e. don't download a new
         version of the list of extensions.
 -w CNT, --worker-count=CNT
         Set number of workers. [Default: 5]
 -u      Just update the list of IDs. Exact opposite of -s. No other
         parameters will have effect when this is specified, except -p.
 --log=LEVEL
         Set the logging level to LEVEL. Can be one of: CRITICAL, ERROR,
         WARNING, INFO, DEBUG, NOTSET. [Default: INFO]
 --recalc
         Re-calculate the centroids for all downloaded CRXs. WARNING: This is
         a destructive operation that will overwrite ALL the unpacked
         extension directories AND update the DB with new values.
 --debug
         Turn on debugging messages. This has a different effect than setting
         the log level to DEBUG.
 --pm    Turn on postmortem debugging. When the crawl() method catches an
         exception, the Python debugger (pdb) will enter an interactive prompt
         for inspecting the exception.

The update process is very memory-intensive. For this reason, it is typically
best to run the tool with the -u option first, then run it again with -s. It's
also best to expect the program to fail, most often due to a memory error, i.e.
running out of memory. For this reason, recovery safeguards are in place to
resume a previously failed update approximately where things left off.

Such memory errors cause the operating system to kill the entire process. As
such, no de-constructors or other specified methods can be called to
gracefully handle shutdown.
"""

try:
    from asyncio import JoinableQueue as Queue
except ImportError:
    from asyncio import Queue
import asyncio
import json
import logging
import os
import pdb
from datetime import datetime
from os import path
from string import ascii_lowercase
from zipfile import BadZipFile

import aiohttp
from docopt import docopt
from lxml import etree
from sqlalchemy import Table, select, and_, update
from sqlalchemy.exc import IntegrityError

from centroid import *
from chrome_db import *
from unpack import unpack, BadCrxHeader
from util import *

# Make asyncio library only log things if they're at least a warning
logging.getLogger('asyncio').setLevel(logging.WARNING)

DONT_OVERWRITE_DOWNLOADED_CRX = False
CHUNK_SIZE = 512
DEBUG = False
POST_MORTEM = False
BACKUP_PERIOD = 500

DBLING_DIR = ''


class ExtensionUnavailable(Exception):
    """Raised when an extension isn't downloadable."""


class BadDownloadURL(Exception):
    """Raised when the ID is valid but we can't download the extension."""


class DuplicateDownload(Exception):
    """Raised when the DB already has a version of the extension."""


class DownloadNewCRXs:

    def __init__(self, ev_loop, max_workers=5, max_queue_size=25, show_progress=False, start_at=None,
                 backup_period=BACKUP_PERIOD):
        """

        :param ev_loop: The event loop used in the outer scope for the
            asynchronous jobs.
        :type ev_loop: asyncio.AbstractEventLoop
        """
        self.max_workers = max_workers
        self._loop = ev_loop
        self.show_progress = show_progress
        self.start_at = start_at
        self.q_done_stage = 'download'
        self.backup_stage = 'download'
        self.backup_period = backup_period
        self.backup_file = path.join(DBLING_DIR, 'src', 'recovery.bak')
        self.failed_downloads_file = path.join(DBLING_DIR, 'src', 'failed_downloads.txt')
        self.update_dt_avail = True
        self.stats = {}
        self.stats_file = 'stats.json'
        self.exact_id = False

        # Figure out where to start if we aren't going to attempt downloading the whole set of IDs
        if self.start_at is not None:
            assert isinstance(self.start_at, str)
            assert self.start_at.isalpha()
            self.start_at = self.start_at.lower().strip()

        # Queues
        self.job_q = Queue(max_queue_size)
        self.stats_q = Queue(1)
        self.backup_q = Queue(1)

        # aiohttp's ClientSession does connection pooling and HTTP keep-alives for us.
        self.session = aiohttp.ClientSession(loop=ev_loop)

        # Open and import the configuration file
        with open(path.join(DBLING_DIR, 'src', 'crx_conf.json')) as fin:
            conf = json.load(fin)

        # Set the download URL based on the latest recorded version of Chrome
        self.download_url = conf['url'].format(calc_chrome_version(conf['version'], conf['release_date']), '{}')

        # Set save and extract paths
        self.crx_save_path = conf['save_path']
        self.crx_extract_dir = conf['extract_dir']

        # Set up the database
        self._db_conn = None
        self.extension = Table('extension', DB_META)
        self.id_table = Table('id_list', DB_META)

    @property
    def db_conn(self):
        """Return a connection to the database."""
        if self._db_conn is None or self._db_conn.closed:
            self._db_conn = DB_META.bind.connect()
        return self._db_conn

    @db_conn.deleter
    def db_conn(self):
        if self._db_conn is None or self._db_conn.closed:
            return
        self._db_conn.close()

    @asyncio.coroutine
    def crawl(self):
        if self.session.closed:
            self.session = aiohttp.ClientSession(loop=self._loop)

        # Get backup if it exists
        if path.exists(self.backup_file):
            logging.info('Recovering previous session using the backup file.')
            with open(self.backup_file) as fin:
                self.start_at = fin.read().strip()

        # Create set of workers to handle each extension
        stat_catcher = self._loop.create_task(self._save_stats())
        backup_worker = self._loop.create_task(self._backup_progress())
        workers = [self._loop.create_task(self.work()) for _ in range(self.max_workers)]

        # Add IDs to download to queue
        try:
            count = yield from self.queue_jobs()
        except:
            if POST_MORTEM:
                pdb.pm()
            logging.critical('Exception raised. Stopping all workers...', exc_info=1)
            # Ensure all the working queues are empty
            for w in workers:
                w.cancel()
            # Try to log all the stats and backup messages
            yield from self.stats_q.join()
            stat_catcher.cancel()
            yield from self.backup_q.join()
            backup_worker.cancel()
            raise
        else:
            if self.show_progress:
                print(count, flush=True)

            logging.info('All %d jobs now on the queue.' % count)

            # Wait until the jobs are done and the results have been processed by the workers
            yield from self.job_q.join()
            for w in workers:
                w.cancel()
            yield from self.stats_q.put('+Exited cleanly')

            # Delete the backup file to indicate the run completed successfully
            logging.debug('Waiting for the backup queue to become empty. Current size: %d' % self.backup_q.qsize())
            yield from self.backup_q.join()
            backup_worker.cancel()
            try:
                os.remove(self.backup_file)
            except FileNotFoundError:
                # There was no file to remove... strange.
                pass

            yield from self.stats_q.join()
            stat_catcher.cancel()
            self._backup_stats(True)
            logging.info('All threads have stopped successfully.')
        finally:
            # Close HTTP session and connection to database
            self.session.close()
            del self.db_conn

    @asyncio.coroutine
    def queue_jobs(self):
        """Add all known IDs to the job queue.

        :return: The number of jobs queued.
        :rtype: int
        """
        if self.start_at is None:
            logging.info('Adding each CRX to the queue.')
            ids_select = select([self.id_table.c.ext_id])
        else:
            logging.info('Adding IDs to the queue starting at "%s"' % self.start_at)
            ids_select = select([self.id_table.c.ext_id]).where(self.id_table.c.ext_id > self.start_at)

        count = 0
        with self.db_conn.begin():
            result = self.db_conn.execute(ids_select)
            for row in result:
                yield from self.job_q.put(row[0])
                count += 1
                if self.show_progress and not count % 1000:
                    print('.', end='', flush=True)
        return count

    @asyncio.coroutine
    def work(self):
        """Download, unpack, profile, and record the extensions from queue."""
        while True:
            ext_id = yield from self.job_q.get()

            ext_obj = yield from self.download(ext_id)
            if ext_obj is None:
                continue

            ext_obj = yield from self.unpack(ext_obj)
            if ext_obj is None:
                continue

            ext_obj = yield from self.calc_centroid(ext_obj)
            if ext_obj is None:
                continue

            yield from self.update_db(ext_obj)

    @asyncio.coroutine
    def download(self, crx_id):
        """Download the current version of the extension with ID crx_id.

        :param crx_id: The ID of the extension to download.
        :type crx_id: str
        :return: An object with all collected information on the extension.
        :rtype: ExtensionEntry
        """
        resp = None  # Response from HTTP GET request
        ret = None  # The return value
        dt_avail = datetime.today()

        try:
            # Check that the ID has a valid form
            validate_crx_id(crx_id)

            # Ensure the extension is still available in the Web Store
            resp = yield from self.session.get(CRX_URL % crx_id)
            self._ensure_redirect(resp)
            yield from resp.release()

            # Make the new request to actually download the extension
            resp = yield from self.session.get(self.download_url.format(crx_id))
            if resp.status != 200:
                # Usually caused by a 401 Not Authorized, meaning it is a paid extension or has restrictions on access
                raise BadDownloadURL
            self._check_duplicate_version(resp.url, crx_id, dt_avail)
            crx_path = yield from self._save_stream(resp, crx_id, self.crx_save_path)

        except MalformedExtId:
            # Don't attempt to download the extension
            yield from self.stats_q.put('-Invalid extension ID: Has invalid form')

        except aiohttp.ClientRequestError:
            logging.warning('%s  Error occurred when sending download request' % crx_id)
            yield from self.stats_q.put('-Error sending download request')

        except aiohttp.ClientResponseError:
            logging.warning('%s  Error occurred when reading download response' % crx_id)
            yield from self.stats_q.put('-Error reading download response')

        except aiohttp.HttpProcessingError as err:
            # Something bad happened trying to download the actual file. No way to know how to resolve it, so
            # just skip it and move on.
            logging.debug('%s  Download failed (%s %s)' % (crx_id, err.code, err.message))
            with open(path.join(DBLING_DIR, 'src', 'failed_downloads.txt'), 'a') as fout:
                fout.write(crx_id + '\n')
            yield from self.stats_q.put('-Got HttpProcessingError error when downloading')

        except ExtensionUnavailable:
            # The URL we requested should have had at least one redirect, leaving the first URL in the history. If the
            # request's history has no pages, we know the extension is not available on the Web Store.
            yield from self.stats_q.put('-Invalid extension ID: No 301 status when expected')

        except DuplicateDownload:
            # The database already has information on this version. The only thing that needs to happen is update the
            # last known available date, which should have already been taken care of in _check_duplicate_version().
            pass

        except FileExistsError as err:
            # Only happens when the versions match and we've chosen not to overwrite the previous file. In such a case,
            # there's no guarantee that the other file made it through the whole profiling process, so we need to
            # extract the crx_path from the error message
            crx_path = err.filename
            crx_version = get_crx_version(crx_path)
            # The package still needs to be profiled
            ret = ExtensionEntry(crx_id, crx_version, crx_path, dt_avail)
            yield from self.stats_q.put('+CRX download completed, but version matched previously downloaded file. '
                                        'Profiling old file.')

        except FileNotFoundError:
            # Probably couldn't properly save the file because of some weird characters in the path we tried
            # to save it at. Keep the ID of the CRX so we can try again later.
            logging.warning('%s  Failed to save CRX' % crx_id, exc_info=1)
            with open(path.join(DBLING_DIR, 'src', 'failed_downloads.txt'), 'a') as fout:
                fout.write(crx_id + '\n')
            yield from self.stats_q.put('-Got FileNotFound error when trying to save the download')

        except BadDownloadURL:
            # Most likely reasons why this error is raised: 1) the extension is part of an invite-only beta or other
            # restricted distribution, or 2) the extension is listed as being compatible with Chrome OS only.
            # Until we develop a workaround, just skip it.
            logging.debug('%s  Bad download URL' % crx_id)
            yield from self.stats_q.put('-Denied access to download')

        except:
            logging.critical('%s  An unknown error occurred while downloading.' % crx_id, exc_info=1)
            raise

        else:
            yield from self.stats_q.put('+CRX download complete, fresh file saved')
            crx_version = get_crx_version(crx_path)
            # The package still needs to be profiled
            ret = ExtensionEntry(crx_id, crx_version, crx_path, dt_avail)

        finally:
            # Always do the following, even if the download failed: release the request object, mark task as done
            if resp is not None:
                yield from resp.release()
            if self.backup_stage == 'download':
                yield from self.backup_q.put(crx_id)
            if self.q_done_stage == 'download':
                self.job_q.task_done()

        return ret

    @asyncio.coroutine
    def unpack(self, ext_obj):

        extracted_path = path.join(self.crx_extract_dir, ext_obj.crx_id, ext_obj.crx_version)
        ret = None

        # TODO: Does the image tally provide any useful information?
        try:
            unpack(ext_obj.crx_path, extracted_path, overwrite_if_exists=True)

        except FileExistsError:
            # No need to get the path from the error since we already know the extracted path
            yield from self.stats_q.put("|Failed to overwrite an existing Zip file, but didn't crash")

        except BadCrxHeader:
            logging.warning('%s  CRX had an invalid header.' % ext_obj.crx_id)
            with open(self.failed_downloads_file, 'a') as fout:
                fout.write(ext_obj.crx_id + '\n')
            yield from self.stats_q.put('-CRX header failed validation')

        except BadZipFile:
            logging.warning('%s  Failed to unzip file because it isn\'t valid.' % ext_obj.crx_id)
            with open(self.failed_downloads_file, 'a') as fout:
                fout.write(ext_obj.crx_id + '\n')
            yield from self.stats_q.put('-Zip file failed validation')

        except MemoryError:
            logging.warning('%s  Failed to unzip file because of a memory error.' % ext_obj.crx_id)
            with open(self.failed_downloads_file, 'a') as fout:
                fout.write(ext_obj.crx_id + '\n')
            yield from self.stats_q.put('-Unpacking Zip file failed due do a MemoryError')

        except (IndexError, IsADirectoryError):
            logging.warning('%s  Failed to unzip file likely because of a member filename error.' % ext_obj.crx_id,
                            exc_info=1)
            with open(self.failed_downloads_file, 'a') as fout:
                fout.write(ext_obj.crx_id + '\n')
            yield from self.stats_q.put('-Other error while unzipping file')

        except NotADirectoryError:
            logging.warning('%s  Failed to unzip file because a file was incorrectly listed as a directory.' %
                            ext_obj.crx_id, exc_info=1)
            with open(self.failed_downloads_file, 'a') as fout:
                fout.write(ext_obj.crx_id + '\n')
            yield from self.stats_q.put('-Unpacking Zip file failed due to a NotADirectoryError')

        except:
            logging.critical('%s  An unknown error occurred while unpacking.' % ext_obj.crx_id, exc_info=1)
            raise

        else:
            yield from self.stats_q.put('+Unpacked a Zip file')
            ext_obj.extracted_path = extracted_path
            ret = ext_obj
            self.log_it('Unpack', ext_obj.crx_id)

        finally:
            if self.backup_stage == 'unpack':
                yield from self.backup_q.put(ext_obj.crx_id)
            if self.q_done_stage == 'unpack':
                self.job_q.task_done()

        return ret

    @asyncio.coroutine
    def calc_centroid(self, ext_obj):
        # Generate graph from directory and centroid from the graph
        dir_graph = make_graph_from_dir(ext_obj.extracted_path)
        cent_vals = calc_centroid(dir_graph)
        # Try to conserve memory usage
        del dir_graph

        # Match up the field names with their values for easier insertion to the DB later
        cent_dict = {}
        for k, v in zip((USED_FIELDS + ('_c_size',)), cent_vals):
            cent_dict[USED_TO_DB[k]] = v
        ext_obj.cent_dict = cent_dict

        yield from self.stats_q.put('+Centroids calculated')
        self.log_it('Centroid calculation', ext_obj.crx_id)

        return ext_obj

    @asyncio.coroutine
    def update_db(self, ext_obj):
        # If we already have this version in the database, update the last known available datetime
        s = select([self.extension]).where(and_(self.extension.c.ext_id == ext_obj.crx_id,
                                                self.extension.c.version == ext_obj.crx_version))
        row = self.db_conn.execute(s).fetchone()
        if row:
            if self.update_dt_avail:
                with self.db_conn.begin():
                    update(self.extension).where(and_(self.extension.c.ext_id == ext_obj.crx_id,
                                                      self.extension.c.version == ext_obj.crx_version)). \
                        values(last_known_available=ext_obj.dt_avail)
                yield from self.stats_q.put('|Updated an existing extension entry in the DB')
            else:
                # We must be re-profiling, so update the profiled date
                ext_obj.cent_dict['profiled'] = datetime.today()
                with self.db_conn.begin():
                    self.db_conn.execute(self.extension.insert().values(ext_obj.cent_dict))
                yield from self.stats_q.put('*Re-profiled an extension and updated its entry in the DB')
        else:
            # Add entry to the database
            ext_obj.cent_dict['ext_id'] = ext_obj.crx_id
            ext_obj.cent_dict['version'] = ext_obj.crx_version
            ext_obj.cent_dict['profiled'] = datetime.today()
            if self.update_dt_avail:
                ext_obj.cent_dict['last_known_available'] = ext_obj.dt_avail
            with self.db_conn.begin():
                self.db_conn.execute(self.extension.insert().values(ext_obj.cent_dict))
            yield from self.stats_q.put('+Successfully added a new extension entry in the DB')

        if self.backup_stage == 'db':
            yield from self.backup_q.put(ext_obj.crx_id)
        self.log_it('Database entry', ext_obj.crx_id)

    @asyncio.coroutine
    def _save_stats(self):
        # Set up for receiving stats to log
        if self.start_at is not None:
            try:
                with open(self.stats_file) as fin:
                    self.stats = json.load(fin)
            except FileNotFoundError:
                # That's okay, we'll just start over
                pass
            yield from self.stats_q.put('|Times recovered from unsuccessful shutdown')

        # Loop forever until we're told to stop (from crawl())
        ttl = 0
        while True:
            stat_type = yield from self.stats_q.get()
            try:
                self.stats[stat_type] += 1
            except KeyError:
                self.stats[stat_type] = 1
            ttl += 1
            self.stats_q.task_done()

            # Make a backup of the file for every 100 entries
            if not ttl % 100:
                self._backup_stats()

    def _backup_stats(self, use_timestamp=False):
        """Save the stored statistics to the stats file.

        :param use_timestamp: When the run is complete, a copy of the stats is
            made with a timestamp appended to the filename. Setting this to
            True triggers that behavior.
        :type use_timestamp: bool
        :return: None
        :rtype: None
        """
        if use_timestamp:
            f = self.stats_file.rsplit('.', 1)
            fname = (f[0] + '_%s.' + f[1]) % datetime.today().strftime('%Y%m%d-%H%M%S')
        else:
            fname = self.stats_file

        with open(fname, 'w') as fout:
            json.dump(self.stats, fout, indent=2, sort_keys=True)

    @asyncio.coroutine
    def _backup_progress(self):
        # Set up for receiving backup requests
        count = 0

        while True:
            crx_id = yield from self.backup_q.get()
            count += 1

            if count % self.backup_period:
                # Don't do the actual backup, just do a DEBUG log
                self.log_it(self.backup_stage, crx_id, logging.DEBUG)

            else:

                self.log_it(self.backup_stage, crx_id, logging.INFO)

                if crx_id[1] == 'a':
                    if crx_id[0] == 'a':
                        bak = 'aa'
                    else:
                        bak = ascii_lowercase[ascii_lowercase.index(crx_id[0])-1] + 'z'
                elif self.exact_id:
                    # Not really exact, but much closer than other approach
                    bak = crx_id[:3] + ascii_lowercase[ascii_lowercase.index(crx_id[3])-1]
                else:
                    bak = crx_id[0] + ascii_lowercase[ascii_lowercase.index(crx_id[1])-1]

                with open(self.backup_file, 'w') as fout:
                    fout.write(bak)

            # Only mark the task done after all processing is done
            self.backup_q.task_done()

    @staticmethod
    def _ensure_redirect(resp):
        """Check that a redirect occurred.

        :param resp: The response object from GET-ting the extension's URL.
        :type resp: aiohttp.ClientResponse
        :return: None
        :rtype: None
        """
        if not len(resp.history):
            raise ExtensionUnavailable('No redirect occurred while fetching URL %s' % resp.url)

    def _check_duplicate_version(self, url, crx_id, dt_avail):
        crx_version = get_crx_version(url.rsplit('extension', 1)[-1])
        # If we already have this version in the database, update the last known available datetime
        s = select([self.extension]).where(and_(self.extension.c.ext_id == crx_id,
                                                self.extension.c.version == crx_version))
        row = self.db_conn.execute(s).fetchone()
        if row:
            with self.db_conn.begin():
                update(self.extension).where(and_(self.extension.c.ext_id == crx_id,
                                                  self.extension.c.version == crx_version)). \
                    values(last_known_available=dt_avail)
            yield from self.stats_q.put('|Updated an existing extension entry in the DB before unpacking')
            raise DuplicateDownload

    @staticmethod
    @asyncio.coroutine
    def _save_stream(resp, crx_id, save_path):
        """Save the file connected to the response.

        :param resp: The response object returned from a call to session.get()
        :type resp: aiohttp.ClientResponse
        :param crx_id: The ID of the CRX being downloaded
        :type crx_id: str
        :param save_path: Directory where to save the CRX
        :type save_path: str
        :return: Full path of the CRX
        :rtype: str
        """
        # Determine name of CRX file
        filename = crx_id + resp.url.rsplit('extension', 1)[-1]  # ID + version
        full_save_path = path.abspath(path.join(save_path, filename))

        # If we don't want to overwrite previously downloaded CRXs and we already have a file with the same name, don't
        # download it.
        if DONT_OVERWRITE_DOWNLOADED_CRX and path.exists(full_save_path):
            err = FileExistsError()
            err.errno = ''
            err.strerror = 'Cannot save CRX to path that already exists'
            err.filename = full_save_path
            raise err

        # Write the CRX one chunk at a time. This conserves memory by not trying to load the whole file at once.
        with open(full_save_path, 'wb') as fout:
            while True:
                chunk = yield from resp.content.read(CHUNK_SIZE)
                if not chunk:
                    break
                fout.write(chunk)

        # Return the full path where the CRX was saved
        return full_save_path

    @staticmethod
    def log_it(action, crx_id, lvl=logging.DEBUG):
        logging.log(lvl, '%s  %s complete' % (crx_id, action))


class RecalcCRXs(DownloadNewCRXs):

    def __init__(self, ev_loop, max_workers=5, max_queue_size=25, show_progress=False, start_at=None,
                 backup_period=BACKUP_PERIOD):
        super().__init__(ev_loop, max_workers=max_workers, max_queue_size=max_queue_size, show_progress=show_progress,
                         start_at=start_at, backup_period=backup_period)
        self.exact_id = True
        self.backup_file = path.join(DBLING_DIR, 'src', 'recalc_recovery.bak')
        self.backup_stage = 'unpack'
        self.q_done_stage = 'unpack'
        self.update_dt_avail = False
        self.stats_file = 'stats_recalc.json'

    @asyncio.coroutine
    def queue_jobs(self):
        """Add all known CRXs to the job queue.

        :return: The number of jobs queued.
        :rtype: int
        """
        if self.start_at is None:
            logging.info('Adding each CRX to the queue.')
        else:
            logging.info('Adding CRXs to the queue starting at "%s"' % self.start_at)

        count = 0
        for root, dirs, files in os.walk(self.crx_save_path):
            files.sort()
            for name in files:
                crx_path = path.join(root, name)
                if crx_path.rsplit('.', 1)[-1] != 'crx':
                    continue
                if self.start_at and name < self.start_at:
                    continue
                crx_id, crx_version = get_id_version(crx_path)
                yield from self.job_q.put(ExtensionEntry(crx_id, crx_version, crx_path))
                count += 1
                if self.show_progress and not count % 1000:
                    print('.', end='', flush=True)
            # Only go through the top-level dir
            break
        return count

    @asyncio.coroutine
    def work(self):
        """Unpack, profile, and record the extensions from the queue."""
        while True:
            ext_obj = yield from self.job_q.get()

            ext_obj = yield from self.unpack(ext_obj)
            if ext_obj is None:
                continue

            ext_obj = yield from self.calc_centroid(ext_obj)
            if ext_obj is None:
                continue

            yield from self.update_db(ext_obj)


class ExtensionEntry:
    def __init__(self, crx_id=None, crx_version=None, crx_path=None, dt_avail=None):
        self.crx_id = crx_id
        self.crx_version = crx_version
        self.crx_path = crx_path
        self.dt_avail = dt_avail
        self._path = None
        self._centroid_vals = None

    @property
    def extracted_path(self):
        if self._path is None:
            return ''
        return self._path

    @extracted_path.setter
    def extracted_path(self, val):
        assert isinstance(val, str)
        if self._path is not None:
            # Only set the value once
            return
        self._path = val

    @property
    def cent_dict(self):
        if self._centroid_vals is None:
            return {}
        return self._centroid_vals

    @cent_dict.setter
    def cent_dict(self, val):
        assert isinstance(val, dict)
        # assert len(dict)
        if self._centroid_vals is not None:
            # Only set the value once
            return
        self._centroid_vals = val


@asyncio.coroutine
def _update_crx_list(ext_url, ev_loop, show_progress=False):
    # Download the list of extensions
    logging.info('Downloading list of extensions.')
    session = aiohttp.ClientSession(loop=ev_loop)
    resp = yield from session.get(ext_url)

    # Save the list
    local_sitemap = path.join(DBLING_DIR, 'src', 'chrome_sitemap.xml')
    with open(local_sitemap, 'wb') as fout:
        while True:
            chunk = yield from resp.content.read(CHUNK_SIZE)
            if not chunk:
                break
            fout.write(chunk)
    yield from resp.release()

    # Get database handles
    id_list = Table('id_list', DB_META)
    db_conn = DB_META.bind.connect()

    logging.info('Download finished. Adding IDs to the database.')
    xml_tree_root = etree.parse(local_sitemap).getroot()  # Downloads for us from the URL
    ns = '{http://www.sitemaps.org/schemas/sitemap/0.9}'

    # Iterate over all url tags, get the string from the loc tag inside, strip off the extension ID
    # using path.basename, and add it to the database.
    count = 0
    for url_elm in xml_tree_root.iterfind(ns + 'url'):
        crx_id = path.basename(url_elm.findtext(ns + 'loc'))[:32]
        del url_elm

        with db_conn.begin():
            try:
                db_conn.execute(id_list.insert().values(ext_id=crx_id))
            except IntegrityError:
                # Duplicate entry. No problem.
                pass

        count += 1
        if show_progress and not count % 1000:
            print('.', end='', flush=True)
    if show_progress:
        print(count, flush=True)
    session.close()
    db_conn.close()
    logging.info('Update complete. Entries parsed: %d' % count)


if __name__ == '__main__':
    # Get command-line parameters
    args = docopt(__doc__)

    # Set the DEBUG and POST_MORTEM globals
    DEBUG = args['--debug']
    POST_MORTEM = args['--pm']

    # Initialize logging
    _log_path = path.join(path.dirname(path.realpath(__file__)), '../log', "crx.log")
    try:
        with open(_log_path, 'a') as _fout:
            _fout.write((' --  '*15)+'\n')
        del _fout
        DBLING_DIR = path.abspath(path.join(path.dirname(path.realpath(__file__)), '..'))
    except FileNotFoundError:
        _log_path = path.join(path.expandvars('$DBLING'), 'log', 'crx.log')
        with open(_log_path, 'a') as _fout:
            _fout.write((' --  '*15)+'\n')
        del _fout
        DBLING_DIR = path.abspath(path.join(path.expandvars('$DBLING')))
    log_format = '%(asctime)s %(levelname) 8s -- %(message)s'
    try:
        assert args['--log'] in ('CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG', 'NOTSET')
    except AssertionError:
        # Fall back to default value of INFO
        args['--log'] = 'INFO'
    log_level = getattr(logging, args['--log'])
    logging.basicConfig(filename=_log_path, level=log_level, format=log_format)
    add_color_log_levels(center=True)

    # Get the configuration
    with open(path.join(DBLING_DIR, 'src', 'crx_conf.json')) as _fin:
        _conf = json.load(_fin)
    # Try to conserve memory usage
    del _fin

    # Set the global variables for the version of Chrome and download URL
    CHROME_VERSION = calc_chrome_version(_conf['version'], _conf['release_date'])
    DOWNLOAD_URL = _conf['url']

    # Create the event loop
    loop = asyncio.get_event_loop()
    loop.set_debug(DEBUG)

    # -- Execute the specified action -- #

    # Download the current version of the sitemap from Google
    if args['-u'] or not args['-s']:
        try:
            loop.run_until_complete(_update_crx_list(_conf['extension_list_url'], loop, show_progress=args['-p']))
        except KeyboardInterrupt:
            logging.warning('Keyboard Interrupt raised.')
            print()
        if args['-u']:
            # Just download, then exit
            exit(0)

    # Re-calculate all centroids
    if args['--recalc']:
        logging.info('Starting CRX re-profiler.')
        r = RecalcCRXs(loop,
                       max_workers=int(args['--worker-count']),
                       max_queue_size=int(args['--queue-max']),
                       show_progress=args['-p'])
        try:
            loop.run_until_complete(r.crawl())
        except KeyboardInterrupt:
            logging.warning('Keyboard Interrupt raised.')
            print()
        exit(0)

    # Download new CRXs and calculate their centroids
    logging.info('Starting CRX downloader.')
    d = DownloadNewCRXs(loop,
                        max_workers=int(args['--worker-count']),
                        max_queue_size=int(args['--queue-max']),
                        show_progress=args['-p'],
                        start_at=args['-b'])
    try:
        loop.run_until_complete(d.crawl())
    except KeyboardInterrupt:
        logging.warning('Keyboard Interrupt raised.')
        print()
