# -*- coding: utf-8 -*-
import io
import os
import pickle
from copy import deepcopy as copy
from datetime import date, timedelta
from os import path

import maya
from apiclient import http as http_, discovery
from progressbar import ProgressBar, UnknownLength

from apis.google import GoogleAPI
from const import DOWNLOAD_DIRECTORY, MIME, PAGE_SIZE
from util import print_json, convert_mime_type_and_extension, CalDict, DateRange

#: Location of pickled data when cached.
DRIVE_BACKUP_FILE = path.join(path.abspath(path.dirname(__file__)), '..', 'drive_data_backup.pkl')
#: Number of hours in a segment. Must be equally divisible by 24 to avoid issues.
SEGMENT_SIZE = 4


class DriveAPI(GoogleAPI):
    """Class to interact with Google Drive APIs.

    Documentation for the Python API:
    - https://developers.google.com/resources/api-libraries/documentation/drive/v3/python/latest/index.html
    """

    _service_name = 'drive'
    _version = 'v3'

    def __init__(self, http=None, impersonated_user_email=None, timezone=None):
        """
        Sets service object to make API calls to Google

        https://developers.google.com/drive/v3/web/quickstart/python

        :param http: http object
        :return DriveAPI Object
        """
        super().__init__(http, impersonated_user_email, timezone)
        # m = [x for x in dir(str) if x.startswith('s')]  # TODO: Playing around with a more intelligent get_all()

        self._team_drives = None

    def activity(self, level, what=('files', 'revisions'), use_cached=False, **kwargs):
        """Compile the user's activity.

        Note about revision history: One of the metadata fields for file
        revisions is called "keepForever". This indicates whether to keep the
        revision forever, even if it is no longer the head revision. If not
        set, the revision will be automatically purged 30 days after newer
        content is uploaded. This can be set on a maximum of 200 revisions for
        a file.

        :param str level: Level of detail on the activity. Accepted values:

            - ``'dy'``: Activity is summarized by day
            - ``'hr'``: Activity is summarized by hour, X:00:00 to X:59:59
            - ``'sg'``: Activity throughout the day is divided into three
              segments:
              - ``mor`` (Morning) 12 AM to 7:59:59 AM
              - ``mid`` (Midday) 8 AM to 3:59:59 PM
              - ``eve`` (Evening) 4 PM to 11:59:59 PM
        :param what: Indicates what kind of content to scan for activity.
            Accepted values:

            - ``'created'``
            - ``'revisions'``
            - ``'comments'``
        :type what: tuple or list
        :param bool use_cached: Whether or not to use cached data. When set,
            this avoids downloading all the file metadata from Google if a
            cached version of the data is available on disk.
        :return: A dictionary containing three keys: ``x``, ``y``, and ``z``.
            Each of these stores a list suitable for passing as the data set
            for a plot.
        :rtype: dict(str, list)
        :raises ValueError: When the ``level`` or ``what`` parameters have an
            unsupported format or value.
        """
        cr, rev, com = self.activity_data(level, what, use_cached)
        return self.activity_plot(created_data=cr, revision_data=rev, comment_data=com, level=level, what=what)

    def activity_data(self, level, what=('files', 'revisions'), use_cached=False):
        # Validate parameter values
        if level not in ('dy', 'sg', 'hr'):
            raise ValueError('Unsupported activity level: {}'.format(level))
        if not isinstance(what, (tuple, list)):
            raise ValueError('Unsupported format of activity content type.')
        for w in what:
            if w not in ('created', 'revisions', 'comments'):
                raise ValueError('Unsupported activity content type: {}'.format(w))

        cache_ok = True
        if use_cached:
            # Unpickle the cached data
            try:
                with open(DRIVE_BACKUP_FILE, 'rb') as f:
                    created_data, modified_data, revision_data, comment_data = pickle.load(f)
            except (pickle.UnpicklingError, FileNotFoundError, EOFError):
                use_cached = False
                cache_ok = False
                print('No valid cache found. Downloading fresh data.')
            else:
                print('Successfully loaded cached data.')

        if not use_cached:  # Don't use elif so we can change the value of use_cached if the cache is bad

            # Prompt before overwriting cache file (unless we already tried using it)
            if cache_ok and path.exists(DRIVE_BACKUP_FILE):
                res = input('Cache file exists. Okay to overwrite? [y/N] ')
                if not len(res) or res[0].lower() != 'y':
                    print('Exiting')
                    return

            # One or more of the following will be crunched, stored to data, and become the z-axis in the figure
            created_data = CalDict()
            modified_data = CalDict()  # TODO: Probably will remove this
            revision_data = CalDict()
            comment_data = CalDict()

            # bar = Counter(format='Downloaded metadata for %(value)d files')
            bar = ProgressBar(max_value=UnknownLength)
            fields = 'id, ownedByMe, createdTime, modifiedByMe, modifiedByMeTime, ' \
                     'viewedByMe, viewedByMeTime, trashed, trashedTime'
            cnt = 0
            for f in self.gen_file_data(fields):
                # Putting the progress bar here shows it to the user much sooner, indicates the program isn't hanging
                if not cnt % 10:
                    bar.update(cnt)

                # If the user created the file (i.e. is the owner), get the creation time
                if f.get('ownedByMe', False):
                    t = maya.parse(f['createdTime']).datetime(to_timezone=self.tz)
                    # import pdb; pdb.set_trace()
                    created_data[t.year][t.month][t.day][t.hour] += 1

                # If the user has modified the file, also get the modification time
                if f.get('modifiedByMe', False):
                    t = maya.parse(f['modifiedByMeTime']).datetime(to_timezone=self.tz)
                    modified_data[t.year][t.month][t.day][t.hour] += 1

                # Get file revisions, if requested
                if 'revisions' in what:
                    self._file_revisions(f['id'], revision_data)

                # Get file comments, if requested
                if 'comments' in what:
                    self._file_comments(f['id'], comment_data)

                cnt += 1

            bar.finish()
            print('Done downloading file metadata')

            # Cache the downloaded data
            with open(DRIVE_BACKUP_FILE, 'wb') as f:
                pickle.dump((created_data, modified_data, revision_data, comment_data), f, protocol=-1)

            # END OF FRESH DOWNLOAD CODE

        return created_data, revision_data, comment_data

    def activity_plot(self, created_data, revision_data, comment_data, level, what):
        data = []  # Will become the z-axis in the figure. list(list(int))
        data_labels = []  # Will become the labels of the y-axis in the figure
        date_range = DateRange(None, None)  # Will become the labels of the x-axis in the figure

        # Prep the labels
        segment_labels = ['{:02}00 to {:02}59'.format(x, x+SEGMENT_SIZE-1) for x in range(24) if not x % SEGMENT_SIZE]
        hour_labels = ['{0:02}00 to {0:02}59'.format(x) for x in range(24)]

        # Reverse the label times
        segment_labels.reverse()
        hour_labels.reverse()

        for method, lvl, data_set, label in (  # These are in the reverse order they'll appear on the y-axis
                ('comments', 'hr', comment_data, 'Drive Files - Comments '),
                ('comments', 'sg', comment_data, 'Drive Files - Comments from '),
                ('comments', 'dy', comment_data, 'Drive Files - Comments Daily'),
                ('revisions', 'hr', revision_data, 'Drive Files - Revisions '),
                ('revisions', 'sg', revision_data, 'Drive Files - Revisions from '),
                ('revisions', 'dy', revision_data, 'Drive Files - Revisions Daily'),
                ('created', 'hr', created_data, 'Drive Files - Created '),
                ('created', 'sg', created_data, 'Drive Files - Created from '),
                ('created', 'dy', created_data, 'Drive Files - Created Daily'),
        ):
            # Only use the specified types of data
            if method not in what:
                continue
            # Only use those methods for the specified level
            if lvl != level:
                continue

            # Add the labels to the label set according to what level we're using
            if lvl == 'dy':
                data_labels.append(label)
            elif lvl == 'sg':
                for l in segment_labels:
                    data_labels.append(label + l)
            elif lvl == 'hr':
                for l in hour_labels:
                    data_labels.append(label + l)

            # Crunch the data
            dates, data_set = crunch(data=data_set, level=level, start=self.start, end=self.end)

            # Align the date ranges
            if None in date_range:
                # No date range has been recorded yet. There are two possible reasons for this. First, no data sets
                # have been collected, so this will be the first possible date range. Second, other collected data sets
                # didn't have any data, in which case, if the data set we're currently processing *does* have data, we
                # need to make two adjustments. First, copy the dates from the current data set (we can actually do
                # this even if the dates are None without it having an effect). Second, we need to add zeros to the
                # data set now that we now how many of them we should add.
                date_range = copy(dates)
                if None in dates:
                    data.append([])
                else:
                    n = (dates.end - dates.start).days + 1
                    for i, d in enumerate(data):
                        if len(d):
                            raise RuntimeError('Non-empty data set with no date range detected.')
                        data[i] = [0] * n

            elif None in dates:
                if len(data_set[0]):
                    raise RuntimeError('Non-empty data set returned with no date range.')
                n = (date_range.end - date_range.start).days + 1
                data_set = [[0] * n]
                dates = DateRange(date_range.start, date_range.start)

            # If the date range is still None, that means there was no data
            if None in date_range:
                # TODO: Verify this is the correct thing to do here
                continue

            # We want to do the following two checks independently (i.e. without using elif statements) because it
            # may be that one range is not a subset of the other. In other words, range A may start before range B
            # and at the same time range B may end after range A. Keeping the condition checks separate handles both
            # adjustments. Also, this isn't a problem because of how Python handles multiplying lists by a negative
            # value, as seen in the following example:
            #
            # >>> [0] * -3
            # []

            renew_range = False
            if dates.start < date_range.start or date_range.end < dates.end:
                # Append/prepend values to the *other* lists of data
                renew_range = True
                pre = (date_range.start - dates.start).days
                post = (dates.end - date_range.end).days
                for i, d in enumerate(data):
                    data[i] = [0] * pre + data[i] + [0] * post

            if date_range.start < dates.start or dates.end < date_range.end:
                # Append/prepend values to the *current* list(s) of data
                renew_range = True
                pre = (dates.start - date_range.start).days
                post = (date_range.end - dates.end).days
                for i, d in enumerate(data_set):
                    data_set[i] = [0] * pre + data_set[i] + [0] * post

            if renew_range:
                date_range.start = date_range.start if date_range.start < dates.start else dates.start
                date_range.end = date_range.end if date_range.end > dates.end else dates.end

            # Add the new data to the data set
            data += data_set

        return {'x': [date_range.end - timedelta(days=x)
                      for x in range((date_range.end - date_range.start).days, -1, -1)],  # Reversed so dates ascend
                'y': data_labels,
                'z': data}

    def _file_revisions(self, file_id, data):
        """Retrieve revisions of a Google Document.

        This includes Google Docs, Google Sheets, etc.

        https://developers.google.com/resources/api-libraries/documentation/drive/v3/python/latest/drive_v3.revisions.html

        :param str file_id: The ID of the file.
        :param CalDict data: The data object to which the revision history will
            be added. This is modified directly, making it unnecessary to
            return the data.
        :rtype: None
        """
        args = {'fileId': file_id,
                'pageSize': PAGE_SIZE,
                'fields': 'nextPageToken, revisions(modifiedTime, lastModifyingUser)'}

        page_token = None
        while True:
            try:
                rev_set = self.service.revisions().list(pageToken=page_token, **args).execute()
            except discovery.HttpError:
                # The file does not support revisions.
                return
            page_token = rev_set.get('nextPageToken')
            for r in rev_set['revisions']:
                # TODO: Filter revisions that don't correspond to the target user
                # if r['lastModifyingUser']['emailAddress'] != self.target_email:
                #     continue

                # For now, we'll just filter by if the user is "me"
                try:
                    if not r['lastModifyingUser']['me']:
                        continue
                except KeyError:
                    # Sometimes there's a revision entry that doesn't include the last modifying user for whatever
                    # reason. Just skip that revision and get the rest.
                    continue

                t = maya.parse(r['modifiedTime']).datetime(to_timezone=self.tz)
                data[t.year][t.month][t.day][t.hour] += 1

            # page_token will be None when there are no more pages of results
            if page_token is None:
                break

    def _file_comments(self, file_id, data):
        """Retrieve comments from a Google Document.

        This includes Google Docs, Google Sheets, etc.

        API:
        https://developers.google.com/resources/api-libraries/documentation/drive/v3/python/latest/drive_v3.comments.html

        Reference:
        https://developers.google.com/drive/v3/reference/comments

        :param str file_id: The ID of the file.
        :param CalDict data: The data object to which the comment history will
            be added. This is modified directly, making it unnecessary to
            return the data.
        :rtype: None
        """
        args = {
            'fileId': file_id,
            'includeDeleted': True,
            'pageSize': PAGE_SIZE,
            'fields': 'nextPageToken, comments(createdTime, author, replies)',
        }

        page_token = None
        while True:
            comment_set = self.service.comments().list(pageToken=page_token, **args).execute()
            page_token = comment_set.get('nextPageToken')
            for c in comment_set['comments']:
                # TODO: Filter comments that don't correspond to the target user
                # if c['author']['emailAddress'] != self.target_email:
                #     continue

                # For now, we'll just filter by if the user is "me"
                if not c['author']['me']:
                    continue

                # Unlike revision history, the modified time of comments is the last time the comment or any of its
                # replies was modified. Since this is too broad, we just look at the time the comment was created.
                t = maya.parse(c['createdTime']).datetime(to_timezone=self.tz)
                data[t.year][t.month][t.day][t.hour] += 1

                # Log replies as well
                for repl in c['replies']:
                    # TODO: Filter replies that don't correspond to the target user
                    # if repl['author']['emailAddress'] != self.target_email:
                    #     continue

                    # For now, we'll just filter by if the user is "me"
                    if not repl['author']['me']:
                        continue

                    # Log the creation time
                    t = maya.parse(repl['createdTime']).datetime(to_timezone=self.tz)
                    data[t.year][t.month][t.day][t.hour] += 1

                    # If the modification time is different from the creation time, log it too
                    if repl['createdTime'] != repl['modifiedTime']:
                        t = maya.parse(repl['modifiedTime']).datetime(to_timezone=self.tz)
                        data[t.year][t.month][t.day][t.hour] += 1

            # page_token will be None when there are no more pages of results
            if page_token is None:
                break

    def get_about(self, fields='*'):
        """
        Retrieves information about the user's Drive. and system capabilities.

        https://developers.google.com/drive/v3/reference/about

        :param fields: fields to be returned
        :type fields: string
        :return: JSON
        """

        # So I can do this.. perfect
        about = self.service.about()
        results = about.get(fields=fields).execute()

        # why do I have this?
        if not results:
            return None
        else:
            return results

            # Needs to loop over all changes using pageToken from start_token and nextPageToken token

    @property
    def team_drives(self):
        """A list of team drives associated with the user.

        :rtype: list(str)
        """
        if isinstance(self._team_drives, list):
            return self._team_drives

        # Populate list of team drives
        self._team_drives = []
        page_token = None
        team_page_size = 100  # Range must be [1, 100]
        while True:
            t = self.service.teamdrives().list(pageToken=page_token, pageSize=team_page_size).execute()
            page_token = t.get('nextPageToken')
            self._team_drives += [x['id'] for x in t['teamDrives']]

            # page_token will be None when there are no more pages of results
            if page_token is None:
                break
        return self._team_drives

    def get_changes(self, spaces='drive', include_team_drives=True, restrict_to_my_drive=False,
                    include_corpus_removals=None, include_removed=None):
        """Return the changes for a Google Drive account.

        The set of changes as returned by this method are more suited for a
        file syncing application.

        In the returned :class:`dict`, the key for changes in the user's
        regular Drive is an empty string (``''``). The data for each Team Drive
        (assuming ``include_team_drives`` is `True`) is stored using a key in
        the format ``'team_drive_X'``, where ``X`` is the ID of the Team Drive.
        For the form of the JSON data, go to
        https://developers.google.com/resources/api-libraries/documentation/drive/v3/python/latest/drive_v3.teamdrives.html#list

        https://developers.google.com/drive/v3/reference/changes

        :param str spaces: A comma-separated list of spaces to query within the
            user corpus. Supported values are 'drive', 'appDataFolder' and
            'photos'.
        :param bool include_team_drives: Whether or not to include data from
            Team Drives as well as the user's Drive.
        :param bool restrict_to_my_drive: Whether to restrict the results to
            changes inside the My Drive hierarchy. This omits changes to files
            such as those in the Application Data folder or shared files which
            have not been added to My Drive.
        :param bool include_corpus_removals: Whether changes should include the
            file resource if the file is still accessible by the user at the
            time of the request, even when a file was removed from the list of
            changes and there will be no further change entries for this file.
        :param bool include_removed: Whether to include changes indicating that
            items have been removed from the list of changes, for example by
            deletion or loss of access.
        :return: All data on changes by the user in JSON format and stored in
            a :class:`dict`.
        :rtype: dict(str, dict)
        """
        args = {
            'spaces': spaces,
            'restrict_to_my_drive': restrict_to_my_drive,
            'include_corpus_removals': include_corpus_removals,
            'include_removed': include_removed,
        }

        # Get changes for regular Drive stuff
        changes = {'': self._get_changes(**args)}

        # Cycle through the Team Drives and get those too
        if include_team_drives:
            for t in self.team_drives():
                changes['team_drive_{}'.format(t)] = self._get_changes(team_drive_id=t, **args)

        return changes

    def _get_changes(self, spaces, team_drive_id=None, restrict_to_my_drive=False, include_corpus_removals=None,
                     include_removed=None):
        """

        :param str spaces: A comma-separated list of spaces to query within the
            user corpus. Supported values are 'drive', 'appDataFolder' and
            'photos'.
        :param str team_drive_id:
        :param bool restrict_to_my_drive: Whether to restrict the results to
            changes inside the My Drive hierarchy. This omits changes to files
            such as those in the Application Data folder or shared files which
            have not been added to My Drive.
        :param bool include_corpus_removals: Whether changes should include the
            file resource if the file is still accessible by the user at the
            time of the request, even when a file was removed from the list of
            changes and there will be no further change entries for this file.
        :param bool include_removed: Whether to include changes indicating that
            items have been removed from the list of changes, for example by
            deletion or loss of access.
        :return: The list of changes combined from all pages.
        :rtype: dict
        """
        chg = self.service.changes()
        args = {'supportsTeamDrives': True,  # "Whether the requesting application supports Team Drives."
                'teamDriveId': team_drive_id}

        # Get the first page token
        start = chg.getStartPageToken(**args).execute()['startPageToken']

        args.update({
            'pageToken': start,
            'pageSize': PAGE_SIZE,
            'includeTeamDriveItems': True if team_drive_id is not None else False,
            # supportsTeamDrives already defined above
            'restrictToMyDrive': restrict_to_my_drive,
            'spaces': spaces,
            # teamDriveId already defined above
            'includeCorpusRemovals': include_corpus_removals,
            'includeRemoved': include_removed,
        })

        # Send the first request (first page)
        req = chg.list(**args)
        resp = req.execute()

        # Process the response
        if True:
            raise NotImplementedError

        while True:
            req = chg.list_next(previous_request=req, previous_response=resp)
            resp = req.execute()  # Returns None when there are no more items in the collection

            if resp is None:
                break

            # Process the response
            pass

        # Return all the responses
        pass

    def gen_file_data(self, fields='*', spaces='drive', include_team_drives=True, corpora=None):
        """Generate the metadata for the user's Drive files.

        This function is a generator, so it yields the metadata for one file at
        a time. For the format of the :class:`dict` generated, see
        https://developers.google.com/resources/api-libraries/documentation/drive/v3/python/latest/drive_v3.files.html#list

        :param str fields: The metadata fields to retrieve.
        :param str spaces: A comma-separated list of spaces to query within the
            user corpus. Supported values are 'drive', 'appDataFolder' and
            'photos'.
        :param bool include_team_drives: Whether or not to include data from
            Team Drives as well as the user's Drive.
        :param str corpora: Comma-separated list of bodies of items
            (files/documents) to which the query applies. Supported bodies are
            'user', 'domain', 'teamDrive' and 'allTeamDrives'. 'allTeamDrives'
            must be combined with 'user'; all other values must be used in
            isolation. Prefer 'user' or 'teamDrive' to 'allTeamDrives' for
            efficiency.
        :return: The file metadata.
        :rtype: dict
        """
        args = {'spaces': spaces,
                'corpora': corpora,
                'fields': fields}

        # Get files from regular Drive
        yield from self._gen_file_data(**args)

        # Cycle through the Team Drives and get those too
        if include_team_drives:
            for t in self.team_drives:
                yield from self._gen_file_data(team_drive_id=t, **args)

    def _gen_file_data(self, fields, spaces, team_drive_id=None, corpora=None):
        """Helper method for :meth:`gen_file_data`.

        For descriptions of the parameters, see the signature for
        :meth:`gen_file_data`.
        """
        args = {
            'includeTeamDriveItems': True if team_drive_id is not None else False,
            'pageSize': PAGE_SIZE,
            'corpora': corpora,  # Not sure how this affects the results...
            'supportsTeamDrives': True,
            'spaces': spaces,
            'teamDriveId': team_drive_id,
            'fields': 'nextPageToken, files({})'.format(fields),
        }

        page_token = None
        while True:
            file_set = self.service.files().list(pageToken=page_token, **args).execute()
            page_token = file_set.get('nextPageToken')
            for f in file_set['files']:
                yield f

            # page_token will be None when there are no more pages of results
            if page_token is None:
                break

    def export_drive_file(self, file_data, download_path):
        """
        Exports and converts .g* files to real files and then downloads them

        https://developers.google.com/drive/v3/reference/files/export

        :param file_data: List of file(s) to be downloaded
        :type file_data: JSON
        :param download_path: Path where the file will be downloaded
        :return: boolean True if downloads succeeded, False if Downloads failed.
        """
        mime_type, extension = convert_mime_type_and_extension(file_data['mimeType'])

        if not mime_type or not extension:
            print('mime type is not found, dumping file\'s information')
            print_json(file_data)
            return False

        os.chdir(download_path)

        request = self.service.files().export(fileId=file_data['id'], mimeType=mime_type)
        fh = io.FileIO(file_data['name'] + extension, 'wb')
        downloader = http_.MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            print(file_data['name'])
            print('Download %d%%.' % int(status.progress() * 100))

        return True

    def export_real_file(self, file_data, download_path):
        """
        Downloads real files. AKA not .g*

        https://developers.google.com/drive/v3/reference/files/export

        :param file_data: List of file(s) to be downloaded
        :type file_data: JSON
        :param download_path: Path where the file will be downloaded
        :return: Nothing
        """
        os.chdir(download_path)
        request = self.service.files().get_media(fileId=file_data['id'])
        fh = io.FileIO(file_data['name'], 'wb')
        downloader = http_.MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            print(file_data['name'])
            print('Download %d%%.' % int(status.progress() * 100))

    # I am sorry for the recursion Mike...
    # TODO Sort the file list so that there is no need to check from the beginning every time
    # For some reason the orderby in the get_file_data() call works and puts folders first but
    # at some point it can put a file before the folders in the list which required this block of
    # code to be written horribly.
    # TODO fix this bug
    def handle_folder_helper(self, file_data_list, download_path, curr_folder_id):
        # Loop over all file data
        for file_data in file_data_list:
            # If file belong in current folder
            if str(file_data['parents'][0]) == str(curr_folder_id):
                # make new folder if it is a folder
                if str(file_data['mimeType']) == str(MIME['g_folder']):
                    os.mkdir(download_path + '/' + file_data['name'])
                    # every time we make a new folder we recursively call
                    self.handle_folder_helper(file_data_list, download_path + '/' + file_data['name'], file_data['id'])
                # it must be a file so download
                else:
                    if str(file_data['parents'][0]) == curr_folder_id:
                        if 'google-apps' not in str(file_data['mimeType']):
                            self.export_real_file(file_data, download_path)

                        elif 'folder' not in str(file_data['mimeType']):
                            download_succeeded = self.export_drive_file(file_data, download_path)

                            # In the event of a Mime Type conversion error the download process will stop
                            if download_succeeded is False:
                                print('Error has occurred, process was aborted.')

    # Always make sure you orderBy folder
    def handle_folders(self, file_list_array, download_path):
        # Get root id
        root_id = self.get_root_file_id()
        # recursively download everything in the drive
        self.handle_folder_helper(file_list_array, download_path, root_id)

    def get_root_file_id(self):
        root_id = self.service.files().get(fileId='root').execute()
        print_json(root_id)
        return root_id['id']

    # TODO HANDLE TRASH....
    def download_files(self, file_list_array=False):
        """
        Downloads files from the user's drive

        https://developers.google.com/drive/v3/web/manage-downloads

        :param file_list_array: list of file(s) to be downloaded
        :type file_list_array: array
        :return: Nothing
        """
        if not file_list_array:
            file_list_array = self.list_file_data()

        # If download directory is set us it for the download folder.
        # Otherwise use the directory of this project
        if DOWNLOAD_DIRECTORY is None:
            download_path = os.getcwd()
        else:
            download_path = path.expanduser(DOWNLOAD_DIRECTORY)
        if not path.exists(download_path + '/trash'):
            os.mkdir(download_path + '/trash')

        # Download trashed files first
        for file_data in file_list_array:
            if file_data['trashed']:
                if 'google-apps' not in str(file_data['mimeType']):
                    self.export_real_file(file_data, download_path + '/trash')

                elif 'folder' not in str(file_data['mimeType']):
                    download_succeeded = self.export_drive_file(file_data, download_path + '/trash')

                    # In the event of a Mime Type conversion error the download process will stop
                    if download_succeeded is False:
                        print('Error has occurred, process was aborted.')

        # Now download the rest of them
        self.handle_folders(file_list_array, download_path)

    def get_app_folder(self, fields='nextPageToken, files(id, name)'):
        """
        Returns the data in the users app data folder

        https://developers.google.com/drive/v3/reference/files/list

        :param fields: fields to be returned
        :type fields: string
        :return: JSON
        """
        response = self.service.files().list(spaces='appDataFolder', fields=fields, pageSize=10).execute()

        items = response.get('files', [])
        while 'nextPageToken' in response:
            response = self.service.files().list(spaces='appDataFolder', pageSize=1000,
                                                 pageToken=str(response['nextPageToken'])).execute()
            items.append(response.get('files', []))

        if not items:
            return None
        else:
            return items

    def get_photo_data(self, fields='nextPageToken, files(id,name)'):
        """
        Returns the data about the user's photos

        https://developers.google.com/drive/v3/reference/files/list

        :param fields: fields to be returned
        :type fields: string
        :return: JSON
        """
        response = self.service.files().list(spaces='photos', fields=fields, pageSize=10).execute()
        items = response.get('files', [])
        while 'nextPageToken' in response:
            response = self.service.files().list(spaces='photos', pageSize=1000,
                                                 pageToken=str(response['nextPageToken'])).execute()
            items.append(response.get('files', []))

        if not items:
            return None
        else:
            return items

    def get_all(self):
        """
        method used for testing

        :return: nothing
        """
        if False:
            print('File Data')
            metadata = self.list_file_data()
            print_json(metadata)
        if False:
            print('About')
            about_info = self.get_about()
            print_json(about_info)
        if False:
            start_token = self.get_start_page_token()
            print_json(start_token)
        if True:
            changes = self.get_changes()
            print_json(changes)
        if False:
            comments, ids = self.get_comments()
            print_json(comments)
            print_json(ids)
            if False:
                replies, parents = self.get_replies(comments, ids)
                print_json(replies)
                print_json(ids)
        if False:
            app_folder = self.get_app_folder()
            print_json(app_folder)

        if False:
            self.download_files()


def crunch(level, **kwargs):
    """Consolidate the data to the specified level.

    :param CalDict data: The data from parsing the Drive metadata.
    :param str level: Must be one of ``dy``, ``sg``, or ``hr``. For an
        explanation of these options, see the docstring for
        :meth:`DriveAPI.activity`.
    :param datetime.date start: The earliest data to collect.
    :param datetime.date end: The latest data to collect.
    :return: Tuple with two elements. The first is a :class:`DateRange` object
        which stores the first and last days with activity (the range of dates
        that the data corresponds to) in its :attr:`~DateRange.start` and
        :attr:`~DateRange.end` attributes, respectively. Both of these
        attributes are :class:`~datetime.date` objects.

        The second element in the returned tuple is a :class:`list` containing
        the data for each day. The contents of this list vary based on the
        value of ``level``:

        - ``dy``: A single :class:`list` of :class:`int`s, one for each day.
        - ``sg``: :class:`list`s of :class:`int`s. Each `list` corresponds to
          a segment, each `int` corresponds to a day. These lists are in
          reverse order, meaning the first `list` represents the last segment
          of a day.
        - ``hr``: :class:`list`s of :class:`int`s. Each `list` corresponds to
          an hour, each `int` corresponds to a day. These lists are in reverse
          order, meaning the first `list` represents the last hour of a day.
    :rtype: tuple(DateRange, list(list(int)))
    """
    if level == 'dy':
        return _do_crunch(num_hours=24, **kwargs)
    elif level == 'sg':
        return _do_crunch(num_hours=SEGMENT_SIZE, **kwargs)
    elif level == 'hr':
        return _do_crunch(num_hours=1, **kwargs)
    raise ValueError('Unsupported data crunching level: {}'.format(level))


def _do_crunch(data, num_hours, start=None, end=None):
    """Do the actual data crunching as requested of :func:`crunch`.

    :param CalDict data: The data to crunch.
    :param int num_hours: The number of hours that should be crunched together.
        For example, to consolidate the activity for an entire day,
        ``num_hours`` should be 24. To show each hour's activity separately,
        ``num_hours`` should be 1.
    :param datetime.date start: The earliest data to collect.
    :param datetime.date end: The latest data to collect.
    :return: See the docs for :func:`crunch`.
    """
    dates = DateRange(None, None)

    years = list(data.keys())
    years.sort()
    try:
        years = list(range(years[0], years[-1] + 1))  # Ensures we don't skip any years
    except IndexError:
        # Means there are no years
        pass

    months = [x for x in range(1, 13)]
    days = [x for x in range(1, 32)]

    new_data = []
    for x in range(24 // num_hours):
        new_data.append([])
    zeros = 0

    for y in years:
        if (start is not None and y < start.year) or \
                (end is not None and y > end.year):
            continue
        for m in months:
            for d in days:
                try:
                    day = date(y, m, d)
                except ValueError:
                    # Means we tried to make an invalid date, like February 30th. Just go to the next day.
                    continue
                # Stay within the specified range of dates
                if (start is not None and day < start) or \
                        (end is not None and day > end):
                    continue

                # Add up the hourly activity for the day
                i = sum(data[y][m][d])
                # Note: It's possible that by accessing the data

                if not dates.start:  # Have we stored the first day with data yet?
                    if not i:  # If this day doesn't have any data, go to the next day
                        continue
                    dates.start = day
                if i:
                    for s in range(len(new_data)):
                        new_data[-1 - s] += [None] * zeros
                        val = sum(data[y][m][d][s:s+num_hours])
                        new_data[-1 - s].append(val if val > 0 else None)
                    dates.end = day
                    zeros = 0
                else:
                    # Count zeros separately from non-zeros. Allows the end date to be the last day with data.
                    zeros += 1

    return dates, new_data
