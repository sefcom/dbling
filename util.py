import os
import httplib2
import json
import env
from oauth2client import client
from oauth2client.file import Storage
from oauth2client import tools


def get_credentials(scope, application_name, secret, credential_file):
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


def set_http():
    credentials = get_credentials(env.SCOPES, env.APPLICATION_NAME, env.CLIENT_SECRET_FILE, env.CREDENTIAL_FILE)
    http = credentials.authorize(httplib2.Http())
    return http


# Was going to fix and make this better. Google APIs return json so just made a simple print_json method.
def pretty_print(obj):
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
    print(json.dumps(obj, sort_keys=True, indent=2))
