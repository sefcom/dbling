# *-* coding: utf-8 *-*

from __future__ import absolute_import

import logging
from datetime import timedelta
from json import dumps
from os import path
from time import perf_counter

from celery import chord
from crx_unpack import *
from requests import HTTPError

from common.crx_conf import conf as _conf
from common.util import calc_chrome_version, dt_dict_now, MalformedExtId, get_crx_version, \
    cent_vals_to_dict, make_graph_from_dir, MunchyMunch, PROGRESS_PERIOD
from common.centroid import calc_centroid
from crawl.celery import app
from crawl.webstore_iface import *
from crawl.db_iface import *

CHROME_VERSION = calc_chrome_version(_conf['version'], _conf['release_date'])
DOWNLOAD_URL = _conf['url'].format(CHROME_VERSION, '{}')

TESTING = READ_ONLY


@app.task
def start_list_download():
    """Download list of current CRXs from Google, start profiling each one.

    Initiated by a Celery "beat" configuration in `crawl.celery_config`.

    Uses a Celery chord to initiate processing all of the CRXs with a single
    callback task (`summarize_job`) that summarizes all the work done in an
    email sent to the admins listed in `crawl.celery_config`.

    Adds the following keys to `crx_obj`:

    - `id`: The 32 character ID of the extension.
    - `dt_avail`: Date and time the list is downloaded.
    - `msgs`: Array of progress messages. These strings are what are compiled
      by `summarize_job` to report on the work done.
    - `job_num`: Index within the current crawl. Although we don't have any
      guarantee that the extensions will be profiled precisely in order, this
      gives tasks processing an extension some idea of how far along in the
      crawl things are. This allows us to do subjective logging (log progress
      only if the job number % 1000 == 0) at higher levels to keep any watching
      users apprised of progress without too many log entries.
    - `job_ttl`: Total number of CRXs that will be processed; equal to the
      number of IDs in the downloaded list of extensions.
    """

    logging.info('Beginning list download...')

    dt_avail = dt_dict_now()  # All CRXs get the same value because we download the list at one specific time
    crx_list = DownloadCRXList(_conf['extension_list_url'])

    # TODO: Delete the next lines for production
    if TESTING:
        crx_list._downloaded_list = True
        crx_list._testing = True

    # Download the list, add each CRX to DB, and keep track of how long it all takes
    t1 = perf_counter()
    for crx in crx_list:
        # We're doing this part synchronously because creating separate tasks for every CRX ID just to add it to the DB
        # create way more overhead than is necessary. Each DB transaction doesn't really incur enough of a performance
        # penalty to justify all the extra time spent sending and managing the messages. The only down sides are that
        # (1) we lose the ability to distribute the work to multiple nodes and (2) if the process is interrupted, then
        # we lose track of our progress.
        add_new_crx_to_db({'id': crx, 'dt_avail': dt_avail}, TESTING and not crx_list.count % PROGRESS_PERIOD)
    ttl_time = str(timedelta(seconds=(perf_counter()-t1)))

    # Notify the admins that the download is complete and the list of CRX IDs has been updated
    email_list_update_summary.delay(crx_list.count, ttl_time)

    # Force the iterator back to the beginning (not generally good practice, but whatever)
    # This reuses the list downloaded earlier and changes the return value
    crx_list.reset_stale(ret_tup=True)

    # Send all CRXs to be queued, then summarize results
    chord((process_crx.s({'id': crx, 'dt_avail': dt_avail, 'msgs': [], 'job_num': num, 'job_ttl': crx_list.count})
           for crx, num in crx_list), summarize_job.s())()


@app.task(base=SqlAlchemyTask)
@MunchyMunch
def process_crx(crx_obj):
    """Control the downloading, extracting, and profiling of the CRX.

    Celery cannot synchronize groups, so we have to synchronously call the
    functions for each step: download, extract, profile.

    Adds the following key to `crx_obj`:

    - `stop_processing`: Flag indicating an error during processing.

    :param crx_obj: Details of a single CRX, which gets updated at every step.
    :type crx_obj: Munch
    :return: Error or success message describing status. These messages from
        all of the process_crx() tasks are synchronized and then sent to be
        summarized by the summarize_job() task.
    :rtype: str
    """
    # This flag tells us if any error occur that are bad enough we should stop processing the CRX
    crx_obj.stop_processing = False

    # The three steps
    for step in (download_crx, extract_crx, profile_crx):
        crx_obj = step(crx_obj)
        if crx_obj.stop_processing:
            break

    log = logging.info if not (crx_obj.job_num % PROGRESS_PERIOD) else logging.debug
    log('{} [{}/{}]  Completed processing CRX'.format(crx_obj.id, crx_obj.job_num, crx_obj.job_ttl))

    return crx_obj.msgs


# TODO: Add other tasks similar to process_crx() that only do the last two or one stages


def download_crx(crx_obj):
    """Download and save the CRX, processes any errors.

    Adds the following keys to `crx_obj`:

    - `dt_downloaded`: Date and time when the CRX was downloaded.
    - `version`: Version number of the extension. Typically set in `save_crx`.
      Only set here if a duplicate download was detected by
      `db_download_complete`.
    - `full_path`: Location of CRX. Typically set in `save_crx`. Only set here
      if a duplicate download was detected by `db_download_complete`.

    This calls :ref:`crawl.webstore_iface.save_crx` which also adds keys.

    :param crx_obj: Previously collected information about the extension.
    :type crx_obj: munch.Munch
    :return: Updated version of `crx_obj`.
    :rtype: munch.Munch
    """
    logging.debug('{} [{}/{}]  Starting download of CRX'.format(crx_obj.id, crx_obj.job_num, crx_obj.job_ttl))

    try:
        # Save the CRX, then check if the DB already has this version.
        crx_obj = save_crx(crx_obj, DOWNLOAD_URL, save_path=_conf['save_path'])
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
                        format(crx_obj.id, crx_obj.job_num, crx_obj.job_ttl), exc_info=err)
        crx_obj.msgs.append("-Couldn't extract version number")
        crx_obj.stop_processing = True

    except:
        logging.critical('{} [{}/{}]  An unknown error occurred while downloading'.
                         format(crx_obj.id, crx_obj.job_num, crx_obj.job_ttl), exc_info=1)
        raise

    else:
        crx_obj.msgs.append('+CRX download complete, fresh file saved')

    return crx_obj


def extract_crx(crx_obj):
    """Unpack (extract) the CRX, process any errors.

    Adds the following keys to `crx_obj`:

    - `extracted_path`: Location of the unpacked extension files.
    - `dt_extracted`: Date and time the extraction was completed.

    :param crx_obj: Previously collected information about the extension.
    :type crx_obj: munch.Munch
    :return: Updated version of `crx_obj`.
    :rtype: munch.Munch
    """

    extracted_path = path.join(_conf['extract_dir'], crx_obj.id, crx_obj.version)

    # TODO: Does the image tally provide any useful information?
    try:
        unpack(crx_obj.full_path, extracted_path, overwrite_if_exists=True)

    except FileExistsError:
        # No need to get the path from the error since we already know the extracted path
        crx_obj.msgs.append("|Failed to overwrite an existing Zip file, but didn't crash")

    except BadCrxHeader:
        logging.warning('{} [{}/{}]  CRX had an invalid header'.format(crx_obj.id, crx_obj.job_number, crx_obj.job_ttl))
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

    except:
        logging.critical('{} [{}/{}]  An unknown error occurred while unpacking'.
                         format(crx_obj.id, crx_obj.job_num, crx_obj.job_ttl), exc_info=1)
        raise

    else:
        crx_obj.msgs.append('+Unpacked a Zip file')
        logging.debug('{} [{}/{}]  Unpack complete'.format(crx_obj.id, crx_obj.job_num, crx_obj.job_ttl))
        crx_obj.extracted_path = extracted_path
        crx_obj.dt_extracted = dt_dict_now()
        db_extract_complete(crx_obj)

    return crx_obj


def profile_crx(crx_obj):
    """Calculate a profile (centroid) using the extension's extracted files.

    Adds the following keys to `crx_obj`:

    - `dt_profiled`
    - `cent_dict`: Centroid values in a dictionary with keys that correspond to
      columns in the `extension` table in the DB. Later, this dict is used to
      store all values that will be inserted into the DB. See
      :ref:`db_profile_complete` for more information. Centroid keys include:

      - `num_dirs`
      - `num_files`
      - `perms`
      - `depth`
      - `type`
      - `size`

    This calls :ref:`db_profile_complete` which also adds keys to `cent_dict`.

    :param crx_obj: Previously collected information about the extension.
    :type crx_obj: munch.Munch
    :return: Updated version of `crx_obj`.
    :rtype: munch.Munch
    """
    # Generate graph from directory and centroid from the graph
    dir_graph = make_graph_from_dir(crx_obj.extracted_path)
    cent_vals = calc_centroid(dir_graph)
    crx_obj.cent_dict = cent_vals_to_dict(cent_vals)

    crx_obj.msgs.append('+Extension successfully profiled, centroid calculated')
    logging.debug('{} [{}/{}]  Centroid calculation'.format(crx_obj.id, crx_obj.job_num, crx_obj.job_ttl))
    crx_obj.dt_profiled = dt_dict_now()

    return db_profile_complete(crx_obj)


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


@app.task
@MunchyMunch
def summarize_job(sub_jobs):
    """Gather all the sub-job stats, email to admins.

    Also logs the information at the WARNING level.

    :param sub_jobs: List of messages. Should be from `crx_obj.msgs`.
    :type sub_jobs: list
    :rtype: None
    """
    stats = {}
    for job in sub_jobs:
        for stat_type in job:
            if stat_type not in stats:
                stats[stat_type] = 1
            else:
                stats[stat_type] += 1

    subject = 'dbling: Profiling and centroid calculations complete'
    body = dumps(stats, indent=2, sort_keys=True)
    try:
        app.mail_admins(subject, body)
    except ConnectionRefusedError:
        # Raised when running on a machine that doesn't accept SMTP connections
        pass
    logging.warning('{}\n{}'.format(subject, body))
