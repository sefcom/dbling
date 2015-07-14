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

"""

from centroid import *
from datetime import date, datetime, timedelta
from docopt import docopt
import graph_tool.all as gt
from hashlib import sha256
import json
import logging
from lxml import etree
import os
from os import path
import queue
import requests
from sqlalchemy import create_engine, engine_from_config, MetaData, engine, Table, Column, String, Integer, Index, \
    DateTime, select, and_, update, Float
from sqlalchemy.exc import IntegrityError
import stat
import threading
from unpack import unpack
from zipfile import BadZipFile

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
USED_TO_DB = {'_c_ctime': 'ctime',
              '_c_num_child_dirs': 'num_dirs',
              '_c_num_child_files': 'num_files',
              '_c_mode': 'perms',
              '_c_depth': 'depth',
              '_c_type': 'type',
              '_c_size': 'size'}
DB_ENGINE = None
DBLING_DIR = None


def download(crx_id, save_path=None):
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
    :return: The full path of the saved file.
    :rtype: str
    """
    # Validate the CRX ID
    assert isinstance(crx_id, str)
    assert crx_id.isalnum()
    # TODO: If we can be sure the length won't change, we can also check that len(crx_id) == 32

    # Open and load the configuration file
    with open(path.join(DBLING_DIR, 'src', 'crx_conf.json')) as fin:
        conf = json.load(fin)

    # Calculate the version of Chrome we should specify in the URL
    version = calc_chrome_version(conf['version'], conf['release_date'])

    # Make the download request
    # For details about the URL, see http://chrome-extension-downloader.com/how-does-it-work.php
    url = conf['url'].format(version, crx_id)
    resp = requests.get(url)
    resp.raise_for_status()  # If there was an HTTP error, raise it

    # Save the CRX file
    filename = crx_id + resp.url.rsplit('extension', 1)[-1]  # ID + version
    if save_path is None:
        try:
            save_path = conf['save_path']
        except KeyError:
            save_path = '.'
    full_save_path = path.abspath(path.join(save_path, filename))

    if path.exists(full_save_path):
        err = FileExistsError()
        err.errno = ''
        err.strerror = 'Cannot save CRX to path that already exists'
        err.filename = full_save_path
        raise err

    with open(full_save_path, 'wb') as fout:
        # Write the whole binary response to the file
        fout.write(resp.content)

    # Try to conserve memory usage
    del fin, fout, resp

    # Return the full path where the CRX was saved
    return full_save_path


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
    # gr.vp['inode'] = gr.new_vertex_property('int')
    # gr.vp['parent_inode'] = gr.new_vertex_property('int')
    gr.vp['filename_id'] = gr.new_vertex_property('string')
    # gr.vp['filename_end'] = gr.new_vertex_property('string')
    # gr.vp['name_type'] = gr.new_vertex_property('string')
    gr.vp['type'] = gr.new_vertex_property('vector<short>')
    # gr.vp['alloc'] = gr.new_vertex_property('bool')
    # gr.vp['used'] = gr.new_vertex_property('bool')
    # gr.vp['fs_offset'] = gr.new_vertex_property('string')
    # gr.vp['filesize'] = gr.new_vertex_property('string')
    # gr.vp['src_files'] = gr.new_vertex_property('vector<short>')
    # gr.vp['encrypted'] = gr.new_vertex_property('bool')
    # gr.vp['eval'] = gr.new_vertex_property('bool')
    gr.vp['size'] = gr.new_vertex_property('string')
    gr.vp['mode'] = gr.new_vertex_property('string')
    # gr.vp['uid'] = gr.new_vertex_property('string')
    # gr.vp['gid'] = gr.new_vertex_property('string')
    # gr.vp['nlink'] = gr.new_vertex_property('string')
    # gr.vp['mtime'] = gr.new_vertex_property('string')
    gr.vp['ctime'] = gr.new_vertex_property('string')
    # gr.vp['atime'] = gr.new_vertex_property('string')
    # gr.vp['crtime'] = gr.new_vertex_property('string')
    # gr.vp['color'] = gr.new_vertex_property('vector<float>')
    # gr.vp['shape'] = gr.new_vertex_property('string')
    # gr.vp['dir_depth'] = gr.new_vertex_property('short')
    # gr.vp['gt_min_depth'] = gr.new_vertex_property('bool')
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


def make_graph_from_dir(top_dir):
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
    digr = _init_graph()
    dir_v = digr.add_vertex()
    _id = _set_vertex_props(digr, dir_v, top_dir)
    id_to_vertex = {_id: dir_v}

    for dirpath, dirnames, filenames in os.walk(top_dir):
        dir_id = sha256(path.abspath(dirpath).encode('utf-8')).hexdigest()

        for f in dirnames + filenames:
            full_filename = path.join(dirpath, f)
            vertex = digr.add_vertex()
            vertex_id = _set_vertex_props(digr, vertex, full_filename)
            id_to_vertex[vertex_id] = vertex
            digr.add_edge(id_to_vertex[dir_id], vertex)

    return digr


def _set_vertex_props(digraph, vertex, filename):
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
    st = os.stat(filename)

    # Set all the attributes for the top directory vertex
    filename_id = sha256(filename.encode('utf-8')).hexdigest()
    digraph.vp['filename_id'][vertex] = filename_id
    m, t = separate_mode_type(st.st_mode)
    digraph.vp['type'][vertex] = (t,)
    digraph.vp['mode'][vertex] = str(m)
    digraph.vp['size'][vertex] = str(st.st_size)
    digraph.vp['ctime'][vertex] = datetime.fromtimestamp(st.st_ctime).strftime(ISO_TIME)
    return filename_id


def _init_db(db_conf):
    """
    Initialize the database by ensuring the engine is instantiated and the
    'extension' table has been created with the proper columns.

    :param db_conf: Configuration settings, from crx_conf.json key "db".
    :type db_conf: dict
    :return: The metadata object bound to the engine.
    :rtype: MetaData
    """
    # Make sure the engine object has been created
    global DB_ENGINE
    if DB_ENGINE is None or not isinstance(DB_ENGINE, engine.Engine):
        if 'sqlalchemy.url' not in db_conf:
            create_str = db_conf['type'] + '://'
            if len(db_conf['user']):
                create_str += db_conf['user']
                if len(db_conf['pass']):
                    create_str += ':' + db_conf['pass']
                create_str += '@'
            create_str += path.join(db_conf['url'], db_conf['name'])
            DB_ENGINE = create_engine(create_str)
        else:
            DB_ENGINE = engine_from_config(db_conf)

    # Make sure the database has the structure we need it to
    metadata = MetaData()
    metadata.bind = DB_ENGINE

    extension = Table('extension', metadata,
                      Column('pk', Integer, primary_key=True),
                      Column('ext_id', String(32)),
                      Column('version', String(20)),
                      Column('last_known_available', DateTime(True)),
                      Column('profiled', DateTime(True)),

                      # Centroid fields
                      Column('size', Float),
                      Column('ctime', Float),
                      Column('num_dirs', Float),
                      Column('num_files', Float),
                      Column('perms', Float),
                      Column('depth', Float),
                      Column('type', Float),

                      # Unique index on the extension ID and version
                      Index('idx_id_ver', 'ext_id', 'version', unique=True)
                      )
    extension.create(checkfirst=True)

    id_list = Table('id_list', metadata,
                    Column('ext_id', String(32), primary_key=True)
                    )
    id_list.create(checkfirst=True)

    return metadata


def _update_crx_list(ext_url, db_meta, show_progress=False):
    # Download the list of extensions
    logging.info('Downloading list of extensions.')
    resp = requests.get(ext_url)
    resp.raise_for_status()  # If there was an HTTP error, raise it

    # Get database handles
    id_list = Table('id_list', db_meta)
    db_conn = db_meta.bind.connect()

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

    # Connect to database
    db_meta = _init_db(conf['db'])

    # This allows the calling function to specify a local filename to use instead of downloading a fresh sitemap
    # from Google, which takes a while to finish.
    if download_fresh_list:
        try:
            _update_crx_list(conf['extension_list_url'], db_meta, show_progress)
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

    # Create the worker threads
    d_threads = []
    u_threads = []
    c_threads = []
    for i in range(thread_count):
        d_threads.append(DownloadWorker(crx_ids, zip_files, save_path))
        u_threads.append(UnpackWorker(zip_files, directories, extract_dir))
        c_threads.append(CentroidWorker(directories, centroids))

    # Create database worker thread
    db_thread = DatabaseWorker(centroids, db_meta)
    all_threads = d_threads + u_threads + c_threads + [db_thread]

    # Start all the downloader and unpacker threads
    for t in all_threads:
        t.start()

    # Get database handles
    id_table = Table('id_list', db_meta)
    db_conn = db_meta.bind.connect()

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
            result = db_conn.execute(select([id_table]))
            for row in result:
                if start_at is not None and row[0] < start_at:
                    continue
                crx_ids.put(row[0])
                count += 1
                del row
                if show_progress and not count % 1000:
                    print('.', end='', flush=True)
    except:
        db_conn.close()
        # Try to let every thread stop its work first so we don't exit in as much of an inconsistent state
        for t in all_threads:
            t.stop()
        for t in all_threads:
            t.join()
        logging.critical('Exception raised. All threads stopped successfully.')
        raise

    if show_progress:
        print(count, flush=True)
    db_conn.close()
    del result, db_conn, id_table

    # Wait until the jobs are done and the results have been processed
    logging.info('All jobs are now on the queue.')
    crx_ids.join()
    for t in d_threads:  # Download workers
        t.stop()

    zip_files.join()
    for t in u_threads:  # Unpack workers
        t.stop()

    directories.join()
    for t in c_threads:  # Centroid workers
        t.stop()

    centroids.join()
    db_thread.stop()  # Database worker

    for t in all_threads:
        t.join()
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

    def __init__(self, jobs, results, save_path):
        super().__init__(jobs, results)
        self.save_path = save_path

    # @profile  # For memory profiling
    def do_job(self, crx_id):
        """
        Get CRX IDs from the jobs queue, download the file, put the save path
        on the results queue. Skip extensions (version must match) that we've
        already downloaded before.

        :return: None
        :rtype: None
        """
        # Download the CRX file, put the full save path on the results queue
        try:
            crx_path = download(crx_id, self.save_path)
        except FileExistsError as err:
            # This should only happen if the versions match. Unfortunately, we can't assume the other version
            # completed successfully, so we need to extract the crx_path from the error message.
            crx_path = err.filename
        except FileNotFoundError:
            # Probably couldn't properly save the file because of some weird characters in the path we tried
            # to save it at. Keep the ID of the CRX so we can try again later.
            logging.warning('%s  Failed to save CRX' % crx_id)
            with open(path.join(DBLING_DIR, 'src', 'failed_downloads.txt'), 'a') as fout:
                fout.write(crx_id + '\n')
            del fout
            return
        except requests.HTTPError as err:
            # Something bad happened trying to download the actual file. No way to know how to resolve it, so
            # just skip it and move on.
            logging.warning('%s  Download failed (%s %s)' % (crx_id, err.response.status_code, err.response.reason))
            with open(path.join(DBLING_DIR, 'src', 'failed_downloads.txt'), 'a') as fout:
                fout.write(crx_id + '\n')
            del fout
            return
        except:
            raise
        crx_version = get_crx_version(crx_path)
        self.results.put((crx_id, crx_version, crx_path, datetime.today()))
        self.log_it('Download', crx_id)


class UnpackWorker(_MyWorker):

    def __init__(self, downloads, unpacked_dirs, extract_path):
        super().__init__(downloads, unpacked_dirs)
        self.ex_path = extract_path

    # @profile  # For memory profiling
    def do_job(self, job):
        crx_id, crx_version, crx_path, dt_avail = job
        extracted_path = path.join(self.ex_path, crx_id, crx_version)
        try:
            unpack(crx_path, extracted_path, overwrite_if_exists=True)
        except FileExistsError:
            # No need to get the path from the error since we already know the extracted path
            pass
        except BadZipFile:
            logging.warning('%s  Failed to unzip file because it isn\'t valid.' % crx_id)
            with open(path.join(DBLING_DIR, 'src', 'failed_downloads.txt'), 'a') as fout:
                fout.write(crx_id + '\n')
            del fout
            return
        except MemoryError:
            logging.warning('%s  Failed to unzip file because of a memory error.' % crx_id)
            with open(path.join(DBLING_DIR, 'src', 'failed_downloads.txt'), 'a') as fout:
                fout.write(crx_id + '\n')
            del fout
            return
        except (IndexError, IsADirectoryError):
            logging.warning('%s  Failed to unzip file likely because of a member filename error.' % crx_id, exc_info=1)
            with open(path.join(DBLING_DIR, 'src', 'failed_downloads.txt'), 'a') as fout:
                fout.write(crx_id + '\n')
            del fout
            return
        self.results.put((crx_id, crx_version, extracted_path, dt_avail))
        self.log_it('Unpack', crx_id)


class CentroidWorker(_MyWorker):

    def __init__(self, unpacked_dirs, dir_graphs):
        super().__init__(unpacked_dirs, dir_graphs)

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
        self.log_it('Centroid calculation', crx_id)


class DatabaseWorker(_MyWorker):

    def __init__(self, centroids, database_metadata):
        """

        :param centroids: The queue of computed centroids.
        :type centroids: queue.Queue
        :param database_metadata: A metadata object bound to an instantiated
                                  engine.
        :type database_metadata: MetaData
        :return:
        """
        super().__init__(centroids, None)
        self.extension = Table('extension', database_metadata)

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
            return

        # Add entry to the database
        cent_vals['ext_id'] = crx_id
        cent_vals['version'] = crx_version
        cent_vals['profiled'] = datetime.today()
        cent_vals['last_known_available'] = dt_avail
        with self.db_conn.begin():
            self.db_conn.execute(self.extension.insert().values(cent_vals))
        self.log_it('Database entry', crx_id, logging.INFO)

        # Try and conserve memory usage
        del cent_vals, crx_id, crx_version, row


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
    logging.basicConfig(filename=_log_path, level=logging.INFO, format=log_format)

    if args['-u']:
        with open(path.join(DBLING_DIR, 'src', 'crx_conf.json')) as _fin:
            _conf = json.load(_fin)
        # Try to conserve memory usage
        del _fin

        # Connect to database
        _db_meta = _init_db(_conf['db'])

        # This allows the calling function to specify a local filename to use instead of downloading a fresh sitemap
        # from Google, which takes a while to finish.
        _update_crx_list(_conf['extension_list_url'], _db_meta, show_progress=args['-p'])
        exit(0)

    logging.info('Starting CRX downloader.')
    update_database(download_fresh_list=(not args['-s']),
                    thread_count=int(args['--thread-count']),
                    queue_max=int(args['--queue-max']),
                    show_progress=args['-p'],
                    start_at=args['-b'])
