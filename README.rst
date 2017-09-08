.. image:: ../logo/logo.png
   :width: 100px
   :align: right

dbling: The Chrome OS Forensic Tool
===================================

dbling is a tool for performing forensics in Chrome OS. More info will be forthcoming.


Installation
------------

.. Ansible instructions

Coming soon!


dbling Components
-----------------

dbling is divided into the following main components:

Crawler
~~~~~~~

The Crawler finds and downloads the list of the currently-available extensions on the Chrome Web Store, determines which
extensions are at a version that has already been downloaded, downloads those that have not yet been downloaded, and
adds information on the newly downloaded extensions to the database.

The code for the Crawler is under `crawl`.


Template Generator
~~~~~~~~~~~~~~~~~~

The Template Generator runs concurrently with the Crawler. For each new extension downloaded by the Crawler, the
Template Generator calculates the centroid of the extension and stores it in the database. The Template Generator does
not run inside Chrome or Chrome OS, and so it does not use the same mechanisms for unpacking and installing that Chrome
does natively. Instead, the primary function of the Template Generator is to mimic as closely as possible the Chrome's
functions as they pertain to unpacking and installing extensions.

The code for the Template Generator is implemented alongside the Crawler, but the main function that creates templates
is :func:`~common.centroid.calc_centroid`.


Profiler
~~~~~~~~

Coming soon!


MERL Exporter
~~~~~~~~~~~~~

Coming soon!


gripper
~~~~~~~

Coming soon!


License
-------

dbling is licensed under the `MIT License <https://github.com/sefcom/dbling/blob/master/LICENSE>`_.



.. toctree::
   :maxdepth: 2
   :hidden:

   Home <self>
   api
   secret
   google_api
