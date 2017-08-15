# This file is obtained from Google through the API pages. Guide posted below
# https://developers.google.com/identity/protocols/OAuth2WebServer
# Look for Create authorization credentials subsection
CLIENT_SECRET_FILE = ''

# name of the file that is made by get_credentials
CREDENTIAL_FILE = ''
# name of the application
APPLICATION_NAME = 'dbling'
# Optional, if set to a path the user's drive files will be downloaded to that location
DOWNLOAD_DIRECTORY = None


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
G_DOCUMENT_TO, G_DOC_EXTENSION = MIME['ms_word'], EXT['ms_word']
G_SHEET_TO, G_SHEET_EXTENSION = MIME['ms_excel'], EXT['ms_excel']
G_DRAWINGS_TO, G_DRAW_EXTENSION = MIME['png'], EXT['png']
G_PRESENTATION_TO, G_PRES_EXTENSION = MIME['ms_ppoint'], EXT['ms_ppoint']
G_APPS_SCRIPTS, G_APPS_EXTENSION = MIME['app_json'], EXT['app_json']
