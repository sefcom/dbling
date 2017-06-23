import os
import httplib2
import argparse
from oauth2client import client
from oauth2client.file import Storage
from oauth2client import tools

# do I even need the try except?
try:
    flags = argparse.ArgumentParser(parents=[tools.argparser]).parse_args()
except ImportError:
    flags = None


# If modifying these scopes, delete your previously saved credentials
# at .credentials/drive-python-quickstart.json
# Permits us readonly access to all data of the Google Drive user
SCOPES = 'https://www.googleapis.com/auth/drive.readonly'
CLIENT_SECRET_FILE = 'client_secret.json'
APPLICATION_NAME = 'Drive API Python Quickstart'


def get_credentials():
    # want this to be the dir where the .py file exists. I think cur with do it
    cur_dir = os.path.dirname(os.path.realpath('__FILE__'))
    credential_dir = os.path.join(cur_dir, '.credentials')
    if not os.path.exists(credential_dir):
        os.makedirs(credential_dir)
    credential_path = os.path.join(credential_dir,
                                   'drive-python-quickstart.json')

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


def set_http():
    credentials = get_credentials()
    http = credentials.authorize(httplib2.Http())
    return http


def pretty_print(obj):
    if type(obj) == dict:
        for k, v in obj.items():
            if hasattr(v, '__iter__'):
                print(k)
                pretty_print(v)
            else:
                print('%s : %s' % (k, v))
        print("==============================")
    elif type(obj) == list:
        for v in obj:
            if hasattr(v, '__iter__'):
                pretty_print(v)
            else:
                print(v)
        # print("===============================")
    else:
        print(obj)
