=======================================
``crawl``: The Chrome Web Store Crawler
=======================================

tasks
-----

Tasks for Celery workers.


Beat Tasks
~~~~~~~~~~

Beat tasks are those that are run on a periodic basis, depending on the configuration in ``celeryconfig.py`` or any cron
jobs setup in the Ansible playbooks. Beat tasks only initiate the workflow by creating the jobs, they don't actually do
the work for each task.

.. autofunction:: crawl.tasks.start_list_download()

.. autofunction:: crawl.tasks.start_redo_extract_profile()


Entry Points
~~~~~~~~~~~~

Entry points are where an actual worker begins its work. A single task corresponds to a specific CRX file. The task
function dictates what operations are performed on the CRX. Each operation is represented by a specific worker function
(as described below).

.. autofunction:: crawl.tasks.process_crx

.. autofunction:: crawl.tasks.redo_extract_profile


Worker Functions
~~~~~~~~~~~~~~~~

Worker functions each represent a discrete action to be taken on a CRX file.

.. autofunction:: crawl.tasks.download_crx

.. autofunction:: crawl.tasks.extract_crx

.. autofunction:: crawl.tasks.read_manifest

.. autofunction:: crawl.tasks.profile_crx


Helper Tasks and Functions
~~~~~~~~~~~~~~~~~~~~~~~~~~

These functions provide additional functionality that don't fit in any of the above categories.

.. autofunction:: crawl.tasks.email_list_update_summary

.. autofunction:: crawl.tasks.summarize

.. autofunction:: crawl.tasks.crxs_on_disk


db_iface
--------

.. automodule:: crawl.db_iface
   :members:
   :exclude-members: SqlAlchemyTask

   .. autofunction:: add_new_crx_to_db(crx_obj, log_progress=False)

   .. autofunction:: db_download_complete(crx_obj, log_progress=False)

   .. autofunction:: db_extract_complete(crx_obj, log_progress=False)

   .. autofunction:: db_profile_complete(crx_obj, log_progress=False, update_dt_avail=True)


webstore_iface
--------------

.. automodule:: crawl.webstore_iface
   :members:
   :private-members:
