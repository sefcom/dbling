# This file is obtained from Google through the API pages. Guide posted below
# https://developers.google.com/identity/protocols/OAuth2WebServer
# Look for Create authorization credentials subsection
CLIENT_SECRET_FILE = 'client_secret.json'

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

CREDENTIAL_FILE = 'dbling.json'
APPLICATION_NAME = 'dbling'
DOWNLOAD_DIRECTORY = '~/Desktop'

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

#
G_DOCUMENT_TO = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
G_SHEET_TO = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
G_DRAWINGS_TO = 'image/jpeg'
G_PRESENTATION_TO = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
G_APPS_SCRIPTS = 'application/vnd.google-apps.script+json'

