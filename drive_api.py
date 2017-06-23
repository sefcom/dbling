
from __future__ import print_function
import util
from apiclient import discovery


class DriveAPI:

    def __init__(self):
        self.http = util.set_http()
        self.service = discovery.build('drive', 'v3', http=self.http)

    def about_user(self):
        results = self.service.about().get(fields="user").execute()
        items = results.get('user', [])

        if not items:
            return None
        else:
            return items

    def get_drive_metadata(self):
        results = self.service.files().list(
            pageSize=1000, fields="nextPageToken, files(id, name)").execute()
        items = results.get('files', [])
        if not items:
            return None
        else:
            return items

    def get_all(self):

        if True:
            metadata = self.get_drive_metadata()
            if metadata is None:
                print("There are no drive files")
            else:
                util.pretty_print(metadata)
                #print('Files:')
                #for item in metadata:
                    #print('{0} ({1})'.format(item['name'], item['id']))
        if False:
            user_info = self.about_user()
            print("User Info\n================================================")
            if not user_info:
                print('No user info found.')
            else:
                util.pretty_print(user_info)
