# This file is obtained from Google through the API pages. Guide posted below
# https://developers.google.com/identity/protocols/OAuth2WebServer
# Look for Create authorization credentials subsection
CLIENT_SECRET_FILE = 'client_secret.json'

# name of the file that is made by get_credentials
CREDENTIAL_FILE = ''
# name of the application
APPLICATION_NAME = 'dbling'
# Optional, if set to a path the user's drive files will be downloaded to that location
DOWNLOAD_DIRECTORY = None

PAGE_SIZE = 100


# Scope: https://developers.google.com/drive/v3/web/about-auth
SCOPES = 'https://www.googleapis.com/auth/drive.readonly ' \
         'https://www.googleapis.com/auth/drive.appfolder ' \
         'https://www.googleapis.com/auth/plus.login ' \
         'https://www.googleapis.com/auth/gmail.readonly ' \
         'https://www.googleapis.com/auth/contacts.readonly ' \
         'https://www.googleapis.com/auth/admin.directory.device.chromeos ' \
         'https://www.googleapis.com/auth/admin.directory.user ' \
         'https://www.googleapis.com/auth/admin.directory.device.mobile.readonly ' \
         'https://www.googleapis.com/auth/admin.directory.customer.readonly ' \
         'https://www.googleapis.com/auth/admin.reports.audit.readonly ' \
         'https://www.googleapis.com/auth/admin.reports.usage.readonly'

MIME = {
    # Multi
    'pdf': 'application/pdf',  # document, spreadsheet, drawing, and presentation
    'html_zip': 'application/zip',  # document and spreadsheet
    'plain_text': 'text/plain',  # document and presentation

    # Documents
    'html': 'text/html',
    'rich_text': 'application/rtf',
    'oo_doc': 'application/vnd.oasis.opendocument.text',
    'ms_word': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'epub': 'application/epub+zip',

    # Spreadsheets
    'ms_excel': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'oo_sheet': 'application/x-vnd.oasis.opendocument.spreadsheet',
    'csv': 'text/csv',
    'tsv': 'text/tab-separated-values',

    # Drawings
    'jpeg': 'image/jpeg',
    'png': 'image/png',
    'svg': 'image/svg+xml',

    # Presentations
    'ms_ppoint': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'oo_presentation': 'application/vnd.oasis.opendocument.presentation',

    # Apps Scripts
    'app_json': 'application/vnd.google-apps.script+json',

    # G Suite and Google Drive types
    'g_audio': 'application/vnd.google-apps.audio',
    'g_doc': 'application/vnd.google-apps.document',
    'g_draw': 'application/vnd.google-apps.drawing',
    'g_file': 'application/vnd.google-apps.file',
    'g_folder': 'application/vnd.google-apps.folder',
    'g_form': 'application/vnd.google-apps.form',
    'g_fusiontable': 'application/vnd.google-apps.fusiontable',
    'g_map': 'application/vnd.google-apps.map',
    'g_photo': 'application/vnd.google-apps.photo',
    'g_presentation': 'application/vnd.google-apps.presentation',
    'g_script': 'application/vnd.google-apps.script',
    'g_site': 'application/vnd.google-apps.sites',
    'g_spreadsheet': 'application/vnd.google-apps.spreadsheet',
    'g_unknown': 'application/vnd.google-apps.unknown',
    'g_video': 'application/vnd.google-apps.video',
    'g_drive_sdk': 'application/vnd.google-apps.drive-sdk',
}

# Reverse of MIME
EMIM = {
    # Multi
    'application/pdf': 'pdf',  # document, spreadsheet, drawing, and presentation
    'application/zip': 'html_zip',  # document and spreadsheet
    'text/plain': 'plain_text',  # document and presentation

    # Documents
    'text/html': 'html',
    'application/rtf': 'rich_text',
    'application/vnd.oasis.opendocument.text': 'oo_doc',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'ms_word',
    'application/epub+zip': 'epub',

    # Spreadsheets
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'ms_excel',
    'application/x-vnd.oasis.opendocument.spreadsheet': 'oo_sheet',
    'text/csv': 'csv',
    'text/tab-separated-values': 'tsv',

    # Drawings
    'image/jpeg': 'jpeg',
    'image/png': 'png',
    'image/svg+xml': 'svg',

    # Presentations
    'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'ms_ppoint',
    'application/vnd.oasis.opendocument.presentation': 'oo_presentation',

    # Apps Scripts
    'application/vnd.google-apps.script+json': 'app_json',

    # G Suite and Google Drive types
    'application/vnd.google-apps.audio': 'g_audio',
    'application/vnd.google-apps.document': 'g_doc',
    'application/vnd.google-apps.drawing': 'g_draw',
    'application/vnd.google-apps.file': 'g_file',
    'application/vnd.google-apps.folder': 'g_folder',
    'application/vnd.google-apps.form': 'g_form',
    'application/vnd.google-apps.fusiontable': 'g_fusiontable',
    'application/vnd.google-apps.map': 'g_map',
    'application/vnd.google-apps.photo': 'g_photo',
    'application/vnd.google-apps.presentation': 'g_presentation',
    'application/vnd.google-apps.script': 'g_script',
    'application/vnd.google-apps.sites': 'g_site',
    'application/vnd.google-apps.spreadsheet': 'g_spreadsheet',
    'application/vnd.google-apps.unknown': 'g_unknown',
    'application/vnd.google-apps.video': 'g_video',
    'application/vnd.google-apps.drive-sdk': 'g_drive_sdk',
}

EXT = {
    # Multi
    'pdf': '.pdf',  # document, spreadsheet, drawing, and presentation
    'html_zip': '.zip',  # document and spreadsheet
    'plain_text': '.txt',  # document and presentation

    # Documents
    'html': '.html',
    'rich_text': '.rtf',
    'oo_doc': '.odt',
    'ms_word': '.docx',
    'epub': 'application/epub+zip',

    # Spreadsheets
    'ms_excel': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'oo_sheet': '.ods',
    'csv': '.csv',
    'tsv': '.tsv',

    # Drawings
    'jpeg': '.jpeg',
    'png': '.png',
    'svg': '.svg',

    # Presentations
    'ms_ppoint': '.pptx',
    'oo_presentation': '.odp',

    # Apps Scripts
    'app_json': '.json',
}

# There are used for exporting .g* file types to real files.
# Currently set to MS Suite office files
CONVERSION = {
    'gdoc':
        (MIME['ms_word'], EXT['ms_word']),
    'g_spreadsheet':
        (MIME['ms_excel'], EXT['ms_excel']),
    'g_draw':
        (MIME['png'], EXT['png']),
    'g_presentation':
        (MIME['ms_ppoint'], EXT['ms_ppoint']),
    'g_script':
        (MIME['app_json'], EXT['app_json']),
}
