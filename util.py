import os
import httplib2
import json
import env
from oauth2client import client
from oauth2client.file import Storage
from oauth2client import tools

"""
Google API Client Library Page
https://developers.google.com/api-client-library/python/reference/pydoc
Python Quick Start Page
https://developers.google.com/drive/v3/web/quickstart/python
"""


def get_credentials(scope, application_name, secret, credential_file):
    """
    Creates credential file for accessing Google APIs.

    https://developers.google.com/drive/v3/web/quickstart/python
    :param str scope: String of Scopes separated by spaces to give access to different Google APIs
    :param str application_name: Name of this Application
    :param str secret: The secret file given from Google
    :param str credential_file: Name of the credential file to be created
    :return: Credential Object
    """
    cur_dir = os.path.dirname(os.path.realpath('__FILE__'))
    secret_file_path = os.path.join(cur_dir, str(secret))
    if os.path.isfile(secret_file_path):
        credential_dir = os.path.join(cur_dir, '.credentials')
        if not os.path.exists(credential_dir):
            os.makedirs(credential_dir)
        credential_path = os.path.join(credential_dir, str(credential_file))
        store = Storage(credential_path)
        credentials = store.get()
        if not credentials or credentials.invalid:
            flow = client.flow_from_clientsecrets(secret, scope)
            flow.user_agent = application_name
            credentials = tools.run_flow(flow, store)
    else:
        print("Client Secret File is missing."
              "\nPlease go to: https://developers.google.com/drive/v3/web/quickstart/python\n"
              "To set up the secret file for OAuth 2.0")
        credentials = False
    return credentials


def set_http(is_domain_wide=False, impersonated_user_email=None):
    """
    Creates http object used to communicate with Google

    https://developers.google.com/drive/v3/web/quickstart/python
    :param boolean is_domain_wide: Turn to True if using domain wide delegation to impersonate a user
    :param str impersonated_user_email: Email address of the User to be impersonated.
    :return: http object or False if incorrect Params are used
    """
    credentials = get_credentials(env.SCOPES, env.APPLICATION_NAME, env.CLIENT_SECRET_FILE, env.CREDENTIAL_FILE)

    if not credentials:
        http = False
    else:
        if is_domain_wide:
            if impersonated_user_email is None:
                print('If using domain wide authority please supply an email to impersonate.')
                http = False
            else:
                http = credentials.create_delegated(impersonated_user_email)
        else:
            http = credentials.authorize(httplib2.Http())

    return http


# Was going to fix and make this better. Google APIs return json so just made a simple print_json method.
def pretty_print(obj):
    """
    Method to print json
    :param obj: JSON object
    :return: nothing
    """
    if type(obj) == dict:
        for k, v in obj.items():
            if hasattr(v, '__iter__'):
                print(k)
                pretty_print(v)
            else:
                print('%s : %s' % (k, v))
    elif type(obj) == list:
        for v in obj:
            if hasattr(v, '__iter__'):
                pretty_print(v)
            else:
                print(v)
    else:
        print(obj)


def print_json(obj):
    """
    Method to print JSON in human readable format

    :param obj: JSON object
    :return: nothing
    """
    print(json.dumps(obj, sort_keys=True, indent=2))


def convert_mime_type(google_mime_type):
    """
    Converts mimeType given from google to one of our choosing for export conversion
    This is necessary to download .g* files.
    Information on MIME types:
        https://developers.google.com/drive/v3/web/mime-types
        https://developers.google.com/drive/v3/web/integrate-open
    :param google_mime_type: mimeType given from Google API
    :return: string
    """
    if google_mime_type == 'application/vnd.google-apps.document':
        conversion_type = env.G_DOCUMENT_TO
    elif google_mime_type == 'application/vnd.google-apps.drawing':
        conversion_type = env.G_DRAWINGS_TO
    elif google_mime_type == 'application/vnd.google-apps.presentation':
        conversion_type = env.G_PRESENTATION_TO
    elif google_mime_type == 'application/vnd.google-apps.spreadsheet':
        conversion_type = env.G_SHEET_TO
    elif google_mime_type == 'application/vnd.google-apps.script':
        conversion_type = env.G_APPS_SCRIPTS
    else:
        conversion_type = False

    return conversion_type
