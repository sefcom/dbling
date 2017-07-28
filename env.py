CLIENT_SECRET_FILE = 'client_secret.json'
# scopes are getting out of hand
# TODO make a system that concats list depending on what methods are going to be called?
SCOPES = 'https://www.googleapis.com/auth/drive.readonly ' \
         'https://www.googleapis.com/auth/drive.appfolder ' \
         'https://www.googleapis.com/auth/plus.login ' \
         'https://www.googleapis.com/auth/gmail.readonly ' \
         'https://www.googleapis.com/auth/contacts.readonly ' \
         'https://www.googleapis.com/auth/admin.directory.device.chromeos ' \
         'https://www.googleapis.com/auth/admin.directory.user ' \
         'https://www.googleapis.com/auth/admin.directory.device.mobile.readonly ' \
         'https://www.googleapis.com/auth/admin.directory.customer.readonly'
CREDENTIAL_FILE = 'dblibng.json'
APPLICATION_NAME = 'finger printer'
