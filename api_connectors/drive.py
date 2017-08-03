from util import print_json
from apiclient import http as _http
from apiclient import discovery
from util import convert_mime_type
import io
import os


class DriveAPI:

    def __init__(self, http):
        """
        Sets service object to make API calls to Google
        :param http: http object
        """
        self.service = discovery.build('drive', 'v3', http=http)

    def get_about(self, fields='*'):
        """
        Retrieves information about the user's Drive. and system capabilities.

        :return: JSON
        """
        results = self.service.about().get(fields=fields)\
            .execute()

        if not results:
            return None
        else:
            return results

    def get_start_page_token(self, supports_team_drive=False):
        """
        Gets the start page token, used to keep track of changes
        :param supports_team_drive:
        :return: JSON
        """
        token = self.service.changes().getStartPageToken(supportsTeamDrives=supports_team_drive).execute()
        return token

    # Needs to loop over all changes using pageToken from start_token and nextPageToken token
    # This might not be useful. Start token is something that would be acquired when a program like Google Drive first
    # installs. Then to check to for updates you would use that to get the next page and compare file changes ect ect.
    # TODO More testing if this is actually needed.
    # TODO BROKEN Logic
    def get_changes(self, fields='kind,comments'):
        """

        :param fields:
        :return:
        """
        # v3 might be broken or the API page isn't up to date
        # self.service = discovery.build('drive', 'v2', http=self.http)

        start_token = self.get_start_page_token()
        changes = self.service.changes().list(pageToken=start_token['pageToken']).execute()
        while True:
            new_changes = self.service.changes().list(pageToken=changes['nextPageToken'], fields=fields)\
                .execute()
            print_json(new_changes)
            if changes['changes']:
                break
            changes['changes'] += new_changes['changes']
        return changes

    # Comments
    # should get all Comments per file
    # Get all files
    # loop over files
    # get all comments per file
    # TODO loop over pages if multiple pages exist
    # TODO make this method depend on get_file_data so I am not calling that twice
    def get_comments(self, fields='kind,comments'):
        """

        :param fields:
        :return:
        """
        file_data = self.get_file_data()
        comments = []
        return_ids = []
        for data in file_data['files']:

            try:
                drive_file = self.service.comments().list(fileId=data['id'], fields=fields).execute()
            except discovery.HttpError:
                continue

            if drive_file['comments']:
                return_ids.append(data['id'])
                comments.append(drive_file['comments'])

        return comments, return_ids

    # TODO PAGINGS JUST LIKE EVERYTHING ELSE
    # appears comments get replies the way I have it set up currently....
    def get_replies(self, comment_data, comment_ids, fields='kind,replies'):
        """

        :param comment_data:
        :param comment_ids:
        :param fields:
        :return:
        """
        parent_ids = []
        replies = []
        # loop over each entry to get all comments for document
        for file in comment_data:
            i = 0
            temp = []
            for comment in file:
                try:
                    print(file['id'])
                    print(comment['id'])
                    replies = self.service.replies().list(fileId=file['id'], commentId=comment['id'],
                                                          fields=fields).execute()
                except discovery.HttpError:
                    continue

                if replies['replies']:
                    temp.append(replies['replies'])

            replies.append(temp)
            parent_ids.append(comment_ids[i])
            i += 1

        #if drive_file["comments"]:
        #    return_ids.append(data["id"])
        #    for comment in drive_file["comments"]:
        #        comments.append(comment)

        print(len(replies))
        print(len(parent_ids))

        return replies, parent_ids

    # files
    #nextPageToken, files(id, name, mimeType, modifiedByMeTime, size, version,"
                                  #" description, modifiedTime, viewedByMe, modifiedByMe, createdTime, md5Checksum,"
                                  #" starred
    # TODO Account for paging
    def get_file_data(self):
        """

        :return:
        """
        results = self.service.files().list(pageSize=1000,).execute()
        items = results.get('files', [])
        if not items:
            return None
        else:
            return items

    def export_drive_file(self, file, path):
        """

        :param file:
        :param path:
        :return:
        """
        mime_type = convert_mime_type(file['mimeType'])

        if not mime_type:
            print('mime type is not found dumping file\'s information')
            print_json(file)
            print('ending execution.')
            return -1

        os.chdir(path + '/drive-files')

        request = self.service.files().export(fileId=file['id'], mimeType=mime_type)
        fh = io.FileIO(file['name'], 'wb')
        downloader = _http.MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            print(file['name'])
            print('Download %d%%.' % int(status.progress() * 100))

    def export_real_file(self, file, path):
        """

        :param file:
        :param path:
        :return:
        """
        os.chdir(path + '/files')
        request = self.service.files().get_media(fileId=file['id'])
        fh = io.FileIO(file['name'], 'wb')
        downloader = _http.MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            print(file['name'])
            print('Download %d%%.' % int(status.progress() * 100))

    def download_files(self, file_list_array=None):
        """

        :param file_list_array:
        :param fields:
        :return:
        """
        if not file_list_array:
            file_list_array = self.get_file_data()

        print_json(file_list_array)
        path = os.getcwd()

        if not os.path.exists(path + '/files'):
            os.mkdir('files')
        if not os.path.exists(path + '/drive-files'):
            os.mkdir('drive-files')

        for file in file_list_array:
            if 'google-apps' not in str(file['mimeType']):
                self.export_real_file(file, path)

            elif 'folder' not in str(file['mimeType']):
                self.export_drive_file(file, path)

    def get_app_folder(self, fields='nextPageToken, files(id, name)'):
        """

        :param fields:
        :return:
        """
        response = self.service.files().list(spaces='appDataFolder', fields=fields,
                                             pageSize=10).execute()
        return response

    # TODO make more modular / configurable
    def get_all(self):
        """
        method used for testing
        :return: nothing
        """
        if False:
            print('File Data')
            metadata = self.get_file_data()
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
