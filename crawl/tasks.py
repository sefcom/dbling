# *-* coding: utf-8 *-*

import logging
from datetime import timedelta, datetime
from json import dumps, load
from json.decoder import JSONDecodeError
from math import ceil
from os import path, listdir, remove
from tempfile import TemporaryDirectory
from time import perf_counter, sleep

from celery import chord
from crx_unpack import *
from crx_unpack.encrypted_dir import EncryptedTempDirectory
from requests import HTTPError

from common.centroid import calc_centroid
from common.const import EXT_NAME_LEN_MAX
from common.crx_conf import conf as _conf
from common.graph import make_graph_from_dir
from common.sync import acquire_lock
from common.util import calc_chrome_version, dt_dict_now, MalformedExtId, get_crx_version, cent_vals_to_dict, \
    MunchyMunch, PROGRESS_PERIOD, ttl_files_in_dir, get_id_version, chunkify
from crawl.celery import app
from crawl.db_iface import *
from crawl.webstore_iface import *

CHROME_VERSION = calc_chrome_version(_conf.version, _conf.release_date)
DOWNLOAD_URL = _conf.url.format(CHROME_VERSION, '{}')
RETRY_DELAY = 5  # Delay for 5 seconds before retrying tasks
JOB_ID_FMT = '%Y-%m-%d_%H-%M-%S'

TESTING = READ_ONLY

CHUNK_SIZE = 10 * 1000
TEST_LIMIT = float('inf')  # 5000  # Set to float('inf') when not testing

##################
#
#   Beat Tasks
#
##################


@app.task(send_error_emails=True)
def start_list_download():
    """Download list of current CRXs from Google, start profiling each one.

    Initiated by a Celery "beat" configuration in :mod:`crawl.celery_config`.

    Uses a Celery chord to initiate processing all of the CRXs with a single
    callback task (:func:`summarize_job`) that summarizes all the work done in
    an email sent to the admins listed in :mod:`crawl.celery_config`.

    Adds the following keys to ``crx_obj``:

    - ``id``: The 32 character ID of the extension.
    - ``dt_avail``: Date and time the list is downloaded.
    - ``msgs``: Array of progress messages. These strings are what are compiled
      by :func:`summarize_job` to report on the work done.
    - ``job_num``: Index within the current crawl. Although we don't have any
      guarantee that the extensions will be profiled precisely in order, this
      gives tasks processing an extension some idea of how far along in the
      crawl things are. This allows us to do subjective logging (log progress
      only if the job number % 1000 == 0) at higher levels to keep any watching
      users apprised of progress without too many log entries.
    - ``job_ttl``: Total number of CRXs that will be processed; equal to the
      number of IDs in the downloaded list of extensions.
    """

    logging.info('Beginning list download...')

    dt_avail = dt_dict_now()  # All CRXs get the same value because we download the list at one specific time
    crx_list = DownloadCRXList(_conf.extension_list_url, return_count=True)

    if TESTING:
        logging.warning('TESTING MODE: All DB transactions will be rolled back, NOT COMMITTED.')

    # Download the list, add each CRX to DB, and keep track of how long it all takes
    t1 = perf_counter()
    list_count = 0
    for crx, num in crx_list:
        # We're doing this part synchronously because creating separate tasks for every CRX ID just to add it to the DB
        # create way more overhead than is necessary. Each DB transaction doesn't really incur enough of a performance
        # penalty to justify all the extra time spent sending and managing the messages. The only down sides are that
        # (1) we lose the ability to distribute the work to multiple nodes and (2) if the process is interrupted, then
        # we lose track of our progress.
        list_count += 1
        add_new_crx_to_db({'id': crx, 'dt_avail': dt_avail}, TESTING and not num % PROGRESS_PERIOD)
    ttl_time = str(timedelta(seconds=(perf_counter() - t1)))

    if list_count != len(crx_list):
        msg = 'Counts of CRXs don\'t match. Downloader reported {} but processed {}.'.format(len(crx_list), list_count)
        logging.critical(msg)
        app.mail_admins('dbling: Problem encountered while downloading lists', msg)
        return

    # Notify the admins that the download is complete and the list of CRX IDs has been updated
    email_list_update_summary.delay(len(crx_list), ttl_time)

    # Split the IDs into sub-lists of CHUNK_SIZE. Each chunk of IDs should be processed using a chord that has as the
    # callback the summarize() function, which keeps track of how many chunks to expect, which ones have completed,
    # and a summary of their statistics. When all chunks have completed, summarize() will send an email with the final
    # stats tally.
    logging.info('Starting extension download/extract/profile process. There are {} total IDs.'.format(len(crx_list)))

    job_id = datetime.now().strftime(JOB_ID_FMT)
    ttl_files = len(crx_list)
    # The code below needs to handle floats because TEST_LIMIT might be infinity
    ttl_chunks = ceil(min(float(ttl_files), TEST_LIMIT) / CHUNK_SIZE)

    for chunk_num, sub_list in enumerate(chunkify(crx_list, CHUNK_SIZE)):
        chord((process_crx.s(make_crx_obj(crx, dt_avail, num, ttl_files)) for crx, num in sub_list))(
            summarize.s(job_id=job_id, chunk_num=chunk_num, ttl_chunks=ttl_chunks))


def make_crx_obj(id_, dt_avail, job_num, job_ttl):
    return {'id': id_, 'dt_avail': dt_avail, 'msgs': [], 'job_num': job_num, 'job_ttl': job_ttl}


@app.task(send_error_emails=True, base=SqlAlchemyTask)
def start_redo_extract_profile():
    """Start re-profiling process on the CRXs already downloaded.

    Adds the following keys to ``crx_obj`` (from :func:`crxs_on_disk`):

    - ``id``: The 32 character ID of the extension.
    - ``version``: Version number of the extension, as obtained from the final
      URL of the download. This may differ from the version listed in the
      extension's manifest.
    - ``msgs``: Array of progress messages. These strings are what are compiled
      by :func:`summarize_job` to report on the work done.
    - ``job_num``: Index within the current crawl. Although we don't have any
      guarantee that the extensions will be profiled precisely in order, this
      gives tasks processing an extension some idea of how far along in the
      crawl things are. This allows us to do subjective logging (log progress
      only if the job number % 1000 == 0) at higher levels to keep any watching
      users apprised of progress without too many log entries.
    - ``job_ttl``: Total number of CRXs that will be processed; equal to the
      number of IDs in the downloaded list of extensions.
    - ``filename``: The basename of the CRX file (not the full path)
    - ``full_path``: The location (full path) of the downloaded CRX file
    """
    # Using the `crxs_on_disk` generator, send all the CRXs to be queued, then summarize the results
    logging.info('Beginning re-profiling process of all CRXs already downloaded.')

    job_id = datetime.now().strftime(JOB_ID_FMT)
    ttl_files = ttl_files_in_dir(_conf.save_path, pat='crx')
    # The code below needs to handle floats because TEST_LIMIT might be infinity
    ttl_chunks = ceil(min(float(ttl_files), TEST_LIMIT) / CHUNK_SIZE)

    for chunk_num, sub_list in enumerate(chunkify(crxs_on_disk(limit=TEST_LIMIT), CHUNK_SIZE)):
        chord((redo_extract_profile.s(crx_obj) for crx_obj in sub_list))(
            summarize.s(job_id=job_id, chunk_num=chunk_num, ttl_chunks=ttl_chunks))


#####################
#
#   Entry Points
#
#####################


@app.task(base=SqlAlchemyTask)
@MunchyMunch
def process_crx(crx_obj):
    """Control the downloading, extracting, and profiling of the CRX.

    Celery cannot synchronize groups, so we have to synchronously call the
    functions for each step: download, extract, profile.

    We use a temporary directory for extracting extensions for two reasons.
    First, using a real directory greatly increases the file operations that
    have to occur via ``sshfs``, which slows things down and increases the I/O
    burden on ``dbling-master``. A temp directory keeps the files local to the
    worker machine and avoids this issue.

    Second, there aren't any very good reasons for keeping three versions of
    every extension. Prior to incorporating the :mod:`tempfile` module, we
    were saving the CRX, the zip version (which is just the CRX without the
    headers), and the extracted zip. Eliminating the latter two versions
    reduces the size of the data set.

    Adds the following keys to ``crx_obj``:

    - ``extracted_path``: Temporary dir where the extension's files will be
      unpacked.
    - ``enc_extracted_path``: Encrypted temporary dir that eCryptfs will mount
      to the ``extracted_path``. This is the directory that will be used for
      profiling the extension.
    - ``stop_processing``: Flag indicating an error during processing.

    :param crx_obj: Details of a single CRX, which gets updated at every step.
    :type crx_obj: Munch
    :return: Error or success message describing status. These messages from
        all of the process_crx() tasks are synchronized and then sent to be
        summarized by the summarize_job() task.
    :rtype: list
    """
    # This flag tells us if any error occur that are bad enough we should stop processing the CRX
    crx_obj.stop_processing = False

    with TemporaryDirectory(dir=_conf.extract_dir) as extracted_path, \
            EncryptedTempDirectory(dir=_conf.extract_dir, upper_dir=extracted_path) as enc_extracted_path:
        # These temporary directories will only exist within this "with" clause
        crx_obj.extracted_path = extracted_path
        crx_obj.enc_extracted_path = enc_extracted_path

        # The three steps
        for step in (download_crx, extract_crx, profile_crx):
            crx_obj = step(crx_obj)
            if crx_obj.stop_processing:
                break

    log = logging.info if not (crx_obj.job_num % PROGRESS_PERIOD) else logging.debug
    log('{} [{}/{}]  Completed processing CRX'.format(crx_obj.id, crx_obj.job_num, crx_obj.job_ttl))

    return crx_obj.msgs


@app.task(base=SqlAlchemyTask)
@MunchyMunch
def redo_extract_profile(crx_obj):
    """Control the re-profiling steps of extraction and profiling for a CRX.

    Functions very similarly to the :func:`process_crx` task, so it may be
    helpful to refer to its documentation.

    Adds the following keys to ``crx_obj``:

    - ``extracted_path``: Temporary dir where the extension's files will be
      unpacked.
    - ``enc_extracted_path``: Encrypted temporary dir that eCryptfs will mount
      to the ``extracted_path``. This is the directory that will be used for
      profiling the extension.
    - ``stop_processing``: Flag indicating an error during processing.

    :param crx_obj: Details of a single CRX, which gets updated at every step.
    :type crx_obj: Munch
    :return: Error or success message describing status. These messages from
        all of the redo_extract_profile() tasks are synchronized and then sent
        to be summarized by the summarize_job() task.
    :rtype: list
    """
    # This flag tells us if any error occur that are bad enough we should stop processing the CRX
    crx_obj.stop_processing = False

    with TemporaryDirectory(dir=_conf.extract_dir) as extracted_path, \
            EncryptedTempDirectory(dir=_conf.extract_dir, upper_dir=extracted_path) as enc_extracted_path:
        # These temporary directories will only exist within this "with" clause
        crx_obj.extracted_path = extracted_path
        crx_obj.enc_extracted_path = enc_extracted_path

        # The two re-profiling steps
        for step in (extract_crx, profile_crx):
            crx_obj = step(crx_obj, re_profiling=True)
            if crx_obj.stop_processing:
                break

    log = logging.info if not (crx_obj.job_num % PROGRESS_PERIOD) else logging.debug
    log('{} [{}/{}]  Completed re-profiling CRX'.format(crx_obj.id, crx_obj.job_num, crx_obj.job_ttl))

    return crx_obj.msgs


#######################
#
#   Worker Functions
#
#######################


def download_crx(crx_obj):
    """Download and save the CRX, processes any errors.

    Adds the following keys to ``crx_obj``:

    - ``dt_downloaded``: Date and time when the CRX was downloaded.
    - ``version``: Version number of the extension. Typically set in
      :func:`webstore_iface.save_crx`. Only set here if a duplicate download
      was detected by :func:`db_iface.db_download_complete`.
    - ``filename``: Base name of the CRX, in format <id>_<version>.crx (set in
      :func:`save_crx`).
    - ``full_path``: Location of CRX. Typically set in :func:`save_crx`. Only
      set here if a duplicate download was detected by
      :func:`db_iface.db_download_complete`.

    This calls :func:`crawl.webstore_iface.save_crx` which also adds keys.

    :param crx_obj: Previously collected information about the extension.
    :type crx_obj: munch.Munch
    :return: Updated version of ``crx_obj``.
    :rtype: munch.Munch
    """
    logging.debug('{} [{}/{}]  Starting download of CRX'.format(crx_obj.id, crx_obj.job_num, crx_obj.job_ttl))

    try:
        # Save the CRX, then check if the DB already has this version.
        crx_obj = save_crx(crx_obj, DOWNLOAD_URL, save_path=_conf.save_path)
        crx_obj.dt_downloaded = dt_dict_now()  # Check duplicate will use this to insert a new row if needed

        db_download_complete(crx_obj)

    except MalformedExtId:
        # Don't attempt to download the extension
        crx_obj.msgs.append('-Invalid extension ID: Has invalid form')
        crx_obj.stop_processing = True

    except HTTPError as err:
        # Something bad happened trying to download the actual file. No way to know how to resolve it, so
        # just skip it and move on.
        logging.warning('{} [{}/{}]  Download failed ({} {})'.format(crx_obj.id, crx_obj.job_num, crx_obj.job_ttl,
                                                                     err.response.status_code, err.response.reason))
        crx_obj.msgs.append('-Got HTTPError error when downloading (non 200 code)')
        crx_obj.stop_processing = True

    except ExtensionUnavailable:
        # The URL we requested should have had at least one redirect, leaving the first URL in the history. If the
        # request's history has no pages, we know the extension is not available on the Web Store.
        crx_obj.msgs.append('-Invalid extension ID: No 301 status when expected')
        # TODO: Save in DB that it is unavailable?
        crx_obj.stop_processing = True

    except DuplicateDownload:
        # The database already has information on this version. The only thing that needs to happen is update the
        # last known available date, which should have already been taken care of in db_download_complete().
        crx_obj.msgs.append('|Updated an existing extension entry in the DB before unpacking')
        crx_obj.stop_processing = True

    except FileExistsError as err:
        # Only happens when the versions match and we've chosen not to overwrite the previous file. In such a case,
        # there's no guarantee that the other file made it through the whole profiling process, so we need to
        # extract the crx_path from the error message so we can still profile it.
        crx_obj.full_path = err.filename
        crx_obj.version = get_crx_version(crx_obj.full_path)
        crx_obj.msgs.append('+CRX download completed, but version matched previously downloaded file. '
                            'Profiling old file.')

    except FileNotFoundError as err:
        # Probably couldn't properly save the file because of some weird characters in the path we tried
        # to save it at. Keep the ID of the CRX so we can try again later.
        logging.warning('{} [{}/{}]  Failed to save CRX'.format(crx_obj.id, crx_obj.job_num, crx_obj.job_ttl),
                        exc_info=err)
        crx_obj.msgs.append('-Got FileNotFound error when trying to save the download')
        crx_obj.stop_processing = True

    except BadDownloadURL:
        # Most likely reasons why this error is raised: 1) the extension is part of an invite-only beta or other
        # restricted distribution, or 2) the extension is listed as being compatible with Chrome OS only.
        # Until we develop a workaround, just skip it.
        logging.debug('{} [{}/{}]  Bad download URL'.format(crx_obj.id, crx_obj.job_num, crx_obj.job_ttl))
        crx_obj.msgs.append('-Denied access to download')
        crx_obj.stop_processing = True

    except VersionExtractError as err:
        logging.warning('{} [{}/{}]  Version number extraction failed'.
                        format(crx_obj.id, crx_obj.job_num, crx_obj.job_ttl))
        logging.debug('{}  Additional info about version number extraction error:\n'.format(crx_obj.id), exc_info=err)
        crx_obj.msgs.append("-Couldn't extract version number")
        crx_obj.stop_processing = True

    except DbActionFailed:
        crx_obj.msgs.append('-DB action failed while saving download information')

    except:
        logging.critical('{} [{}/{}]  An unknown error occurred while downloading'.
                         format(crx_obj.id, crx_obj.job_num, crx_obj.job_ttl), exc_info=1)
        raise

    else:
        crx_obj.msgs.append('+CRX download complete, fresh file saved')

    return crx_obj


def extract_crx(crx_obj, **kwargs):
    """Unpack (extract) the CRX, process any errors.

    Adds the following key to ``crx_obj``:

    - ``dt_extracted``: Date and time the extraction was completed.

    Also calls :func:`read_manifest`, which adds the following keys to
    ``crx_obj``:

    - ``name``: Name of the extension as specified in the manifest.
    - ``m_version``: Version of the extension as specified in the manifest.

    :param munch.Munch crx_obj: Previously collected information about the
        extension.
    :return: Updated version of ``crx_obj``.
    :rtype: munch.Munch
    """

    # TODO: Does the image tally provide any useful information?
    try:
        unpack(crx_obj.full_path, crx_obj.extracted_path, overwrite_if_exists=True)

    except FileExistsError:
        # No need to get the path from the error since we already know the extracted path
        crx_obj.msgs.append("|Failed to overwrite an existing Zip file, but didn't crash")

    except BadCrxHeader:
        logging.warning('{} [{}/{}]  CRX had an invalid header'.format(crx_obj.id, crx_obj.job_num, crx_obj.job_ttl))
        crx_obj.msgs.append('-CRX header failed validation')
        crx_obj.stop_processing = True

    except BadZipFile:
        logging.warning('{} [{}/{}]  Failed to unzip file because it isn\'t valid'.
                        format(crx_obj.id, crx_obj.job_num, crx_obj.job_ttl))
        crx_obj.msgs.append('-Zip file failed validation')
        crx_obj.stop_processing = True

    except MemoryError:
        logging.warning('{} [{}/{}]  Failed to unzip file because of a memory error'.
                        format(crx_obj.id, crx_obj.job_num, crx_obj.job_ttl))
        crx_obj.msgs.append('-Unpacking Zip file failed due do a MemoryError')
        crx_obj.stop_processing = True

    except (IndexError, IsADirectoryError):
        logging.warning('{} [{}/{}]  Failed to unzip file likely because of a member filename error'.
                        format(crx_obj.id, crx_obj.job_num, crx_obj.job_ttl), exc_info=1)
        crx_obj.msgs.append('-Other error while unzipping file')
        crx_obj.stop_processing = True

    except NotADirectoryError:
        logging.warning('{} [{}/{}]  Failed to unzip file because a file was incorrectly listed as a directory'.
                        format(crx_obj.id, crx_obj.job_num, crx_obj.job_ttl), exc_info=1)
        crx_obj.msgs.append('-Unpacking Zip file failed due to a NotADirectoryError')
        crx_obj.stop_processing = True

    except OSError:
        logging.error('Info on badly-named CRX:\n{}'.format(crx_obj))
        raise

    except:
        logging.critical('{} [{}/{}]  An unknown error occurred while unpacking'.
                         format(crx_obj.id, crx_obj.job_num, crx_obj.job_ttl), exc_info=1)
        raise

    else:
        crx_obj.msgs.append('+Unpacked a Zip file')
        logging.debug('{} [{}/{}]  Unpack complete'.format(crx_obj.id, crx_obj.job_num, crx_obj.job_ttl))
        crx_obj.dt_extracted = dt_dict_now()
        crx_obj = read_manifest(crx_obj)
        try:
            db_extract_complete(crx_obj)
        except DbActionFailed:
            crx_obj.msgs.append('-DB action failed while saving extraction information')

    return crx_obj


def read_manifest(crx_obj):
    """Retrieve name and version info from the manifest.

    For manifest file format info, see
    https://developer.chrome.com/extensions/manifest

    Adds the following keys to ``crx_obj``:

    - ``name``: Name of the extension as specified in the manifest.
    - ``m_version``: Version of the extension as specified in the manifest.

    :param munch.Munch crx_obj: Previously collected information about the
        extension.
    :return: Updated version of ``crx_obj``.
    :rtype: munch.Munch
    """
    # Open manifest file from extracted dir and get name and version of the extension
    try:
        with open(path.join(crx_obj.extracted_path, 'manifest.json')) as manifest_file:
            manifest = load(manifest_file)
    except JSONDecodeError:
        # The JSON file must have a Byte Order Marking (BOM) character. Try a different encoding that can handle this.
        try:
            with open(path.join(crx_obj.extracted_path, 'manifest.json'), encoding='utf-8-sig') as manifest_file:
                manifest = load(manifest_file)
        except JSONDecodeError:
            # Must be some invalid control characters still present. Just leave the name and version NULL.
            crx_obj.name = None
            crx_obj.m_version = None
            crx_obj.msgs.append('-Error decoding manifest due to JSON decoding error')
            logging.warning('{id} [{job_num}/{job_ttl}]  Error decoding manifest due to JSON decoding error'.
                            format(**crx_obj))
            return crx_obj
        else:
            crx_obj.msgs.append('|Manifest (JSON) contained BOM character, had to alter encoding')

    crx_obj.name = manifest['name'][:EXT_NAME_LEN_MAX]  # Truncate in case name has invalid length
    crx_obj.m_version = manifest['version']

    return crx_obj


def profile_crx(crx_obj, re_profiling=False):
    """Calculate a profile (centroid) using the extension's extracted files.

    Adds the following keys to ``crx_obj``:

    - ``dt_profiled``
    - ``cent_dict``: Centroid values in a dictionary with keys that correspond
      to columns in the ``extension`` table in the DB. Later, this dict is used
      to store all values that will be inserted into the DB. See
      :func:`db_iface.db_profile_complete` for more information. Centroid keys
      include:

      - ``num_dirs``
      - ``num_files``
      - ``perms``
      - ``depth``
      - ``type``
      - ``size``

    This calls :func:`db_iface.db_profile_complete` which also adds keys to
    ``cent_dict``.

    :param munch.Munch crx_obj: Previously collected information about the
        extension.
    :param bool re_profiling: Set when we're re-profiling downloaded
        extensions. This keeps the database interface from attempting to update
        the ``dt_avail`` field.
    :return: Updated version of ``crx_obj``.
    :rtype: munch.Munch
    """
    # Generate graph from directory and centroid from the graph
    dir_graph = make_graph_from_dir(crx_obj.enc_extracted_path)
    cent_vals = calc_centroid(dir_graph)
    crx_obj.cent_dict = cent_vals_to_dict(cent_vals)

    crx_obj.msgs.append('+Extension successfully profiled, centroid calculated')
    logging.debug('{} [{}/{}]  Centroid calculation'.format(crx_obj.id, crx_obj.job_num, crx_obj.job_ttl))
    crx_obj.dt_profiled = dt_dict_now()

    return db_profile_complete(crx_obj, update_dt_avail=not re_profiling)


##################################
#
#   Helper Tasks and Functions
#
##################################


@app.task
def email_list_update_summary(id_count, ttl_time):
    """Email admins that list download has completed.

    Also logs the information at the WARNING level.

    :param id_count: Number of extension IDs processed. Note that this may and
        probably will differ from the number of IDs added to the database.
    :type id_count: int
    :param ttl_time: Length of time it took to download the list and update the
        database.
    :type ttl_time: str
    :rtype: None
    """
    subject = 'dbling: List update complete'
    body = 'Extension IDs: {}\nRun time: {}'.format(id_count, ttl_time)
    try:
        app.mail_admins(subject, body)
    except ConnectionRefusedError:
        # Raised when running on a machine that doesn't accept SMTP connections
        pass
    logging.warning('{}\n{}'.format(subject, body))


@app.task(bind=True)
def summarize(self, jobs, *, job_id, chunk_num, ttl_chunks):
    """Gather all the sub-job stats, email to admins.

    Also logs the information at the WARNING level.

    :param self: Because this is a "bound" function, it will have access to
        additional methods via the ``self`` parameter. Not sure what type it is.
    :param list jobs: List of messages. Should be from ``crx_obj.msgs``.
    :param str job_id: ID for the set of job chunks. Should be the timestamp
        with the format given in :data:`JOB_ID_FMT`.
    :param int chunk_num: Which chunk this set of results corresponds to. Must
        be in the range 0 to ``ttl_chunks``-1.
    :param int ttl_chunks: Total number of chunks in this job. It is critical
        to how this function works that this number be accurate.
    :rtype: None
    """
    with acquire_lock(job_id, wait=RETRY_DELAY):
        # Compute the file name where the job details are (will be) stored
        detail_filename = 'job_detail-{}.json'.format(job_id)

        # First chunk encountered of the set, need to initialize
        if not path.exists(detail_filename):
            action = 'Initialized'
            # Create list of all chunks
            all_jobs = list(range(ttl_chunks))
            stats = {}

        # File exists, load previous data
        else:
            action = 'Appended'
            with open(detail_filename) as f:
                job_data = load(f)
            all_jobs = job_data['all_jobs']
            stats = job_data['stats']

        # Remove the current chunk number from the list of all jobs
        try:
            all_jobs.remove(chunk_num)
        except ValueError:
            logging.critical('Unable to find chunk {} in list of all chunks for job {}'.format(chunk_num, job_id))

        # Merge the current chunk of job data with the previous
        ttl_stats_merged = 0
        for job in jobs:
            for stat_type in job:
                try:
                    stats[stat_type] += 1
                except KeyError:
                    # Key didn't already exist for this statistic, so create it
                    stats[stat_type] = 1
            ttl_stats_merged += 1
        logging.info('Job: {}  {} stats from {} jobs. Chunk: {} / {}'
                     .format(job_id, action, ttl_stats_merged, chunk_num + 1, ttl_chunks))

        # If the job is done, delete the job file, email admins, log results
        if not len(all_jobs):
            logging.info('Job complete. Deleting job detail file {}'.format(detail_filename))
            remove(detail_filename)

            subject = 'dbling: Profiling and centroid calculations complete'
            body = dumps(stats, indent=2, sort_keys=True)
            try:
                app.mail_admins(subject, body)
            except ConnectionRefusedError:
                # Raised when running on a machine that doesn't accept SMTP connections
                pass

            logging.warning('{}\n{}'.format(subject, body))

        # Otherwise, save the current job information
        else:
            logging.debug('Saving data for job {}'.format(job_id))
            with open(detail_filename, 'w') as f:
                f.write(dumps({'all_jobs': all_jobs, 'stats': stats}))


def crxs_on_disk(crx_dir=_conf.save_path, limit=float('inf')):
    """Generate crx_obj dicts for CRXs already downloaded to ``crx_dir``.

    :param str crx_dir: Directory where the CRXs are saved when downloaded.
    :param limit: When testing, this can be set to a number, and only that
        many CRXs will be returned. If the value of limit is a `float` instead
        of an `int` it should be infinity (e.g. ``float('inf')``).
    :type limit: int or float
    :return: Dict with the following keys:

        - ``id``
        - ``version``
        - ``msgs``
        - ``job_num``
        - ``job_ttl``
        - ``filename``
        - ``full_path``
    :rtype: dict
    """
    ttl = ttl_files_in_dir(crx_dir, pat='crx')
    logging.info('Total number of CRXs on disk: {}'.format(ttl))
    if limit != float('inf'):
        logging.info('... but ony {} will be processed while testing.'.format(limit))
    num = 0

    for filename in listdir(crx_dir):
        if filename == '0' or filename.rfind('.crx', -4) == -1:
            continue

        num += 1
        crx, version = get_id_version(filename)
        if num > limit:
            raise StopIteration

        yield {
            'id': crx,
            'version': version,
            'msgs': [],
            'job_num': num,
            'job_ttl': ttl,
            'filename': filename,
            'full_path': path.join(crx_dir, filename),
        }
