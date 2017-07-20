from __future__ import print_function
import httplib2
import os

from apiclient import discovery
from oauth2client import client
from oauth2client import tools
from oauth2client.file import Storage

try:
    import argparse

    flags = argparse.ArgumentParser(parents=[tools.argparser]).parse_args()
except ImportError:
    flags = None

# If modifying these scopes, delete your previously saved credentials
# at ~/.credentials/drive-python-quickstart.json
SCOPES = 'https://www.googleapis.com/auth/drive.metadata.readonly'
CLIENT_SECRET_FILE = 'client_secret.json'
APPLICATION_NAME = 'Fingerprint Client'


def print_prettyish(obj):
    """ 
    Prints the result in a readable format 
    since schema.py's function doesn't work 
    """
    if type(obj) == dict:
        for k, v in obj.items():
            if hasattr(v, '__iter__'):
                print(k)
                print_prettyish(v)
            else:
                print('%s : %s' % (k, v))
    elif type(obj) == list:
        for v in obj:
            if hasattr(v, '__iter__'):
                print_prettyish(v)
            else:
                print(v)
    else:
        print(obj)


def get_credentials():
    """
    Gets valid user credentials
    """
    home_dir = os.path.expanduser('~')
    credential_dir = os.path.join(home_dir, '.credentials')
    if not os.path.exists(credential_dir):
        os.makedirs(credential_dir)
    credential_path = os.path.join(credential_dir,
                                   'drive-info.json')

    store = Storage(credential_path)
    credentials = store.get()
    if not credentials or credentials.invalid:
        flow = client.flow_from_clientsecrets(CLIENT_SECRET_FILE, SCOPES)
        flow.user_agent = APPLICATION_NAME
        if flags:
            credentials = tools.run_flow(flow, store, flags)
        else:  # Needed only for compatibility with Python 2.6
            credentials = tools.run(flow, store)
        print('Storing credentials to ' + credential_path)
    return credentials


def list_files():
    """
    Creates a Google Drive API service object and outputs the names and IDs
    for up to 10 files.
    """
    credentials = get_credentials()
    http = credentials.authorize(httplib2.Http())
    service = discovery.build('drive', 'v3', http=http)
    # See the resource https://developers.google.com/drive/v3/reference/files#resource
    results = service.files().list(pageSize=10, fields="nextPageToken, files(id, name, version, createdTime, "
                                                       "modifiedTime, owners, md5Checksum, lastModifyingUser)"
                                   ).execute()
    items = results.get('files', [])
    if not items:
        print('No files found.')
    else:
        print('Files Found\n================================================')
        for item in items:
            print('File: {0}\nID: {1})\nVersion: {2}\nMD5: {3}\nCreated:  {4}\nModified: {5}\nOwners: \n{6}\nLast '
                  'Modified User: \n{7}\n'.
                  format(item['name'], item['id'], item['version'], item['md5Checksum'], item['createdTime'],
                         item['modifiedTime'], item['owners'], item['lastModifyingUser']))


def about_user():
    credentials = get_credentials()
    http = credentials.authorize(httplib2.Http())
    service = discovery.build('drive', 'v3', http=http)
    results = service.about().get(fields="user").execute();
    items = results.get('user', [])
    print("User Info\n================================================")
    if not items:
        print('No user info found.')
    else:
        print_prettyish(items)


def main():
    about_user()
    print("")
    list_files()


if __name__ == '__main__':
    main()
