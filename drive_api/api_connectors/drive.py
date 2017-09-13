# -*- coding: utf-8 -*-
import io
import os

from apiclient import http as http_, discovery

from api_connectors.google import GoogleAPI
from const import DOWNLOAD_DIRECTORY, MIME, PAGE_SIZE
from util import print_json, convert_mime_type_and_extension


class DriveAPI(GoogleAPI):
    """
    Class to interact with Google Drive APIs

    Documentation for the Python API:
    - https://developers.google.com/resources/api-libraries/documentation/drive/v3/python/latest/index.html
    """

    _service_name = 'drive'
    _version = 'v3'

    def __init__(self, http):
        """
        Sets service object to make API calls to Google

        https://developers.google.com/drive/v3/web/quickstart/python

        :param http: http object
        :return DriveAPI Object
        """
        super().__init__(http)

        self._team_drives = None

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
        while True:
            t = self.service.teamdrives().list(pageToken=page_token, pageSize=PAGE_SIZE).execute()
            assert isinstance(t, dict)
            page_token = t.get('nextPageToken')
            self._team_drives += [x['id'] for x in t['teamDrives']]

            # page_token will be None when there are no more pages of results
            if page_token is None:
                break

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
        :param bool include_team_drives: Whether or not to include
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
                args.update({'team_drive_id': t})
                changes['team_drive_{}'.format(t)] = self._get_changes(**args)

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
        args = {'supportsTeamDrives': True if team_drive_id is not None else False,
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

    def get_start_page_token(self, supports_team_drive=False, team_drive_id=None):
        """
        Gets the start page token, used to keep track of changes

        getStartPageToken: https://developers.google.com/drive/v3/reference/changes/getStartPageToken

        :param supports_team_drive: Whether the requesting application supports Team Drives. (Default: False)
        :type supports_team_drive: boolean
        :param team_drive_id: the ID of the team drive
        :type team_drive_id: string
        :return: JSON or None if improper params are in use
        """
        # Test to make sure you need both params
        if team_drive_id is None:
            token = self.service.changes().getStartPageToken().execute()
        elif supports_team_drive is True:
            token = self.service.changes().getStartPageToken(supportsTeamDrives=supports_team_drive).execute()
        else:
            print('Need to specify team_drive_id if application supports team drive')
            return None
        return token

    # Comments
    # TODO Test paging and that replies are returned
    def get_comments(self, fields='kind,comments', file_data=None):
        """
        Retrieves Comments from a Google Document. This includes gdocs, gsheets, ect

        https://developers.google.com/drive/v3/reference/comments

        :param fields: fields to be returned
        :type fields: string
        :param file_data: list of files
        :type file_data: JSON
        :return: JSON
        """
        return_ids = []
        comments = []
        if file_data is None:
            file_data = self.get_file_data()

        for data in file_data['files']:

            try:
                drive_file = self.service.comments().list(fileId=data['id'], fields=fields).execute()
            # Could never figure out the cause of this random exception
            except discovery.HttpError:
                continue

            if drive_file['comments']:
                return_ids.append(drive_file.get('id', []))
                comments.append(drive_file.get('comments', []))

                while 'nextPageToken' in drive_file:
                    try:
                        drive_file = self.service.comments().list(filedId=['id'], fields=fields,
                                                                  pageToken=drive_file['nextPageToken']).execute()
                    # Could never figure out the cause of this random exception
                    except discovery.HttpError:
                        continue
                    return_ids.append(drive_file.get('id', []))
                    comments.append(drive_file.get('comments', []))

        return comments, return_ids

    # This method is not needed, replies can easily be pulled through the get_comments method.
    # PAGING Needs to be fixed if method is to be used
    def get_replies(self, comment_data, comment_ids, fields='kind,replies'):
        """
        Returns replies for a Google Document

        https://developers.google.com/drive/v3/reference/replies

        :param comment_data:
        :param comment_ids:
        :param fields: fields to be returned
        :type fields: string
        :return: JSON
        """
        parent_ids = []
        replies = []
        # loop over each entry to get all comments for document
        for file_data in comment_data:
            i = 0
            temp = []
            for comment in file_data:
                try:
                    print(file_data['id'])
                    print(comment['id'])
                    replies = self.service.replies().list(fileId=file_data['id'], commentId=comment['id'],
                                                          fields=fields).execute()
                except discovery.HttpError:
                    continue

                if replies['replies']:
                    temp.append(replies['replies'])

            replies.append(temp)
            parent_ids.append(comment_ids[i])
            i += 1

        # if drive_file["comments"]:
        #    return_ids.append(data["id"])
        #    for comment in drive_file["comments"]:
        #        comments.append(comment)

        print(len(replies))
        print(len(parent_ids))

        return replies, parent_ids

    def list_file_data(self, fields='files(id,name,mimeType,parents,trashed)'):
        """
        Returns list of files in the users drive.

        https://developers.google.com/drive/v3/reference/files/list

        :return: JSON
        """
        response = self.service.files().list(pageSize=100, fields=fields).execute()

        items = response.get('files', [])
        while 'nextPageToken' in response:
            response = self.service.files().list(pageSize=100, fields=fields,
                                                 pageToken=str(response['nextPageToken']), orderBy='folder').execute()
            items.append(response.get('files', []))

        if not items:
            return None
        else:
            return items

    def export_drive_file(self, file_data, path):
        """
        Exports and converts .g* files to real files and then downloads them

        https://developers.google.com/drive/v3/reference/files/export

        :param file_data: List of file(s) to be downloaded
        :type file_data: JSON
        :param path: Path where the file will be downloaded
        :return: boolean True if downloads succeeded, False if Downloads failed.
        """
        mime_type, extension = convert_mime_type_and_extension(file_data['mimeType'])

        if not mime_type or not extension:
            print('mime type is not found, dumping file\'s information')
            print_json(file_data)
            return False

        os.chdir(path)

        request = self.service.files().export(fileId=file_data['id'], mimeType=mime_type)
        fh = io.FileIO(file_data['name'] + extension, 'wb')
        downloader = http_.MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            print(file_data['name'])
            print('Download %d%%.' % int(status.progress() * 100))

        return True

    def export_real_file(self, file_data, path):
        """
        Downloads real files. AKA not .g*

        https://developers.google.com/drive/v3/reference/files/export

        :param file_data: List of file(s) to be downloaded
        :type file_data: JSON
        :param path: Path where the file will be downloaded
        :return: Nothing
        """
        os.chdir(path)
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
    def handle_folder_helper(self, file_data_list, path, curr_folder_id):
        # Loop over all file data
        for file_data in file_data_list:
            # If file belong in current folder
            if str(file_data['parents'][0]) == str(curr_folder_id):
                # make new folder if it is a folder
                if str(file_data['mimeType']) == str(MIME['g_folder']):
                    os.mkdir(path + '/' + file_data['name'])
                    # every time we make a new folder we recursively call
                    self.handle_folder_helper(file_data_list, path + '/' + file_data['name'], file_data['id'])
                # it must be a file so download
                else:
                    if str(file_data['parents'][0]) == curr_folder_id:
                        if 'google-apps' not in str(file_data['mimeType']):
                            self.export_real_file(file_data, path)

                        elif 'folder' not in str(file_data['mimeType']):
                            download_succeeded = self.export_drive_file(file_data, path)

                            # In the event of a Mime Type conversion error the download process will stop
                            if download_succeeded is False:
                                print('Error has occurred, process was aborted.')

    # Always make sure you orderBy folder
    def handle_folders(self, file_list_array, path):
        # Get root id
        root_id = self.get_root_file_id()
        # recursively download everything in the drive
        self.handle_folder_helper(file_list_array, path, root_id)

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
            path = os.getcwd()
        else:
            path = os.path.expanduser(DOWNLOAD_DIRECTORY)
        if not os.path.exists(path + '/trash'):
            os.mkdir(path + '/trash')

        # Download trashed files first
        for file_data in file_list_array:
            if file_data['trashed']:
                if 'google-apps' not in str(file_data['mimeType']):
                    self.export_real_file(file_data, path + '/trash')

                elif 'folder' not in str(file_data['mimeType']):
                    download_succeeded = self.export_drive_file(file_data, path + '/trash')

                    # In the event of a Mime Type conversion error the download process will stop
                    if download_succeeded is False:
                        print('Error has occurred, process was aborted.')

        # Now download the rest of them
        self.handle_folders(file_list_array, path)

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
        if False:
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

        if True:
            self.download_files()
