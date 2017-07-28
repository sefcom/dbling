from util import print_json
from apiclient import discovery


class DriveAPI:

    def __init__(self, http):
        self.service = discovery.build('drive', 'v3', http=http)

    # about
    def get_about(self):
        results = self.service.about().get(fields="kind,maxUploadSize,teamDriveThemes,"
                                                  "maxImportSizes,storageQuota,importFormats,"
                                                  "appInstalled,folderColorPalette,exportFormats,user")\
            .execute()

        if not results:
            return None
        else:
            return results

    # CHANGES #################
    def get_start_page_token(self):
        token = self.service.changes().getStartPageToken(supportsTeamDrives=False).execute()
        return token

    # Needs to loop over all changes using pageToken from start_token and nextPageToken token
    # This might not be useful. Start token is something that would be acquired when a program like Google Drive first
    # installs. Then to check to for updates you would use that to get the next page and compare file changes ect ect.
    # TODO More testing if this is actually needed.
    # TODO BROKEN Logic
    def get_changes(self):
        # v3 might be broken or the API page isn't up to date
        # self.service = discovery.build('drive', 'v2', http=self.http)

        start_token = self.get_start_page_token()
        changes = self.service.changes().list(pageToken=start_token["pageToken"]).execute()
        while True:
            new_changes = self.service.changes().list(pageToken=changes["nextPageToken"], fields="kind,comments")\
                .execute()
            print_json(new_changes)
            if changes["changes"]:
                break
            changes["changes"] += new_changes["changes"]
        return changes

    # Comments
    # should get all Comments per file
    # Get all files
    # loop over files
    # get all comments per file
    # TODO loop over pages if multiple pages exist
    # TODO make this method depend on get_file_data so I am not calling that twice
    def get_comments(self):
        file_data = self.get_file_data()
        comments = []
        return_ids = []
        for data in file_data["files"]:

            try:
                drive_file = self.service.comments().list(fileId=data["id"], fields="kind,comments").execute()
            except discovery.HttpError:
                continue

            if drive_file["comments"]:
                return_ids.append(data["id"])
                comments.append(drive_file["comments"])

        return comments, return_ids

    # TODO PAGINGS JUST LIKE EVERYTHING ELSE
    # appears comments get replies the way I have it set up currently....
    def get_replies(self, comment_data, comment_ids):

        parent_ids = []
        replies = []
        # loop over each entry to get all comments for document
        for file in comment_data:
            i = 0
            temp = []
            for comment in file:
                try:
                    print(file["id"])
                    print(comment["id"])
                    replies = self.service.replies().list(fileId=file["id"], commentId=comment["id"],
                                                                fields="kind,replies").execute()
                except discovery.HttpError:
                    continue

                if replies["replies"]:
                    temp.append(replies["replies"])

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
        results = self.service.files().list(
            pageSize=1000, fields="*").execute()
        # items = results.get('files', [])
        if not results:
            return None
        else:
            return results

    # Application Data Folder
    def get_app_folder(self):
        response = self.service.files().list(spaces='appDataFolder',
                                              fields='nextPageToken, files(id, name)',
                                              pageSize=10).execute()
        return response

    # TODO make more modular / configurable
    def get_all(self):
        if False:
            print("File Data")
            metadata = self.get_file_data()
            print_json(metadata)
        if False:
            print("About")
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

