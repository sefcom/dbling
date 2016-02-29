#!/usr/bin/env python3
"""
Usage: crx.py [options]

Options:
 -b ID   Process extensions beginning at ID. Can be a single letter.
 -p      Use periods to show progress in the thousands.
 -q QMAX, --queue-max=QMAX
         Set the maximum number of items in the queue. [Default: 25]
 -s      Use a "stale" version of the database, i.e. don't download a new
         version of the list of extensions.
 -t CNT, --thread-count=CNT
         Set number of worker threads. [Default: 5]
 -u      Just update the list of IDs. Exact opposite of -s. No other
         parameters will have effect when this is specified, except -p.
 --log=LEVEL
         Set the logging level to LEVEL. Can be one of: CRITICAL, ERROR,
         WARNING, INFO, DEBUG, NOTSET. [Default: INFO]

The update process is very memory-intensive. For this reason, it is typically
best to run the tool with the -u option first, then run it again with -s. It's
also best to expect the program to fail, most often due to a memory error, i.e.
running out of memory. For this reason, recovery safeguards are in place to
resume a previously failed update approximately where things left off.

Such memory errors cause the operating system to kill the entire process. As
such, no de-constructors or other specified methods can be called to
gracefully handle shutdown.
"""

import json
import logging
import os
import queue
import stat
import threading
from datetime import date, datetime, timedelta
from hashlib import sha256
from os import path
import re
from string import ascii_lowercase
from time import sleep
from zipfile import BadZipFile

import graph_tool.all as gt
import requests
from docopt import docopt
from lxml import etree
from requests.exceptions import ChunkedEncodingError
from sqlalchemy import MetaData, Table, select, and_, update
from sqlalchemy.exc import IntegrityError

from centroid import *
from chrome_db import *
from const import EVAL_NONE, IN_PAT_VAULT, ENC_PAT, MIN_DEPTH
from unpack import unpack
from util import verify_crx_availability, add_color_log_levels, get_dir_depth, SLICE_PAT

# Make 'requests' library only log things if they're at least a warning
logging.getLogger('requests').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)


FILE_TYPES = {stat.S_IFREG: 1,
              stat.S_IFDIR: 2,
              stat.S_IFCHR: 3,
              stat.S_IFBLK: 4,
              stat.S_IFIFO: 5,
              stat.S_IFSOCK: 6,
              stat.S_IFLNK: 7}
TYPE_TO_NAME = {1: 'r',
                2: 'd',
                3: 'c',  # TODO: 3-7 may not actually correspond to the DFXML standard
                4: 'b',
                5: 'f',
                6: 's',
                7: 'l'}
CHROME_VERSION = None
DOWNLOAD_URL = None
DBLING_DIR = None


class BadDownloadURL(Exception):
    pass


class DuplicateDownload(Exception):
    pass


def download(crx_id, save_path=None, resp_obj=None):
    """
    Given an extension ID, download the .crx file. If save_path is given, save
    the CRX to that directory, otherwise fall back to the default specified in
    the configuration file. If the configuration file doesn't specify one, use
    the current directory. The saved file will have the format:
    <extension ID>_<version>.crx

    :param crx_id: The ID of the extension to download.
    :type crx_id: str
    :param save_path: Directory where the CRX should be saved.
    :type save_path: str|None
    :param resp_obj: The Response object to work with instead of initiating
        the download in this function. If not given, a call will be made to
        _get_resp_obj().
    :type resp_obj: requests.Response|None
    :return: The full path of the saved file.
    :rtype: str
    """
    # Validate the CRX ID
    # validate_crx_id(crx_id)  # Unnecessary since we've already validated it.

    assert isinstance(resp_obj, requests.Response)
    if resp_obj is None:
        resp = _get_resp_obj(crx_id)
    else:
        resp = resp_obj

    # Save the CRX file
    filename = crx_id + resp.url.rsplit('extension', 1)[-1]  # ID + version
    if save_path is None:
        save_path = path.join('.', 'downloads')
    full_save_path = path.abspath(path.join(save_path, filename))

    if path.exists(full_save_path):
        err = FileExistsError()
        err.errno = ''
        err.strerror = 'Cannot save CRX to path that already exists'
        err.filename = full_save_path
        raise err

    with open(full_save_path, 'wb') as fout:
        # Write the binary response to the file 512 bytes at a time
        for chunk in resp.iter_content(chunk_size=512):
            fout.write(chunk)

    # Try to conserve memory usage
    del fout, resp

    # Return the full path where the CRX was saved
    return full_save_path


def _get_resp_obj(crx_id):
    """
    Make the download request, but just return it instead of actually
    processing it. This allows us to do some checks on the response before
    actually downloading the whole file.

    :param crx_id: The ID of the extension of interest.
    :type crx_id: str
    :return: The Response object for downloading the extension.
    :rtype: requests.Response
    """
    # Make the download request
    # For details about the URL, see http://chrome-extension-downloader.com/how-does-it-work.php
    url = DOWNLOAD_URL.format(CHROME_VERSION, crx_id)
    # Add some resiliency to how we make the request
    tries = 0
    while True:
        tries += 1
        try:
            resp = requests.get(url, stream=True)
        except requests.ConnectionError:
            if tries < 5:
                sleep(2)  # Problem may resolve itself by waiting for a bit before retrying
            else:
                raise
        else:
            break
    resp.raise_for_status()  # If there was an HTTP error, raise it

    # If the URL we got back was the same one we requested, the download failed
    if url == resp.url:
        raise BadDownloadURL
    return resp


def calc_chrome_version(last_version, release_date, release_period=10):
    """
    Calculate the most likely version number of Chrome is based on the last
    known version number and its release date, based on the number of weeks
    (release_period) it usually takes to release the next major version. A
    list of releases and their dates is available at
    https://en.wikipedia.org/wiki/Google_Chrome_release_history.

    :param last_version: Last known version number, e.g. "43.0". Should only
                         have the major and minor version numbers and exclude
                         the build and patch numbers.
    :type last_version: str
    :param release_date: Release date of the last known version number. Must
                         be a list of three integers: [YYYY, MM, DD].
    :type release_date: list
    :param release_period: Typical number of weeks between releases.
    :type release_period: int
    :return: The most likely current version number of Chrome in the same
             format required of the last_version parameter.
    :rtype: str
    """
    base_date = date(release_date[0], release_date[1], release_date[2])
    today = date.today()
    td = int((today - base_date) / timedelta(weeks=release_period))
    return str(float(last_version) + td)


def _init_graph():
    """
    Create a new graph and give it the vertex properties needed later.

    :return: The graph object.
    :rtype: graph_tool.all.Graph
    """
    gr = gt.Graph()
    # Create the internal property maps
    # TODO: Clean this up when the fields are finalized
    gr.vp['inode'] = gr.new_vertex_property('int')
    gr.vp['parent_inode'] = gr.new_vertex_property('int')
    gr.vp['filename'] = gr.new_vertex_property('string')
    gr.vp['filename_id'] = gr.new_vertex_property('string')
    gr.vp['filename_end'] = gr.new_vertex_property('string')
    gr.vp['name_type'] = gr.new_vertex_property('string')
    gr.vp['type'] = gr.new_vertex_property('vector<short>')
    # gr.vp['alloc'] = gr.new_vertex_property('bool')
    # gr.vp['used'] = gr.new_vertex_property('bool')
    # gr.vp['fs_offset'] = gr.new_vertex_property('string')
    gr.vp['filesize'] = gr.new_vertex_property('string')
    # gr.vp['src_files'] = gr.new_vertex_property('vector<short>')
    gr.vp['encrypted'] = gr.new_vertex_property('bool')
    gr.vp['eval'] = gr.new_vertex_property('bool')
    gr.vp['size'] = gr.new_vertex_property('string')
    gr.vp['mode'] = gr.new_vertex_property('string')
    gr.vp['uid'] = gr.new_vertex_property('string')
    gr.vp['gid'] = gr.new_vertex_property('string')
    gr.vp['nlink'] = gr.new_vertex_property('string')
    gr.vp['mtime'] = gr.new_vertex_property('string')
    gr.vp['ctime'] = gr.new_vertex_property('string')
    gr.vp['atime'] = gr.new_vertex_property('string')
    # gr.vp['crtime'] = gr.new_vertex_property('string')
    # gr.vp['color'] = gr.new_vertex_property('vector<float>')
    # gr.vp['shape'] = gr.new_vertex_property('string')
    gr.vp['dir_depth'] = gr.new_vertex_property('short')
    gr.vp['gt_min_depth'] = gr.new_vertex_property('bool')
    return gr


def separate_mode_type(mode):
    """
    Separate out the values for the mode (permissions) and the file type from
    the given mode.

    Both returned values are integers. The mode is just the permissions
    (usually displayed in the octal format), and the type corresponds to the
    standard VFS types:

    * 0: Unknown file
    * 1: Regular file
    * 2: Directory
    * 3: Character device
    * 4: Block device
    * 5: Named pipe (identified by the Python stat library as a FIFO)
    * 6: Socket
    * 7: Symbolic link

    :param mode: The mode value to be separated.
    :type mode: int
    :return: Tuple of ints in the form: (mode, type)
    :rtype: tuple
    """
    m = stat.S_IMODE(mode)
    t = stat.S_IFMT(mode)
    return m, FILE_TYPES.get(t, 0)


def make_graph_from_dir(top_dir, digr=None):
    """
    Given a directory path, create and return a directed graph representing it
    and all its contents.

    :param top_dir: Path to the top-most directory to add to the graph.
    :type top_dir: str
    :return: The graph object with all the information about the directory.
    :rtype: graph_tool.all.Graph
    """
    assert path.isdir(top_dir)
    # TODO: dd? DFXML? Or is that overkill?

    # Initialize the graph with all the vertex properties, then add the top directory vertex
    slice_path = True  # TODO: Not working
    if digr is None or not isinstance(digr, gt.Graph):
        digr = _init_graph()
        slice_path = False
    dir_v = digr.add_vertex()
    _id = _set_vertex_props(digr, dir_v, top_dir, slice_path)
    id_to_vertex = {_id: dir_v}

    ttl_objects = 1

    for dirpath, dirnames, filenames in os.walk(top_dir):
        dir_id = sha256(path.abspath(dirpath).encode('utf-8')).hexdigest()

        for f in dirnames + filenames:
            full_filename = path.join(dirpath, f)
            vertex = digr.add_vertex()
            digr.add_edge(id_to_vertex[dir_id], vertex)
            vertex_id = _set_vertex_props(digr, vertex, full_filename, slice_path)
            id_to_vertex[vertex_id] = vertex
            ttl_objects += 1

    logging.info('Total imported file objects: %d' % ttl_objects)
    return digr


def _set_vertex_props(digraph, vertex, filename, slice_path=False):
    """
    Use Python's os.stat method to store information about the file in the
    vertex properties of the graph the vertex belongs to. Return the SHA256
    hash of the file's full, normalized path.

    :param digraph: The graph the vertex belongs to.
    :type digraph: graph_tool.all.Graph
    :param vertex: The vertex object that will correspond with the file.
    :type vertex: graph_tool.all.Vertex
    :param filename: The path to the file.
    :type filename: str
    :return: SHA256 hash of the file's full, normalized path. (hex digest)
    :rtype: str
    """
    # Get the full, normalized path for the filename, then get its stat() info
    filename = path.abspath(filename)
    st = os.stat(filename, follow_symlinks=False)

    # Set all the attributes for the top directory vertex
    filename_id = sha256(filename.encode('utf-8')).hexdigest()
    m, t = separate_mode_type(st.st_mode)

    sliced_fn = filename
    if slice_path:
        _m = re.search(SLICE_PAT, filename)
        if _m:
            sliced_fn = _m.group(1)
    dir_depth = get_dir_depth(sliced_fn)

    try:
        parent_ver = list(vertex.in_neighbours())[0]
    except IndexError:
        pass
    else:
        digraph.vp['parent_inode'][vertex] = digraph.vp['inode'][parent_ver]

    digraph.vp['inode'][vertex] = st.st_ino
    digraph.vp['filename'][vertex] = filename
    digraph.vp['filename_id'][vertex] = filename_id
    digraph.vp['filename_end'][vertex] = path.basename(filename[-13:])
    digraph.vp['name_type'][vertex] = TYPE_TO_NAME[t]
    digraph.vp['type'][vertex] = (t,)
    digraph.vp['filesize'][vertex] = str(st.st_size)
    digraph.vp['size'][vertex] = str(st.st_size)
    digraph.vp['encrypted'][vertex] = bool(re.search(ENC_PAT, sliced_fn))
    digraph.vp['eval'][vertex] = EVAL_NONE
    digraph.vp['dir_depth'][vertex] = dir_depth
    digraph.vp['gt_min_depth'][vertex] = bool(re.match(IN_PAT_VAULT, sliced_fn)) and dir_depth >= MIN_DEPTH
    digraph.vp['mode'][vertex] = str(m)
    digraph.vp['uid'][vertex] = st.st_uid
    digraph.vp['gid'][vertex] = st.st_gid
    digraph.vp['nlink'][vertex] = st.st_nlink
    digraph.vp['mtime'][vertex] = datetime.fromtimestamp(st.st_mtime).strftime(ISO_TIME)
    digraph.vp['ctime'][vertex] = datetime.fromtimestamp(st.st_ctime).strftime(ISO_TIME)
    digraph.vp['atime'][vertex] = datetime.fromtimestamp(st.st_atime).strftime(ISO_TIME)
    return filename_id


def _update_crx_list(ext_url, show_progress=False):
    # Download the list of extensions
    logging.info('Downloading list of extensions.')
    resp = None
    for i in range(5):
        try:
            resp = requests.get(ext_url)
        except ChunkedEncodingError:
            sleep(10 * (i+1))
            pass
        else:
            break
    if resp is None:
        logging.critical('Failed to download list of extensions. Centroid calculation may use an old list.')
        return

    resp.raise_for_status()  # If there was an HTTP error, raise it

    # Get database handles
    id_list = Table('id_list', DB_META)
    db_conn = DB_META.bind.connect()

    # Save the list
    local_sitemap = path.join(DBLING_DIR, 'src', 'chrome_sitemap.xml')
    with open(local_sitemap, 'wb') as fout:
        fout.write(resp.content)
    # Try to conserve memory usage
    del resp, fout

    count = 0

    logging.info('Download finished. Adding IDs to the database.')
    xml_tree_root = etree.parse(local_sitemap).getroot()  # Downloads for us from the URL
    ns = '{http://www.sitemaps.org/schemas/sitemap/0.9}'
    for url_elm in xml_tree_root.iterfind(ns + 'url'):
        # Iterate over all url tags, get the string from the loc tag inside, strip off the extension ID
        # using path.basename, and add it to the database.
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
    db_conn.close()
    logging.info('Update complete. Entries parsed: %d' % count)

    # Try to conserve memory usage
    del db_conn, xml_tree_root, id_list


# @profile  # For memory profiling
def update_database(download_fresh_list=True, thread_count=5, queue_max=25, show_progress=False, start_at=None):
    # Open and import the configuration file
    with open(path.join(DBLING_DIR, 'src', 'crx_conf.json')) as fin:
        conf = json.load(fin)
    # Try to conserve memory usage
    del fin

    # Check to see if we need to recover from a previously failed run
    backup_file = path.join(DBLING_DIR, 'src', 'recovery.bak')
    if path.exists(backup_file):
        logging.info('Recovering previous session using the backup file.')
        download_fresh_list = False
        with open(backup_file) as fin:
            start_at = fin.read(2)  # Only need the first 2 characters

    # This allows us to either use the list of extension IDs already in the database or download a fresh sitemap
    # from Google.
    if download_fresh_list:
        try:
            _update_crx_list(conf['extension_list_url'], show_progress)
        except:
            logging.critical('Something bad happened while updating the CRX list.', exc_info=1)
            raise

    # Get the paths to the working directories
    try:
        save_path = conf['save_path']
    except KeyError:
        save_path = None  # Use the default of the download() function

    try:
        extract_dir = conf['extract_dir']
    except KeyError:
        extract_dir = None  # Use the default of the unpack() function

    # Set up the queues so we can communicate with the threads
    crx_ids = queue.Queue(queue_max)
    zip_files = queue.Queue(queue_max)
    directories = queue.Queue(queue_max)
    centroids = queue.Queue(queue_max)
    stats = queue.Queue(queue_max)
    backup_queue = queue.Queue()

    # Create the worker threads
    d_threads = []
    u_threads = []
    c_threads = []
    for i in range(thread_count):
        d_threads.append(DownloadWorker(crx_ids, zip_files, save_path, stats, DB_META, backup_queue))
        u_threads.append(UnpackWorker(zip_files, directories, extract_dir, stats))
        c_threads.append(CentroidWorker(directories, centroids, stats))

    # Create database worker, error processor, and backup worker threads
    db_thread = DatabaseWorker(centroids, DB_META, stats)
    backup_thread = BackupWorker(backup_queue, backup_file)
    stat_thread = StatsProcessor(stats, start_at)
    # The stats thread always has to come last in this list or else the pop() below won't work right
    all_threads = d_threads + u_threads + c_threads + [db_thread, backup_thread, stat_thread]

    # Start all the downloader and unpacker threads
    for t in all_threads:
        t.start()

    # Get database handles
    id_table = Table('id_list', DB_META)
    db_conn = DB_META.bind.connect()

    if start_at is None:
        logging.info('Adding each CRX to the queue.')
    else:
        assert isinstance(start_at, str)
        assert start_at.isalpha()
        start_at = start_at.lower()
        logging.info('Adding IDs to the queue starting at "%s"' % start_at)
    count = 0
    try:
        # Put each CRX ID on the jobs queue
        with db_conn.begin():
            # TODO: Change the following to only select starting from start_at, when applicable
            result = db_conn.execute(select([id_table]))
            for row in result:
                if start_at is not None and row[0] < start_at:
                    continue
                crx_ids.put(row[0])
                count += 1
                del row
                if show_progress and not count % 1000:
                    print('.', end='', flush=True)
        del result, id_table
    except:
        # Try to let every thread stop its work first so we don't exit in as much of an inconsistent state
        for t in all_threads:
            t.stop()
        for t in all_threads:
            t.join()
        db_conn.close()
        logging.critical('Exception raised. All threads stopped successfully.')
        raise

    if show_progress:
        print(count, flush=True)

    # Wait until the jobs are done and the results have been processed
    logging.info('All jobs are now on the queue.')
    crx_ids.join()
    for t in d_threads:  # Download workers
        t.stop()

    backup_queue.join()
    backup_thread.stop()  # Backup worker

    zip_files.join()
    for t in u_threads:  # Unpack workers
        t.stop()

    directories.join()
    for t in c_threads:  # Centroid workers
        t.stop()

    centroids.join()
    db_thread.stop()  # Database worker

    # Take the stat_thread out of the list so we can stop it separately
    all_threads.pop()
    for t in all_threads:
        t.join()

    db_conn.close()

    # Delete the backup file to indicate the run completed successfully
    os.remove(backup_file)

    stats.put('+Exited cleanly')
    stats.join()
    stat_thread.stop()
    stat_thread.join()
    logging.info('All threads have stopped successfully.')


def get_crx_version(crx_path):
    """
    From the path to a CRX, extract and return the version number as a string.

    The return value from the download() function is in the form:
    <extension ID>_<version>.crx

    The <version> part of that format is "x_y_z" for version "x.y.z". To
    convert to the latter, we need to 1) get the basename of the path, 2) take
    off the trailing ".crx", 3) remove the extension ID and '_' after it, and
    4) replace all occurrences of '_' with '.'.

    :param crx_path: The full path to the downloaded CRX, as returned by the
                     download() function.
    :type crx_path: str
    :return: The version number in the form "x.y.z".
    :rtype: str
    """
    # TODO: This approach has some issues with catching some outliers that don't match the regular pattern
    ver_str = path.basename(crx_path).split('.crx')[0].split('_', 1)[1]
    return ver_str.replace('_', '.')


class _MyWorker(threading.Thread):

    def __init__(self, jobs, results):
        """
        Set up the variables common to all subclasses.

        :param jobs: The queue of things to do.
        :type jobs: queue.Queue
        :param results: The queue of things we've done.
        :type results: queue.Queue|None
        :return: None
        :rtype: None
        """
        super().__init__()
        self._stop_signal = False
        self.jobs = jobs
        self.results = results

    def stop(self):
        """
        Tell this thread to stop processing jobs.

        :return: None
        :rtype: None
        """
        self._stop_signal = True

    def run(self):
        """
        Get a job from the jobs queue, call the do_job() method which must be
        implemented by an inheriting class, and mark the job as done. Use a
        loop that breaks when the stop() method is called.
        """
        while not self._stop_signal:
            try:
                job = self.jobs.get(timeout=1)
            except queue.Empty:
                # Either there's nothing in the queue or we hit the timeout, just try again
                pass
            else:
                self.do_job(job)
                self.jobs.task_done()
        self.leave()

    def do_job(self, job):
        raise NotImplementedError

    def leave(self):
        """
        Optional clean-up method, called when run() is done.
        """
        pass

    @staticmethod
    def log_it(action, crx_id, lvl=logging.DEBUG):
        logging.log(lvl, '%s  %s complete' % (crx_id, action))


class DownloadWorker(_MyWorker):
    """
    Download CRX files and save them for unpacking.
    """

    def __init__(self, jobs, results, save_path, stats_queue, database_metadata, backup_queue):
        """
        Download extensions to the save path.

        :param jobs: The queue with the extension IDs to download.
        :type jobs: queue.Queue
        :param results: The queue for downloaded CRXs.
        :type results: queue.Queue
        :param save_path: Directory where the CRX files should be downloaded to.
        :type save_path: str
        :param stats_queue: The queue for statistics collecting.
        :type stats_queue: queue.Queue
        :param database_metadata: A metadata object bound to an instantiated
            engine.
        :type database_metadata: MetaData
        :param backup_queue: The queue for backing up the progress of all the
            DownloadWorker threads.
        :type backup_queue: queue.Queue
        :return:
        """
        super().__init__(jobs, results)
        self.save_path = save_path
        self.stats = stats_queue
        self.extension = Table('extension', database_metadata)
        # Open connection to the database
        self.db_conn = database_metadata.bind.connect()
        self.backup = backup_queue

    # @profile  # For memory profiling
    def do_job(self, crx_id):
        """
        Get CRX IDs from the jobs queue, download the file, put the save path
        on the results queue. Skip extensions (version must match) that we've
        already downloaded before.

        :return: None
        :rtype: None
        """
        # Check that the ID is for a valid extension
        try:
            valid = verify_crx_availability(crx_id)
        except requests.ConnectionError:
            logging.warning('%s  Problem connecting to verify extension ID' % crx_id)
            self.stats.put('-Connection error when verifying extension ID')
            return
        else:
            if not valid:
                # This could mean a few things. Either it was never a valid extension ID, it was taken down by Google,
                # or the author removed it.
                # TODO: Update the database. Mark this extension as invalid.
                self.stats.put('-Invalid extension ID: No 301 status when expected')
                return
        dt_avail = datetime.today()

        # Download the CRX file, put the full save path on the results queue
        try:
            resp = _get_resp_obj(crx_id)
            self._check_duplicate_version(resp, crx_id, dt_avail)
            crx_path = download(crx_id, self.save_path, resp)
        except FileExistsError as err:
            # This should only happen if the versions match. Unfortunately, we can't assume the other version
            # completed successfully, so we need to extract the crx_path from the error message.
            crx_path = err.filename
            crx_version = get_crx_version(crx_path)
            # The package still needs to be profiled
            self.results.put((crx_id, crx_version, crx_path, dt_avail))
            self.stats.put('+CRX download completed, but overwrote previously downloaded file')
        except FileNotFoundError:
            # Probably couldn't properly save the file because of some weird characters in the path we tried
            # to save it at. Keep the ID of the CRX so we can try again later.
            logging.warning('%s  Failed to save CRX' % crx_id, exc_info=1)
            with open(path.join(DBLING_DIR, 'src', 'failed_downloads.txt'), 'a') as fout:
                fout.write(crx_id + '\n')
            del fout
            self.stats.put('-Got FileNotFound error when trying to save the download')
            return
        except BadDownloadURL:
            # Most likely reasons why this error is raised: 1) the extension is part of an invite-only beta or other
            # restricted distribution, or 2) the extension is listed as being compatible with Chrome OS only.
            # Until we develop a workaround, just skip it.
            logging.debug('%s  Bad download URL' % crx_id)
            self.stats.put('-Denied access to download')
            return
        except requests.HTTPError as err:
            # Something bad happened trying to download the actual file. No way to know how to resolve it, so
            # just skip it and move on.
            logging.debug('%s  Download failed (%s %s)' % (crx_id, err.response.status_code, err.response.reason))
            with open(path.join(DBLING_DIR, 'src', 'failed_downloads.txt'), 'a') as fout:
                fout.write(crx_id + '\n')
            del fout
            self.stats.put('-Got HTTPError error when downloading')
            return
        except DuplicateDownload:
            # We've already updated the database, so there's nothing else to do here but close the connection
            pass
        except:
            raise
        else:
            self.stats.put('+CRX download complete, fresh file saved')
            crx_version = get_crx_version(crx_path)
            # The package still needs to be profiled
            self.results.put((crx_id, crx_version, crx_path, dt_avail))

        self.backup.put(crx_id)

    def _check_duplicate_version(self, resp_obj, crx_id, dt_avail):
        crx_version = get_crx_version(resp_obj.url.rsplit('extension', 1)[-1])
        # If we already have this version in the database, update the last known available datetime
        s = select([self.extension]).where(and_(self.extension.c.ext_id == crx_id,
                                                self.extension.c.version == crx_version))
        row = self.db_conn.execute(s).fetchone()
        if row:
            with self.db_conn.begin():
                update(self.extension).where(and_(self.extension.c.ext_id == crx_id,
                                                  self.extension.c.version == crx_version)).\
                    values(last_known_available=dt_avail)
            self.stats.put('|Updated an existing extension entry in the DB before unpacking')
            resp_obj.close()  # The Response object must not be accessed after this call
            raise DuplicateDownload


class UnpackWorker(_MyWorker):

    def __init__(self, downloads, unpacked_dirs, extract_path, stats_queue):
        super().__init__(downloads, unpacked_dirs)
        self.ex_path = extract_path
        self.stats = stats_queue

    # @profile  # For memory profiling
    def do_job(self, job):
        crx_id, crx_version, crx_path, dt_avail = job
        extracted_path = path.join(self.ex_path, crx_id, crx_version)
        try:
            unpack(crx_path, extracted_path, overwrite_if_exists=True)
        except FileExistsError:
            # No need to get the path from the error since we already know the extracted path
            self.stats.put('|Failed to overwrite an existing Zip file, but didn\'t crash')
        except BadZipFile:
            logging.warning('%s  Failed to unzip file because it isn\'t valid.' % crx_id)
            with open(path.join(DBLING_DIR, 'src', 'failed_downloads.txt'), 'a') as fout:
                fout.write(crx_id + '\n')
            del fout
            self.stats.put('-Zip file failed validation')
            return
        except MemoryError:
            logging.warning('%s  Failed to unzip file because of a memory error.' % crx_id)
            with open(path.join(DBLING_DIR, 'src', 'failed_downloads.txt'), 'a') as fout:
                fout.write(crx_id + '\n')
            del fout
            self.stats.put('-Unpacking Zip file failed due do a MemoryError')
            return
        except (IndexError, IsADirectoryError):
            logging.warning('%s  Failed to unzip file likely because of a member filename error.' % crx_id, exc_info=1)
            with open(path.join(DBLING_DIR, 'src', 'failed_downloads.txt'), 'a') as fout:
                fout.write(crx_id + '\n')
            del fout
            self.stats.put('-Other error while unzipping file')
            return
        else:
            self.stats.put('+Unpacked a Zip file')
        self.results.put((crx_id, crx_version, extracted_path, dt_avail))
        self.log_it('Unpack', crx_id)


class CentroidWorker(_MyWorker):

    def __init__(self, unpacked_dirs, dir_graphs, stats_queue):
        super().__init__(unpacked_dirs, dir_graphs)
        self.stats = stats_queue

    # @profile  # For memory profiling
    def do_job(self, job):
        crx_id, crx_version, ext_path, dt_avail = job
        # Generate graph from directory and centroid from the graph
        dir_graph = make_graph_from_dir(ext_path)
        cent_vals = calc_centroid(dir_graph)
        # Try to conserve memory usage
        del dir_graph

        # Match up the field names with their values for easier insertion to the DB later
        cent_dict = {}
        for k, v in zip((USED_FIELDS + ('_c_size',)), cent_vals):
            cent_dict[USED_TO_DB[k]] = v
        self.results.put((crx_id, crx_version, cent_dict, dt_avail))
        self.stats.put('+Centroids calculated')
        self.log_it('Centroid calculation', crx_id)


class DatabaseWorker(_MyWorker):

    def __init__(self, centroids, database_metadata, stats_queue):
        """

        :param centroids: The queue of computed centroids.
        :type centroids: queue.Queue
        :param database_metadata: A metadata object bound to an instantiated
            engine.
        :type database_metadata: MetaData
        :param stats_queue: Queue for keeping track of run statistics.
        :type stats_queue: queue.Queue
        :return:
        """
        super().__init__(centroids, None)
        self.extension = Table('extension', database_metadata)
        self.stats = stats_queue

        # Open connection to the database
        self.db_conn = database_metadata.bind.connect()

    def leave(self):
        # Close the connection to the database
        self.db_conn.close()

    # @profile  # For memory profiling
    def do_job(self, job):
        crx_id, crx_version, cent_vals, dt_avail = job
        # If we already have this version in the database, update the last known available datetime
        s = select([self.extension]).where(and_(self.extension.c.ext_id == crx_id,
                                                self.extension.c.version == crx_version))
        row = self.db_conn.execute(s).fetchone()
        if row:
            with self.db_conn.begin():
                update(self.extension).where(and_(self.extension.c.ext_id == crx_id,
                                                  self.extension.c.version == crx_version)).\
                    values(last_known_available=dt_avail)
            self.stats.put('|Updated an existing extension entry in the DB')
        else:
            # Add entry to the database
            cent_vals['ext_id'] = crx_id
            cent_vals['version'] = crx_version
            cent_vals['profiled'] = datetime.today()
            cent_vals['last_known_available'] = dt_avail
            with self.db_conn.begin():
                self.db_conn.execute(self.extension.insert().values(cent_vals))
            self.stats.put('+Successfully added a new extension entry in the DB')

        self.log_it('Database entry', crx_id)

        # Try and conserve memory usage
        del cent_vals, crx_id, crx_version, row


class StatsProcessor(_MyWorker):

    def __init__(self, stats_queue, recovery=False):
        super().__init__(stats_queue, None)
        self._total = 0
        if recovery:
            try:
                with open('stats.json') as fin:
                    self.stats = json.load(fin)
            except FileNotFoundError:
                self.stats = {}
            self.do_job('|Times recovered from unsuccessful shutdown')
        else:
            self.stats = {}

    def do_job(self, stat_type):
        if stat_type not in self.stats:
            self.stats[stat_type] = 1
        else:
            self.stats[stat_type] += 1
        self._total += 1
        if not self._total % 100:
            # Every 100 entries, make a backup copy of the file
            self._log_stat()
        del stat_type

    def _log_stat(self, use_timestamp=False):
        if use_timestamp:
            fname = 'stats_%s.json' % datetime.today().strftime('%Y%m%d-%H%M%S')
        else:
            fname = 'stats.json'

        with open(fname, 'w') as fout:
            json.dump(self.stats, fout, indent=2, sort_keys=True)
        del fout

    def leave(self):
        self._log_stat(use_timestamp=True)


class BackupWorker(_MyWorker):

    def __init__(self, backup_queue, backup_file):
        super().__init__(backup_queue, None)
        # Store count of jobs completed so we know when to back up our progress
        self.backup_file = backup_file
        self.count = 0

    def _backup_progress(self, crx_id):
        """
        Using the given ID, store a 2-character starting point in the backup
        file. For example, if crx_id starts with "ca...", the stored string
        will be "bz" to ensure no gap between what is done and where the
        program picks up again later.

        :param crx_id: The ID of an extension that has been successfully
            downloaded (or skipped because it was already downloaded).
        :type crx_id: str
        :return: None
        :rtype: None
        """
        if crx_id[1] == 'a':
            if crx_id[0] == 'a':
                bak = 'aa'
            else:
                bak = ascii_lowercase[ascii_lowercase.index(crx_id[0])-1] + 'z'
        else:
            bak = crx_id[0] + ascii_lowercase[ascii_lowercase.index(crx_id[1])-1]

        with open(self.backup_file, 'w') as fout:
            fout.write(bak)

        del crx_id, bak, fout

    def do_job(self, job):
        self.count += 1
        # Only log every 500 successful entries at a higher logging level
        if not self.count % 500:
            self._backup_progress(job)
            self.log_it('Download', job, logging.INFO)
        else:
            self.log_it('Download', job, logging.DEBUG)


if __name__ == '__main__':
    # Get command-line parameters
    args = docopt(__doc__)

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
    assert args['--log'] in ('CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG', 'NOTSET')
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

    if args['-u']:
        # Just download the current version of the sitemap from Google, then exit
        _update_crx_list(_conf['extension_list_url'], show_progress=args['-p'])
        exit(0)

    logging.info('Starting CRX downloader.')
    update_database(download_fresh_list=(not args['-s']),
                    thread_count=int(args['--thread-count']),
                    queue_max=int(args['--queue-max']),
                    show_progress=args['-p'],
                    start_at=args['-b'])
