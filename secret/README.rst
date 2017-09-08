Secret Files
============

The ``secret`` directory is used to store sensitive information specific to an installation of dbling. The files in this
directory have excluded from the repository for obvious reasons, but should include a ``creds.py`` file. It has should
have a form such as displayed below.

.. include:: ../secret/creds_template.py
   :code: python


The template above references another file that should be in the ``secret`` directory, ``passes.yml``. This should have
a form as shown below. Without this file, the Ansible playbooks will not function properly.

.. include:: ../secret/passes_template.yml
   :code: yaml
