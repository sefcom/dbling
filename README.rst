.. image:: ../logo/logo.png
   :width: 100px
   :align: right

dbling: The Chrome OS Forensic Tool
===================================

|docs| |python_versions| |license_type|

dbling is a tool for performing forensics in Chrome OS.

Please view the latest version of the documentation on `Read the Docs`_ and the latest version of the code on `GitHub`_.


Publication
-----------

This work is based on the following publication:

- `Mike Mabey <https://mikemabey.com>`_, `Adam Doupé <https://adamdoupe.com>`_, `Ziming Zhao
  <http://www.public.asu.edu/~zzhao30/>`_, and `Gail-Joon Ahn <http://www.public.asu.edu/~gahn1/>`_. "dbling:
  Identifying Extensions Installed on Encrypted Web Thin Clients". In: *Digital Investigation* (2016). The Proceedings
  of the Sixteenth Annual DFRWS Conference. URL: http://www.sciencedirect.com/science/article/pii/S174228761630038X


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
   google/index


.. |docs| image:: https://readthedocs.org/projects/crx-unpack/badge/
    :alt: Documentation Status
    :target: `Read the Docs`_

.. |python_versions| image:: https://img.shields.io/badge/python-3.5%2C%203.6-blue.svg
    :alt: Python versions supported
    :target: `GitHub`_

.. |license_type| image:: https://img.shields.io/github/license/sefcom/dbling.svg
    :alt: License: MIT
    :target: `GitHub`_

.. _Read the Docs: http://dbling.readthedocs.io/

.. _GitHub: https://github.com/sefcom/dbling
