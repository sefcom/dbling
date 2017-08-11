from util import print_json
from apiclient import http as _http
from apiclient import discovery
from util import convert_mime_type_and_extension
from env import DOWNLOAD_DIRECTORY
from env import G_APPS_FOLDER
import io
import os


class DriveAPI:
    """
    Class to interact with Google Drive APIs

    https://developers.google.com/resources/api-libraries/documentation/drive/v3/python/latest/index.html
    """
    def __init__(self, http):
        """
        Sets service object to make API calls to Google

        https://developers.google.com/drive/v3/web/quickstart/python
        :param http: http object
        :return DriveAPI Object
        """

        self.service = discovery.build('drive', 'v3', http=http)

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

    # For time-line creation and acquiring user files this is not useful.
    # This would be useful for an file syncing application
    # paging needs fixing
    def get_changes(self, fields='kind,comments'):
        """
        Returns list of changes for a google drive account

        https://developers.google.com/drive/v3/reference/changes
        :param fields: fields to be returned
        :type fields: string
        :return: JSON
        """

        start_token = self.get_start_page_token()
        changes = self.service.changes().list(pageToken=start_token['pageToken']).execute()
        while True:
            new_changes = self.service.changes().list(pageToken=changes['nextPageToken'], fields=fields).execute()
            print_json(new_changes)
            if changes['changes']:
                break
            changes['changes'] += new_changes['changes']
        return changes

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

    def list_file_data(self, fields='files(id,name,mimeType,parents)'):
        """
        Returns list of files in the users drive.

        https://developers.google.com/drive/v3/reference/files/list
        :return: JSON
        """
        response = self.service.files().list(pageSize=100, fields=fields).execute()
        print_json(response)
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
        downloader = _http.MediaIoBaseDownload(fh, request)
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
        downloader = _http.MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            print(file_data['name'])
            print('Download %d%%.' % int(status.progress() * 100))

    # I am sorry for the recursion Mike...
    def handle_folder_helper(self, file_data_list, path, curr_folder_id):
        # Loop over all file data
        for file_data in file_data_list:
            # If file belong in current folder
            if str(file_data['parents'][0]) == str(curr_folder_id):
                # make new folder if it is a folder
                if str(file_data['mimeType']) == str(G_APPS_FOLDER):
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

    # TODO MAKE file downloads maintain same directory structure
    # TODO HANDLE TRASH....
    def download_files(self, file_list_array=None):
        """
        Downloads files from the user's drive

        https://developers.google.com/drive/v3/web/manage-downloads
        :param file_list_array: list of file(s) to be downloaded
        :type file_list_array: array
        :return: Nothing
        """
        if not file_list_array:
            file_list_array = self.list_file_data()

        # print_json(file_list_array)
        # If download directory is set us it for the download folder.
        # Otherwise use the directory of this project
        if DOWNLOAD_DIRECTORY is None:
            path = os.getcwd()
        else:
            path = os.path.expanduser(DOWNLOAD_DIRECTORY)

        self.handle_folders(file_list_array, path)
        '''

        for file_data in file_list_array:
            if 'google-apps' not in str(file_data['mimeType']):
                self.export_real_file(file_data, path)

            elif 'folder' not in str(file_data['mimeType']):
                download_succeeded = self.export_drive_file(file_data, path)

                # In the event of a Mime Type conversion error the download process will stop
                if download_succeeded is False:
                    print('Error has occurred, process was aborted.')
    '''
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
