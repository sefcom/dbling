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

# Google Media MIME Types
'''
MIME Type	                            Description
application/vnd.google-apps.audio
application/vnd.google-apps.document	  Google Docs
application/vnd.google-apps.drawing	      Google Drawing
application/vnd.google-apps.file	      Google Drive file
application/vnd.google-apps.folder	      Google Drive folder
application/vnd.google-apps.form	      Google Forms
application/vnd.google-apps.fusiontable	  Google Fusion Tables
application/vnd.google-apps.map	          Google My Maps
application/vnd.google-apps.photo
application/vnd.google-apps.presentation  Google Slides
application/vnd.google-apps.script	      Google Apps Scripts
application/vnd.google-apps.sites	      Google Sites
application/vnd.google-apps.spreadsheet	  Google Sheets
application/vnd.google-apps.unknown
application/vnd.google-apps.video
application/vnd.google-apps.drive-sdk	  3rd party shortcut
'''

# Export Mime Type Conversions
# Information on MIMI types:
#        https://developers.google.com/drive/v3/web/mime-types
#        https://developers.google.com/drive/v3/web/integrate-open
'''
Google Doc Format	Conversion Format	       Corresponding MIME type
Documents	        HTML	                   text/html
                    HTML (zipped)	           application/zip
                    Plain text	               text/plain
                    Rich text	               application/rtf
                    Open Office doc	           application/vnd.oasis.opendocument.text
                    PDF	                       application/pdf
                    MS Word document	       application/vnd.openxmlformats-officedocument.wordprocessingml.document
                    EPUB	                   application/epub+zip

Spreadsheets	    MS Excel	               application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
                    Open Office sheet	       application/x-vnd.oasis.opendocument.spreadsheet
                    PDF	                       application/pdf
                    CSV (1st sheet only)       text/csv
                    TSV (1st sheet only)       text/tab-separated-values
                    HTML (zipped)	           application/zip

Drawings	        JPEG	                   image/jpeg
                    PNG	                       image/png
                    SVG	                       image/svg+xml
                    PDF	                       application/pdf

Presentations	    MS PowerPoint	           application/vnd.openxmlformats-officedocument.presentationml.presentation
                    Open Office presentation   application/vnd.oasis.opendocument.presentation
                    PDF	                       application/pdf
                    Plain text	               text/plain

Apps Scripts	    JSON	                   application/vnd.google-apps.script+json
'''

# There are used for exporting .g* file types to real files.
# Currently set to MS Suite office files
G_DOCUMENT_TO, G_DOC_EXTENSION = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', '.docx'
G_SHEET_TO, G_SHEET_EXTENSION = 'application/x-vnd.oasis.opendocument.spreadsheet', '.xlsx'
G_DRAWINGS_TO, G_DRAW_EXTENSION = 'image/jpeg', ',jpeg'
G_PRESENTATION_TO, G_PRES_EXTENSION = 'application/vnd.openxmlformats-officedocument.presentationml.presentation',\
                                      '.pptx'
G_APPS_SCRIPTS, G_APPS_EXTENSION = 'application/vnd.google-apps.script+json', '.json'
G_APPS_FOLDER = 'application/vnd.google-apps.folder'