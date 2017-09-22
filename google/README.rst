Google API Acquisition Tool
===========================

Access many APIs and acquire as much user identifying information as possible.


Getting Started
---------------

Gripper depends on an active `G Suite`_ account, which requires a domain name for your organization (you can create a
new domain while creating your G Suite account if you don't already have one).


Only has been tested in a Linux environment.

Install python 3 / pip3

Install google api python client

::

    pip3 install --upgrade google-api-python-client

Prerequisites
~~~~~~~~~~~~~

Installing
~~~~~~~~~~

.. running_goes_here


Bugs or Issues
~~~~~~~~~~~~~~

If you receive this error:

::

    Failed to start a local webserver listening on either port 8080
    or port 8090. Please check your firewall settings and locally
    running programs that may be blocking or using those ports.

use: ``lsof -w -n -i tcp:8080`` or ``lsof -w -n -i tcp:8090`` respectively.
then: ``kill -9 PID``

Or you can click the click provided in the terminal and then copy and paste
the key from the webpage that is launched.

.. start_mime_info


MIME Type Info
--------------

As specified in the `Google Drive API documentation`_, G Suite
and Google Drive use MIME types *specific to those services*, as
follows:

+--------------------------------------------+------------------------+
| MIME Type                                  | Description            |
+============================================+========================+
| application/vnd.google-apps.audio          |                        |
+--------------------------------------------+------------------------+
| application/vnd.google-apps.document       | Google Docs            |
+--------------------------------------------+------------------------+
| application/vnd.google-apps.drawing        | Google Drawing         |
+--------------------------------------------+------------------------+
| application/vnd.google-apps.file           | Google Drive file      |
+--------------------------------------------+------------------------+
| application/vnd.google-apps.folder         | Google Drive folder    |
+--------------------------------------------+------------------------+
| application/vnd.google-apps.form           | Google Forms           |
+--------------------------------------------+------------------------+
| application/vnd.google-apps.fusiontable    | Google Fusion Tables   |
+--------------------------------------------+------------------------+
| application/vnd.google-apps.map            | Google My Maps         |
+--------------------------------------------+------------------------+
| application/vnd.google-apps.photo          |                        |
+--------------------------------------------+------------------------+
| application/vnd.google-apps.presentation   | Google Slides          |
+--------------------------------------------+------------------------+
| application/vnd.google-apps.script         | Google Apps Scripts    |
+--------------------------------------------+------------------------+
| application/vnd.google-apps.sites          | Google Sites           |
+--------------------------------------------+------------------------+
| application/vnd.google-apps.spreadsheet    | Google Sheets          |
+--------------------------------------------+------------------------+
| application/vnd.google-apps.unknown        |                        |
+--------------------------------------------+------------------------+
| application/vnd.google-apps.video          |                        |
+--------------------------------------------+------------------------+
| application/vnd.google-apps.drive-sdk      | 3rd party shortcut     |
+--------------------------------------------+------------------------+


In addition to the above MIME types, Google Doc formats can be exported as the
following MIME types, as described in the `Drive documentation`_:

+---------------------+---------------------+-----------------------------------------------+
| Google Doc Format   | Conversion Format   | Corresponding MIME type                       |
+=====================+=====================+===============================================+
| Documents           | HTML                | text/html                                     |
+---------------------+---------------------+-----------------------------------------------+
|                     | HTML (zipped)       | application/zip                               |
+---------------------+---------------------+-----------------------------------------------+
|                     | Plain text          | text/plain                                    |
+---------------------+---------------------+-----------------------------------------------+
|                     | Rich text           | application/rtf                               |
+---------------------+---------------------+-----------------------------------------------+
|                     | Open Office doc     | application/vnd.oasis.opendocument.text       |
+---------------------+---------------------+-----------------------------------------------+
|                     | PDF                 | application/pdf                               |
+---------------------+---------------------+-----------------------------------------------+
|                     | MS Word             | application/vnd.openxmlformats-officedocument |
|                     | document            | .wordprocessingml.document                    |
+---------------------+---------------------+-----------------------------------------------+
|                     | EPUB                | application/epub+zip                          |
+---------------------+---------------------+-----------------------------------------------+
| Spreadsheets        | MS Excel            | application/vnd.openxmlformats-officedocument |
|                     |                     | .spreadsheetml.sheet                          |
+---------------------+---------------------+-----------------------------------------------+
|                     | Open Office sheet   | application/x-vnd.oasis.opendocument.spreadsh |
|                     |                     | eet                                           |
+---------------------+---------------------+-----------------------------------------------+
|                     | PDF                 | application/pdf                               |
+---------------------+---------------------+-----------------------------------------------+
|                     | CSV (1st sheet      | text/csv                                      |
|                     | only)               |                                               |
+---------------------+---------------------+-----------------------------------------------+
|                     | TSV (1st sheet      | text/tab-separated-values                     |
|                     | only)               |                                               |
+---------------------+---------------------+-----------------------------------------------+
|                     | HTML (zipped)       | application/zip                               |
+---------------------+---------------------+-----------------------------------------------+
| Drawings            | JPEG                | image/jpeg                                    |
+---------------------+---------------------+-----------------------------------------------+
|                     | PNG                 | image/png                                     |
+---------------------+---------------------+-----------------------------------------------+
|                     | SVG                 | image/svg+xml                                 |
+---------------------+---------------------+-----------------------------------------------+
|                     | PDF                 | application/pdf                               |
+---------------------+---------------------+-----------------------------------------------+
| Presentations       | MS PowerPoint       | application/vnd.openxmlformats-officedocument |
|                     |                     | .presentationml.presentation                  |
+---------------------+---------------------+-----------------------------------------------+
|                     | Open Office         | application/vnd.oasis.opendocument.presentati |
|                     | presentation        | on                                            |
+---------------------+---------------------+-----------------------------------------------+
|                     | PDF                 | application/pdf                               |
+---------------------+---------------------+-----------------------------------------------+
|                     | Plain text          | text/plain                                    |
+---------------------+---------------------+-----------------------------------------------+
| Apps Scripts        | JSON                | application/vnd.google-apps.script+json       |
+---------------------+---------------------+-----------------------------------------------+


Authors
-------

-  **Daniel Caruso II** - *Creator* - `Daniel Caruso II`_


.. _Daniel Caruso II: https://github.com/c4ruso
.. _Google Drive API documentation: https://developers.google.com/drive/v3/web/mime-types
.. _Drive documentation: https://developers.google.com/drive/v3/web/integrate-open
.. _G Suite: https://gsuite.google.com/
