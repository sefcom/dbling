import os
import httplib2
import json
import env
from src.json2xml import Json2xml
from oauth2client import client
from oauth2client.file import Storage
from oauth2client import tools


def get_credentials(scope, application_name, secret, credential_file):
    """
    Creates credential file for accessing Google APIs.

    :param str scope: String of Scopes separated by spaces to give access to different Google APIs
    :param str application_name: Name of this Application
    :param str secret: The secret file given from Google
    :param str credential_file: Name of the credential file to be created
    :return: Credential Object
    """
    cur_dir = os.path.dirname(os.path.realpath('__FILE__'))
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
    return credentials


def set_http(is_domain_wide=False, impersonated_user_email=None):
    """
    Creates http object used to comunicate with Google
    :param boolean is_domain_wide:
    :param str impersonated_user_email: Email address of the User to be impersonated.
    :return: http object
    """
    credentials = get_credentials(env.SCOPES, env.APPLICATION_NAME, env.CLIENT_SECRET_FILE, env.CREDENTIAL_FILE)
    if is_domain_wide:
        http = credentials.create_delegated(impersonated_user_email)
    elif is_domain_wide and impersonated_user_email is None:
        return False
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
